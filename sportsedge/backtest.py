"""Walk-forward backtest: for each past date, project using ONLY data before that date,
then score against what actually happened. Use it to tune config numbers and to see
whether the model beats simple baselines before risking money.

Historical prop lines aren't free, so prop calibration uses a synthetic line
(player's season-to-date average rounded to .5). That tests whether the model's
probabilities are honest, which is what pricing a real line depends on.
"""
from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

from .config import PLAYER_STATS
from .models.games import TeamRatings
from .models.dist import nb_probs
from .models.players import PlayerProjector

ALPHA_GRID = [0.0, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.13, 0.17, 0.22, 0.3, 0.4]


def best_alpha(g: pd.DataFrame) -> float:
    """Overdispersion that gives the best log-loss on P(over line) - i.e. calibrates the tails."""
    y = g["hit_over"].values
    best, best_ll = None, 1e9
    for a in ALPHA_GRID:
        p = np.array([nb_probs(m, a, L)[0] for m, L in zip(g["proj"], g["line"])]).clip(1e-4, 1 - 1e-4)
        ll = -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
        if ll < best_ll:
            best, best_ll = a, ll
    return best


def run(ds, cfg: dict, start, end, stats: list[str] | None = None, every: int = 1, verbose=True):
    sport = ds.sport
    stats = stats or PLAYER_STATS[sport][:6]
    tg = ds.team_games
    dates = sorted(d for d in tg["date"].unique() if pd.Timestamp(start) <= d <= pd.Timestamp(end))[::every]
    prow, grow = [], []
    for i, d in enumerate(dates):
        d = pd.Timestamp(d)
        if verbose and i % 10 == 0:
            print(f"  backtest {sport}: {d.date()} ({i + 1}/{len(dates)})", file=sys.stderr)
        day = tg[(tg["date"] == d) & tg["home"]]
        slate = pd.DataFrame({"game_id": day["game_id"], "date": d, "home": day["team"], "away": day["opp"]})
        pp = PlayerProjector(ds, cfg, d)
        proj = pp.project_slate(slate)
        actual = ds.player_games[ds.player_games["date"] == d]
        if len(proj) and len(actual):
            m = proj.merge(actual, on=["game_id", "player_id"], suffixes=("", "_act"))
            m = m[m["minutes"] > 0]
            for s in stats:
                if s not in m:
                    continue
                for r in m.itertuples():
                    prev = pp.by_player.get(r.player_id)
                    if prev is None or len(prev) < 5:
                        continue
                    base = prev[s].mean()
                    l10 = prev[s].tail(10).mean()
                    line = math.floor(base) + 0.5
                    pr = getattr(r, s)
                    over, push, under = pp.probs(s, pr, line)
                    act = getattr(r, s + "_act")
                    naive_p = ((prev[s] > line).sum() + 1) / (len(prev) + 2)
                    prow.append({"date": d, "stat": s, "player": r.player, "proj": pr, "actual": act,
                                 "alpha_used": pp.alpha.get(s),
                                 "season_avg": base, "l10_avg": l10, "line": line, "p_over": over,
                                 "naive_p_over": naive_p, "hit_over": float(act > line),
                                 "proj_min": r.proj_min, "act_min": r.minutes})
        tr = TeamRatings(ds, cfg, d)
        for g in slate.itertuples():
            try:
                gm = tr.predict(g.home, g.away, d)
            except KeyError:
                continue
            res = day[day["team"] == g.home].iloc[0]
            grow.append({"date": d, "game": f"{g.away}@{g.home}", "proj_total": gm.summary()["proj_total"],
                         "proj_margin": gm.summary()["proj_margin"], "p_home": gm.p_ml("home")[0],
                         "act_total": res["pf"] + res["pa"], "act_margin": res["pf"] - res["pa"],
                         "home_won": float(res["pf"] > res["pa"])})
    return pd.DataFrame(prow), pd.DataFrame(grow)


def summarize(props: pd.DataFrame, games: pd.DataFrame) -> dict:
    out = {}
    if len(props):
        rows = []
        for s, g in props.groupby("stat"):
            p = g["p_over"].clip(1e-4, 1 - 1e-4)
            rows.append({
                "stat": s, "n": len(g),
                "MAE_model": (g["proj"] - g["actual"]).abs().mean(),
                "RMSE_model": np.sqrt(((g["proj"] - g["actual"]) ** 2).mean()),
                "RMSE_season_avg": np.sqrt(((g["season_avg"] - g["actual"]) ** 2).mean()),
                "MAE_season_avg": (g["season_avg"] - g["actual"]).abs().mean(),
                "MAE_last10": (g["l10_avg"] - g["actual"]).abs().mean(),
                "bias": (g["proj"] - g["actual"]).mean(),
                "brier_model": ((p - g["hit_over"]) ** 2).mean(),
                "brier_hit_rate": ((g["naive_p_over"] - g["hit_over"]) ** 2).mean(),
                "minutes_MAE": (g["proj_min"] - g["act_min"]).abs().mean(),
                "alpha_used": g["alpha_used"].mean(),
                "alpha_suggested": best_alpha(g.sample(min(len(g), 3000), random_state=0)),
            })
        out["props"] = pd.DataFrame(rows)
        bins = np.linspace(0, 1, 11)
        props = props.assign(bucket=pd.cut(props["p_over"], bins))
        out["calibration"] = (props.groupby("bucket", observed=True)
                              .agg(n=("hit_over", "size"), predicted=("p_over", "mean"), actual=("hit_over", "mean"))
                              .reset_index())
    if len(games):
        pt = games["p_home"].clip(1e-4, 1 - 1e-4)
        rt, rm = games["act_total"] - games["proj_total"], games["act_margin"] - games["proj_margin"]
        out["games"] = pd.DataFrame([{
            "n": len(games), "MAE_total": rt.abs().mean(), "bias_total": rt.mean(),
            "resid_sd_total": rt.std(), "MAE_margin": rm.abs().mean(), "resid_sd_margin": rm.std(),
            "ML_brier": ((pt - games["home_won"]) ** 2).mean(),
            "ML_logloss": -(games["home_won"] * np.log(pt) + (1 - games["home_won"]) * np.log(1 - pt)).mean(),
            "ML_accuracy": ((pt > 0.5) == (games["home_won"] == 1)).mean(),
        }])
    return out
