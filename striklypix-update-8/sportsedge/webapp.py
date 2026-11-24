"""StriklyPix page: one self-contained page per sport (Home / Trends / Matchups), rendered in the
browser from a compact JSON payload so every bet can open its own trend chart.

Python decides what is worth showing (value, Strong / Trap tags, Hot Hands); the page only draws it.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from .card import BOOK_NAMES, STAT_NAMES, _flag_text, tracker_summary
from .data.dataset import season_start_year
from .data.names import norm
from .trends import wilson

LOG_STATS = {"nba": ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pra", "pr", "pa", "ra"],
             "nfl": ["rec_yds", "rec", "targets", "rush_yds", "rush_att", "rush_rec_yds", "pass_yds", "pass_att",
                     "pass_cmp", "pass_td", "pass_rush_yds", "td"],
             "nhl": ["sog", "goals", "assists", "points", "hits", "blocks"]}
SHORT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM", "stl": "STL", "blk": "BLK", "tov": "TOV",
         "pra": "PRA", "pr": "P+R", "pa": "P+A", "ra": "R+A", "pass_yds": "Pass yds", "pass_att": "Pass att",
         "pass_cmp": "Comp", "pass_td": "Pass TD", "rush_yds": "Rush yds", "rush_att": "Rush att", "rec": "Rec",
         "rec_yds": "Rec yds", "targets": "Targets", "td": "TD", "rush_rec_yds": "Rush+Rec yds",
         "pass_rush_yds": "Pass+Rush yds", "sog": "SOG", "goals": "G", "assists": "A",
         "points": "P", "hits": "Hits", "blocks": "BLK"}
TYPE_KEY = {"Prop": "prop", "Moneyline": "ml", "Spread": "spread", "Total": "total", "Team total": "tt"}


def _f(x, nd=3):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def _pid(x):
    """Player ids as clean strings ("1234", never "1234.0"), None when missing."""
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) else str(int(x))
    if isinstance(x, (np.integer,)):
        return str(int(x))
    return str(x)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return _f(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.strftime("%Y-%m-%d")
    return o


# ---------------------------------------------------------------------- hit rates
def hits_for(values: np.ndarray, line: float, side: str) -> np.ndarray:
    """1 where the bet would have won in that game. values oldest -> newest."""
    return (values > line) if side == "Over" else (values < line)


def hit_summary(h: np.ndarray, season_mask: np.ndarray | None = None) -> dict:
    h = np.asarray(h, dtype=bool)
    out = {}
    for n in (5, 10, 20):
        s = h[-n:]
        out[f"L{n}"] = (int(s.sum()), len(s))
    hs = h[season_mask] if season_mask is not None else h
    out["szn"] = (int(hs.sum()), len(hs))
    streak = 0
    for x in h[::-1]:
        if not x:
            break
        streak += 1
    out["streak"] = streak
    return out


class TrendBook:
    """Game logs for the slate, indexed for quick hit-rate lookups."""

    def __init__(self, ctx):
        self.ctx, self.sport = ctx, ctx.sport
        self.season = season_start_year(ctx.date)
        pg = ctx.ds.player_games
        pg = pg[pg["minutes"] > 0] if "minutes" in pg else pg
        teams = set(ctx.slate["home"]) | set(ctx.slate["away"]) if len(ctx.slate) else set()
        ids = set(ctx.proj["player_id"].map(_pid)) if len(ctx.proj) else set()
        pg = pg.assign(pid=pg["player_id"].map(_pid))
        pg = pg[pg["pid"].isin(ids) | pg["team"].isin(teams)].sort_values("date")
        self.pg = pg
        self.by_pid = {k: g for k, g in pg.groupby("pid")}
        tg = ctx.ds.team_games
        tg = tg[tg["date"].map(season_start_year) == self.season] if len(tg) else tg
        self.tg = tg.sort_values("date") if len(tg) else tg
        self.by_team = {k: g for k, g in self.tg.groupby("team")} if len(tg) else {}

    def prop(self, pid, stat, line, side):
        g = self.by_pid.get(_pid(pid))
        if g is None or stat not in g or line is None or (isinstance(line, float) and math.isnan(line)):
            return None
        g = g.tail(40)
        h = hits_for(g[stat].values.astype(float), float(line), side)
        return hit_summary(h, (g["date"].map(season_start_year) == self.season).values)

    def team_total(self, team, point, side):
        """A team's own games: did the GAME total go over/under `point`?"""
        g = self.by_team.get(team)
        if g is None or not len(g):
            return None
        return hit_summary(hits_for((g["pf"] + g["pa"]).values.astype(float), float(point), side))

    def game(self, typ, team, point, side, home=None, away=None):
        if typ == "Team total":
            g = self.by_team.get(team)
            if g is None or not len(g):
                return None
            return hit_summary(hits_for(g["pf"].values.astype(float), float(point), side))
        if typ == "Total":
            parts = [self.by_team.get(t) for t in (home, away)]
            parts = [p for p in parts if p is not None]
            if not parts:
                return None
            g = pd.concat(parts).sort_values("date")
            tot = (g["pf"] + g["pa"]).values.astype(float)
            return hit_summary(hits_for(tot, float(point), side))
        g = self.by_team.get(team)
        if g is None or not len(g):
            return None
        margin = (g["pf"] - g["pa"]).values.astype(float)
        h = margin > 0 if typ == "Moneyline" else (margin + float(point)) > 0
        return hit_summary(h)


