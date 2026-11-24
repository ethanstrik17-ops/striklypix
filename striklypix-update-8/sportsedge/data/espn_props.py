"""Free player-prop lines from ESPN's odds feed (DraftKings, ESPN provider id 100). No key, no credits.

    https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{E}/competitions/{E}/odds/100/propBets

Each over/under line comes as TWO items for the same athlete, prop type and line, with no Over/Under
label: the first item is the Over and the second the Under (checked against DraftKings' own
milestone ladders: every lopsided line agreed). Yes-only props (anytime TD) come as one item.
Athletes are ESPN ids, the same ids our ESPN box scores use, so no name matching is needed.
"""
from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd

from .odds import COLS, to_decimal

CORE = "https://sports.core.api.espn.com/v2/sports/{path}/events/{e}/competitions/{e}/odds/{prov}/propBets"
LEAGUE_PATH = {"nba": "basketball/leagues/nba", "nfl": "football/leagues/nfl"}

# ESPN prop type name (lower case, "total " removed) -> our stat key
NBA_TYPES = {"points": "pts", "rebounds": "reb", "assists": "ast", "3-point field goals": "fg3m",
             "three pointers made": "fg3m", "steals": "stl", "blocks": "blk", "turnovers": "tov",
             "points and rebounds": "pr", "points and assists": "pa", "assists and rebounds": "ra",
             "rebounds and assists": "ra", "points, rebounds, and assists": "pra",
             "points, rebounds and assists": "pra"}
NFL_TYPES = {"passing yards": "pass_yds", "passing attempts": "pass_att", "pass attempts": "pass_att",
             "passing completions": "pass_cmp", "pass completions": "pass_cmp", "completions": "pass_cmp",
             "passing touchdowns": "pass_td", "touchdown passes": "pass_td", "rushing yards": "rush_yds",
             "rushing attempts": "rush_att", "rush attempts": "rush_att", "carries": "rush_att",
             "receptions": "rec", "receiving yards": "rec_yds", "rushing plus receiving yards": "rush_rec_yds",
             "rushing + receiving yards": "rush_rec_yds", "passing plus rushing yards": "pass_rush_yds",
             "passing + rushing yards": "pass_rush_yds"}
SKIP = re.compile(r"quarter|half|1st|2nd|3rd|4th|first|milestone|longest|\balt\b|race|period|double|triple")


def _stat(sport: str, type_name: str) -> str | None:
    t = re.sub(r"\s*\(incl\.? overtime\)", "", type_name.strip().lower())
    if sport == "nfl" and t in ("anytime touchdown scorer", "anytime td scorer"):
        return "td"
    if SKIP.search(t):
        return None
    t = re.sub(r"^(total|player)\s+", "", t)
    return (NBA_TYPES if sport == "nba" else NFL_TYPES).get(t)


TEAM_TOTAL = re.compile(r"^(team )?total points$")


def _team(item: dict) -> str | None:
    ref = (item.get("team") or {}).get("$ref", "")
    m = re.search(r"/teams/([^/?]+)", ref)
    return m.group(1) if m else None


def _athlete(item: dict) -> str | None:
    ref = (item.get("athlete") or {}).get("$ref", "")
    m = re.search(r"/athletes/([^/?]+)", ref)
    return m.group(1) if m else None


def _price(item: dict) -> float | None:
    o = item.get("odds") or {}
    for path in (("decimal", "value"), ("american", "value")):
        v = (o.get(path[0]) or {}).get(path[1])
        try:
            if v not in (None, "", "OFF"):
                return to_decimal(float(str(v).replace("+", "")))
        except ValueError:
            continue
    return None


def _line(item: dict) -> float | None:
    for k in ("current", "open"):
        v = ((item.get(k) or {}).get("target") or {}).get("value")
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                pass
    v = ((item.get("odds") or {}).get("total") or {}).get("value")
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def parse_prop_items(sport: str, items: list[dict], event_id: str, commence, home, away,
                     book: str = "draftkings", team_ids: dict | None = None) -> pd.DataFrame:
    """team_ids maps ESPN team id -> our abbreviation (for team totals)."""
    groups: dict[tuple, list] = {}
    for it in items:
        if "athlete" not in it and _team(it) and team_ids:
            abbr = team_ids.get(_team(it))
            line, price = _line(it), _price(it)
            if abbr in (home, away) and TEAM_TOTAL.match((it.get("type") or {}).get("name", "").strip().lower()) \
                    and line is not None and price and price > 1:
                groups.setdefault(("T:" + abbr, "team_totals", line), []).append(price)
            continue
        aid = _athlete(it)
        stat = _stat(sport, (it.get("type") or {}).get("name", ""))
        if not aid or not stat:
            continue
        price = _price(it)   # None = DraftKings line posted but no price yet (common for NFL early in the week)
        if price is not None and price <= 1:
            continue
        line = _line(it)
        if stat == "td":
            line = 0.5
        if line is None:
            continue
        groups.setdefault((aid, stat, line), []).append(price)
    rows = []
    for (aid, stat, line), prices in groups.items():
        names = ("Over", "Under") if len(prices) == 2 else (("Over",) if stat == "td" and len(prices) == 1 else ())
        if stat == "team_totals" and None in prices:
            continue   # unpriced team totals come as a whole ladder of lines: no way to tell the main one
        team = aid[2:] if aid.startswith("T:") else None
        for nm, p in zip(names, prices):
            rows.append({"event_id": str(event_id), "commence": commence, "home": home, "away": away, "book": book,
                         "market": stat, "name": nm, "player": team, "point": line, "price": p,
                         "player_id": None if team else aid})
    return pd.DataFrame(rows, columns=COLS + ["player_id"])


def fetch_props(sport: str, slate: pd.DataFrame, http, ttl: float = 900, provider_id: int = 100,
                team_ids: dict | None = None) -> pd.DataFrame:
    """All DraftKings player props ESPN lists for the games on the slate."""
    if sport not in LEAGUE_PATH or not len(slate):
        return pd.DataFrame(columns=COLS + ["player_id"])
    frames, n_ok = [], 0
    for g in slate.itertuples():
        url = CORE.format(path=LEAGUE_PATH[sport], e=g.game_id, prov=provider_id)
        items, page, pages = [], 1, 1
        try:
            while page <= pages and page <= 6:
                d = http.get_json(url, params={"limit": 1000, "page": page}, ttl=ttl)
                items += d.get("items", [])
                pages = int(d.get("pageCount") or 1)
                page += 1
        except RuntimeError as e:
            print(f"  warn: ESPN props for {g.away}@{g.home} unavailable ({str(e)[:80]})", file=sys.stderr)
            continue
        df = parse_prop_items(sport, items, g.game_id, g.start_utc, g.home, g.away, team_ids=team_ids)
        if len(df):
            n_ok += 1
            frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS + ["player_id"])
    n_tt = int((out["market"] == "team_totals").sum() // 2) if len(out) else 0
    print(f"  team totals: {n_tt} lines", file=sys.stderr)
    print(f"  prop lines: {len(out) // 2 - n_tt} from ESPN/DraftKings for {n_ok}/{len(slate)} games (free)", file=sys.stderr)
    return out
