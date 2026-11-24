"""Shared ESPN helpers: free game lines (the sportsbook ESPN partners with, currently DraftKings)
and the league injury report. Both come from ESPN's public JSON, no key or credits needed.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .names import norm, team_abbr
from .odds import COLS, to_decimal

SPORT_PATH = {"nba": "basketball/nba", "nfl": "football/nfl", "nhl": "hockey/nhl"}
ESPN_ABBR_FIX = {"nba": {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"},
                 "nfl": {"WAS": "WSH", "JAC": "JAX"}, "nhl": {}}


def espn_team(sport: str, t: dict) -> str | None:
    ab = team_abbr(sport, t.get("displayName") or "") if t.get("displayName") else None
    if not ab:
        raw = str(t.get("abbreviation", "")).upper()
        ab = ESPN_ABBR_FIX.get(sport, {}).get(raw, raw) or None
    return ab


def _num(v):
    try:
        return float(str(v).lstrip("ou").replace("+", "")) if v not in (None, "", "OFF", "EVEN") else (
            100.0 if v == "EVEN" else None)
    except ValueError:
        return None


def parse_odds(sport: str, event_id: str, comp: dict, commence: str | None) -> tuple[list[dict], dict]:
    """ESPN competition 'odds' block -> rows in the standard odds format, plus line-movement info."""
    rows, move = [], {}
    odds = (comp.get("odds") or [])
    if not odds:
        return rows, move
    o = odds[0]
    book = str((o.get("provider") or {}).get("name") or "espn").lower().replace(" ", "")
    teams = {c["homeAway"]: espn_team(sport, c["team"]) for c in comp.get("competitors", [])}
    home, away = teams.get("home"), teams.get("away")

    def add(market, name, point, american):
        p = _num(american)
        if p is None or p == 0:
            return
        rows.append({"event_id": str(event_id), "commence": commence, "home": home, "away": away, "book": book,
                     "market": market, "name": name, "player": None,
                     "point": np.nan if point is None else float(point), "price": to_decimal(p)})

    ml, ps, tot = o.get("moneyline") or {}, o.get("pointSpread") or {}, o.get("total") or {}
    # moneyline
    for side in ("home", "away"):
        cur = ((ml.get(side) or {}).get("close") or {}).get("odds")
        if cur is None:
            cur = ((o.get(f"{side}TeamOdds") or {}).get("moneyLine"))
        add("h2h", side, None, cur)
    # spread
    for side in ("home", "away"):
        cl = (ps.get(side) or {}).get("close") or {}
        line, price = _num(cl.get("line")), cl.get("odds")
        if line is None and o.get("spread") is not None:
            line = float(o["spread"]) * (1 if side == "home" else -1)
            price = (o.get(f"{side}TeamOdds") or {}).get("spreadOdds", -110)
        if line is not None:
            add("spreads", side, line, price if price is not None else -110)
    # total
    for side, name in (("over", "Over"), ("under", "Under")):
        cl = (tot.get(side) or {}).get("close") or {}
        line, price = _num(cl.get("line")), cl.get("odds")
        if line is None and o.get("overUnder") is not None:
            line, price = float(o["overUnder"]), o.get(f"{side}Odds", -110)
        if line is not None:
            add("totals", name, line, price if price is not None else -110)
    # line movement (open -> now), shown in the "why" text
    so, sc = _num(((ps.get("home") or {}).get("open") or {}).get("line")), _num(((ps.get("home") or {}).get("close") or {}).get("line"))
    to, tc = _num(((tot.get("over") or {}).get("open") or {}).get("line")), _num(((tot.get("over") or {}).get("close") or {}).get("line"))
    mo, mc = _num(((ml.get("home") or {}).get("open") or {}).get("odds")), _num(((ml.get("home") or {}).get("close") or {}).get("odds"))
    move = {"home": home, "away": away, "spread_open": so, "spread_now": sc, "total_open": to, "total_now": tc,
            "ml_home_open": mo, "ml_home_now": mc, "book": book}
    return rows, move


def odds_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLS)


# ---------------------------------------------------------------------------- injuries
OUT_STATUSES = {"out", "injured reserve", "suspension", "doubtful", "physically unable to perform",
                "non-football injury", "reserve"}
Q_STATUSES = {"questionable", "day-to-day", "game-time decision"}
_AVAIL_TEXT = re.compile(r"\bis available\b|will play|cleared to play|expected to play|will return|is active", re.I)
_DAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_OUT_TEXT = re.compile(r"\b(will|is|has been) (be )?(ruled )?out\b|won't play|will not play|ruled out|will sit out|"
                       r"sit out|out for (the|his|tonight|sunday|monday|thursday|saturday)", re.I)


def parse_injuries(sport: str, data: dict, now=None) -> pd.DataFrame:
    """level: 'out' (won't play) or 'questionable'. A day-to-day note like "out for Sunday's game"
    only counts as OUT if that day is today (ET); otherwise it's treated as questionable."""
    now = pd.Timestamp(now or pd.Timestamp.now(tz="UTC"))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    today = now.tz_convert("America/Toronto").day_name().lower()
    rows = []
    for t in data.get("injuries", []):
        for i in t.get("injuries", []):
            a = i.get("athlete") or {}
            team = espn_team(sport, a.get("team") or {}) or team_abbr(sport, t.get("displayName") or "")
            status = str(i.get("status") or "").strip()
            st = status.lower()
            comment = i.get("shortComment") or ""
            when = pd.Timestamp(i["date"]) if i.get("date") else None
            recent = when is not None and (now - when).days <= 2
            if st in OUT_STATUSES:
                level = "out"
            elif st in Q_STATUSES:
                if _AVAIL_TEXT.search(comment) and recent:
                    continue
                day = _DAY.search(comment)
                same_day = day is None or day.group(1).lower() == today
                level = "out" if (recent and same_day and _OUT_TEXT.search(comment)) else "questionable"
            else:
                continue  # "Active" etc.
            rows.append({"team": team, "player": a.get("displayName"),
                         "pos": ((a.get("position") or {}).get("abbreviation")), "status": status, "level": level,
                         "comment": comment, "date": when})
    return pd.DataFrame(rows, columns=["team", "player", "pos", "status", "level", "comment", "date"])


def injury_overrides(inj: pd.DataFrame, teams: set | None = None) -> dict:
    """ESPN injury report -> overrides the projectors understand (out + questionable lists)."""
    if inj is None or not len(inj):
        return {}
    df = inj[inj["team"].isin(teams)] if teams else inj
    return {"out": sorted(set(df.loc[df["level"] == "out", "player"].dropna())),
            "questionable": sorted(set(df.loc[df["level"] == "questionable", "player"].dropna())),
            "injury_notes": {norm(r.player): f"{r.status}: {r.comment}"[:160] for r in df.itertuples() if r.player}}


def merge_overrides(manual: dict, auto: dict) -> dict:
    out = dict(auto or {})
    for k, v in (manual or {}).items():
        if isinstance(v, list):
            out[k] = sorted(set(out.get(k, [])) | set(v))
        elif isinstance(v, dict):
            out[k] = {**out.get(k, {}), **v}
        else:
            out[k] = v
    return out


def game_meta(sport: str, comp: dict) -> dict:
    """Venue, team names/colours and current records from an ESPN scoreboard competition."""
    v = comp.get("venue") or {}
    addr = v.get("address") or {}
    out = {"venue": v.get("fullName") or "", "city": ", ".join(x for x in (addr.get("city"), addr.get("state")) if x)}
    for c in comp.get("competitors", []):
        t = c.get("team") or {}
        recs = {str(r.get("type") or r.get("name") or "").lower(): r.get("summary") for r in c.get("records") or []}
        out[c.get("homeAway", "")] = {
            "abbr": espn_team(sport, t), "id": str(t.get("id") or ""), "name": t.get("shortDisplayName") or t.get("name") or "",
            "full": t.get("displayName") or "", "color": "#" + str(t.get("color") or "334155").lstrip("#"),
            "rec": recs.get("total") or recs.get("overall") or "", "home": recs.get("home") or "",
            "road": recs.get("road") or recs.get("away") or ""}
    return out
