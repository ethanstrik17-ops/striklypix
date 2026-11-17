"""Offline tests: math, parsers (with API-shaped fixtures) and full pipelines with mocked HTTP."""
import numpy as np
import pandas as pd
import pytest

from sportsedge import pipeline
from sportsedge.config import load_config
from sportsedge.data.names import PlayerMatcher, team_abbr
from sportsedge.data.odds import OddsClient, to_american, to_decimal
from sportsedge.models.dist import nb_probs
from sportsedge.value import devig_power, evaluate, market_table


# ------------------------------------------------------------------ math
def test_nb_probs_sum_to_one_and_push():
    o, p, u = nb_probs(2.7, 0.1, 3.0)
    assert abs(o + p + u - 1) < 1e-9 and p > 0
    from scipy.stats import poisson
    o, p, u = nb_probs(2.7, 0.0, 2.5)
    assert p == 0 and o == pytest.approx(1 - poisson.cdf(2, 2.7))


def test_devig_and_odds():
    assert to_decimal(-110) == pytest.approx(1.9091, 1e-3)
    assert to_decimal(150) == 2.5 and to_american(2.5) == 150 and to_american(1.5) == -200
    a, b = devig_power(1 / 1.91, 1 / 1.91)
    assert a == pytest.approx(0.5) and a + b == pytest.approx(1)
    a, b = devig_power(1 / 1.30, 1 / 3.60)
    assert a + b == pytest.approx(1, abs=1e-6) and a > 0.7


def test_value_evaluate_ev():
    df = pd.DataFrame({"model_win": [0.60], "model_push": [0.0], "market_p": [0.50], "best_price": [2.0]})
    cfg = load_config()["value"]
    out = evaluate(df, 0.5, cfg)
    assert out["final_p"].iloc[0] == pytest.approx(0.55)
    assert out["ev"].iloc[0] == pytest.approx(0.10)
    assert out["flag"].iloc[0] == "BET"


def test_names():
    assert team_abbr("nhl", "Toronto Maple Leafs") == "TOR"
    assert team_abbr("nhl", "Montréal Canadiens") == "MTL"
    assert team_abbr("nba", "LA Clippers") == "LAC"
    m = PlayerMatcher([(1, "Alexis Lafrenière", "NYR"), (2, "Jack Hughes", "NJD"), (3, "Quinn Hughes", "VAN")])
    assert m.match("Alexis Lafreniere") == 1
    assert m.match("J. Hughes") == 2


# ------------------------------------------------------------------ odds parsing
def test_odds_api_parse():
    ev = {"id": "e1", "commence_time": "2026-11-04T00:00:00Z", "home_team": "Boston Bruins",
          "away_team": "Toronto Maple Leafs", "bookmakers": [{"key": "draftkings", "markets": [
              {"key": "h2h", "outcomes": [{"name": "Boston Bruins", "price": 1.95},
                                          {"name": "Toronto Maple Leafs", "price": 1.91}]},
              {"key": "totals", "outcomes": [{"name": "Over", "price": 1.87, "point": 6.5},
                                             {"name": "Under", "price": 1.95, "point": 6.5}]},
              {"key": "player_shots_on_goal", "outcomes": [
                  {"name": "Over", "description": "Auston Matthews", "price": 1.80, "point": 3.5},
                  {"name": "Under", "description": "Auston Matthews", "price": 2.00, "point": 3.5}]}]}]}
    oc = OddsClient(load_config())
    rows = pd.DataFrame(oc._parse_event("nhl", ev))
    assert set(rows["market"]) == {"h2h", "totals", "sog"}
    assert set(rows[rows.market == "h2h"]["name"]) == {"home", "away"}
    mt = market_table(rows, ["pinnacle"])
    sog = mt[(mt.market == "sog") & (mt.name == "Over")].iloc[0]
    assert 0.45 < sog.market_p < 0.55 and sog.player == "Auston Matthews"


