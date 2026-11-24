"""Trend detection that tells you whether a trend is real or just noise.

"Hit the over in 7 of last 10" sounds strong, but with n=10 the 95% interval is roughly
40%-90%: usually not evidence of anything. Every trend here comes with a sample-size check.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def prop_trend(pg: pd.DataFrame, player_id, stat: str, line: float, opp: str | None = None,
               fair_p: float | None = None) -> dict:
    g = pg[(pg["player_id"] == player_id) & (pg["minutes"] > 0)].sort_values("date")
    x = g[stat].values
    if not len(x):
        return {}
    out = {"games": len(x), "season_avg": x.mean(), "median": float(np.median(x))}
    for n in (5, 10, 20):
        s = x[-n:]
        out[f"L{n}_avg"] = s.mean()
        out[f"L{n}_over"] = f"{int((s > line).sum())}/{len(s)}"
    k, n = int((x > line).sum()), len(x)
    lo, hi = wilson(k, n)
    out["season_over_rate"] = k / n
    out["over_rate_95ci"] = f"{lo:.0%}-{hi:.0%}"
    for flag, lab in ((True, "home_avg"), (False, "away_avg")):
        s = g[g["home"] == flag][stat]
        out[lab] = s.mean() if len(s) else np.nan
    if opp:
        s = g[g["opp"] == opp][stat]
        out["vs_opp_avg"] = s.mean() if len(s) else np.nan
        out["vs_opp_games"] = len(s)
    out["min_L5"] = g["minutes"].values[-5:].mean()
    out["min_season"] = g["minutes"].mean()
    if fair_p is not None:
        if lo > fair_p:
            out["verdict"] = f"over-trend is statistically meaningful vs market {fair_p:.0%}"
        elif hi < fair_p:
            out["verdict"] = f"under-trend is statistically meaningful vs market {fair_p:.0%}"
        else:
            out["verdict"] = f"trend is within noise of market {fair_p:.0%} (n={n})"
    return out


def form_scan(pg: pd.DataFrame, proj: pd.DataFrame, stats: list[str], sport: str) -> pd.DataFrame:
    """Hot/cold streaks and role changes (minutes) for players on the slate, with z-scores."""
    rows = []
    min_jump = 4.0 if sport == "nba" else 1.5
    for r in proj.itertuples():
        g = pg[(pg["player_id"] == r.player_id) & (pg["minutes"] > 0)].sort_values("date")
        if len(g) < 10:
            continue
        recent, base = g.tail(5), g.iloc[:-5]
        m_recent, m_base = g["minutes"].tail(3).mean(), g["minutes"].iloc[:-3].tail(10).mean()
        msd = g["minutes"].std() or 1.0
        mz = (m_recent - m_base) / (msd / math.sqrt(3))
        if abs(m_recent - m_base) >= min_jump and abs(mz) >= 2:
            rows.append({"player": r.player, "team": r.team, "type": "ROLE " + ("UP" if mz > 0 else "DOWN"),
                         "stat": "minutes", "recent": m_recent, "baseline": m_base, "z": mz,
                         "note": "minutes change; check lineup news - books can be slow on role changes"})
        for s in stats:
            if s not in g:
                continue
            b = base[s] / base["minutes"].clip(lower=1)   # per-minute so minutes swings don't fake a streak
            rr = recent[s].sum() / max(recent["minutes"].sum(), 1)
            if b.mean() <= 0:
                continue
            # standard error from the player's own game-to-game spread (not Poisson: points come in 2s/3s)
            se_emp = b.std(ddof=1) / math.sqrt(len(recent)) if len(b) > 3 else 0.0
            se_poi = math.sqrt(max(b.mean(), 1e-6) / max(recent["minutes"].sum(), 1))
            z = (rr - b.mean()) / max(se_emp, se_poi)
            if abs(z) >= 2.0:
                rows.append({"player": r.player, "team": r.team, "type": "HOT" if z > 0 else "COLD", "stat": s,
                             "recent": recent[s].mean(), "baseline": base[s].mean(), "z": z,
                             "note": "per-minute rate L5 vs earlier; regression to the mean is the default"})
    df = pd.DataFrame(rows)
    return df.sort_values("z", key=abs, ascending=False) if len(df) else df


def team_total_trend(tg: pd.DataFrame, team: str, line: float) -> dict:
    g = tg[tg["team"] == team].sort_values("date")
    tot = (g["pf"] + g["pa"]).values
    if not len(tot):
        return {}
    k10 = int((tot[-10:] > line).sum())
    k, n = int((tot > line).sum()), len(tot)
    lo, hi = wilson(k, n)
    return {"team": team, "games": n, "avg_total": tot.mean(), "L10_avg_total": tot[-10:].mean(),
            "L10_over": f"{k10}/{min(10, n)}", "season_over": f"{k}/{n}", "over_95ci": f"{lo:.0%}-{hi:.0%}"}
