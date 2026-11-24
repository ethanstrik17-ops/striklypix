"""Sportsbook odds: The Odds API (https://the-odds-api.com, free tier available) or a manual CSV.

Everything is normalised to one long table:
    event_id, commence, home, away, book, market, name, player, point, price (decimal odds)
market: "h2h" | "spreads" | "totals" | a stat key such as "sog", "pts", "saves"
name:   "home"/"away" for h2h & spreads, "Over"/"Under" for totals and props
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..config import ODDS_MARKET_TO_STAT, ODDS_SPORT_KEY
from .names import team_abbr

BASE = "https://api.the-odds-api.com/v4"
COLS = ["event_id", "commence", "home", "away", "book", "market", "name", "player", "point", "price"]


def et_date(iso):
    if not iso:
        return None
    return pd.Timestamp(iso).tz_convert("America/New_York").date()


def to_decimal(v) -> float:
    v = float(v)
    if abs(v) >= 100:
        return 1 + (v / 100 if v > 0 else 100 / -v)
    return v


def to_american(dec: float) -> int:
    if dec >= 2:
        return int(round((dec - 1) * 100))
    return int(round(-100 / (dec - 1)))


class OddsClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg["odds"]
        self.key = os.environ.get(self.cfg["api_key_env"])
        self.snap_dir = Path(cfg["general"]["output_dir"]) / "odds_snapshots"
        self.remaining = None
        self.reserve = float(self.cfg.get("min_credits_left", 0) or 0)

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, **params):
        params = {"apiKey": self.key, "oddsFormat": "decimal", "dateFormat": "iso", **params}
        if self.cfg.get("bookmakers"):
            params["bookmakers"] = self.cfg["bookmakers"]
            params.pop("regions", None)
        r = requests.get(f"{BASE}{path}", params=params, timeout=30)
        r.raise_for_status()
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            print(f"  The Odds API credits remaining: {rem}", file=sys.stderr)
            try:
                self.remaining = float(rem)
            except ValueError:
                pass
        return r.json()

    def _parse_event(self, sport: str, ev: dict) -> list[dict]:
        home, away = team_abbr(sport, ev["home_team"]), team_abbr(sport, ev["away_team"])
        rows = []
        m2s = ODDS_MARKET_TO_STAT[sport]
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                key = mk["key"]
                for o in mk.get("outcomes", []):
                    name, player, point = o.get("name"), None, o.get("point")
                    if key in ("h2h", "spreads"):
                        ab = team_abbr(sport, name)
                        name = "home" if ab == home else "away" if ab == away else name
                        market = key
                    elif key == "totals":
                        market = key
                    elif key in m2s:
                        market, player = m2s[key], o.get("description")
                        if name in ("Yes",):
                            name, point = "Over", point if point is not None else 0.5
                        elif name in ("No",):
                            name, point = "Under", point if point is not None else 0.5
                    else:
                        continue
                    rows.append({"event_id": ev["id"], "commence": ev.get("commence_time"), "home": home,
                                 "away": away, "book": bk["key"], "market": market, "name": name,
                                 "player": player, "point": np.nan if point is None else float(point),
                                 "price": float(o["price"])})
        return rows

    def game_odds(self, sport: str) -> pd.DataFrame:
        data = self._get(f"/sports/{ODDS_SPORT_KEY[sport]}/odds", regions=self.cfg["regions"],
                         markets="h2h,spreads,totals")
        rows = [r for ev in data for r in self._parse_event(sport, ev)]
        return self._snap(sport, "games", pd.DataFrame(rows, columns=COLS))

    def events(self, sport: str) -> list[dict]:
        return self._get(f"/sports/{ODDS_SPORT_KEY[sport]}/events")

    def prop_odds(self, sport: str, date=None, teams: set | None = None) -> pd.DataFrame:
        markets = ",".join(self.cfg["prop_markets"][sport])
        rows = []
        for ev in self.events(sport):
            h, a = team_abbr(sport, ev["home_team"]), team_abbr(sport, ev["away_team"])
            if teams and not ({h, a} & teams):
                continue
            if date is not None and et_date(ev.get("commence_time")) != pd.Timestamp(date).date():
                continue
            if ev.get("commence_time") and pd.Timestamp(ev["commence_time"]) <= pd.Timestamp.now(tz="UTC"):
                continue  # already started: live prices aren't comparable, don't spend credits
            if self.remaining is not None and self.remaining - len(self.cfg["prop_markets"][sport]) < self.reserve:
                print(f"  stopping prop downloads: credits would drop below the {self.reserve:.0f} reserve",
                      file=sys.stderr)
                break
            data = self._get(f"/sports/{ODDS_SPORT_KEY[sport]}/events/{ev['id']}/odds",
                             regions=self.cfg["regions"], markets=markets)
            rows += self._parse_event(sport, data)
        return self._snap(sport, "props", pd.DataFrame(rows, columns=COLS))

    def _snap(self, sport, kind, df):
        if len(df):
            self.snap_dir.mkdir(parents=True, exist_ok=True)
            ts = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%S")
            df.assign(snapshot_utc=ts).to_csv(self.snap_dir / f"{sport}_{kind}_{ts}.csv", index=False)
        return df


def load_manual_lines(path: str, sport: str) -> pd.DataFrame:
    """CSV columns: market, player, game, line, over, under, book
    market = stat key (sog, pts, reb, saves, ...) or 'total' for a game total.
    game   = "AWAY@HOME" (e.g. TOR@BOS). over/under = American (-115) or decimal (1.87) odds.
    """
    df = pd.read_csv(path)
    rows = []
    for r in df.itertuples():
        away, home = (str(r.game).upper().split("@") + [None])[:2] if isinstance(r.game, str) else (None, None)
        market = "totals" if str(r.market).lower() in ("total", "totals") else str(r.market).lower()
        for name, price in (("Over", r.over), ("Under", r.under)):
            if pd.notna(price):
                rows.append({"event_id": f"manual-{away}@{home}", "commence": None, "home": home, "away": away,
                             "book": getattr(r, "book", "manual") or "manual", "market": market, "name": name,
                             "player": r.player if isinstance(r.player, str) else None,
                             "point": float(r.line), "price": to_decimal(price)})
    return pd.DataFrame(rows, columns=COLS)