# ------------------------------------------------------------------ demo pipelines
@pytest.mark.parametrize("sport", ["nhl", "nba"])
def test_demo_end_to_end(sport):
    cfg = load_config()
    prov = pipeline.get_provider(sport, cfg, demo=True)
    ctx = pipeline.build(sport, "2026-11-03", cfg, prov)
    assert len(ctx.games) == len(ctx.slate) > 0
    assert len(ctx.proj) > 20
    gv = pipeline.game_value(ctx, prov.odds(ctx.date, "games"))
    pv = pipeline.prop_value(ctx, prov.odds(ctx.date, "props"))
    assert len(gv) and len(pv)
    assert gv["final_p"].between(0, 1).all() and pv["final_p"].between(0, 1).all()
    for m in ctx.games.values():
        o, p = m.p_total(5.5 if sport == "nhl" else 220.5)
        assert 0 < o < 1
        h, _ = m.p_ml("home")
        a, _ = m.p_ml("away")
        assert h + a == pytest.approx(1)


def test_injury_override_moves_minutes():
    cfg = load_config()
    prov = pipeline.get_provider("nba", cfg, demo=True)
    base = pipeline.build("nba", "2026-11-03", cfg, prov)
    star = base.proj.sort_values("proj_min", ascending=False).iloc[0]
    ctx = pipeline.build("nba", "2026-11-03", cfg, prov, {"out": [star.player]})
    assert star.player_id not in set(ctx.proj.player_id)
    mates_before = base.proj[(base.proj.team == star.team) & (base.proj.player_id != star.player_id)]["proj_min"].sum()
    mates_after = ctx.proj[ctx.proj.team == star.team]["proj_min"].sum()
    assert mates_after > mates_before
    gid = star.game_id
    side = "home_pts" if ctx.slate.set_index("game_id").loc[gid, "home"] == star.team else "away_pts"
    assert getattr(ctx.games[gid], side) < getattr(base.games[gid], side)


