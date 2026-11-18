"""Live NFL data from ESPN's public JSON (box scores, schedule, free DraftKings lines, injuries)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

from .dataset import Dataset
from .espn import espn_team, game_meta, parse_injuries, parse_odds
from .http import CachedClient

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
PLAYER_COLS = ["pass_att", "pass_cmp", "pass_yds", "pass_td", "ints", "rush_att", "rush_yds", "rush_td",
               "rec", "rec_yds", "rec_td", "targets", "td"]


def nfl_season_year(date) -> int:
    d = pd.Timestamp(date)
    return d.year if d.month >= 3 else d.year - 1


def et_date(iso) -> pd.Timestamp | None:
    if not iso:
        return None
    t = pd.Timestamp(iso)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return pd.Timestamp(t.tz_convert("America/Toronto").date())


def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _pair(v) -> tuple[float, float]:
    try:
        a, b = str(v).replace("-", "/").split("/")[:2]
        return float(a), float(b)
    except ValueError:
        return 0.0, 0.0


class NFLProvider:
    sport = "nfl"

    def __init__(self, cfg: dict):
        g = cfg["general"]
        self.cfg = cfg
        self.espn = CachedClient(os.path.join(g["cache_dir"], "nfl_espn"), delay=0.25)
        self.prior_weeks = int(cfg.get("nfl", {}).get("prior_weeks", 8))
        self.slate_days = int(cfg.get("nfl", {}).get("slate_days", 7))
        self._odds, self.line_moves = [], {}

    # ------------------------------------------------------------------ schedule
    def _week(self, year: int, week: int, seasontype: int = 2, ttl=1800) -> dict:
        return self.espn.get_json(f"{ESPN}/scoreboard", params={"dates": year, "seasontype": seasontype,
                                                                "week": week}, ttl=ttl)

    @staticmethod
    def _events(data: dict) -> list[dict]:
        out = []
        for ev in data.get("events", []):
            comp = ev["competitions"][0]
            if (ev.get("season") or {}).get("type", 2) != 2:
                continue
            teams = {c["homeAway"]: espn_team("nfl", c["team"]) for c in comp["competitors"]}
            st = (comp.get("status") or ev.get("status") or {}).get("type", {})
            out.append({"game_id": str(ev["id"]), "date": et_date(ev.get("date")), "start_utc": ev.get("date"),
                        "home": teams.get("home"), "away": teams.get("away"), "state": st.get("state"),
                        "completed": bool(st.get("completed")), "_comp": comp})
        return out

    def season_games(self, year: int, upto=None) -> list[dict]:
        games = []
        today = pd.Timestamp.today().normalize()
        for w in range(1, 19):
            approx_end = pd.Timestamp(f"{year}-09-04") + pd.Timedelta(days=7 * w + 2)
            if upto is not None and approx_end - pd.Timedelta(days=12) > pd.Timestamp(upto):
                break
            ttl = None if approx_end < today - pd.Timedelta(days=4) else 1800
            try:
                games += self._events(self._week(year, w, ttl=ttl))
            except RuntimeError as e:
                print(f"  warn: NFL week {w} schedule failed ({e})", file=sys.stderr)
        return games

    def slate(self, date) -> pd.DataFrame:
        """Upcoming (not started) games in the next `slate_days` days: this week's NFL card."""
        date = pd.Timestamp(date).normalize()
        cur = self.espn.get_json(f"{ESPN}/scoreboard", ttl=900)
        evs = self._events(cur)
        wk = (cur.get("week") or {}).get("number")
        if wk and wk < 18:
            try:
                evs += self._events(self._week(nfl_season_year(date), wk + 1, ttl=900))
            except RuntimeError:
                pass
        seen, rows, self._odds, self.game_meta = set(), [], [], {}
        for e in evs:
            if e["game_id"] in seen or e["completed"] or e["state"] != "pre" or e["date"] is None:
                continue
            if not (date <= e["date"] < date + pd.Timedelta(days=self.slate_days)):
                continue
            seen.add(e["game_id"])
            self.game_meta[e["game_id"]] = game_meta("nfl", e["_comp"])
            rows.append({k: e[k] for k in ("game_id", "date", "start_utc", "home", "away", "state")})
            r, mv = parse_odds("nfl", e["game_id"], e["_comp"], e["start_utc"])
            self._odds += r
            if mv:
                self.line_moves[(mv["home"], mv["away"])] = mv
        return pd.DataFrame(rows, columns=["game_id", "date", "start_utc", "home", "away", "state"])

    def espn_game_odds(self) -> list[dict]:
        return list(self._odds)

    def injuries(self) -> pd.DataFrame:
        try:
            return parse_injuries("nfl", self.espn.get_json(f"{ESPN}/injuries", ttl=1800))
        except (RuntimeError, KeyError) as e:
            print(f"  warn: NFL injury report unavailable ({e})", file=sys.stderr)
            return pd.DataFrame()

    # ------------------------------------------------------------------ box scores
    @staticmethod
    def parse_summary(data: dict, date) -> tuple[list, list]:
        comp = data["header"]["competitions"][0]
        gid = str(data["header"].get("id") or comp.get("id"))
        side = {c["homeAway"]: (espn_team("nfl", c["team"]), _f(c.get("score"))) for c in comp["competitors"]}
        home = side["home"][0]
        opp = {side["home"][0]: side["away"][0], side["away"][0]: side["home"][0]}
        score = {side["home"][0]: side["home"][1], side["away"][0]: side["away"][1]}
        players: dict = {}
        for tb in data.get("boxscore", {}).get("players", []):
            team = espn_team("nfl", tb["team"])
            if team not in opp:
                continue
            for cat in tb.get("statistics", []):
                keys = [str(k) for k in (cat.get("keys") or cat.get("labels") or [])]
                for a in cat.get("athletes", []):
                    ath = a.get("athlete") or {}
                    pid = str(ath.get("id"))
                    st = dict(zip(keys, a.get("stats") or []))
                    row = players.setdefault(pid, {"sport": "nfl", "game_id": gid, "date": date, "player_id": pid,
                                                   "player": ath.get("displayName"), "team": team, "opp": opp[team],
                                                   "home": team == home, **{c: 0.0 for c in PLAYER_COLS}})
                    name = cat.get("name")
                    if name == "passing":
                        cmp_, att = _pair(st.get("completions/passingAttempts", st.get("C/ATT")))
                        row.update(pass_cmp=cmp_, pass_att=att, pass_yds=_f(st.get("passingYards", st.get("YDS"))),
                                   pass_td=_f(st.get("passingTouchdowns", st.get("TD"))),
                                   ints=_f(st.get("interceptions", st.get("INT"))))
                    elif name == "rushing":
                        row.update(rush_att=_f(st.get("rushingAttempts", st.get("CAR"))),
                                   rush_yds=_f(st.get("rushingYards", st.get("YDS"))),
                                   rush_td=_f(st.get("rushingTouchdowns", st.get("TD"))))
                    elif name == "receiving":
                        row.update(rec=_f(st.get("receptions", st.get("REC"))),
                                   rec_yds=_f(st.get("receivingYards", st.get("YDS"))),
                                   rec_td=_f(st.get("receivingTouchdowns", st.get("TD"))),
                                   targets=_f(st.get("receivingTargets", st.get("TGTS"))))
        prow = []
        for r in players.values():
            r["td"] = r["rush_td"] + r["rec_td"]
            if r["pass_att"] or r["rush_att"] or r["targets"] or r["rec"]:
                prow.append(r)
        teams = []
        for tb in data.get("boxscore", {}).get("teams", []):
            team = espn_team("nfl", tb["team"])
            if team not in opp:
                continue
            ts = {}
            for x in tb.get("statistics", []):
                ts.setdefault(x.get("name"), x.get("displayValue"))
            _, patt = _pair(ts.get("completionAttempts", "0/0"))
            sacks, _ = _pair(ts.get("sacksYardsLost", "0-0"))
            teams.append({"game_id": gid, "date": date, "team": team, "opp": opp[team], "home": team == home,
                          "pf": score[team], "pa": score[opp[team]], "pass_att": patt, "sacks": sacks,
                          "rush_att": _f(ts.get("rushingAttempts")), "pass_yds": _f(ts.get("netPassingYards")),
                          "rush_yds": _f(ts.get("rushingYards")), "plays": _f(ts.get("totalOffensivePlays")),
                          "yards": _f(ts.get("totalYards")), "turnovers": _f(ts.get("turnovers"))})
        if len(teams) == 2:  # defensive "allowed" columns
            a, b = teams
            for x, y in ((a, b), (b, a)):
                x.update(opp_pass_att=y["pass_att"], opp_rush_att=y["rush_att"], opp_pass_yds=y["pass_yds"],
                         opp_rush_yds=y["rush_yds"], opp_sacks=y["sacks"])
        return prow, teams

    def _games_frames(self, games: list[dict], verbose: bool, label: str):
        P, T = [], []
        for i, g in enumerate(games):
            if verbose and (i % 25 == 0 or i == len(games) - 1):
                print(f"  NFL {label}: game {i + 1}/{len(games)}", file=sys.stderr)
            try:
                data = self.espn.get_json(f"{ESPN}/summary", params={"event": g["game_id"]}, ttl=None,
                                          retries=2, timeout=20)
                p, t = self.parse_summary(data, g["date"])
            except (RuntimeError, KeyError, IndexError, TypeError) as e:
                print(f"  warn: skipped NFL game {g['game_id']} ({str(e)[:80]})", file=sys.stderr)
                continue
            P += p; T += t
        pg, tg = pd.DataFrame(P), pd.DataFrame(T)
        if len(pg):
            pg["minutes"] = 60.0  # placeholder so shared code paths work; NFL uses usage shares instead
            pg["rush_rec_yds"] = pg["rush_yds"].fillna(0) + pg["rec_yds"].fillna(0)
            pg["pass_rush_yds"] = pg["pass_yds"].fillna(0) + pg["rush_yds"].fillna(0)
            pg["pos"] = pg["player_id"].map(infer_roles(pg))
        return pg, tg

    def load(self, asof, verbose: bool = True) -> Dataset:
        asof = pd.Timestamp(asof).normalize()
        y = nfl_season_year(asof)
        if verbose:
            print("  NFL: reading ESPN schedule", file=sys.stderr)
        done = [g for g in self.season_games(y, upto=asof) if g["completed"] and g["date"] is not None
                and g["date"] < asof]
        pg, tg = self._games_frames(done, verbose, "this season")
        prior = []
        for w in range(19 - self.prior_weeks, 19):
            try:
                prior += [g for g in self._events(self._week(y - 1, w, ttl=None)) if g["completed"]]
            except RuntimeError:
                pass
        ppg, ptg = self._games_frames(prior, verbose, "last season (one-time download)")
        pp = (ppg.groupby("player_id").agg(player=("player", "last"), pos=("pos", "last"), games=("game_id", "count"),
                                           **{c: (c, "sum") for c in PLAYER_COLS}).reset_index() if len(ppg)
              else pd.DataFrame())
        tp = (ptg.groupby("team")[["pf", "pa", "pass_att", "rush_att", "pass_yds", "rush_yds", "opp_pass_att",
                                   "opp_rush_att", "opp_pass_yds", "opp_rush_yds"]].mean().reset_index()
              if len(ptg) else pd.DataFrame())
        return Dataset("nfl", pg, tg, pd.DataFrame(), pp, tp)


def infer_roles(pg: pd.DataFrame) -> dict:
    """ESPN box scores don't carry positions, so infer QB / RB / WR (WR includes TE) from usage."""
    s = pg.groupby("player_id")[["pass_att", "rush_att", "targets"]].sum()
    roles = {}
    for pid, r in s.iterrows():
        if r.pass_att >= 8 and r.pass_att >= r.rush_att:
            roles[pid] = "QB"
        elif r.rush_att > r.targets:
            roles[pid] = "RB"
        else:
            roles[pid] = "WR"
    return roles