def _rate(t):
    return t[0] / t[1] if t and t[1] else None


def tag_card(card: pd.DataFrame, tb: TrendBook) -> pd.DataFrame:
    """Adds hit-rate columns and the Strong / Trap tag.

    Strong = we have an edge AND the recent trend agrees (last 10 clearly above what the price needs, and the
             season at least at break-even). These move up the Top lists.
    Trap   = the trend looks great (7+ of last 10) but the price has no value: popular, overpriced, skip it.
    """
    if not len(card):
        return card.assign(tag="", h=None)
    tags, hs = [], []
    for r in card.itertuples():
        if r.type == "Prop":
            stat = r.market
            pid = getattr(r, "player_id", None)
            h = tb.prop(pid, stat, r.point, r.side) if pid is not None else None
        else:
            team = getattr(r, "team", None) or (r.home if r.side == "home" else r.away)
            h = tb.game(r.type, team, r.point, r.side, r.home, r.away)
        hs.append(h)
        tag = ""
        if h and not getattr(r, "tbd", False):
            be = 1 / r.price if r.price else 1
            l10, szn = _rate(h["L10"]), _rate(h["szn"])
            n10 = h["L10"][1]
            if r.flag in ("BET", "lean") and r.ev > 0 and n10 >= 6 and l10 is not None and l10 >= be + 0.1 \
                    and (szn is None or szn >= be):
                tag = "strong"
            elif n10 >= 8 and l10 is not None and l10 >= 0.7 and r.ev < -0.02 and r.flag != "CHECK NEWS":
                tag = "trap"
        tags.append(tag)
    return card.assign(tag=tags, h=hs)


def hot_hands(card: pd.DataFrame, n: int = 12) -> list[int]:
    """Players on a run against today's line. Only real samples (8+ of the last 10 played), one per player."""
    if not len(card) or "h" not in card:
        return []
    rows = []
    for i, r in card.iterrows():
        if r["type"] != "Prop" or not r["h"]:
            continue
        h = r["h"]
        k10, n10 = h["L10"]
        if n10 < 8:
            continue
        l10 = k10 / n10
        if l10 >= 0.8 or h["streak"] >= 6:
            ev = -1.0 if r.get("tbd") else r["ev"]
            rows.append((i, r["player"], {"strong": 0, "": 1, "trap": 2}[r["tag"]], -l10, -h["streak"], -ev))
    rows.sort(key=lambda x: x[2:])
    seen, out = set(), []
    for i, p, *_ in rows:
        if p in seen:
            continue
        seen.add(p)
        out.append(int(i))
        if len(out) >= n:
            break
    return out


def team_hot_hands(card: pd.DataFrame, tb: "TrendBook", n: int = 10) -> list[list]:
    """Teams on a run against today's lines: winning, covering, team total over/under, and their own
    games going over/under today's game total. Returns [bet index, team or None]; team is set when the
    run is one team's games against a game total. One card per team per bet type."""
    if not len(card) or "h" not in card:
        return []
    rows = []
    rank = {"strong": 0, "": 1, "trap": 2}
    for i, r in card[card["type"] != "Prop"].iterrows():
        if r["type"] == "Total":
            for t in (r["home"], r["away"]):
                h = tb.team_total(t, r["point"], r["side"])
                if h and h["L10"][1] >= 6 and h["L10"][0] / h["L10"][1] >= 0.7:
                    rows.append((int(i), t, "total", rank[r["tag"]], -h["L10"][0] / h["L10"][1], -h["streak"], -r["ev"]))
            continue
        h = r["h"]
        if not h:
            continue
        k, m = h["L10"]
        if m >= 6 and k / m >= 0.7:
            team = r.get("team") or (r["home"] if r["side"] == "home" else r["away"])
            rows.append((int(i), None, f"{team}:{r['type']}", rank[r["tag"]], -k / m, -h["streak"], -r["ev"]))
    rows.sort(key=lambda x: x[3:])
    seen, out = set(), []
    for i, t, key, *_ in rows:
        k = (t or "") + key
        if k in seen:
            continue
        seen.add(k)
        out.append([i, t])
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------------- payload
def _injury_map(ctx) -> dict:
    inj = ctx.injuries
    out = {}
    if inj is None or not len(inj):
        return out
    for r in inj.itertuples():
        out.setdefault(r.team, []).append([r.player, r.status, r.level, str(getattr(r, "comment", "") or "")[:160]])
    return out