# ------------------------------------------------------------------ live NHL code path, mocked HTTP
def _nhl_fixtures():
    teams = {"TOR": 10, "BOS": 6}
    def skater(pid, name, sog, toi, goals=0, assists=0):
        return {"playerId": pid, "name": {"default": name}, "position": "C", "goals": goals, "assists": assists,
                "points": goals + assists, "sog": sog, "hits": 2, "blockedShots": 1, "toi": toi}
    def box(gid, date, home, away, hs, as_):
        return {"id": gid, "season": 20262027, "gameDate": date,
                "awayTeam": {"abbrev": away, "score": as_, "sog": 30},
                "homeTeam": {"abbrev": home, "score": hs, "sog": 33},
                "gameOutcome": {"lastPeriodType": "REG"},
                "playerByGameStats": {
                    "awayTeam": {"forwards": [skater(100 + i, f"A. Away{i}", 3, "18:00") for i in range(12)],
                                 "defense": [skater(200 + i, f"D. Away{i}", 1, "21:30") for i in range(6)],
                                 "goalies": [{"playerId": 300, "name": {"default": "G. Away"}, "toi": "60:00",
                                              "saveShotsAgainst": "30/33", "starter": True}]},
                    "homeTeam": {"forwards": [skater(400 + i, f"H. Home{i}", 3, "17:00", goals=int(i < 2))
                                              for i in range(12)],
                                 "defense": [skater(500 + i, f"E. Home{i}", 1, "22:00") for i in range(6)],
                                 "goalies": [{"playerId": 600, "name": {"default": "G. Home"}, "toi": "60:00",
                                              "shotsAgainst": 30, "saves": 28, "goalsAgainst": 2, "starter": True}]}}}
    def pbp(gid, home, away):
        roster = ([{"playerId": 100 + i, "teamId": teams[away], "firstName": {"default": "Al"},
                    "lastName": {"default": f"Away{i}"}} for i in range(12)] +
                  [{"playerId": 400 + i, "teamId": teams[home], "firstName": {"default": "Hal"},
                    "lastName": {"default": f"Home{i}"}} for i in range(12)])
        plays = []
        for k in range(40):
            shooter = (400 + k % 12) if k % 2 else (100 + k % 12)
            t = ["shot-on-goal", "missed-shot", "blocked-shot", "goal"][k % 4]
            d = {"shootingPlayerId": shooter, "xCoord": 70 - k % 30, "yCoord": (k % 9) - 4, "shotType": "wrist"}
            if t == "goal":
                d = {"scoringPlayerId": shooter, "assist1PlayerId": shooter + 1, **d}
            plays.append({"typeDescKey": t, "periodDescriptor": {"number": 1 + k // 15, "periodType": "REG"},
                          "timeInPeriod": f"{k % 19:02d}:{(k * 7) % 60:02d}", "situationCode": "1451" if k == 3 else "1551",
                          "details": d})
        return {"id": gid, "homeTeam": {"id": teams[home], "abbrev": home},
                "awayTeam": {"id": teams[away], "abbrev": away}, "rosterSpots": roster, "plays": plays}
    return box, pbp


def test_nhl_live_parsers_with_mock(monkeypatch, tmp_path):
    from sportsedge.data import nhl as nhlmod
    box, pbp = _nhl_fixtures()
    games = {f"2026-10-{d:02d}": 2026020000 + d for d in range(10, 31, 2)}

    def fake_get(self, url, params=None, ttl=None, **kw):
        if "/schedule/" in url:
            day = url.rsplit("/", 1)[1]
            start = pd.Timestamp(day)
            week = []
            for i in range(7):
                d = (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
                gl = []
                if d in games:
                    gl.append({"id": games[d], "gameType": 2, "gameState": "OFF", "startTimeUTC": d + "T23:00:00Z",
                               "homeTeam": {"abbrev": "TOR"}, "awayTeam": {"abbrev": "BOS"}})
                if d == "2026-11-03":
                    gl.append({"id": 2026029999, "gameType": 2, "gameState": "FUT", "startTimeUTC": d + "T23:00:00Z",
                               "homeTeam": {"abbrev": "BOS"}, "awayTeam": {"abbrev": "TOR"}})
                week.append({"date": d, "games": gl})
            return {"gameWeek": week, "nextStartDate": (start + pd.Timedelta(days=7)).strftime("%Y-%m-%d")}
        if url.endswith("/boxscore"):
            gid = int(url.split("/")[-2])
            d = [k for k, v in games.items() if v == gid][0]
            return box(gid, d, "TOR", "BOS", 3, 2)
        if url.endswith("/play-by-play"):
            return pbp(int(url.split("/")[-2]), "TOR", "BOS")
        if "skater/summary" in url:
            return {"data": [{"playerId": 400, "skaterFullName": "Hal Home0", "positionCode": "C", "gamesPlayed": 80,
                              "goals": 30, "assists": 40, "points": 70, "shots": 250, "ppPoints": 20,
                              "timeOnIcePerGame": 1100}]}
        if "skater/realtime" in url:
            return {"data": [{"playerId": 400, "hits": 50, "blockedShots": 30}]}
        if "/standings/" in url:
            return {"standings": [{"teamAbbrev": {"default": "TOR"}, "gamesPlayed": 82, "goalFor": 270, "goalAgainst": 240},
                                  {"teamAbbrev": {"default": "BOS"}, "gamesPlayed": 82, "goalFor": 230, "goalAgainst": 250}]}
        raise AssertionError(url)

    monkeypatch.setattr(nhlmod.CachedClient, "get_json", fake_get)
    cfg = load_config()
    cfg["general"]["cache_dir"] = str(tmp_path)
    prov = nhlmod.NHLProvider(cfg)
    ds = prov.load("2026-11-03", verbose=False)
    assert len(ds.team_games) == 2 * len(games)
    assert ds.player_games["attempts"].sum() > 0 and ds.player_games["ppp"].sum() > 0
    assert ds.team_games["xgf"].notna().all()
    assert ds.player_games.loc[ds.player_games.player_id == 400, "player"].iloc[0] == "Hal Home0"
    ctx = pipeline.build("nhl", "2026-11-03", cfg, prov, ds=ds)
    assert len(ctx.slate) == 1 and len(ctx.proj) >= 30 and len(ctx.goalie_proj) == 2


def test_nba_log_normalisers():
    from sportsedge.data.nba import NBAProvider
    hdr = ["SEASON_ID", "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE", "MATCHUP", "MIN",
           "PTS", "REB", "AST", "FG3M", "FGA", "FG3A", "FTA", "STL", "BLK", "TOV", "OREB", "DREB"]
    rows = [["22026", 1, "Jayson Tatum", "BOS", "0022600001", "2026-10-22", "BOS vs. NYK", 36.5,
             30, 8, 5, 4, 22, 10, 6, 1, 1, 3, 1, 7]]
    p = NBAProvider.normalize_player_log(pd.DataFrame(rows, columns=hdr), {1: "F"})
    assert p.iloc[0]["home"] and p.iloc[0]["opp"] == "NYK" and p.iloc[0]["pra"] == 43
    th = ["SEASON_ID", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE", "MATCHUP", "MIN", "PTS", "FGA", "OREB", "TOV", "FTA"]
    t = pd.DataFrame([["22026", "BOS", "g1", "2026-10-22", "BOS vs. NYK", 240, 115, 88, 10, 12, 20],
                      ["22026", "NYK", "g1", "2026-10-22", "NYK @ BOS", 240, 108, 90, 12, 14, 18]], columns=th)
    tg = NBAProvider.normalize_team_log(t)
    assert tg.set_index("team").loc["BOS", "pa"] == 108 and 90 < tg["poss"].iloc[0] < 110


def test_nba_slate_cdn(monkeypatch, tmp_path):
    from sportsedge.data import nba as nbamod
    data = {"leagueSchedule": {"gameDates": [{"gameDate": "11/03/2026 00:00:00", "games": [
        {"gameId": "0022600050", "gameDateEst": "2026-11-03T00:00:00Z", "gameDateTimeUTC": "2026-11-04T00:00:00Z",
         "homeTeam": {"teamTricode": "TOR"}, "awayTeam": {"teamTricode": "BOS"}, "gameStatus": 1},
        {"gameId": "0012600001", "gameDateEst": "2026-11-03T00:00:00Z", "gameDateTimeUTC": "2026-11-04T00:00:00Z",
         "homeTeam": {"teamTricode": "LAL"}, "awayTeam": {"teamTricode": "GSW"}, "gameStatus": 1}]}]}}
    monkeypatch.setattr(nbamod.CachedClient, "get_json", lambda self, url, **kw: data)
    cfg = load_config()
    cfg["general"]["cache_dir"] = str(tmp_path)
    cfg["nba"]["source"] = "cdn"
    s = nbamod.NBAProvider(cfg).slate("2026-11-03")
    assert list(s["home"]) == ["TOR"]  # preseason game id 001... filtered out


def test_clv_from_snapshot(tmp_path):
    from sportsedge import ledger
    snap = tmp_path / "odds_snapshots"
    snap.mkdir()
    rows = pd.DataFrame([
        {"event_id": "e1", "commence": "2026-11-04T00:00:00Z", "home": "BOS", "away": "TOR", "book": "pinnacle",
         "market": "totals", "name": n, "player": None, "point": 6.5, "price": p}
        for n, p in (("Over", 1.80), ("Under", 2.05))])
    rows.to_csv(snap / "nhl_games_20261103T230000.csv", index=False)
    row = pd.Series({"sport": "nhl", "commence": "2026-11-04T00:00:00Z", "event_id": "e1", "market": "totals",
                     "player": np.nan, "name": "Over", "point": 6.5})
    p = ledger._closing(row, str(snap), ["pinnacle"])
    assert 0.52 < p < 0.56


def test_nba_cdn_source(monkeypatch, tmp_path):
    from sportsedge.data import nba as nbamod

    def team(tri, score, base_id):
        players = [{"personId": base_id + i, "name": f"{tri} Player{i}", "position": ["PG", "SG", "SF", "PF", "C"][i] if i < 5 else "",
                    "played": "1", "statistics": {"minutes": f"PT{30 - i}M12.00S", "points": 20 - i, "reboundsTotal": 5,
                                                  "reboundsOffensive": 1, "reboundsDefensive": 4, "assists": 4, "steals": 1,
                                                  "blocks": 0, "turnovers": 2, "fieldGoalsAttempted": 15, "threePointersMade": 2,
                                                  "threePointersAttempted": 6, "freeThrowsAttempted": 4}}
                   for i in range(9)]
        players.append({"personId": base_id + 99, "name": "DNP Guy", "played": "0", "statistics": {"minutes": ""}})
        return {"teamTricode": tri, "score": score, "players": players,
                "statistics": {"fieldGoalsAttempted": 88, "reboundsOffensive": 10, "turnoversTotal": 13,
                               "freeThrowsAttempted": 22, "points": score}}

    sched_games = []
    for k in range(1, 9):
        sched_games.append({"gameId": f"00226{k:05d}", "gameDateEst": f"2026-10-{20 + k}T00:00:00Z", "gameStatus": 3,
                            "homeTeam": {"teamTricode": "BOS"}, "awayTeam": {"teamTricode": "NYK"}})
    sched_games.append({"gameId": "0022600100", "gameDateEst": "2026-11-08T00:00:00Z", "gameStatus": 1,
                        "gameDateTimeUTC": "2026-11-09T00:30:00Z",
                        "homeTeam": {"teamTricode": "NYK"}, "awayTeam": {"teamTricode": "BOS"}})

    def fake_get(self, url, params=None, ttl=None, **kw):
        if url.endswith("/injuries"):
            return {"injuries": []}
        if "scheduleLeagueV2" in url:
            return {"leagueSchedule": {"gameDates": [{"games": sched_games}]}}
        if "boxscore_" in url:
            gid = url.split("_")[-1].split(".")[0]
            if gid.startswith("00225") and int(gid[-5:]) % 7 == 0:
                raise RuntimeError("403")
            return {"game": {"gameId": gid, "period": 5 if gid.endswith("3") else 4, "gameTimeUTC": "2026-04-01T23:00:00Z",
                             "homeTeam": team("BOS", 112, 1000), "awayTeam": team("NYK", 105, 2000)}}
        raise AssertionError(url)

    monkeypatch.setattr(nbamod.CachedClient, "get_json", fake_get)
    cfg = load_config()
    cfg["general"]["cache_dir"] = str(tmp_path)
    cfg["nba"]["prior_games"] = 30
    cfg["nba"]["source"] = "cdn"
    prov = nbamod.NBAProvider(cfg)
    ds = prov.load("2026-11-08", verbose=False)
    assert len(ds.team_games) == 16 and ds.team_games["ot"].sum() == 2
    assert len(ds.player_games) == 8 * 18
    assert ds.player_games.loc[ds.player_games.player_id == 1004, "pos"].iloc[0] == "C"
    assert ds.player_games["minutes"].iloc[0] == pytest.approx(30.2)
    assert len(ds.player_prior) == 18 and len(ds.team_prior) == 2
    ctx = pipeline.build("nba", "2026-11-08", cfg, prov, ds=ds)
    assert len(ctx.games) == 1 and len(ctx.proj) >= 14


def test_nba_espn_source(monkeypatch, tmp_path):
    from sportsedge.data import nba as nbamod
    keys = ["minutes", "fieldGoalsMade-fieldGoalsAttempted", "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
            "freeThrowsMade-freeThrowsAttempted", "offensiveRebounds", "defensiveRebounds", "rebounds", "assists",
            "steals", "blocks", "turnovers", "fouls", "plusMinus", "points"]

    def tbox(abbr, name, base):
        ath = [{"athlete": {"id": str(base + i), "displayName": f"{abbr} Guy{i}",
                            "position": {"abbreviation": ["PG", "SG", "SF", "PF", "C", "G", "F", "C", "G"][i]}},
                "starter": i < 5, "didNotPlay": False,
                "stats": [str(32 - i), "8-15", "2-6", "4-4", "1", "5", "6", "4", "1", "0", "2", "3", "+5", str(22 - i)]}
               for i in range(9)]
        ath.append({"athlete": {"id": str(base + 99), "displayName": "Bench Guy"}, "didNotPlay": True, "stats": []})
        return {"team": {"abbreviation": abbr, "displayName": name}, "statistics": [{"keys": keys, "athletes": ath}]}

    def tstats(abbr, name):
        return {"team": {"abbreviation": abbr, "displayName": name}, "statistics": [
            {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "42-88"},
            {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "18-22"},
            {"name": "offensiveRebounds", "displayValue": "10"}, {"name": "totalTurnovers", "displayValue": "13"}]}

    def summary(eid):
        return {"header": {"id": eid, "competitions": [{"status": {"period": 4}, "competitors": [
                    {"homeAway": "home", "score": "112", "team": {"abbreviation": "GS", "displayName": "Golden State Warriors"}},
                    {"homeAway": "away", "score": "104", "team": {"abbreviation": "NY", "displayName": "New York Knicks"}}]}]},
                "boxscore": {"players": [tbox("GS", "Golden State Warriors", 1000), tbox("NY", "New York Knicks", 2000)],
                             "teams": [tstats("GS", "Golden State Warriors"), tstats("NY", "New York Knicks")]}}

    def event(eid, completed, typ=2):
        return {"id": eid, "date": "2026-11-09T00:30Z", "season": {"type": typ},
                "competitions": [{"status": {"type": {"completed": completed, "state": "post" if completed else "pre"}},
                                  "competitors": [
                                      {"homeAway": "home", "team": {"abbreviation": "GS", "displayName": "Golden State Warriors"}},
                                      {"homeAway": "away", "team": {"abbreviation": "NY", "displayName": "New York Knicks"}}]}]}

    def fake_get(self, url, params=None, ttl=None, **kw):
        if url.endswith("/injuries"):
            return {"injuries": []}
        if url.endswith("/scoreboard"):
            d = params["dates"]
            if d == "20261108":
                return {"events": [event("901", False)]}
            if d.startswith("202610") and d >= "20261021" and int(d[-2:]) % 3 == 0:
                return {"events": [event(f"8{d}", True)]}
            if d.startswith("202604") and d <= "20260412":
                return {"events": [event(f"7{d}", True), event(f"6{d}", True)]}
            if d == "20261005":
                return {"events": [event("pre1", True, typ=1)]}
            return {"events": []}
        if url.endswith("/summary"):
            return summary(params["event"])
        raise AssertionError(url)

    monkeypatch.setattr(nbamod.CachedClient, "get_json", fake_get)
    cfg = load_config()
    cfg["general"]["cache_dir"] = str(tmp_path)
    cfg["nba"]["prior_games"] = 20
    prov = nbamod.NBAProvider(cfg)
    sl = prov.slate("2026-11-08")
    assert list(sl["home"]) == ["GSW"] and list(sl["away"]) == ["NYK"]
    ds = prov.load("2026-11-08", verbose=False)
    assert ds.team_games["team"].isin(["GSW", "NYK"]).all() and len(ds.team_games) == 2 * 4
    pg = ds.player_games
    assert len(pg) == 4 * 18 and pg["fga"].iloc[0] == 15 and pg["fg3m"].iloc[0] == 2
    assert pg.loc[pg.player_id == "1004", "pos"].iloc[0] == "C"
    assert len(ds.player_prior) == 18 and set(ds.team_prior["team"]) == {"GSW", "NYK"}
    ctx = pipeline.build("nba", "2026-11-08", cfg, prov, ds=ds)
    assert len(ctx.games) == 1 and len(ctx.proj) >= 14


def test_my_books_limits_best_price():
    rows = []
    for book, o, u in (("pinnacle", 1.95, 1.95), ("fanduel", 1.83, 2.00), ("betmgm", 2.10, 1.75)):
        for n, p in (("Over", o), ("Under", u)):
            rows.append({"event_id": "e", "commence": None, "home": "BOS", "away": "NYK", "book": book, "market": "pts",
                         "name": n, "player": "X Y", "point": 20.5, "price": p})
    df = pd.DataFrame(rows)
    allb = market_table(df, ["pinnacle"]).set_index("name")
    mine = market_table(df, ["pinnacle"], ["fanduel", "bet99"]).set_index("name")
    assert allb.loc["Over", "best_book"] == "betmgm" and mine.loc["Over", "best_book"] == "fanduel"
    assert mine.loc["Over", "market_p"] == pytest.approx(0.5) and mine.loc["Over", "market_src"] == "sharp"


@pytest.mark.parametrize("sport", ["nba", "nhl"])
def test_daily_card_and_parlays(sport):
    from sportsedge import card as cardmod
    cfg = load_config()
    prov = pipeline.get_provider(sport, cfg, demo=True)
    ctx = pipeline.build(sport, "2026-11-08", cfg, prov)
    gv = pipeline.game_value(ctx, prov.odds(ctx.date, "games"))
    pv = pipeline.prop_value(ctx, prov.odds(ctx.date, "props"))
    card = cardmod.unify(ctx, gv, pv)
    assert {"Prop", "Moneyline", "Total"} <= set(card["type"])
    assert set(card["flag"]) <= {"BET", "CHECK NEWS", "lean", ""}
    parlays = cardmod.build_parlays(card, cfg["value"])
    for p in parlays:
        games = [l["game"] for l in p["legs"]]
        assert len(set(games)) == len(games)            # never two legs from one game
        assert p["ev"] > 0 and p["stake_pct"] <= cfg["value"]["max_parlay_stake_pct"]
    lists = cardmod.select_lists(card)
    assert len(lists["best"]) <= 10 and (lists["best"]["ev"] > 0).all()
    assert (lists["props"]["type"] == "Prop").all() and lists["props"]["player"].is_unique
    assert lists["best"].groupby("game").size().max() <= 2
    assert not (lists["best"]["flag"] == "CHECK NEWS").any()
    page = cardmod.render_page(ctx, card, lists, parlays, bankroll=500, demo=True)
    for tab in ("Top 10 Bets", "Top 10 Props", "Long shots", "Streaks &amp; injuries", "Tracker", "Parlays",
                "All picks", "Games", "Players"):
        assert f">{tab}<" in page


def test_site_build_demo(tmp_path):
    from sportsedge.site import build_site
    cfg = load_config("site_config.yaml")
    assert cfg["value"]["min_ev"] == 0.03  # merged with defaults
    cfg["general"]["output_dir"] = str(tmp_path / "data")
    cfg["general"]["picks_file"] = str(tmp_path / "data" / "picks.csv")
    out = tmp_path / "docs"
    build_site(cfg, str(out), "2026-11-10", ["nba", "nhl"], demo=True)
    page = (out / "nba.html").read_text()
    assert "Strikly<span class=px>Pix</span> <span class=sp>NBA</span>" in page and "href='nhl.html'" in page and "href='archive/index.html'" in page
    assert "<span class=sp>NHL</span>" in (out / "nhl.html").read_text()
    arch = (out / "archive" / "nba_2026-11-10.html").read_text()
    assert "href='../nhl.html'" in arch
    assert "nba_2026-11-10.html" in (out / "archive" / "index.html").read_text()
    assert (out / ".nojekyll").exists()


# ------------------------------------------------------------------ NFL (real ESPN samples)
FIX = __import__("pathlib").Path(__file__).parent / "fixtures"


def _nfl_mock(monkeypatch, tmp_path):
    import copy
    import json as _json
    from sportsedge.data import nfl as nflmod
    base = _json.loads((FIX / "nfl_summary_401873052.json").read_text())       # WSH @ NYG, final
    scoreboard = _json.loads((FIX / "nfl_scoreboard.json").read_text())        # week with LAC @ BAL upcoming
    names = {"BAL": "Baltimore Ravens", "LAC": "Los Angeles Chargers", "WSH": "Washington Commanders",
             "NYG": "New York Giants"}

    def summary(gid, home, away, hs, as_):
        d = copy.deepcopy(base)
        swap = {"NYG": home, "WSH": away}
        def fix_team(t):
            ab = swap.get(t.get("abbreviation"), t.get("abbreviation"))
            t["abbreviation"], t["displayName"] = ab, names[ab]
        comp = d["header"]["competitions"][0]
        d["header"]["id"] = gid
        for c in comp["competitors"]:
            fix_team(c["team"])
            c["score"] = str(hs if c["homeAway"] == "home" else as_)
        for tb in d["boxscore"]["players"] + d["boxscore"]["teams"]:
            fix_team(tb["team"])
        for tb in d["boxscore"]["players"]:
            for cat in tb["statistics"]:
                for a in cat["athletes"]:
                    a["athlete"]["id"] = f"{tb['team']['abbreviation']}-{a['athlete']['id']}"
                    a["athlete"]["displayName"] = f"{tb['team']['abbreviation']} {a['athlete']['displayName']}"
        return d

    games = {}
    for w in range(1, 10):
        for k, (h, a) in enumerate((("BAL", "LAC"), ("NYG", "WSH")) if w % 2 else (("LAC", "BAL"), ("WSH", "NYG"))):
            gid = f"9{w:02d}{k}"
            day = pd.Timestamp("2026-09-13") + pd.Timedelta(days=7 * (w - 1))
            games[gid] = (w, h, a, day, 20 + w, 17 + (w % 4))

    def week_events(year, w):
        if year != 2026:
            return []
        evs = []
        for gid, (wk, h, a, day, hs, as_) in games.items():
            if wk == w:
                evs.append({"id": gid, "date": f"{day:%Y-%m-%d}T17:00Z", "season": {"type": 2},
                            "competitions": [{"status": {"type": {"completed": True, "state": "post"}}, "competitors": [
                                {"homeAway": "home", "team": {"abbreviation": h, "displayName": names[h]}},
                                {"homeAway": "away", "team": {"abbreviation": a, "displayName": names[a]}}]}]})
        return evs

    def fake_get(self, url, params=None, ttl=None, **kw):
        if url.endswith("/injuries"):
            return {"injuries": [{"displayName": "Baltimore Ravens", "injuries": [
                {"status": "Out", "shortComment": "out", "date": "2026-11-15T12:00Z",
                 "athlete": {"displayName": "BAL Isaiah Likely", "team": {"abbreviation": "BAL",
                                                                          "displayName": "Baltimore Ravens"}}}]}]}
        if url.endswith("/scoreboard"):
            if not params:
                return scoreboard
            return {"events": week_events(int(params["dates"]), int(params["week"]))}
        if url.endswith("/summary"):
            gid = params["event"]
            w, h, a, day, hs, as_ = games[gid]
            return summary(gid, h, a, hs, as_)
        raise AssertionError(url)

    monkeypatch.setattr(nflmod.CachedClient, "get_json", fake_get)
    cfg = load_config()
    cfg["general"]["cache_dir"] = str(tmp_path)
    return nflmod, cfg


def test_nfl_end_to_end(monkeypatch, tmp_path):
    nflmod, cfg = _nfl_mock(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "_now", lambda: pd.Timestamp("2026-11-16T18:00Z"))
    from sportsedge import card as cardmod
    prov = nflmod.NFLProvider(cfg)
    ds = prov.load("2026-11-16", verbose=False)
    assert len(ds.team_games) == 36 and set(ds.player_games["pos"]) == {"QB", "RB", "WR"}
    ctx = pipeline.build("nfl", "2026-11-16", cfg, prov, ds=ds)
    assert list(zip(ctx.slate.home, ctx.slate.away)) == [("BAL", "LAC")]
    assert "BAL Isaiah Likely" in ctx.overrides["out"]
    proj = ctx.proj
    assert "BAL Isaiah Likely" not in set(proj["player"])            # OUT player removed
    assert (proj["flags"].str.contains("role_bump")).any()          # his targets went to teammates
    qb = proj[proj["pass_att"] > 10]
    assert sorted(qb["team"]) == ["BAL", "LAC"] and qb["pass_yds"].between(120, 350).all()  # one starter each
    m = ctx.games[ctx.slate.game_id.iloc[0]]
    assert 25 < m.total < 60 and abs(m.p_ml("home")[0] + m.p_ml("away")[0] - 1) < 1e-9
    go = pipeline.fetch_odds(ctx, prov, "games", demo=False)
    assert set(go["market"]) == {"h2h", "spreads", "totals"} and set(go["book"]) == {"draftkings"}
    gv = pipeline.game_value(ctx, go)
    assert len(gv) == 6
    wr = proj.sort_values("rec_yds").iloc[-1]
    rows = [{"event_id": "x", "commence": ctx.slate.start_utc.iloc[0], "home": "BAL", "away": "LAC", "book": b,
             "market": "rec_yds", "name": n, "player": wr.player, "point": 55.5, "price": p}
            for b in ("fanduel", "draftkings") for n, p in (("Over", 1.87), ("Under", 1.95))]
    pv = pipeline.prop_value(ctx, pd.DataFrame(rows))
    assert len(pv) == 2 and pv["model_win"].between(0.05, 0.95).all()
    card = cardmod.unify(ctx, gv, pv)
    assert {"Moneyline", "Spread", "Total", "Prop"} <= set(card["type"])


def test_password_protection_roundtrip(tmp_path, monkeypatch):
    from sportsedge.protect import decrypt_bytes, encrypt_bytes, lock_page
    blob = encrypt_bytes(b"date,selection\n2026-11-16,BAL -4.5\n", "pw1")
    assert decrypt_bytes(blob, "pw1").startswith(b"date,selection")
    with pytest.raises(Exception):
        decrypt_bytes(blob, "nope")
    page = lock_page("<html><body>SECRET PICKS</body></html>", "pw1")
    assert "SECRET PICKS" not in page and "crypto.subtle" in page
    from sportsedge.site import build_site
    cfg = load_config("site_config.yaml")
    cfg["general"]["output_dir"] = str(tmp_path / "data")
    cfg["general"]["picks_file"] = str(tmp_path / "data" / "picks.csv")
    monkeypatch.setenv("SITE_PASSWORD", "pw1")
    build_site(cfg, str(tmp_path / "docs"), "2026-11-10", ["nba"], demo=True)
    html = (tmp_path / "docs" / "nba.html").read_text()
    assert "Top 10 Bets" not in html and "Private page" in html
