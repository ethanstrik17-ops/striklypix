"""Game-level models: team strength ratings -> score distributions -> ML / spread / total probabilities.

NBA: pace x offensive/defensive efficiency (per 100 possessions), normal margin & total.
NHL: Poisson goals from blended xG + actual-goal attack/defence ratings, with OT/shootout handling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ..data.dataset import Dataset
from .dist import normal_probs


def _ewm_shrunk(values: np.ndarray, halflife: float, k: float, prior: float) -> float:
    if len(values) == 0:
        return prior
    w = 0.5 ** (np.arange(len(values))[::-1] / halflife)
    return float(((w * values).sum() + k * prior) / (w.sum() + k))


class TeamRatings:
    def __init__(self, ds: Dataset, cfg: dict, asof):
        self.sport = ds.sport
        self.cfg = cfg[ds.sport]
        self.asof = pd.Timestamp(asof)
        tg = ds.before(self.asof).team_games
        self.tg = tg.sort_values("date") if len(tg) else tg
        self.prior = ds.team_prior.set_index("team") if len(ds.team_prior) else pd.DataFrame()
        self.ratings = {}
        if self.sport == "nba":
            self._nba()
        else:
            self._nhl()

    def _prior(self, team, col, lg):
        reg = self.cfg["prior_regression"]
        if len(self.prior) and team in self.prior.index and col in self.prior.columns and pd.notna(self.prior.at[team, col]):
            return lg + (1 - reg) * (float(self.prior.at[team, col]) - lg)
        return lg

    def _teams(self):
        teams = set(self.tg["team"]) if len(self.tg) else set()
        return teams | (set(self.prior.index) if len(self.prior) else set())

    def _nba(self):
        tg = self.tg
        if len(tg) >= 60:
            self.lg_rtg = float(100 * tg["pf"].sum() / tg["poss"].sum())
            self.lg_pace = float(tg["pace"].mean())
        elif len(self.prior):
            self.lg_rtg, self.lg_pace = float(self.prior["ortg"].mean()), float(self.prior["pace"].mean())
        else:
            self.lg_rtg, self.lg_pace = 114.0, 99.0
        h, k = self.cfg["team_halflife"], self.cfg["team_shrink_games"]
        for t in self._teams():
            g = tg[tg["team"] == t] if len(tg) else tg
            o = (100 * g["pf"] / g["poss"]).values if len(g) else np.array([])
            d = (100 * g["pa"] / g["poss"]).values if len(g) else np.array([])
            p = g["pace"].values if len(g) else np.array([])
            self.ratings[t] = {
                "ortg": _ewm_shrunk(o, h, k, self._prior(t, "ortg", self.lg_rtg)),
                "drtg": _ewm_shrunk(d, h, k, self._prior(t, "drtg", self.lg_rtg)),
                "pace": _ewm_shrunk(p, h, k, self._prior(t, "pace", self.lg_pace)),
                "games": len(g),
            }

    def _nhl(self):
        tg = self.tg
        has = len(tg) >= 64
        self.lg_g = float(tg["gf"].mean()) if has else (float(self.prior["gf"].mean()) if len(self.prior) else 3.05)
        self.lg_xg = float(tg["xgf"].mean()) if has and tg["xgf"].notna().any() else self.lg_g
        self.lg_sf = float(tg["sf"].mean()) if has and tg["sf"].notna().any() else 28.5
        h, k = self.cfg["team_halflife"], self.cfg["team_shrink_games"]
        for t in self._teams():
            g = tg[tg["team"] == t] if len(tg) else tg
            col = lambda c: g[c].dropna().values.astype(float) if len(g) and c in g else np.array([])
            gf = _ewm_shrunk(col("gf"), h, k, self._prior(t, "gf", self.lg_g))
            ga = _ewm_shrunk(col("ga"), h, k, self._prior(t, "ga", self.lg_g))
            self.ratings[t] = {
                "gf": gf, "ga": ga,
                "xgf": _ewm_shrunk(col("xgf"), h, k, gf * self.lg_xg / self.lg_g),
                "xga": _ewm_shrunk(col("xga"), h, k, ga * self.lg_xg / self.lg_g),
                "sf": _ewm_shrunk(col("sf"), h, k, self.lg_sf),
                "sa": _ewm_shrunk(col("sa"), h, k, self.lg_sf),
                "games": len(g),
            }

    def rested(self, team, date) -> int:
        """Days since team's last game (99 if none)."""
        if not len(self.tg):
            return 99
        g = self.tg[self.tg["team"] == team]
        return int((pd.Timestamp(date) - g["date"].max()).days) if len(g) else 99

    def predict(self, home: str, away: str, date, goalie_factor: dict | None = None):
        if self.sport == "nba":
            return NBAGame(self, home, away, date)
        return NHLGame(self, home, away, date, goalie_factor or {})


