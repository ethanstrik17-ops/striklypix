"""Live NBA data from stats.nba.com (game logs) and the NBA CDN (schedule).

No key required. stats.nba.com sometimes blocks cloud/VPN IPs; run from a home
connection. One call returns every player game of the season, so loads are fast.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

from .dataset import Dataset, add_combos, season_start_year
from .http import CachedClient

STATS = "https://stats.nba.com/stats"
CDN_BOX = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{}.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ESPN_ABBR = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS", "PHO": "PHX",
             "BRK": "BKN", "CHO": "CHA", "NOR": "NOP"}
PRIOR_STATS = ["minutes", "pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "stl", "blk", "tov",
               "oreb", "dreb", "pra", "pr", "pa", "ra"]
SCHEDULE = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}


def season_str(y: int) -> str:
    return f"{y}-{str(y + 1)[-2:]}"


def _rs(data: dict, idx: int = 0) -> pd.DataFrame:
    rs = data["resultSets"][idx] if isinstance(data.get("resultSets"), list) else data["resultSet"]
    return pd.DataFrame(rs["rowSet"], columns=rs["headers"])


def _iso_minutes(v) -> float:
    """'PT34M12.00S' -> 34.2"""
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", str(v or ""))
    if not m:
        return 0.0
    return float(m.group(1) or 0) + float(m.group(2) or 0) / 60.0


def _pos_group(p: str) -> str | None:
    p = (p or "").upper()
    if not p:
        return None
    return "C" if p.startswith("C") else ("G" if p.endswith("G") or p.startswith("G") else "F")


def _minutes(v) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 0.0
    if isinstance(v, str) and ":" in v:
        m, s = v.split(":")[:2]
        return int(m) + int(s) / 60
    return float(v)


class NBAProvider:
    sport = "nba"

    def __init__(self, cfg: dict):
        g = cfg["general"]
        self.http = CachedClient(os.path.join(g["cache_dir"], "nba"), delay=max(g["request_delay"], 0.6),
                                 headers=HEADERS)
        # "cdn" (default): NBA.com's game-page feed, works from almost any connection.
        # "stats": stats.nba.com game logs (faster, but often blocks/hangs for non-browsers).
        # "espn" (default): ESPN's public JSON - works from almost any connection.
        self.source = cfg.get("nba", {}).get("source", "espn")
        self.espn = CachedClient(os.path.join(g["cache_dir"], "nba_espn"), delay=0.25)
        self.prior_games = cfg.get("nba", {}).get("prior_games", 400)
        self.cdn = CachedClient(os.path.join(g["cache_dir"], "nba"), delay=0.15)

    # ------------------------------------------------------------------ schedule
    def slate(self, date) -> pd.DataFrame:
        if self.source == "espn":
            return self._espn_slate(date)
        d = pd.Timestamp(date).strftime("%Y-%m-%d")
        rows = []
        try:
            data = self.http.get_json(SCHEDULE, ttl=6 * 3600)
            for day in data["leagueSchedule"]["gameDates"]:
                for g in day["games"]:
                    gd = (g.get("gameDateEst") or g.get("gameDateTimeEst") or "")[:10]
                    if gd != d or not str(g.get("gameId", "")).startswith("002"):
                        continue  # 002 = regular season (incl. NBA Cup group games)
                    rows.append({"game_id": g["gameId"], "date": pd.Timestamp(d),
                                 "start_utc": g.get("gameDateTimeUTC"),
                                 "home": g["homeTeam"]["teamTricode"], "away": g["awayTeam"]["teamTricode"],
                                 "state": g.get("gameStatus")})
        except (RuntimeError, KeyError) as e:
            print(f"  warn: CDN schedule failed ({e}); trying scoreboard", file=sys.stderr)
            sb = _rs(self.http.get_json(f"{STATS}/scoreboardv2", ttl=900,
                                        params={"GameDate": d, "LeagueID": "00", "DayOffset": 0}))
            for _, g in sb.iterrows():
                code = g["GAMECODE"].split("/")[1]
                rows.append({"game_id": g["GAME_ID"], "date": pd.Timestamp(d), "start_utc": None,
                             "home": code[3:6], "away": code[:3], "state": g.get("GAME_STATUS_ID")})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ logs
    def _gamelog(self, y: int, kind: str, ttl) -> pd.DataFrame:
        params = {"Counter": 0, "DateFrom": "", "DateTo": "", "Direction": "ASC", "LeagueID": "00",
                  "PlayerOrTeam": kind, "Season": season_str(y), "SeasonType": "Regular Season",
                  "Sorter": "DATE"}
        return _rs(self.http.get_json(f"{STATS}/leaguegamelog", params=params, ttl=ttl))

    def _positions(self, y: int) -> dict:
        try:
            df = _rs(self.http.get_json(f"{STATS}/playerindex", ttl=7 * 86400,
                                        params={"LeagueID": "00", "Season": season_str(y), "Historical": 1}))
            return {r.PERSON_ID: (str(r.POSITION or "F")[:1] or "F") for r in df.itertuples()}
        except (RuntimeError, KeyError, IndexError) as e:
            print(f"  warn: no NBA positions ({e})", file=sys.stderr)
            return {}

    @staticmethod
    def normalize_player_log(df: pd.DataFrame, pos: dict) -> pd.DataFrame:
        out = pd.DataFrame({
            "sport": "nba", "season": df["SEASON_ID"], "game_id": df["GAME_ID"],
            "date": pd.to_datetime(df["GAME_DATE"]), "player_id": df["PLAYER_ID"],
            "player": df["PLAYER_NAME"], "team": df["TEAM_ABBREVIATION"],
            "opp": df["MATCHUP"].str.split().str[-1], "home": df["MATCHUP"].str.contains("vs."),
            "minutes": df["MIN"].map(_minutes),
        })
        cols = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "fg3m", "FGA": "fga", "FG3A": "fg3a",
                "FTA": "fta", "STL": "stl", "BLK": "blk", "TOV": "tov", "OREB": "oreb", "DREB": "dreb"}
        for k, v in cols.items():
            out[v] = pd.to_numeric(df[k], errors="coerce").fillna(0).astype(float)
        out["pos"] = out["player_id"].map(pos).fillna("F")
        return add_combos(out, "nba")

    @staticmethod
    def normalize_team_log(df: pd.DataFrame) -> pd.DataFrame:
        t = pd.DataFrame({
            "game_id": df["GAME_ID"], "date": pd.to_datetime(df["GAME_DATE"]), "season": df["SEASON_ID"],
            "team": df["TEAM_ABBREVIATION"], "opp": df["MATCHUP"].str.split().str[-1],
            "home": df["MATCHUP"].str.contains("vs."), "pf": df["PTS"].astype(float),
            "min": df["MIN"].map(_minutes),
            "est_poss": (df["FGA"] - df["OREB"] + df["TOV"] + 0.44 * df["FTA"]).astype(float),
        })
        opp = t[["game_id", "team", "pf", "est_poss"]].rename(
            columns={"team": "opp", "pf": "pa", "est_poss": "opp_poss"})
        t = t.merge(opp, on=["game_id", "opp"], how="left")
        t["poss"] = (t["est_poss"] + t["opp_poss"]) / 2
        t["min"] = t["min"].where(t["min"] > 200, 240.0)
        t["pace"] = t["poss"] * 240.0 / t["min"]          # possessions per 48 minutes
        t["ot"] = t["min"] > 241
        return t.drop(columns=["est_poss", "opp_poss"])

    # ------------------------------------------------------------------ ESPN (default) source
    @staticmethod
    def _espn_team(t: dict) -> str | None:
        from .names import team_abbr
        ab = team_abbr("nba", t.get("displayName") or "") if t.get("displayName") else None
        if not ab:
            raw = str(t.get("abbreviation", "")).upper()
            ab = ESPN_ABBR.get(raw, raw)
        return ab

    def _espn_day(self, d: pd.Timestamp) -> list[dict]:
        past = d < pd.Timestamp.today().normalize() - pd.Timedelta(days=2)
        data = self.espn.get_json(f"{ESPN}/scoreboard", params={"dates": d.strftime("%Y%m%d"), "limit": 100},
                                  ttl=None if past else 600)
        out = []
        for ev in data.get("events", []):
            if (ev.get("season") or {}).get("type", 2) != 2:
                continue  # 1 = preseason, 3 = playoffs
            comp = ev["competitions"][0]
            teams = {c["homeAway"]: self._espn_team(c["team"]) for c in comp["competitors"]}
            st = (comp.get("status") or ev.get("status") or {}).get("type", {})
            out.append({"game_id": str(ev["id"]), "date": d, "start_utc": ev.get("date"),
                        "home": teams.get("home"), "away": teams.get("away"),
                        "state": st.get("state"), "completed": bool(st.get("completed")), "_comp": comp})
        return out

    def _espn_slate(self, date) -> pd.DataFrame:
        from .espn import parse_odds
        rows = [r for r in self._espn_day(pd.Timestamp(date).normalize()) if not r["completed"]]
        from .espn import game_meta
        self._odds, self.line_moves = [], {}
        self.game_meta = {r["game_id"]: game_meta("nba", r["_comp"]) for r in rows if r.get("_comp")}
        for r in rows:
            if r.get("state") == "pre":
                o, mv = parse_odds("nba", r["game_id"], r["_comp"], r["start_utc"])
                self._odds += o
                if mv:
                    self.line_moves[(mv["home"], mv["away"])] = mv
        return pd.DataFrame(rows, columns=["game_id", "date", "start_utc", "home", "away", "state"])

    def espn_game_odds(self) -> list[dict]:
        return list(getattr(self, "_odds", []))

    def injuries(self) -> pd.DataFrame:
        from .espn import parse_injuries
        try:
            return parse_injuries("nba", self.espn.get_json(f"{ESPN}/injuries", ttl=1800))
        except (RuntimeError, KeyError) as e:
            print(f"  warn: NBA injury report unavailable ({e})", file=sys.stderr)
            return pd.DataFrame()

    @classmethod
    def parse_espn_summary(cls, data: dict, date) -> tuple[list, list]:
        comp = data["header"]["competitions"][0]
        gid = str(data["header"].get("id") or comp.get("id"))
        side = {}
        for c in comp["competitors"]:
            side[c["homeAway"]] = (cls._espn_team(c["team"]), float(c.get("score") or 0))
        period = int((comp.get("status") or {}).get("period") or 4)
        team_min = 240.0 + 25.0 * max(0, period - 4)
        home_ab = side["home"][0]
        opp_of = {side["home"][0]: side["away"][0], side["away"][0]: side["home"][0]}
        score = {side["home"][0]: side["home"][1], side["away"][0]: side["away"][1]}
        players, teams = [], []

        def split(v):
            try:
                a, b = str(v).split("-")[:2]
                return float(a), float(b)
            except ValueError:
                return 0.0, 0.0

        def num(v):
            try:
                return float(str(v).replace("+", ""))
            except ValueError:
                return 0.0

        for tb in data.get("boxscore", {}).get("players", []):
            team = cls._espn_team(tb["team"])
            if team not in opp_of:
                continue
            for block in tb.get("statistics", []):
                keys = block.get("keys") or block.get("names") or block.get("labels") or []
                keys = [str(k) for k in keys]
                for a in block.get("athletes", []):
                    if a.get("didNotPlay") or not a.get("stats"):
                        continue
                    st = dict(zip(keys, a["stats"]))
                    get = lambda *names: next((st[n] for n in names if n in st), "0")
                    mins = num(get("minutes", "MIN"))
                    if mins <= 0:
                        continue
                    _, fga = split(get("fieldGoalsMade-fieldGoalsAttempted", "FG"))
                    fg3m, fg3a = split(get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "3PT"))
                    _, fta = split(get("freeThrowsMade-freeThrowsAttempted", "FT"))
                    ath = a.get("athlete", {})
                    players.append({
                        "sport": "nba", "season": "espn", "game_id": gid, "date": date,
                        "player_id": str(ath.get("id")), "player": ath.get("displayName") or ath.get("shortName"),
                        "team": team, "opp": opp_of[team], "home": team == home_ab, "minutes": mins,
                        "_pos": _pos_group((ath.get("position") or {}).get("abbreviation")),
                        "pts": num(get("points", "PTS")), "reb": num(get("rebounds", "totalRebounds", "REB")),
                        "ast": num(get("assists", "AST")), "fg3m": fg3m, "fga": fga, "fg3a": fg3a, "fta": fta,
                        "stl": num(get("steals", "STL")), "blk": num(get("blocks", "BLK")),
                        "tov": num(get("turnovers", "TO")), "oreb": num(get("offensiveRebounds", "OREB")),
                        "dreb": num(get("defensiveRebounds", "DREB")),
                    })
        for tb in data.get("boxscore", {}).get("teams", []):
            team = cls._espn_team(tb["team"])
            if team not in opp_of:
                continue
            ts = {x.get("name"): x.get("displayValue") for x in tb.get("statistics", [])}
            _, fga = split(ts.get("fieldGoalsMade-fieldGoalsAttempted", "0-0"))
            _, fta = split(ts.get("freeThrowsMade-freeThrowsAttempted", "0-0"))
            tov = num(ts.get("totalTurnovers") or ts.get("turnovers") or 0)
            teams.append({"GAME_ID": gid, "GAME_DATE": date, "SEASON_ID": "espn", "TEAM_ABBREVIATION": team,
                          "MATCHUP": f"{team} {'vs.' if team == home_ab else '@'} {opp_of[team]}",
                          "PTS": score[team], "MIN": team_min, "FGA": fga,
                          "OREB": num(ts.get("offensiveRebounds", 0)), "TOV": tov, "FTA": fta})
        return players, teams

    def _espn_games(self, games: list[dict], verbose: bool, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        P, T = [], []
        for i, g in enumerate(games):
            if verbose and (i % 25 == 0 or i == len(games) - 1):
                print(f"  NBA {label}: game {i + 1}/{len(games)}", file=sys.stderr)
            try:
                data = self.espn.get_json(f"{ESPN}/summary", params={"event": g["game_id"]}, ttl=None,
                                          retries=2, timeout=20)
                p, t = self.parse_espn_summary(data, pd.Timestamp(g["date"]))
            except (RuntimeError, KeyError, IndexError, TypeError) as e:
                print(f"  warn: skipped game {g['game_id']} ({str(e)[:80]})", file=sys.stderr)
                continue
            P += p; T += t
        pg = pd.DataFrame(P)
        if len(pg):
            pos = pg.dropna(subset=["_pos"]).groupby("player_id")["_pos"].agg(lambda x: x.mode().iloc[0])
            pg["pos"] = pg["player_id"].map(pos).fillna("F")
            pg = add_combos(pg.drop(columns=["_pos"]), "nba")
        tg = self.normalize_team_log(pd.DataFrame(T)) if T else pd.DataFrame()
        if len(tg):
            tg = tg[tg["pa"].notna()]
        return pg, tg

    def _load_espn(self, asof, verbose) -> Dataset:
        y = season_start_year(asof)
        if verbose:
            print("  NBA: reading ESPN schedule", file=sys.stderr)
        done = []
        for d in pd.date_range(f"{y}-10-01", asof - pd.Timedelta(days=1)):
            done += [g for g in self._espn_day(d) if g["completed"]]
        pg, tg = self._espn_games(done, verbose, "this season")
        # prior: last season's final N regular-season games, walking back from late April
        n, prior, d = int(self.prior_games), [], pd.Timestamp(f"{y}-04-20")
        while len(prior) < n and d > pd.Timestamp(f"{y - 1}-10-15"):
            prior += [g for g in self._espn_day(d) if g["completed"]]
            d -= pd.Timedelta(days=1)
        ppg, ptg = self._espn_games(prior[:n], verbose, "last season (one-time download)")
        pp, tp = self._summarise_prior(ppg, ptg)
        return Dataset("nba", pg, tg, pd.DataFrame(), pp, tp).before(asof)

    # ------------------------------------------------------------------ CDN source
    @staticmethod
    def parse_cdn_box(data: dict, date) -> tuple[list, list]:
        g = data["game"]
        gid = g["gameId"]
        period = int(g.get("period") or 4)
        team_min = 240.0 + 25.0 * max(0, period - 4)
        players, teams = [], []
        sides = ((g["homeTeam"], g["awayTeam"], True), (g["awayTeam"], g["homeTeam"], False))
        for me, them, is_home in sides:
            for p in me.get("players", []):
                st = p.get("statistics") or {}
                mins = _iso_minutes(st.get("minutes"))
                if str(p.get("played", "1")) != "1" or mins <= 0:
                    continue
                players.append({
                    "sport": "nba", "season": gid[3:5], "game_id": gid, "date": date,
                    "player_id": p["personId"],
                    "player": p.get("name") or f"{p.get('firstName', '')} {p.get('familyName', '')}".strip(),
                    "team": me["teamTricode"], "opp": them["teamTricode"], "home": is_home,
                    "minutes": mins, "_pos": _pos_group(p.get("position")),
                    "pts": st.get("points", 0), "reb": st.get("reboundsTotal", 0), "ast": st.get("assists", 0),
                    "fg3m": st.get("threePointersMade", 0), "fga": st.get("fieldGoalsAttempted", 0),
                    "fg3a": st.get("threePointersAttempted", 0), "fta": st.get("freeThrowsAttempted", 0),
                    "stl": st.get("steals", 0), "blk": st.get("blocks", 0), "tov": st.get("turnovers", 0),
                    "oreb": st.get("reboundsOffensive", 0), "dreb": st.get("reboundsDefensive", 0),
                })
            ts = me.get("statistics") or {}
            teams.append({
                "GAME_ID": gid, "GAME_DATE": date, "SEASON_ID": gid[3:5], "TEAM_ABBREVIATION": me["teamTricode"],
                "MATCHUP": f"{me['teamTricode']} {'vs.' if is_home else '@'} {them['teamTricode']}",
                "PTS": float(me.get("score", ts.get("points", 0)) or 0), "MIN": team_min,
                "FGA": float(ts.get("fieldGoalsAttempted", 0)), "OREB": float(ts.get("reboundsOffensive", 0)),
                "TOV": float(ts.get("turnoversTotal", ts.get("turnovers", 0))),
                "FTA": float(ts.get("freeThrowsAttempted", 0)),
            })
        return players, teams

    def _cdn_games(self, ids_dates: list, verbose: bool, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        P, T = [], []
        for i, (gid, date) in enumerate(ids_dates):
            if verbose and (i % 50 == 0 or i == len(ids_dates) - 1):
                print(f"  NBA {label}: game {i + 1}/{len(ids_dates)}", file=sys.stderr)
            try:
                data = self.cdn.get_json(CDN_BOX.format(gid), ttl=None, retries=2, timeout=20)
            except RuntimeError:
                continue  # not available (postponed etc.)
            if date is None:
                date = pd.Timestamp(str(data["game"].get("gameEt") or data["game"]["gameTimeUTC"])[:10])
            p, t = self.parse_cdn_box(data, pd.Timestamp(date))
            P += p; T += t
        pg = pd.DataFrame(P)
        if len(pg):
            for c in ["pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "stl", "blk", "tov", "oreb", "dreb"]:
                pg[c] = pd.to_numeric(pg[c], errors="coerce").fillna(0).astype(float)
            pos = pg.dropna(subset=["_pos"]).groupby("player_id")["_pos"].agg(lambda x: x.mode().iloc[0])
            pg["pos"] = pg["player_id"].map(pos).fillna("F")
            pg = add_combos(pg.drop(columns=["_pos"]), "nba")
        tg = self.normalize_team_log(pd.DataFrame(T)) if T else pd.DataFrame()
        return pg, tg

    def _load_cdn(self, asof, verbose) -> Dataset:
        y = season_start_year(asof)
        sched = self.http.get_json(SCHEDULE, ttl=3 * 3600)
        done = []
        for day in sched["leagueSchedule"]["gameDates"]:
            for g in day["games"]:
                d = (g.get("gameDateEst") or "")[:10]
                if str(g.get("gameId", "")).startswith("002") and g.get("gameStatus") == 3 and d \
                        and pd.Timestamp(d) < asof:
                    done.append((g["gameId"], d))
        pg, tg = self._cdn_games(done, verbose, "this season")
        # last season's final N games as the prior (regular-season ids are sequential 1..1230)
        yy = str(y - 1)[-2:]
        n = int(self.prior_games)
        ids = [(f"002{yy}{k:05d}", None) for k in range(max(1, 1231 - n), 1231)]
        ppg, ptg = self._cdn_games(ids, verbose, "last season (one-time download)")
        pp, tp = self._summarise_prior(ppg, ptg)
        return Dataset("nba", pg, tg, pd.DataFrame(), pp, tp).before(asof)

    @staticmethod
    def _summarise_prior(prev: pd.DataFrame, t: pd.DataFrame):
        if not len(prev) or not len(t):
            return pd.DataFrame(), pd.DataFrame()
        pp = prev.groupby("player_id").agg(player=("player", "last"), pos=("pos", "last"),
                                           games=("game_id", "count"),
                                           **{s: (s, "sum") for s in PRIOR_STATS}).reset_index()
        tp = t.groupby("team").agg(pf=("pf", "sum"), pa=("pa", "sum"), poss=("poss", "sum"),
                                   pace=("pace", "mean")).reset_index()
        tp["ortg"] = 100 * tp["pf"] / tp["poss"]
        tp["drtg"] = 100 * tp["pa"] / tp["poss"]
        return pp, tp[["team", "ortg", "drtg", "pace"]]

    def load(self, asof, verbose: bool = True) -> Dataset:
        asof = pd.Timestamp(asof)
        if self.source == "espn":
            return self._load_espn(asof, verbose)
        if self.source == "cdn":
            return self._load_cdn(asof, verbose)
        y = season_start_year(asof)
        if verbose:
            print("  NBA: loading game logs", file=sys.stderr)
        pos = self._positions(y)
        try:
            pg = self.normalize_player_log(self._gamelog(y, "P", ttl=3 * 3600), pos)
            tg = self.normalize_team_log(self._gamelog(y, "T", ttl=3 * 3600))
        except (RuntimeError, KeyError) as e:
            print(f"  warn: no current-season logs yet ({e})", file=sys.stderr)
            pg, tg = pd.DataFrame(), pd.DataFrame()
        pp, tp = self.priors(y - 1, pos)
        ds = Dataset("nba", pg, tg, pd.DataFrame(), pp, tp)
        return ds.before(asof)

    def priors(self, y: int, pos: dict):
        try:
            prev = self.normalize_player_log(self._gamelog(y, "P", ttl=None), pos)
            stats = ["minutes", "pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "stl", "blk", "tov",
                     "oreb", "dreb", "pra", "pr", "pa", "ra"]
            pp = prev.groupby("player_id").agg(player=("player", "last"), pos=("pos", "last"),
                                               games=("game_id", "count"),
                                               **{s: (s, "sum") for s in stats}).reset_index()
            t = self.normalize_team_log(self._gamelog(y, "T", ttl=None))
            tp = t.groupby("team").agg(pf=("pf", "sum"), pa=("pa", "sum"), poss=("poss", "sum"),
                                       pace=("pace", "mean")).reset_index()
            tp["ortg"] = 100 * tp["pf"] / tp["poss"]
            tp["drtg"] = 100 * tp["pa"] / tp["poss"]
            return pp, tp[["team", "ortg", "drtg", "pace"]]
        except (RuntimeError, KeyError) as e:
            print(f"  warn: no NBA priors ({e})", file=sys.stderr)
            return pd.DataFrame(), pd.DataFrame()