def allowed_ranks(ctx, tb: "TrendBook", stats: list[str]) -> dict:
    """What each defence gives up per game this season (all opponents' players summed), ranked
    1 = allows the most. Plus team points allowed under '_pts'."""
    out = {}
    pg = ctx.ds.player_games
    if len(pg) and "game_id" in pg:
        pg = pg[pg["date"].map(season_start_year) == tb.season]
        for st in stats:
            if st not in pg:
                continue
            per = pg.groupby(["game_id", "opp"])[st].sum().groupby("opp").mean()
            if len(per) < 4:
                continue
            rk = per.rank(ascending=False, method="min")
            out[st] = {t: [round(float(v), 1), int(rk[t])] for t, v in per.items()}
            out[st]["_n"] = int(len(per))
            out[st]["_avg"] = round(float(per.mean()), 1)
    tg = tb.tg
    if len(tg):
        pa = tg.groupby("team")["pa"].mean()
        rk = pa.rank(ascending=False, method="min")
        out["_pts"] = {t: [round(float(v), 1), int(rk[t])] for t, v in pa.items()}
        out["_pts"]["_n"] = int(len(pa))
        out["_pts"]["_avg"] = round(float(pa.mean()), 1)
        pf = tg.groupby("team")["pf"].mean()
        rk = pf.rank(ascending=False, method="min")
        out["_pf"] = {t: [round(float(v), 1), int(rk[t])] for t, v in pf.items()}
        out["_pf"]["_n"] = int(len(pf))
    return out


