"""Live NHL data from the public NHL APIs (api-web.nhle.com and api.nhle.com/stats/rest).

No key required. Finished games are cached on disk forever, so the first run of a
season takes a few minutes and later runs only fetch new games.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd

from .dataset import Dataset, season_start_year
from .http import CachedClient

BASE = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
SHOT_EVENTS = {"shot-on-goal": "sog", "missed-shot": "miss", "blocked-shot": "block", "goal": "goal"}


def _toi(s) -> float:
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s) / 60.0 if s > 100 else float(s)
    try:
        m, sec = str(s).split(":")[:2]
        return int(m) + int(sec) / 60.0
    except ValueError:
        return 0.0


def _name(obj) -> str:
    if isinstance(obj, dict):
        return obj.get("default") or next(iter(obj.values()), "")
    return obj or ""


class NHLProvider:
    sport = "nhl"

    def __init__(self, cfg: dict):
        g = cfg["general"]
        self.http = CachedClient(os.path.join(g["cache_dir"], "nhl"), delay=g["request_delay"])

    # ------------------------------------------------------------------ schedule
    def _week(self, date: str, ttl):
        return self.http.get_json(f"{BASE}/schedule/{date}", ttl=ttl)

    def slate(self, date) -> pd.DataFrame:
        d = pd.Timestamp(date).strftime("%Y-%m-%d")
        data = self._week(d, ttl=900)
        rows = []
        for day in data.get("gameWeek", []):
            if day.get("date") != d:
                continue
            for g in day.get("games", []):
                if g.get("gameType") != 2:
                    continue
                rows.append({"game_id": g["id"], "date": pd.Timestamp(d), "start_utc": g.get("startTimeUTC"),
                             "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"],
                             "state": g.get("gameState")})
        return pd.DataFrame(rows)

    def finished_games(self, start, end) -> list[dict]:
        out, cur = [], pd.Timestamp(start)
        end = pd.Timestamp(end)
        while cur <= end:
            ttl = None if cur + pd.Timedelta(days=7) < pd.Timestamp.now() - pd.Timedelta(days=2) else 1800
            data = self._week(cur.strftime("%Y-%m-%d"), ttl=ttl)
            for day in data.get("gameWeek", []):
                dd = pd.Timestamp(day["date"])
                if dd > end or dd < pd.Timestamp(start):
                    continue
                for g in day.get("games", []):
                    if g.get("gameType") == 2 and g.get("gameState") in ("OFF", "FINAL"):
                        out.append({"game_id": g["id"], "date": dd})
            nxt = data.get("nextStartDate")
            cur = pd.Timestamp(nxt) if nxt else cur + pd.Timedelta(days=7)
        return out

    # ------------------------------------------------------------------ parsing
    @staticmethod
    def parse_boxscore(box: dict, date) -> tuple[list, list, list]:
        players, goalies, teams = [], [], []
        away, home = box["awayTeam"], box["homeTeam"]
        last = (box.get("gameOutcome") or {}).get("lastPeriodType", "REG")
        pbg = box.get("playerByGameStats", {})
        season = box.get("season")
        sides = (("awayTeam", away, home, False), ("homeTeam", home, away, True))
        for key, me, them, is_home in sides:
            grp = pbg.get(key, {})
            for pos_key in ("forwards", "defense"):
                for p in grp.get(pos_key, []):
                    players.append({
                        "season": season, "game_id": box["id"], "date": date,
                        "player_id": p["playerId"], "player": _name(p.get("name")),
                        "team": me["abbrev"], "opp": them["abbrev"], "home": is_home,
                        "pos": "D" if pos_key == "defense" else "F",
                        "minutes": _toi(p.get("toi")),
                        "goals": p.get("goals", 0) or 0, "assists": p.get("assists", 0) or 0,
                        "points": p.get("points", 0) or 0,
                        "sog": p.get("sog", p.get("shots", 0)) or 0,
                        "hits": p.get("hits", 0) or 0, "blocks": p.get("blockedShots", 0) or 0,
                    })
            for g in grp.get("goalies", []):
                toi = _toi(g.get("toi"))
                sa, sv = g.get("shotsAgainst"), g.get("saves")
                if sa is None and g.get("saveShotsAgainst"):
                    sv, sa = (int(x) for x in str(g["saveShotsAgainst"]).split("/"))
                if not toi:
                    continue
                goalies.append({
                    "game_id": box["id"], "date": date, "player_id": g["playerId"],
                    "player": _name(g.get("name")), "team": me["abbrev"], "opp": them["abbrev"],
                    "home": is_home, "minutes": toi, "sa": sa or 0, "saves": sv or 0,
                    "ga": g.get("goalsAgainst", (sa or 0) - (sv or 0)),
                    "started": bool(g.get("starter", toi >= 30)),
                })
            pf, pa = me.get("score", 0), them.get("score", 0)
            if last == "SO":  # shootout winner is credited 1 goal; remove for strength ratings
                pf_adj = pf - 1 if pf > pa else pf
                pa_adj = pa - 1 if pa > pf else pa
            else:
                pf_adj, pa_adj = pf, pa
            teams.append({"game_id": box["id"], "date": date, "season": season, "team": me["abbrev"],
                          "opp": them["abbrev"], "home": is_home, "pf": pf, "pa": pa,
                          "gf": pf_adj, "ga": pa_adj, "sf": me.get("sog"), "sa": them.get("sog"),
                          "ot": last in ("OT", "SO"), "so": last == "SO"})
        return players, goalies, teams

    @staticmethod
    def parse_pbp(pbp: dict) -> tuple[pd.DataFrame, dict, dict]:
        """Returns shot events, {player_id: full name}, {player_id: ppp}."""
        home_id, away_id = pbp["homeTeam"]["id"], pbp["awayTeam"]["id"]
        abbr = {home_id: pbp["homeTeam"]["abbrev"], away_id: pbp["awayTeam"]["abbrev"]}
        roster = {}
        names = {}
        for r in pbp.get("rosterSpots", []):
            roster[r["playerId"]] = r.get("teamId")
            names[r["playerId"]] = f"{_name(r.get('firstName'))} {_name(r.get('lastName'))}".strip()
        rows, ppp, prev = [], {}, None
        for play in pbp.get("plays", []):
            t = play.get("typeDescKey")
            if t not in SHOT_EVENTS:
                continue
            per = play.get("periodDescriptor", {})
            if per.get("periodType") == "SO":
                continue
            d = play.get("details", {}) or {}
            shooter = d.get("shootingPlayerId") or d.get("scoringPlayerId")
            team_id = roster.get(shooter) or d.get("eventOwnerTeamId")
            sit = str(play.get("situationCode") or "1551").zfill(4)
            a_g, a_s, h_s, h_g = (int(c) for c in sit[:4])
            is_home = team_id == home_id
            own, opp = (h_s, a_s) if is_home else (a_s, h_s)
            opp_goalie = a_g if is_home else h_g
            strength = "PP" if own > opp else ("SH" if own < opp else "EV")
            mm, ss = (play.get("timeInPeriod") or "0:00").split(":")
            secs = (per.get("number", 1) - 1) * 1200 + int(mm) * 60 + int(ss)
            rebound = bool(prev and prev[0] == team_id and 0 <= secs - prev[1] <= 3)
            prev = (team_id, secs)
            rows.append({"game_id": pbp["id"], "team": abbr.get(team_id), "shooter": shooter,
                         "event": SHOT_EVENTS[t], "x": d.get("xCoord"), "y": d.get("yCoord"),
                         "shot_type": d.get("shotType") or "unknown", "rebound": rebound,
                         "strength": strength, "empty_net": opp_goalie == 0, "is_home": is_home})
            if t == "goal" and strength == "PP":
                for pid in (d.get("scoringPlayerId"), d.get("assist1PlayerId"), d.get("assist2PlayerId")):
                    if pid:
                        ppp[pid] = ppp.get(pid, 0) + 1
        return pd.DataFrame(rows), names, ppp

    # ------------------------------------------------------------------ loading
    def load(self, asof, verbose: bool = True) -> Dataset:
        from ..models.xg import XGModel

        asof = pd.Timestamp(asof)
        y = season_start_year(asof)
        games = self.finished_games(pd.Timestamp(f"{y}-09-25"), asof - pd.Timedelta(days=1))
        P, G, T, S, full_names, ppp_rows = [], [], [], [], {}, []
        for i, g in enumerate(games):
            if verbose and (i % 25 == 0 or i == len(games) - 1):
                print(f"  NHL: loading game {i + 1}/{len(games)}", file=sys.stderr)
            box = self.http.get_json(f"{BASE}/gamecenter/{g['game_id']}/boxscore", ttl=None)
            p, gl, t = self.parse_boxscore(box, g["date"])
            P += p; G += gl; T += t
            try:
                pbp = self.http.get_json(f"{BASE}/gamecenter/{g['game_id']}/play-by-play", ttl=None)
                shots, names, ppp = self.parse_pbp(pbp)
                S.append(shots)
                full_names.update(names)
                ppp_rows += [{"game_id": g["game_id"], "player_id": k, "ppp": v} for k, v in ppp.items()]
            except RuntimeError as e:
                print(f"  warn: no play-by-play for {g['game_id']}: {e}", file=sys.stderr)

        pg, gg, tg = pd.DataFrame(P), pd.DataFrame(G), pd.DataFrame(T)
        shots = pd.concat(S, ignore_index=True) if S else pd.DataFrame()
        if len(pg):
            pg["player"] = pg["player_id"].map(full_names).fillna(pg["player"])
            att = (shots.groupby(["game_id", "shooter"]).size().rename("attempts").reset_index()
                   .rename(columns={"shooter": "player_id"})) if len(shots) else pd.DataFrame(
                columns=["game_id", "player_id", "attempts"])
            pg = pg.merge(att, on=["game_id", "player_id"], how="left")
            pg = pg.merge(pd.DataFrame(ppp_rows, columns=["game_id", "player_id", "ppp"]),
                          on=["game_id", "player_id"], how="left")
            pg["attempts"] = pg["attempts"].fillna(pg["sog"]).astype(float)
            pg["ppp"] = pg["ppp"].fillna(0).astype(float)
            pg["sport"] = "nhl"
        if len(gg):
            gg["player"] = gg["player_id"].map(full_names).fillna(gg["player"])
        if len(tg):
            tg = self._add_shot_metrics(tg, shots, XGModel)
        pp, tp = self.priors(y - 1)
        return Dataset("nhl", pg, tg, gg, pp, tp)

    @staticmethod
    def _add_shot_metrics(tg: pd.DataFrame, shots: pd.DataFrame, XGModel) -> pd.DataFrame:
        if not len(shots):
            tg["cf"] = tg["ca"] = tg["xgf"] = tg["xga"] = np.nan
            return tg
        model = XGModel().fit(shots)
        shots = shots.copy()
        shots["xg"] = model.predict(shots)
        no_en = shots[~shots["empty_net"]]
        agg = no_en.groupby(["game_id", "team"]).agg(cf=("event", "size"), xgf=("xg", "sum")).reset_index()
        tg = tg.merge(agg, on=["game_id", "team"], how="left")
        opp = agg.rename(columns={"team": "opp", "cf": "ca", "xgf": "xga"})
        tg = tg.merge(opp, on=["game_id", "opp"], how="left")
        return tg

    def priors(self, prev_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        sid = f"{prev_year}{prev_year + 1}"
        params = {"isAggregate": "true", "isGame": "false", "limit": -1,
                  "cayenneExp": f"seasonId={sid} and gameTypeId=2"}
        try:
            s = pd.DataFrame(self.http.get_json(f"{STATS}/skater/summary", params=params, ttl=None)["data"])
            pp = pd.DataFrame({
                "player_id": s["playerId"], "player": s["skaterFullName"],
                "pos": np.where(s["positionCode"] == "D", "D", "F"), "games": s["gamesPlayed"],
                "minutes": s["timeOnIcePerGame"] * s["gamesPlayed"] / 60.0,
                "goals": s["goals"], "assists": s["assists"], "points": s["points"],
                "sog": s["shots"], "ppp": s.get("ppPoints"),
            })
            try:
                rt = pd.DataFrame(self.http.get_json(f"{STATS}/skater/realtime", params=params, ttl=None)["data"])
                keep = {"playerId": "player_id", "hits": "hits", "blockedShots": "blocks"}
                rt = rt[[c for c in keep if c in rt]].rename(columns=keep)
                pp = pp.merge(rt, on="player_id", how="left")
            except (RuntimeError, KeyError):
                pass
        except (RuntimeError, KeyError) as e:
            print(f"  warn: no NHL player priors ({e})", file=sys.stderr)
            pp = pd.DataFrame()
        try:
            st = self.http.get_json(f"{BASE}/standings/{prev_year + 1}-04-14", ttl=None)["standings"]
            tp = pd.DataFrame([{"team": _name(t["teamAbbrev"]), "gf": t["goalFor"] / t["gamesPlayed"],
                                "ga": t["goalAgainst"] / t["gamesPlayed"]} for t in st if t.get("gamesPlayed")])
        except (RuntimeError, KeyError) as e:
            print(f"  warn: no NHL team priors ({e})", file=sys.stderr)
            tp = pd.DataFrame()
        return pp, tp