class NBAGame:
    def __init__(self, tr: TeamRatings, home, away, date):
        c = tr.cfg
        H, A = tr.ratings.get(home), tr.ratings.get(away)
        if H is None or A is None:
            raise KeyError(f"no ratings for {home} or {away}")
        self.pace = H["pace"] * A["pace"] / tr.lg_pace
        self.home_pts = self.pace * (H["ortg"] * A["drtg"] / tr.lg_rtg) / 100 + c["home_court_pts"] / 2
        self.away_pts = self.pace * (A["ortg"] * H["drtg"] / tr.lg_rtg) / 100 - c["home_court_pts"] / 2
        if tr.rested(home, date) == 1:
            self.home_pts -= c["b2b_pts"]
        if tr.rested(away, date) == 1:
            self.away_pts -= c["b2b_pts"]
        self.sd_m, self.sd_t = c["margin_sd"], c["total_sd"]
        self.home, self.away = home, away
        self._finish()

    def _finish(self):
        self.margin = self.home_pts - self.away_pts
        self.total = self.home_pts + self.away_pts

    def blend(self, bu_home: float, bu_away: float, w: float):
        """Mix in bottom-up (sum of player projections) scores, so injuries/minutes move the line."""
        self.td_home, self.td_away = self.home_pts, self.away_pts
        self.home_pts = (1 - w) * self.home_pts + w * bu_home
        self.away_pts = (1 - w) * self.away_pts + w * bu_away
        self._finish()

    def p_ml(self, side):
        p = float(stats.norm.cdf(self.margin / self.sd_m))
        return (p if side == "home" else 1 - p), 0.0

    def p_cover(self, side, point):
        """side covers with spread `point` (e.g. home -5.5). Returns (win, push)."""
        mu = self.margin if side == "home" else -self.margin
        over, push, _ = normal_probs(mu, self.sd_m, -point)
        return over, push

    def p_total(self, line):
        over, push, _ = normal_probs(self.total, self.sd_t, line)
        return over, push

    def p_team_total(self, side, line):
        mu = self.home_pts if side == "home" else self.away_pts
        over, push, _ = normal_probs(mu, self.sd_t * 0.68, line)
        return over, push

    def summary(self):
        return {"home": self.home, "away": self.away, "proj_home": self.home_pts, "proj_away": self.away_pts,
                "proj_total": self.total, "proj_margin": self.margin, "pace": self.pace,
                "p_home_win": self.p_ml("home")[0]}


class NHLGame:
    OT_SHARE = 0.03  # share of a team's expected goals that come in OT

    def __init__(self, tr: TeamRatings, home, away, date, goalie_factor: dict):
        c = tr.cfg
        H, A = tr.ratings.get(home), tr.ratings.get(away)
        if H is None or A is None:
            raise KeyError(f"no ratings for {home} or {away}")
        w = c["xg_weight"]
        att = lambda R: w * R["xgf"] / tr.lg_xg + (1 - w) * R["gf"] / tr.lg_g
        dfn = lambda R: w * R["xga"] / tr.lg_xg + (1 - w) * R["ga"] / tr.lg_g
        hf = np.sqrt(c["home_goal_factor"])
        self.lam_h = tr.lg_g * att(H) * dfn(A) * hf * goalie_factor.get(away, 1.0)
        self.lam_a = tr.lg_g * att(A) * dfn(H) / hf * goalie_factor.get(home, 1.0)
        self.sog_h = H["sf"] * A["sa"] / tr.lg_sf * 1.01
        self.sog_a = A["sf"] * H["sa"] / tr.lg_sf * 0.99
        self.n = c["max_goals"]
        self.home, self.away = home, away
        self._build()

    def blend(self, bu_home: float, bu_away: float, w: float):
        self.lam_h = (1 - w) * self.lam_h + w * bu_home
        self.lam_a = (1 - w) * self.lam_a + w * bu_away
        self._build()

    def _build(self):
        n = self.n
        ph = stats.poisson.pmf(np.arange(n + 1), self.lam_h * (1 - self.OT_SHARE))
        pa = stats.poisson.pmf(np.arange(n + 1), self.lam_a * (1 - self.OT_SHARE))
        M = np.outer(ph, pa)
        M /= M.sum()
        self.M = M
        self.p_tie = float(np.trace(M))
        self.p_ot_home = self.lam_h / (self.lam_h + self.lam_a)
        # final margin (home - away) and total distributions incl. OT/SO (+1 to winner)
        margin, total = {}, {}
        for i in range(n + 1):
            for j in range(n + 1):
                p = M[i, j]
                if i == j:
                    margin[1] = margin.get(1, 0) + p * self.p_ot_home
                    margin[-1] = margin.get(-1, 0) + p * (1 - self.p_ot_home)
                    total[2 * i + 1] = total.get(2 * i + 1, 0) + p
                else:
                    margin[i - j] = margin.get(i - j, 0) + p
                    total[i + j] = total.get(i + j, 0) + p
        self.margin_dist, self.total_dist = margin, total

    def _prob(self, dist, line):
        over = sum(p for k, p in dist.items() if k > line)
        push = sum(p for k, p in dist.items() if k == line)
        return float(over), float(push)

    def p_ml(self, side):
        p = sum(p for k, p in self.margin_dist.items() if k > 0)
        return (p if side == "home" else 1 - p), 0.0

    def p_cover(self, side, point):
        d = self.margin_dist if side == "home" else {-k: p for k, p in self.margin_dist.items()}
        return self._prob(d, -point)

    def p_total(self, line):
        return self._prob(self.total_dist, line)

    def p_team_total(self, side, line):
        lam = self.lam_h if side == "home" else self.lam_a
        p = stats.poisson(lam)
        if float(line).is_integer():
            return float(1 - p.cdf(line)), float(p.pmf(line))
        return float(1 - p.cdf(np.floor(line))), 0.0

    def summary(self):
        return {"home": self.home, "away": self.away, "proj_home": self.lam_h, "proj_away": self.lam_a,
                "proj_total": float(sum(k * p for k, p in self.total_dist.items())),
                "proj_margin": self.lam_h - self.lam_a, "p_home_win": self.p_ml("home")[0],
                "p_ot": self.p_tie, "proj_sog_home": self.sog_h, "proj_sog_away": self.sog_a,
                "p_home_-1.5": self.p_cover("home", -1.5)[0], "p_away_-1.5": self.p_cover("away", -1.5)[0]}
