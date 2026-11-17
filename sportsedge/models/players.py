"""Player stat projections.

projection = projected minutes (or TOI)
           x per-minute rate (recency-weighted, shrunk toward last season / league prior)
           x opponent factor (what this opponent allows to this position, shrunk)
           x home/away factor
Each projected mean gets a negative-binomial distribution so any line can be priced.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PLAYER_STATS
from ..data.dataset import Dataset
from ..data.names import norm
from .dist import fit_alpha, nb_probs


def _w(n: int, halflife: float) -> np.ndarray:
    """Exponential weights, last element = most recent game = weight 1."""
    return 0.5 ** (np.arange(n)[::-1] / max(halflife, 0.1))


class PlayerProjector:
    def __init__(self, ds: Dataset, cfg: dict, asof):
        self.sport = ds.sport
        self.cfg = cfg[ds.sport]
        self.asof = pd.Timestamp(asof)
        self.ds = ds.before(self.asof)
        self.stats = PLAYER_STATS[ds.sport]
        pg = self.ds.player_games
        self.pg = pg[pg["minutes"] > 0].sort_values(["date", "game_id"]) if len(pg) else pg
        self.by_player = {pid: g for pid, g in self.pg.groupby("player_id")} if len(self.pg) else {}
        self._league_rates()
        self._opp_factors()
        self._home_factors()
        self._alphas()
        self.prior = (self.ds.player_prior.set_index("player_id")
                      if len(self.ds.player_prior) else pd.DataFrame())
        tg = self.ds.team_games
        self.team_dates = {t: sorted(g["date"].unique()) for t, g in tg.groupby("team")} if len(tg) else {}
        self.team_games_ids = ({t: list(g.sort_values("date")["game_id"]) for t, g in tg.groupby("team")}
                               if len(tg) else {})

    # ---------------------------------------------------------------- league context
    def _league_rates(self):
        src = self.pg if len(self.pg) > 300 else self.ds.player_prior
        self.lg = {}
        if not len(src):
            return
        for pos, g in src.groupby("pos"):
            m = g["minutes"].sum()
            self.lg[pos] = {s: (g[s].sum() / m if s in g and m > 0 else np.nan) for s in self.stats}
        allm = src["minutes"].sum()
        self.lg["ALL"] = {s: (src[s].sum() / allm if s in src else np.nan) for s in self.stats}
        # fill stats missing in the prior table (e.g. attempts) from current data ratios
        if src is not self.pg and len(self.pg):
            for pos in self.lg:
                for s in self.stats:
                    if np.isnan(self.lg[pos].get(s, np.nan)) and s in self.pg:
                        g = self.pg if pos == "ALL" else self.pg[self.pg["pos"] == pos]
                        if g["minutes"].sum() > 0:
                            self.lg[pos][s] = g[s].sum() / g["minutes"].sum()

    def lg_rate(self, pos: str, stat: str) -> float:
        v = self.lg.get(pos, self.lg.get("ALL", {})).get(stat, np.nan)
        if v is None or np.isnan(v):
            v = self.lg.get("ALL", {}).get(stat, 0.0)
        return float(v or 0.0)

    def _opp_factors(self):
        self.opp = {}
        if not len(self.pg):
            return
        k = self.cfg["opp_shrink_games"]
        lo, hi = self.cfg["opp_factor_cap"]
        for (opp, pos), g in self.pg.groupby(["opp", "pos"]):
            n = g["game_id"].nunique()
            m = g["minutes"].sum()
            for s in self.stats:
                lg = self.lg_rate(pos, s)
                if lg <= 0 or m <= 0:
                    continue
                raw = (g[s].sum() / m) / lg
                self.opp[(opp, pos, s)] = float(np.clip(1 + (raw - 1) * n / (n + k), lo, hi))

    def _home_factors(self):
        self.homef = {}
        if not len(self.pg):
            return
        n = len(self.pg)
        for s in self.stats:
            tot = self.pg[s].sum() / self.pg["minutes"].sum()
            if tot <= 0:
                continue
            for flag in (True, False):
                g = self.pg[self.pg["home"] == flag]
                raw = (g[s].sum() / g["minutes"].sum()) / tot if len(g) else 1.0
                self.homef[(s, flag)] = 1 + (raw - 1) * n / (n + 5000)

    def _alphas(self):
        self.alpha = {}
        d = self.cfg["default_alpha"]
        fixed = self.cfg.get("alpha") or {}       # calibrated values from `backtest` take priority
        for s in self.stats:
            if s in fixed:
                self.alpha[s] = float(fixed[s])
            elif len(self.pg) and s in self.pg:
                self.alpha[s] = max(self.cfg.get("alpha_floor", 0.0),
                                    fit_alpha((g[s].values for g in self.by_player.values()), default=d))
            else:
                self.alpha[s] = d

    # ---------------------------------------------------------------- per player
    def roster(self, team: str) -> pd.DataFrame:
        """Players whose latest game was for `team` and who played in its last 10 games."""
        if not len(self.pg):
            return pd.DataFrame()
        last = self.pg.groupby("player_id").tail(1)
        recent_ids = set(self.team_games_ids.get(team, [])[-10:])
        played_recent = set(self.pg[self.pg["game_id"].isin(recent_ids)]["player_id"])
        return last[(last["team"] == team) & last["player_id"].isin(played_recent)]

    def _is_b2b(self, team, date) -> bool:
        ds = self.team_dates.get(team, [])
        return bool(ds) and (pd.Timestamp(date) - pd.Timestamp(ds[-1])).days == 1

    def project_minutes(self, g: pd.DataFrame, pid) -> float:
        mins = g["minutes"].values[-15:]
        w = _w(len(mins), self.cfg["minutes_halflife"])
        ew = float((w * mins).sum() / w.sum())
        season = float(g["minutes"].mean())
        m = 0.75 * ew + 0.25 * season
        n = len(g)
        if n < 10 and len(self.prior) and pid in self.prior.index:
            pr = self.prior.loc[pid]
            if pr["games"] > 0:
                m = (n * m + 3 * pr["minutes"] / pr["games"]) / (n + 3)
        return min(m, self.cfg["max_minutes"])

    def rate(self, g: pd.DataFrame, pid, pos: str, stat: str) -> float:
        k = self.cfg["stabilize"].get(stat, 400)
        lg = self.lg_rate(pos, stat)
        prior_rate = lg
        if len(self.prior) and pid in self.prior.index and stat in self.prior.columns:
            pr = self.prior.loc[pid]
            if pd.notna(pr[stat]) and pr["minutes"] > 0:
                prior_rate = (pr[stat] + k * lg) / (pr["minutes"] + k)
        w = _w(len(g), self.cfg["rate_halflife"])
        return float(((w * g[stat].values).sum() + k * prior_rate) / ((w * g["minutes"].values).sum() + k))

    def project_team(self, team: str, opp: str, home: bool, date, overrides: dict | None = None) -> pd.DataFrame:
        overrides = overrides or {}
        out_names = {norm(n) for n in overrides.get("out", [])}
        q_names = {norm(n) for n in overrides.get("questionable", [])}
        notes = overrides.get("injury_notes", {}) or {}
        min_over = {norm(k): v for k, v in (overrides.get("minutes") or {}).items()}
        ros = self.roster(team)
        rows = []
        last_team_game = (self.team_games_ids.get(team) or [None])[-1]
        b2b = self._is_b2b(team, date)
        for r in ros.itertuples():
            g = self.by_player[r.player_id]
            mins = self.project_minutes(g, r.player_id)
            if self.sport == "nba" and b2b:
                mins *= self.cfg["b2b_minutes_factor"]
            flags = []
            if last_team_game is not None and last_team_game not in set(g["game_id"]):
                flags.append("missed_last_game")
            if len(g) < self.cfg.get("min_games", 5):
                flags.append(f"only_{len(g)}_games")
            if norm(r.player) in q_names:
                flags.append("questionable")
            rows.append({"player_id": r.player_id, "player": r.player, "team": team, "opp": opp,
                         "home": home, "pos": r.pos, "games": len(g), "proj_min": mins,
                         "out": norm(r.player) in out_names, "flags": flags, "hist_df": g})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # --- injuries / overrides: give an OUT player's minutes to teammates at the same position group
        for idx in df.index[df["out"]]:
            freed = df.at[idx, "proj_min"]
            grp = df["pos"] == df.at[idx, "pos"] if self.sport == "nhl" else pd.Series(True, index=df.index)
            mates = df.index[grp & ~df["out"] & (df["proj_min"] >= self.cfg["min_proj_minutes"])]
            if len(mates):
                share = df.loc[mates, "proj_min"] / df.loc[mates, "proj_min"].sum()
                df.loc[mates, "proj_min"] = (df.loc[mates, "proj_min"] + freed * share).clip(
                    upper=self.cfg["max_minutes"])
                for m in mates:
                    df.at[m, "flags"] = df.at[m, "flags"] + ["minutes_bump"]
        for idx in df.index:
            key = norm(df.at[idx, "player"])
            if key in min_over:
                df.at[idx, "proj_min"] = float(min_over[key])
                df.at[idx, "flags"] = df.at[idx, "flags"] + ["minutes_override"]
        df = df[~df["out"] & (df["proj_min"] >= self.cfg["min_proj_minutes"])].copy()
        for s in self.stats:
            vals = []
            for r in df.itertuples():
                rate = self.rate(r.hist_df, r.player_id, r.pos, s)
                f_opp = self.opp.get((opp, r.pos, s), 1.0)
                f_home = self.homef.get((s, bool(home)), 1.0)
                vals.append(rate * r.proj_min * f_opp * f_home)
            df[s] = vals
        df["flags"] = df["flags"].map(lambda f: ",".join(f))
        df["injury_note"] = df["player"].map(lambda n: notes.get(norm(n), ""))
        return df.drop(columns=["hist_df", "out"])

    def project_slate(self, slate: pd.DataFrame, overrides: dict | None = None) -> pd.DataFrame:
        parts = []
        for g in slate.itertuples():
            for team, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
                p = self.project_team(team, opp, home, g.date, overrides)
                if len(p):
                    p["game_id"] = g.game_id
                    parts.append(p)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def probs(self, stat: str, mean: float, line: float):
        return nb_probs(mean, self.alpha.get(stat, self.cfg["default_alpha"]), line)


class GoalieProjector:
    """NHL goalie saves = projected shots against x shrunk save %."""

    def __init__(self, ds: Dataset, cfg: dict, asof):
        self.cfg = cfg["nhl"]
        self.ds = ds.before(asof)
        gg = self.ds.goalie_games
        self.gg = gg.sort_values("date") if len(gg) else gg
        self.lg_sv = float(gg["saves"].sum() / gg["sa"].sum()) if len(gg) and gg["sa"].sum() else 0.900
        if len(gg):
            self.alpha = fit_alpha((g["saves"].values for _, g in gg[gg["started"]].groupby("player_id")),
                                   min_mean=5, default=0.02)
        else:
            self.alpha = 0.02

    def likely_starter(self, team: str, override: str | None = None):
        g = self.gg[(self.gg["team"] == team) & self.gg["started"]] if len(self.gg) else self.gg
        if not len(g):
            return None
        if override:
            m = g[g["player"].map(norm) == norm(override)]
            if len(m):
                return m.iloc[-1]["player_id"], m.iloc[-1]["player"]
        recent = g.tail(5)
        counts = recent.groupby("player_id").size()
        lastw = recent.groupby("player_id")["date"].max()
        best = sorted(counts.index, key=lambda p: (counts[p], lastw[p]))[-1]
        return best, recent[recent["player_id"] == best].iloc[-1]["player"]

    def save_pct(self, pid) -> float:
        k = self.cfg["goalie_shrink_shots"]
        g = self.gg[self.gg["player_id"] == pid]
        return float((g["saves"].sum() + k * self.lg_sv) / (g["sa"].sum() + k))

    def project(self, team: str, opp: str, shots_against: float, override: str | None = None) -> dict | None:
        st = self.likely_starter(team, override)
        if st is None:
            return None
        pid, name = st
        sv = self.save_pct(pid)
        return {"player_id": pid, "player": name, "team": team, "opp": opp, "proj_sa": shots_against,
                "sv_pct": sv, "saves": shots_against * sv, "flags": "" if override else "starter_unconfirmed"}

    def probs(self, mean: float, line: float):
        return nb_probs(mean, self.alpha, line)
