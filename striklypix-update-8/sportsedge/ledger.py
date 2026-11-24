"""Pick log + grading + closing line value (CLV).

CLV is the best early signal of real skill: if the prices you take beat the closing
no-vig price on average, you're likely +EV long before the win/loss record can prove it.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .data.names import norm
from .value import market_table, selection_key

LOG_COLS = ["logged_utc", "sport", "date", "event_id", "commence", "home", "away", "market", "player", "point",
            "name", "selection", "type", "category", "best_price", "best_book", "final_p", "ev", "stake_pct", "result",
            "profit_units", "closing_fair_p", "clv_ev"]


def _append(rows: pd.DataFrame, path: str) -> int:
    for c in LOG_COLS:
        if c not in rows:
            rows[c] = np.nan
    rows = rows[LOG_COLS]
    exists = Path(path).exists()
    if exists:  # same pick for the same game is only logged once (first price seen is the one tracked)
        old = pd.read_csv(path, usecols=lambda c: c in ("sport", "date", "selection"))
        seen = set(zip(old["sport"], old["date"].astype(str), old["selection"]))
        rows = rows[[(s, str(d), x) not in seen for s, d, x in zip(rows["sport"], rows["date"], rows["selection"])]]
        if not len(rows):
            return 0
        cols = list(pd.read_csv(path, nrows=0).columns)
        if cols != LOG_COLS:  # older log format: rewrite with the new columns
            pd.concat([pd.read_csv(path), rows], ignore_index=True).reindex(columns=LOG_COLS).to_csv(path, index=False)
            return len(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(path, mode="a", header=not exists, index=False)
    return len(rows)


def log_card(lists: dict, sport: str, path: str) -> int:
    """Log every pick shown in the Top 10 Bets / Top 10 Props / Long shots lists."""
    frames = []
    for key, label in (("best", "Top 10 Bets"), ("props", "Top 10 Props"), ("long", "Long shots")):
        df = lists.get(key)
        if df is None or not len(df):
            continue
        frames.append(pd.DataFrame({
            "logged_utc": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "sport": sport,
            "date": df["game_date"].values, "event_id": df["event_id"].values, "commence": df["start"].values,
            "home": df["home"].values, "away": df["away"].values, "market": df["market"].values,
            "player": df["player"].values, "point": df["point"].values, "name": df["side"].values,
            "selection": df["pick"].values, "type": df["type"].values, "category": label,
            "best_price": df["price"].values, "best_book": df["book"].values, "final_p": df["final_p"].values,
            "ev": df["ev"].values, "stake_pct": df["stake_pct"].values}))
    if not frames:
        return 0
    allp = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["date", "selection"])
    return _append(allp, path)


def log_picks(df: pd.DataFrame, sport: str, date, path: str) -> int:
    bets = df[df["flag"] == "BET"].copy() if len(df) else df
    if not len(bets):
        return 0
    bets["logged_utc"] = pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    bets["sport"], bets["date"] = sport, pd.Timestamp(date).strftime("%Y-%m-%d")
    for c in LOG_COLS:
        if c not in bets:
            bets[c] = np.nan
    bets["type"] = bets["market"].map(lambda m: {"h2h": "Moneyline", "spreads": "Spread", "totals": "Total",
                                                     "team_totals": "Team total"}.get(m, "Prop"))
    bets["category"] = "Manual log"
    return _append(bets, path)


def _closing(row, snap_dir: str, sharp: list[str]):
    files = sorted(glob.glob(os.path.join(snap_dir, f"{row['sport']}_*.csv")))
    if not files or pd.isna(row["commence"]):
        return np.nan
    start = pd.Timestamp(row["commence"])
    best = None
    for f in files:
        ts = pd.Timestamp(Path(f).stem.split("_")[-1]).tz_localize("UTC")
        if ts <= start:
            best = f
    if best is None:
        return np.nan
    snap = pd.read_csv(best)
    snap = snap[snap["event_id"] == row["event_id"]]
    if not len(snap):
        return np.nan
    mt = market_table(snap, sharp)
    key = (row["market"], row["player"] if isinstance(row["player"], str) else None, row["name"])
    for r in mt.itertuples():
        rp = r.player if isinstance(r.player, str) else None
        if (r.market, rp, r.name) == key and np.isclose(r.point if pd.notna(r.point) else 0,
                                                              row["point"] if pd.notna(row["point"]) else 0):
            return r.market_p
    return np.nan


def grade(path: str, sport: str, ds, cfg: dict) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    log = pd.read_csv(path).reindex(columns=LOG_COLS)
    log["result"] = log["result"].astype(object)
    pg, tg = ds.player_games, ds.team_games
    snap_dir = os.path.join(cfg["general"]["output_dir"], "odds_snapshots")
    for i, r in log[(log["sport"] == sport) & log["result"].isna()].iterrows():
        d = pd.Timestamp(r["date"])
        res = None
        # match the game itself (teams + date within a day), so a UTC/ET date mix-up can't leave picks pending
        near = (tg["date"] >= d - pd.Timedelta(days=1)) & (tg["date"] <= d + pd.Timedelta(days=1)) if len(tg) else None
        if r["market"] == "team_totals" and isinstance(r["player"], str):
            opp = r["away"] if r["player"] == r["home"] else r["home"]
            g = tg[near & (tg["team"] == r["player"]) & (tg["opp"] == opp)]
            if len(g):
                v = g.iloc[0]["pf"] - r["point"]
                res = "P" if v == 0 else ("W" if (v > 0) == (r["name"] == "Over") else "L")
        elif r["market"] in ("h2h", "spreads", "totals"):
            g = tg[near & (tg["team"] == r["home"]) & (tg["opp"] == r["away"])] if len(tg) else tg
            if len(g):
                g = g.iloc[0]
                margin, total = g["pf"] - g["pa"], g["pf"] + g["pa"]
                if r["market"] == "h2h":
                    res = "W" if (margin > 0) == (r["name"] == "home") else "L"
                elif r["market"] == "spreads":
                    m = margin if r["name"] == "home" else -margin
                    v = m + r["point"]
                    res = "P" if v == 0 else ("W" if v > 0 else "L")
                else:
                    v = total - r["point"]
                    res = "P" if v == 0 else ("W" if (v > 0) == (r["name"] == "Over") else "L")
        else:
            src = ds.goalie_games if r["market"] == "saves" else pg
            if len(src) and isinstance(r["player"], str):
                day = src[(src["date"] >= d - pd.Timedelta(days=1)) & (src["date"] <= d + pd.Timedelta(days=1))]
                if "opp" in day:
                    day = day[day["opp"].isin([r["home"], r["away"]])]
                g = day[day["player"].map(norm) == norm(r["player"])]
                if len(g) and r["market"] in g:
                    v = g.iloc[0][r["market"]] - r["point"]
                    res = "P" if v == 0 else ("W" if (v > 0) == (r["name"] == "Over") else "L")
                elif len(tg) and (near & (tg["team"] == r["home"]) & (tg["opp"] == r["away"])).any():
                    res = "P"  # game was played but the player didn't play: books void (refund) these
        if res:
            log.at[i, "result"] = res
            # flat 1 unit per pick: easy to read, and independent of how much anyone actually bet
            log.at[i, "profit_units"] = {"W": float(r["best_price"]) - 1, "L": -1.0, "P": 0.0}[res]
            cf = _closing(r, snap_dir, cfg["odds"]["sharp_books"])
            log.at[i, "closing_fair_p"] = cf
            log.at[i, "clv_ev"] = cf * r["best_price"] - 1 if pd.notna(cf) else np.nan
    log.to_csv(path, index=False)
    return log