def build_payload(ctx, card: pd.DataFrame, lists: dict, *, tracker=None, updated="", note="", demo=False) -> dict:
    sport = ctx.sport
    tb = TrendBook(ctx)
    stats = [s for s in LOG_STATS.get(sport, []) if s in tb.pg.columns]
    # players: everyone projected today + anyone with a line
    players = {}
    projd = (ctx.proj.assign(pid=ctx.proj["player_id"].map(_pid)).drop_duplicates("pid").set_index("pid")
             if len(ctx.proj) else None)   # first (soonest) game if a team plays twice on the slate
    want = set(projd.index) if projd is not None else set()
    if len(card) and "player_id" in card:
        want |= {_pid(x) for x in card["player_id"].dropna()}
    for pid in want:
        g = tb.by_pid.get(pid)
        if g is None:
            continue
        g = g.tail(40)
        last = g.iloc[-1]
        pr = projd.loc[pid] if projd is not None and pid in projd.index else None
        players[pid] = {
            "n": last["player"], "t": pr["team"] if pr is not None else last["team"],
            "pos": str(last.get("pos", "") or ""),
            "g": [[d.strftime("%Y-%m-%d"), o, int(bool(h)), _f(m, 1), int(season_start_year(d) == tb.season)]
                  + [_f(v, 1) for v in vals]
                  for d, o, h, m, *vals in zip(g["date"], g["opp"], g["home"], g.get("minutes", pd.Series(0, index=g.index)),
                                               *[g[s] for s in stats])],
            "pj": {s: _f(pr[s], 2) for s in stats if pr is not None and s in pr.index} if pr is not None else {},
            "mn": _f(pr.get("proj_min"), 1) if pr is not None else None,
            "fl": _flag_text(pr.get("flags", "")) if pr is not None else "",
        }
    # teams: this season's results
    teams = {}
    for t, g in tb.by_team.items():
        if len(ctx.slate) and t not in set(ctx.slate["home"]) | set(ctx.slate["away"]):
            continue
        teams[t] = [[d.strftime("%Y-%m-%d"), o, int(bool(h)), int(pf), int(pa)]
                    for d, o, h, pf, pa in zip(g["date"], g["opp"], g["home"], g["pf"], g["pa"])]
    # games
    games = []
    moves = getattr(ctx, "line_moves", {}) or {}
    for g in (ctx.slate.sort_values("start_utc").itertuples() if len(ctx.slate) else []):
        m = ctx.games.get(g.game_id)
        s = m.summary() if m is not None else {}
        meta = (getattr(ctx, "game_meta", {}) or {}).get(g.game_id, {})
        mv = moves.get((g.home, g.away), {})
        games.append({
            "id": str(g.game_id), "home": g.home, "away": g.away, "start": g.start_utc,
            "venue": meta.get("venue", ""), "city": meta.get("city", ""),
            "hm": meta.get("home", {}), "am": meta.get("away", {}),
            "proj": {"home": _f(s.get("proj_home"), 1), "away": _f(s.get("proj_away"), 1),
                     "total": _f(s.get("proj_total"), 1), "margin": _f(s.get("proj_margin"), 1),
                     "ph": _f(s.get("p_home_win"), 3)},
            "line": {"spread": mv.get("spread_now"), "total": mv.get("total_now"), "mlh": mv.get("ml_home_now"),
                     "mla": mv.get("ml_away_now")},
        })
    gid_by_teams = {(g["home"], g["away"]): g["id"] for g in games}
    # bets
    bets = []
    if len(card):
        listed = set()
        for k in ("best", "props", "long"):
            listed |= set(lists.get(k, pd.DataFrame()).index) if len(lists.get(k, [])) else set()
        for i, r in card.iterrows():
            pid = r.get("player_id")
            bets.append({
                "i": int(i), "k": TYPE_KEY.get(r["type"], "prop"), "g": gid_by_teams.get((r["home"], r["away"]), ""),
                "pk": r["pick"], "pid": _pid(pid),
                "st": r["market"] if r["type"] == "Prop" else None, "sd": r["side"], "ln": _f(r["point"], 1),
                "pr": _f(r["price"], 3), "bk": BOOK_NAMES.get(str(r["book"]), str(r["book"])),
                "p": _f(r["final_p"]), "mp": _f(r["market_p"]), "mo": _f(r["model_p"]), "ev": _f(r["ev"], 4), "fl": r["flag"] or "",
                "pj": _f(r["proj"], 2), "tag": r.get("tag", ""),
                "tm": r.get("team") if r["type"] != "Prop" else None, "tbd": int(bool(r.get("tbd", False))),
                "why": r["why"] if i in listed else "",
            })
    ids = lambda df: [int(i) for i in df.index] if df is not None and len(df) else []
    tr = None
    if tracker is not None and len(tracker):
        s = tracker_summary(tracker)
        rec = tracker.sort_values(["date", "logged_utc"], ascending=False).head(60)
        tr = {**{k: s[k] for k in ("w", "l", "p", "units", "roi", "hit", "pending")},
              "rows": [[str(r.date), r.selection, _f(r.best_price), r.result if isinstance(r.result, str) else "",
                        _f(r.profit_units, 2), str(r.type)] for r in rec.itertuples()]}
    return _clean({
        "sport": sport, "date": ctx.date.strftime("%Y-%m-%d"), "updated": updated, "note": note, "demo": demo,
        "stats": stats, "statNames": {s: STAT_NAMES.get(s, s) for s in stats}, "short": {s: SHORT.get(s, s) for s in stats},
        "games": games, "teams": teams, "players": players, "bets": bets,
        "lists": {k: ids(lists.get(k)) for k in ("best", "props", "long")},
        "hot": hot_hands(card) if len(card) else [], "teamHot": team_hot_hands(card, tb) if len(card) else [],
        "inj": _injury_map(ctx), "tracker": tr, "allow": allowed_ranks(ctx, tb, stats),
    })


def render(payload: dict, nav_sports: list[str], pages: dict, version: str = "") -> str:
    """version is added to links (nba.html?v=...) so a click always loads the newest build, never a
    copy the browser saved earlier."""
    from .webapp_assets import CSS, HTML, JS
    sport = payload["sport"]
    v = f"?v={version}" if version else ""
    switch = "".join(f"<a href='{pages.get(s, s + '.html')}{v}' class='{'on' if s == sport else ''}'>{s.upper()}</a>"
                     for s in nav_sports)
    payload = {**payload, "v": version}
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return (HTML.replace("{{CSS}}", CSS).replace("{{JS}}", JS).replace("{{SWITCH}}", switch)
            .replace("{{SPORT}}", sport.upper()).replace("{{DATA}}", data))
