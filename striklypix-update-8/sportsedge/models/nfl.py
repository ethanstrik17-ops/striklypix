"""NFL models.

Game: team points for/against (recency-weighted, shrunk to last season and league average)
      -> expected score each side + home field -> normal margin & total.
Players: projection = team volume (pass attempts / rush attempts, adjusted for opponent)
         x player's share of that volume (targets, carries, QB dropbacks)
         x player's efficiency (catch rate, yards per target/carry/attempt, TD rates), shrunk to league
         x opponent defence factor.
Injured players are removed and their share is handed to teammates in the same role.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ..data.dataset import Dataset
from ..data.names import norm
from .dist import fit_alpha, nb_probs, normal_probs

NFL_STATS = ["pass_yds", "pass_att", "pass_cmp", "pass_td", "rush_yds", "rush_att", "rec", "rec_yds",
             "targets", "td"]


def _ew(values, halflife):
    v = np.asarray(values, dtype=float)
    w = 0.5 ** (np.arange(len(v))[::-1] / halflife)
    return v, w


def _shrunk(values, halflife, k, prior):
    v, w = _ew(values, halflife)
    if not len(v):
        return prior
    return float(((w * v).sum() + k * prior) / (w.sum() + k))


class NFLTeamModel:
    COLS = ["pf", "pa", "pass_att", "rush_att", "pass_yds", "rush_yds", "opp_pass_att", "opp_rush_att",
            "opp_pass_yds", "opp_rush_yds"]

    def __init__(self, ds: Dataset, cfg: dict, asof):
        self.cfg = cfg["nfl"]
        self.sport = "nfl"
        tg = ds.before(asof).team_games
        self.tg = tg.sort_values("date") if len(tg) else tg
        prior = ds.team_prior.set_index("team") if len(ds.team_prior) else pd.DataFrame()
        src = self.tg if len(self.tg) >= 40 else (ds.team_prior if len(ds.team_prior) else self.tg)
        self.lg = {c: float(src[c].mean()) if len(src) and c in src else np.nan for c in self.COLS}
        defaults = {"pf": 22.0, "pa": 22.0, "pass_att": 33.0, "rush_att": 26.0, "pass_yds": 215.0,
                    "rush_yds": 115.0}
        for c in self.COLS:
            base = c.replace("opp_", "")
            if np.isnan(self.lg[c]):
                self.lg[c] = defaults.get(base, 0.0)
        self.lg["pa"] = self.lg["pf"]
        h, k, reg = self.cfg["team_halflife"], self.cfg["team_shrink_games"], self.cfg["prior_regression"]
        teams = set(self.tg["team"]) if len(self.tg) else set()
        teams |= set(prior.index) if len(prior) else set()
        self.ratings = {}
        for t in teams:
            g = self.tg[self.tg["team"] == t] if len(self.tg) else self.tg
            r = {"games": len(g)}
            for c in self.COLS:
                pr = self.lg[c]
                if len(prior) and t in prior.index and c in prior.columns and pd.notna(prior.at[t, c]):
                    pr = self.lg[c] + (1 - reg) * (float(prior.at[t, c]) - self.lg[c])
                vals = g[c].dropna().values if len(g) and c in g else []
                r[c] = _shrunk(vals, h, k, pr)
            self.ratings[t] = r

    def rested(self, team, date):
        if not len(self.tg):
            return 99
        g = self.tg[self.tg["team"] == team]
        return int((pd.Timestamp(date) - g["date"].max()).days) if len(g) else 99

    def predict(self, home, away, date, *_):
        return NFLGame(self, home, away, date)

    # opponent-adjusted volume & efficiency factors used by the player model
    def volume(self, team, opp):
        T, O = self.ratings[team], self.ratings[opp]
        pa = T["pass_att"] * (O["opp_pass_att"] / self.lg["opp_pass_att"]) ** 0.5
        ra = T["rush_att"] * (O["opp_rush_att"] / self.lg["opp_rush_att"]) ** 0.5
        return pa, ra

    def defense(self, opp):
        O, cap = self.ratings[opp], self.cfg["opp_factor_cap"]
        f = lambda x, lg: float(np.clip(x / lg, *cap)) if lg else 1.0
        pass_eff = f(O["opp_pass_yds"] / max(O["opp_pass_att"], 1), self.lg["opp_pass_yds"] / self.lg["opp_pass_att"])
        rush_eff = f(O["opp_rush_yds"] / max(O["opp_rush_att"], 1), self.lg["opp_rush_yds"] / self.lg["opp_rush_att"])
        pts = f(O["pa"], self.lg["pf"])
        return pass_eff, rush_eff, pts


class NFLGame:
    def __init__(self, tm: NFLTeamModel, home, away, date):
        c = tm.cfg
        H, A = tm.ratings.get(home), tm.ratings.get(away)
        if H is None or A is None:
            raise KeyError(f"no ratings for {home} or {away}")
        lg = tm.lg["pf"]
        self.home_pts = lg + (H["pf"] - lg) + (A["pa"] - lg) + c["home_field_pts"] / 2
        self.away_pts = lg + (A["pf"] - lg) + (H["pa"] - lg) - c["home_field_pts"] / 2
        self.home_pts, self.away_pts = max(self.home_pts, 6.0), max(self.away_pts, 6.0)
        self.margin = self.home_pts - self.away_pts
        self.total = self.home_pts + self.away_pts
        self.sd_m, self.sd_t = c["margin_sd"], c["total_sd"]
        self.home, self.away = home, away

    def p_ml(self, side):
        p = float(stats.norm.cdf(self.margin / self.sd_m))
        return (p if side == "home" else 1 - p), 0.0

    def p_cover(self, side, point):
        mu = self.margin if side == "home" else -self.margin
        over, push, _ = normal_probs(mu, self.sd_m, -point)
        return over, push

    def p_total(self, line):
        over, push, _ = normal_probs(self.total, self.sd_t, line)
        return over, push

    def p_team_total(self, side, line):
        mu = self.home_pts if side == "home" else self.away_pts
        over, push, _ = normal_probs(mu, self.sd_t * 0.72, line)
        return over, push

    def summary(self):
        return {"home": self.home, "away": self.away, "proj_home": self.home_pts, "proj_away": self.away_pts,
                "proj_total": self.total, "proj_margin": self.margin, "p_home_win": self.p_ml("home")[0]}


class NFLPlayerProjector:
    def __init__(self, ds: Dataset, cfg: dict, asof, teams: NFLTeamModel):
        self.sport = "nfl"
        self.cfg = cfg["nfl"]
        self.asof = pd.Timestamp(asof)
        self.ds = ds.before(self.asof)
        self.tm = teams
        pg = self.ds.player_games
        self.pg = pg.sort_values(["date", "game_id"]) if len(pg) else pg
        self.stats = NFL_STATS
        tg = self.ds.team_games
        self.team_tot = (tg.set_index(["game_id", "team"])[["pass_att", "rush_att"]] if len(tg) else pd.DataFrame())
        self.team_games_ids = ({t: list(g.sort_values("date")["game_id"]) for t, g in tg.groupby("team")}
                               if len(tg) else {})
        self.by_player = {pid: self._with_team(g) for pid, g in self.pg.groupby("player_id")} if len(self.pg) else {}
        self.prior = self.ds.player_prior.set_index("player_id") if len(self.ds.player_prior) else pd.DataFrame()
        self._league()
        self.alpha = {}
        floors = self.cfg.get("alpha_floor", {})
        fixed = self.cfg.get("alpha") or {}
        for s in self.stats:
            if s in fixed:
                self.alpha[s] = float(fixed[s])
                continue
            groups = (g[s].values for g in self.by_player.values() if g[s].mean() >= 0.5) if self.by_player else []
            self.alpha[s] = max(floors.get(s, 0.05), fit_alpha(groups, min_games=4, min_mean=0.5,
                                                              default=floors.get(s, 0.1)))

    def _with_team(self, g):
        if not len(self.team_tot):
            return g.assign(team_pass_att=np.nan, team_rush_att=np.nan)
        idx = list(zip(g["game_id"], g["team"]))
        tt = self.team_tot.reindex(idx)
        return g.assign(team_pass_att=tt["pass_att"].values, team_rush_att=tt["rush_att"].values)

    def _league(self):
        pg = self.pg if len(self.pg) else self.ds.player_prior
        tot = lambda c: float(pg[c].sum()) if len(pg) and c in pg else 0.0
        div = lambda a, b, d: a / b if b > 0 else d
        self.lg = {
            "catch": div(tot("rec"), tot("targets"), 0.65), "ypt": div(tot("rec_yds"), tot("targets"), 7.8),
            "ypc": div(tot("rush_yds"), tot("rush_att"), 4.3), "ypa": div(tot("pass_yds"), tot("pass_att"), 6.9),
            "cmp": div(tot("pass_cmp"), tot("pass_att"), 0.65), "rec_td": div(tot("rec_td"), tot("targets"), 0.045),
            "rush_td": div(tot("rush_td"), tot("rush_att"), 0.03), "pass_td": div(tot("pass_td"), tot("pass_att"), 0.045),
        }

    # ---------------------------------------------------------------- roster & shares
    def roster(self, team: str) -> list:
        recent = set(self.team_games_ids.get(team, [])[-3:])
        out = []
        for pid, g in self.by_player.items():
            if g["team"].iloc[-1] == team and set(g["game_id"]) & recent:
                out.append(pid)
        return out

    def _share(self, g, num, den, k=3.0):
        g = g.dropna(subset=[den])
        g = g[g[den] > 0]
        if not len(g):
            return 0.0
        v = (g[num] / g[den]).values[-10:]
        season = float(g[num].sum() / g[den].sum())
        return _shrunk(v, self.cfg["share_halflife"], k, season)

    def _eff(self, made, opps, k, lg):
        return float((made + k * lg) / (opps + k))

    def project_team(self, team, opp, home, overrides=None) -> pd.DataFrame:
        ov = overrides or {}
        out_names = {norm(n) for n in ov.get("out", [])}
        q_names = {norm(n) for n in ov.get("questionable", [])}
        notes = ov.get("injury_notes", {})
        if team not in self.tm.ratings or opp not in self.tm.ratings:
            return pd.DataFrame()
        team_pa, team_ra = self.tm.volume(team, opp)
        f_pass, f_rush, f_pts = self.tm.defense(opp)
        last_gid = (self.team_games_ids.get(team) or [None])[-1]
        rows = []
        for pid in self.roster(team):
            g = self.by_player[pid]
            role = g["pos"].iloc[-1]
            rows.append({"player_id": pid, "player": g["player"].iloc[-1], "team": team, "opp": opp, "home": home,
                         "pos": role, "games": len(g), "hist": g,
                         "t_share": self._share(g, "targets", "team_pass_att"),
                         "c_share": self._share(g, "rush_att", "team_rush_att"),
                         "p_share": self._share(g, "pass_att", "team_pass_att") if role == "QB" else 0.0,
                         "out": norm(g["player"].iloc[-1]) in out_names,
                         "flags": (["missed_last_game"] if last_gid is not None and last_gid not in set(g["game_id"])
                                   else []) + (["questionable"] if norm(g["player"].iloc[-1]) in q_names else [])})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # one starting QB: most recent game's leader among healthy QBs
        qbs = df[(df["pos"] == "QB") & ~df["out"]]
        starter = None
        if len(qbs):
            starter = max(qbs.itertuples(), key=lambda r: (r.hist["pass_att"].iloc[-1] if len(r.hist) else 0,
                                                           r.p_share)).player_id
        df.loc[df["pos"] == "QB", "p_share"] = 0.0
        if starter is not None:
            df.loc[df["player_id"] == starter, "p_share"] = 0.97
            if (df["out"] & (df["pos"] == "QB")).any():
                df.loc[df["player_id"] == starter, "flags"] = df.loc[df["player_id"] == starter, "flags"].map(
                    lambda f: f + ["starting_for_injured_qb"])
        # injured players' targets / carries go to healthy teammates in proportion to their own share
        for col in ("t_share", "c_share"):
            freed = df.loc[df["out"], col].sum()
            alive = ~df["out"] & (df[col] > 0.02)
            if freed > 0 and alive.any():
                df.loc[alive, col] += freed * df.loc[alive, col] / df.loc[alive, col].sum()
                df.loc[alive, "flags"] = df.loc[alive, "flags"].map(lambda f: f + ["role_bump"] if "role_bump" not in f else f)
            tot = df.loc[~df["out"], col].sum()
            cap = 0.97 if col == "t_share" else 0.95
            if tot > cap:
                df.loc[~df["out"], col] *= cap / tot
        df = df[~df["out"]].copy()
        recs = []
        for r in df.itertuples():
            g = r.hist
            targets = r.t_share * team_pa
            carries = r.c_share * team_ra
            patt = r.p_share * team_pa
            catch = self._eff(g["rec"].sum(), g["targets"].sum(), 40, self.lg["catch"])
            ypt = self._eff(g["rec_yds"].sum(), g["targets"].sum(), 60, self.lg["ypt"])
            ypc = self._eff(g["rush_yds"].sum(), g["rush_att"].sum(), 80, self.lg["ypc"])
            ypa = self._eff(g["pass_yds"].sum(), g["pass_att"].sum(), 250, self.lg["ypa"])
            cmp_ = self._eff(g["pass_cmp"].sum(), g["pass_att"].sum(), 200, self.lg["cmp"])
            rtd = self._eff(g["rec_td"].sum(), g["targets"].sum(), 150, self.lg["rec_td"])
            utd = self._eff(g["rush_td"].sum(), g["rush_att"].sum(), 150, self.lg["rush_td"])
            ptd = self._eff(g["pass_td"].sum(), g["pass_att"].sum(), 400, self.lg["pass_td"])
            recs.append({
                "player_id": r.player_id, "player": r.player, "team": team, "opp": opp, "home": home, "pos": r.pos,
                "games": r.games, "proj_min": np.nan, "t_share": r.t_share, "c_share": r.c_share,
                "targets": targets, "rec": targets * catch, "rec_yds": targets * ypt * f_pass,
                "rush_att": carries, "rush_yds": carries * ypc * f_rush,
                "pass_att": patt, "pass_cmp": patt * cmp_, "pass_yds": patt * ypa * f_pass, "pass_td": patt * ptd * f_pts,
                "td": (targets * rtd + carries * utd) * f_pts,
                "flags": ",".join(r.flags + ([f"only_{r.games}_games"] if r.games < 3 else [])),
                "injury_note": notes.get(norm(r.player), ""),
            })
        out = pd.DataFrame(recs)
        if len(out):
            out["rush_rec_yds"] = out["rush_yds"] + out["rec_yds"]
            out["pass_rush_yds"] = out["pass_yds"] + out["rush_yds"]
        keep = (out["targets"] >= 1.5) | (out["rush_att"] >= 3) | (out["pass_att"] >= 10)
        return out[keep].reset_index(drop=True)

    def project_slate(self, slate: pd.DataFrame, overrides: dict | None = None) -> pd.DataFrame:
        parts = []
        for g in slate.itertuples():
            for team, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
                p = self.project_team(team, opp, home, overrides)
                if len(p):
                    p["game_id"] = g.game_id
                    parts.append(p)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def probs(self, stat: str, mean: float, line: float):
        return nb_probs(mean, self.alpha.get(stat, 0.1), line)
