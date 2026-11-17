"""Simulated league so you can try every command with no internet or API key (--demo).

Numbers are fake but realistic in shape. Nothing here is real data or a real betting line.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .dataset import Dataset, add_combos, season_start_year
from .names import NBA_TEAMS, NHL_TEAMS

FIRST = ["Alex", "Ben", "Chris", "Dan", "Eli", "Finn", "Gabe", "Hugo", "Ian", "Jake", "Kyle", "Leo",
         "Max", "Nate", "Owen", "Paul", "Ryan", "Sam", "Theo", "Vic", "Will", "Zane"]
LAST = ["Abbott", "Barnes", "Cole", "Dorsey", "Ellis", "Fox", "Grant", "Hale", "Irwin", "Judd", "Kerr",
        "Lowe", "Mason", "Nash", "Ortiz", "Price", "Quinn", "Reyes", "Shaw", "Tate", "Udall", "Voss",
        "Ward", "Young", "Zeller", "Archer", "Boone", "Crane", "Drake", "Easton", "Frost", "Gage", "Hart",
        "Ives", "Kemp"]


class DemoProvider:
    def __init__(self, sport: str, seed: int = 7):
        self.sport = sport
        self.rng = np.random.default_rng(seed)
        self.teams = list(NBA_TEAMS if sport == "nba" else NHL_TEAMS)
        self._make_league()
        self._cache = {}

    # ------------------------------------------------------------------ league
    def _name(self, i):
        i -= 1000
        return f"{FIRST[i % len(FIRST)]} {LAST[(i // len(FIRST)) % len(LAST)]}"

    def _make_league(self):
        r = self.rng
        self.players, pid = [], 1000
        self.team_str = {}
        for ti, t in enumerate(self.teams):
            if self.sport == "nba":
                self.team_str[t] = {"off": r.normal(1, 0.035), "def": r.normal(1, 0.035), "pace": r.normal(99, 2.5)}
                mins = [35, 33, 32, 30, 28, 25, 22, 18, 14, 10, 6]
                poss = ["G", "G", "F", "F", "C", "G", "F", "C", "G", "F", "C"]
                for k, (m, p) in enumerate(zip(mins, poss)):
                    star = max(0.3, r.normal(1.0, 0.15)) * (1.15 if k < 3 else 1.0)
                    reb = {"C": 0.30, "F": 0.19, "G": 0.12}[p] * r.lognormal(0, 0.15)
                    ast = {"C": 0.07, "F": 0.10, "G": 0.20}[p] * r.lognormal(0, 0.25)
                    fga = 0.33 * star * r.lognormal(0, 0.1)
                    fg3a = fga * {"C": 0.15, "F": 0.38, "G": 0.45}[p] * r.lognormal(0, 0.2)
                    self.players.append({
                        "player_id": pid, "player": self._name(pid), "team": t, "pos": p, "min": m,
                        "rates": {"fga": fga, "fg3a": fg3a, "fta": fga * 0.28, "reb": reb, "ast": ast,
                                  "stl": 0.03, "blk": 0.06 if p == "C" else 0.015, "tov": 0.04 + ast * 0.25},
                        "fg2": r.normal(0.53, 0.03), "fg3": r.normal(0.36, 0.03)})
                    pid += 1
            else:
                self.team_str[t] = {"off": r.normal(1, 0.08), "def": r.normal(1, 0.08)}
                lines = [("F", m) for m in (20, 19.5, 19, 17.5, 17, 16, 15, 14, 13.5, 12.5, 11, 10)] + \
                        [("D", m) for m in (24, 22.5, 20.5, 19, 17, 15)]
                for k, (p, m) in enumerate(lines):
                    sog = (0.13 if p == "F" else 0.075) * r.lognormal(0, 0.28) * (1.2 if k < 3 else 1)
                    self.players.append({
                        "player_id": pid, "player": self._name(pid), "team": t, "pos": p, "min": m,
                        "rates": {"sog": sog, "hits": (0.07 if p == "F" else 0.08) * r.lognormal(0, 0.5),
                                  "blocks": (0.03 if p == "F" else 0.09) * r.lognormal(0, 0.3)},
                        "sh": r.normal(0.105 if p == "F" else 0.05, 0.02), "playmaker": r.lognormal(0, 0.4)})
                    pid += 1
                for g in range(2):
                    self.players.append({"player_id": pid, "player": self._name(pid), "team": t, "pos": "G",
                                         "sv": r.normal(0.905, 0.008), "goalie_rank": g})
                    pid += 1
        self.by_team = {}
        for p in self.players:
            self.by_team.setdefault(p["team"], []).append(p)

    def _schedule(self, start, end):
        r = np.random.default_rng(11)
        days = pd.date_range(start, end)
        rows, gid = [], 1
        for d in days:
            teams = list(self.teams)
            r.shuffle(teams)
            n = r.integers(4, 9) if self.sport == "nba" else r.integers(3, 8)
            for i in range(n):
                rows.append({"game_id": f"D{d:%Y%m%d}{i:02d}", "date": d, "home": teams[2 * i],
                             "away": teams[2 * i + 1], "start_utc": f"{d:%Y-%m-%d}T23:30:00Z", "state": "SIM"})
                gid += 1
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ simulation
    def _sim_nba(self, g, r):
        out, teams = [], []
        H, A = self.team_str[g.home], self.team_str[g.away]
        pace = H["pace"] * A["pace"] / 99 * r.normal(1, 0.03)
        pts = {}
        for side, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
            o, d = self.team_str[side], self.team_str[opp]
            mult = o["off"] * d["def"] * (1.012 if home else 0.988)
            tot = 0
            act = [p for p in self.by_team[side] if r.random() >= 0.04]   # 4% rest / injury
            mins = [float(np.clip(r.normal(p["min"], 3), 0, 46)) for p in act]
            lam_fga = np.array([p["rates"]["fga"] * m * pace / 99 * mult for p, m in zip(act, mins)])
            # team shot volume is constrained by possessions -> allocate a team total (realistic variance)
            team_fga = int(round(r.normal(lam_fga.sum(), 0.35 * np.sqrt(lam_fga.sum()))))
            fga_alloc = r.multinomial(max(team_fga, 0), lam_fga / lam_fga.sum())
            for p, m, fga in zip(act, mins, fga_alloc):
                lam = {k: v * m * pace / 99 for k, v in p["rates"].items()}
                gam = 1.0
                fg3a = r.binomial(fga, min(0.9, p["rates"]["fg3a"] / p["rates"]["fga"]))
                fg3m = r.binomial(fg3a, np.clip(p["fg3"], 0.2, 0.5))
                fg2m = r.binomial(fga - fg3a, np.clip(p["fg2"] * mult ** 0.5, 0.35, 0.7))
                fta = r.poisson(lam["fta"] * gam)
                ftm = r.binomial(fta, 0.78)
                reb = r.poisson(lam["reb"] * r.gamma(10, 0.1))
                row = {"sport": "nba", "season": "2", "game_id": g.game_id, "date": g.date,
                       "player_id": p["player_id"], "player": p["player"], "team": side, "opp": opp,
                       "home": home, "pos": p["pos"], "minutes": m, "pts": float(2 * fg2m + 3 * fg3m + ftm),
                       "fga": float(fga), "fg3a": float(fg3a), "fg3m": float(fg3m), "fta": float(fta),
                       "reb": float(reb), "oreb": float(r.binomial(reb, 0.25)),
                       "ast": float(r.poisson(lam["ast"] * r.gamma(8, 1 / 8))),
                       "stl": float(r.poisson(lam["stl"])), "blk": float(r.poisson(lam["blk"])),
                       "tov": float(r.poisson(lam["tov"]))}
                row["dreb"] = row["reb"] - row["oreb"]
                tot += row["pts"]
                out.append(row)
            pts[side] = tot
        if pts[g.home] == pts[g.away]:
            pts[g.home] += 3
        for side, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
            teams.append({"game_id": g.game_id, "date": g.date, "season": "2", "team": side, "opp": opp,
                          "home": home, "pf": pts[side], "pa": pts[opp], "poss": pace, "pace": pace,
                          "min": 240.0, "ot": False})
        return out, teams, []

    def _sim_nhl(self, g, r):
        out, teams, goalies = [], [], []
        res = {}
        for side, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
            o, d = self.team_str[side], self.team_str[opp]
            mult = o["off"] * d["def"] * (1.02 if home else 0.98)
            rows, goals = [], 0
            sk = [p for p in self.by_team[side] if p["pos"] != "G"]
            for p in sk:
                m = float(np.clip(r.normal(p["min"], 2), 4, 30))
                sog = r.poisson(p["rates"]["sog"] * m * mult * r.gamma(6, 1 / 6))
                gl = r.binomial(sog, np.clip(p["sh"], 0.02, 0.25))
                goals += gl
                rows.append({"sport": "nhl", "season": 2, "game_id": g.game_id, "date": g.date,
                             "player_id": p["player_id"], "player": p["player"], "team": side, "opp": opp,
                             "home": home, "pos": p["pos"], "minutes": m, "sog": float(sog),
                             "attempts": float(sog + r.poisson(0.85 * sog + 0.4)), "goals": float(gl),
                             "assists": 0.0, "hits": float(r.poisson(p["rates"]["hits"] * m)),
                             "blocks": float(r.poisson(p["rates"]["blocks"] * m)), "ppp": 0.0,
                             "_pm": p["playmaker"] * m})
            w = np.array([x["_pm"] for x in rows])
            for _ in range(int(goals)):
                for k in r.choice(len(rows), size=r.choice([1, 2], p=[0.25, 0.75]), replace=False, p=w / w.sum()):
                    rows[k]["assists"] += 1
                if r.random() < 0.22:
                    rows[int(r.choice(len(rows), p=w / w.sum()))]["ppp"] += 1
            for x in rows:
                x["points"] = x["goals"] + x["assists"]
                x.pop("_pm")
            res[side] = {"rows": rows, "goals": goals, "sog": sum(x["sog"] for x in rows), "home": home, "opp": opp}
        ot = so = False
        gh, ga = res[g.home]["goals"], res[g.away]["goals"]
        fh, fa = gh, ga
        if gh == ga:
            ot = True
            so = r.random() < 0.35
            if r.random() < 0.5:
                fh += 1
            else:
                fa += 1
        final = {g.home: fh, g.away: fa}
        reg = {g.home: gh + (0 if so else fh - gh), g.away: ga + (0 if so else fa - ga)}
        for side, v in res.items():
            out += v["rows"]
            opp = v["opp"]
            gl = [p for p in self.by_team[side] if p["pos"] == "G"]
            gk = gl[0] if r.random() < 0.68 else gl[1]
            sa = res[opp]["sog"]
            goalies.append({"game_id": g.game_id, "date": g.date, "player_id": gk["player_id"],
                            "player": gk["player"], "team": side, "opp": opp, "home": v["home"], "minutes": 60.0,
                            "sa": float(sa), "saves": float(sa - res[opp]["goals"]),
                            "ga": float(res[opp]["goals"]), "started": True})
            teams.append({"game_id": g.game_id, "date": g.date, "season": 2, "team": side, "opp": opp,
                          "home": v["home"], "pf": final[side], "pa": final[opp], "gf": reg[side], "ga": reg[opp],
                          "sf": v["sog"], "sa": sa, "cf": v["sog"] * 1.8, "ca": sa * 1.8,
                          "xgf": v["sog"] * 0.1 * r.normal(1, 0.1) * self.team_str[side]["off"],
                          "xga": sa * 0.1 * r.normal(1, 0.1) * self.team_str[opp]["off"],
                          "ot": ot, "so": so})
        return out, teams, goalies

    # ------------------------------------------------------------------ API
    def _season(self, asof):
        y = season_start_year(asof)
        key = (y, pd.Timestamp(asof))
        if key in self._cache:
            return self._cache[key]
        start = pd.Timestamp(f"{y}-10-08")
        sched = self._schedule(start, pd.Timestamp(asof) + pd.Timedelta(days=3))
        r = np.random.default_rng(99)
        P, T, G = [], [], []
        for g in sched[sched["date"] < pd.Timestamp(asof)].itertuples():
            p, t, gl = (self._sim_nba if self.sport == "nba" else self._sim_nhl)(g, r)
            P += p; T += t; G += gl
        pg = pd.DataFrame(P)
        if self.sport == "nba":
            pg = add_combos(pg, "nba")
        self._cache[key] = (sched, pg, pd.DataFrame(T), pd.DataFrame(G))
        return self._cache[key]

    def _priors(self):
        r = np.random.default_rng(5)
        rows = []
        for p in self.players:
            if p["pos"] == "G":
                continue
            games = int(r.integers(40, 80))
            mins = p["min"] * games
            row = {"player_id": p["player_id"], "player": p["player"], "pos": p["pos"], "games": games,
                   "minutes": mins}
            if self.sport == "nba":
                pts_rate = (p["rates"]["fga"] - p["rates"]["fg3a"]) * 2 * p["fg2"] + p["rates"]["fg3a"] * 3 * p["fg3"] \
                    + p["rates"]["fta"] * 0.78
                base = {**p["rates"], "pts": pts_rate, "fg3m": p["rates"]["fg3a"] * p["fg3"],
                        "oreb": p["rates"]["reb"] * 0.25, "dreb": p["rates"]["reb"] * 0.75}
            else:
                base = {"sog": p["rates"]["sog"], "goals": p["rates"]["sog"] * p["sh"],
                        "assists": p["rates"]["sog"] * 0.11 * p["playmaker"] * 1.4,
                        "hits": p["rates"]["hits"], "blocks": p["rates"]["blocks"]}
                base["points"] = base["goals"] + base["assists"]
                base["ppp"] = base["points"] * 0.22
            for k, v in base.items():
                row[k] = v * mins * r.lognormal(0, 0.12)
            rows.append(row)
        pp = pd.DataFrame(rows)
        opps = lambda t: [o for o in self.teams if o != t]
        if self.sport == "nba":
            pp = add_combos(pp, "nba")
            rows = []
            for t, s in self.team_str.items():
                pace = np.mean([s["pace"] * self.team_str[o]["pace"] / 99 for o in opps(t)])
                pf = np.mean([self._true_score(t, o, True) for o in opps(t)])
                pa = np.mean([self._true_score(o, t, True) for o in opps(t)])
                rows.append({"team": t, "ortg": 100 * pf / pace * r.normal(1, 0.02),
                             "drtg": 100 * pa / pace * r.normal(1, 0.02), "pace": pace})
            tp = pd.DataFrame(rows)
        else:
            tp = pd.DataFrame([{"team": t,
                                "gf": np.mean([self._true_score(t, o, True) for o in opps(t)]) * r.normal(1, 0.06),
                                "ga": np.mean([self._true_score(o, t, True) for o in opps(t)]) * r.normal(1, 0.06)}
                               for t in self.teams])
        return pp, tp

    def load(self, asof, verbose: bool = True) -> Dataset:
        _, pg, tg, gg = self._season(asof)
        pp, tp = self._priors()
        return Dataset(self.sport, pg, tg, gg, pp, tp)

    def slate(self, date) -> pd.DataFrame:
        sched, *_ = self._season(date)
        return sched[sched["date"] == pd.Timestamp(date)].reset_index(drop=True)

    def _true_score(self, side, opp, home):
        """Hidden 'true' expected score (used only to make fake demo lines)."""
        o, d = self.team_str[side], self.team_str[opp]
        if self.sport == "nba":
            pace = o["pace"] * d["pace"] / 99
            mult = o["off"] * d["def"] * (1.012 if home else 0.988)
            tot = 0.0
            for p in self.by_team[side]:
                rt = p["rates"]
                fg2a = rt["fga"] * mult - rt["fg3a"]
                tot += 0.96 * p["min"] * pace / 99 * (2 * fg2a * np.clip(p["fg2"] * mult ** 0.5, 0.35, 0.7)
                                                      + 3 * rt["fg3a"] * p["fg3"] + 0.78 * rt["fta"])
            return tot
        mult = o["off"] * d["def"] * (1.02 if home else 0.98)
        return sum(p["rates"]["sog"] * p["min"] * mult * np.clip(p["sh"], 0.02, 0.25)
                   for p in self.by_team[side] if p["pos"] != "G")

    # fake sportsbook lines built from the hidden "true" talent + noise
    def odds(self, date, kind: str) -> pd.DataFrame:
        r = np.random.default_rng(int(pd.Timestamp(date).strftime("%Y%m%d")))
        books = ["demo_book_a", "demo_book_b", "demo_book_c"]
        rows = []

        def two_way(ev, g, market, player, point, p_over, names=("Over", "Under")):
            for b in books:
                vig = r.uniform(0.035, 0.06)
                pb = float(np.clip(p_over + r.normal(0, 0.012), 0.05, 0.95))
                for nm, p in ((names[0], pb), (names[1], 1 - pb)):
                    rows.append({"event_id": ev, "commence": g.start_utc, "home": g.home, "away": g.away,
                                 "book": b, "market": market, "name": nm, "player": player,
                                 "point": point, "price": round(1 / (p * (1 + vig)), 3)})

        for g in self.slate(date).itertuples():
            ev = f"demo-{g.game_id}"
            if kind == "games":
                from scipy.stats import norm, poisson
                th, ta = self._true_score(g.home, g.away, True), self._true_score(g.away, g.home, False)
                if self.sport == "nba":
                    tot, mar = (th + ta) * r.normal(1, 0.01), th - ta
                    two_way(ev, g, "totals", None, round(tot * 2) / 2, 0.5)
                    sp = round(-mar * 2) / 2
                    two_way(ev, g, "spreads", None, sp, 0.5, ("home", "away"))
                    for row in rows[-6:]:
                        if row["name"] == "away":
                            row["point"] = -sp
                    two_way(ev, g, "h2h", None, np.nan, float(norm.cdf(mar / 12.5)), ("home", "away"))
                else:
                    tot = th + ta
                    line = 6.5 if tot > 6.0 else 5.5
                    p_over = 1 - poisson.cdf(np.floor(line), tot * 1.04)
                    two_way(ev, g, "totals", None, line, float(p_over))
                    ph = sum(poisson.pmf(i, th) * poisson.cdf(i - 1, ta) for i in range(15))
                    pt = sum(poisson.pmf(i, th) * poisson.pmf(i, ta) for i in range(15))
                    two_way(ev, g, "h2h", None, np.nan, float(ph + pt * th / (th + ta)), ("home", "away"))
            else:
                from ..models.dist import nb_probs
                for side, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
                    o, dfn = self.team_str[side], self.team_str[opp]
                    for p in self.by_team[side]:
                        if p["pos"] == "G" or r.random() < 0.4:
                            continue
                        if self.sport == "nba":
                            mult = o["off"] * dfn["def"]
                            pts = ((p["rates"]["fga"] - p["rates"]["fg3a"]) * 2 * p["fg2"] + p["rates"]["fg3a"] * 3 *
                                   p["fg3"] + p["rates"]["fta"] * 0.78) * p["min"] * mult
                            markets = (("pts", pts), ("reb", p["rates"]["reb"] * p["min"]),
                                       ("ast", p["rates"]["ast"] * p["min"]))
                        else:
                            mult = o["off"] * dfn["def"] * (1.02 if home else 0.98)
                            markets = (("sog", p["rates"]["sog"] * p["min"] * mult),
                                       ("blocks", p["rates"]["blocks"] * p["min"]))
                        for st, mu in markets:
                            if mu < 1.0 or (st == "blocks" and p["pos"] != "D"):
                                continue
                            line = np.floor(mu) + 0.5 if r.random() < 0.5 else np.floor(mu) - 0.5 + (mu % 1 > 0.5)
                            line = max(0.5, float(line))
                            p_over = nb_probs(mu, 0.06, line)[0]
                            two_way(ev, g, st, p["player"], line, p_over)
        return pd.DataFrame(rows)
