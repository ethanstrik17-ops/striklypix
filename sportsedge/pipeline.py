"""Glue: load data -> build models -> projections -> compare with odds."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

from .data.dataset import Dataset
from .data.names import PlayerMatcher, norm
from .models.games import TeamRatings
from .models.players import GoalieProjector, PlayerProjector
from .value import evaluate, market_table


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def get_provider(sport: str, cfg: dict, demo: bool = False):
    if demo:
        from .data.demo import DemoProvider
        return DemoProvider(sport)
    if sport == "nhl":
        from .data.nhl import NHLProvider
        return NHLProvider(cfg)
    if sport == "nfl":
        from .data.nfl import NFLProvider
        return NFLProvider(cfg)
    from .data.nba import NBAProvider
    return NBAProvider(cfg)


def load_overrides(path: str | None, sport: str) -> dict:
    if not path:
        return {}
    with open(path) as fh:
        return (yaml.safe_load(fh) or {}).get(sport, {}) or {}


@dataclass
class Context:
    sport: str
    date: pd.Timestamp
    cfg: dict
    ds: Dataset
    slate: pd.DataFrame
    overrides: dict = field(default_factory=dict)
    players: PlayerProjector | None = None
    goalies: GoalieProjector | None = None
    teams: TeamRatings | None = None
    games: dict = field(default_factory=dict)       # game_id -> game model
    proj: pd.DataFrame = field(default_factory=pd.DataFrame)
    goalie_proj: pd.DataFrame = field(default_factory=pd.DataFrame)
    line_moves: dict = field(default_factory=dict)
    injuries: pd.DataFrame = field(default_factory=pd.DataFrame)
    game_meta: dict = field(default_factory=dict)


def build(sport: str, date, cfg: dict, provider, overrides: dict | None = None, ds: Dataset | None = None) -> Context:
    date = pd.Timestamp(date).normalize()
    if ds is None:
        ds = provider.load(date)
    slate = provider.slate(date)
    overrides = overrides or {}
    inj = pd.DataFrame()
    if cfg["general"].get("auto_injuries", True) and hasattr(provider, "injuries") and len(slate):
        from .data.espn import injury_overrides, merge_overrides
        inj = provider.injuries()
        teams = set(slate["home"]) | set(slate["away"])
        overrides = merge_overrides(overrides, injury_overrides(inj, teams))
        if len(inj):
            print(f"  injury report: {len(overrides.get('out', []))} out, "
                  f"{len(overrides.get('questionable', []))} questionable on today's teams", file=sys.stderr)
    ctx = Context(sport, date, cfg, ds, slate, overrides)
    ctx.line_moves = getattr(provider, "line_moves", {})
    ctx.injuries = inj
    ctx.game_meta = getattr(provider, "game_meta", {}) or {}
    if not len(slate):
        print(f"No {sport.upper()} games on {date.date()}.", file=sys.stderr)
        return ctx
    if sport == "nfl":
        from .models.nfl import NFLPlayerProjector, NFLTeamModel
        ctx.teams = NFLTeamModel(ds, cfg, date)
        for g in slate.itertuples():
            try:
                ctx.games[g.game_id] = ctx.teams.predict(g.home, g.away, date)
            except KeyError as e:
                print(f"  skip {g.away}@{g.home}: {e}", file=sys.stderr)
        ctx.players = NFLPlayerProjector(ds, cfg, date, ctx.teams)
        ctx.proj = ctx.players.project_slate(slate, ctx.overrides)
        return ctx
    ctx.teams = TeamRatings(ds, cfg, date)
    gf = {}
    if sport == "nhl":
        ctx.goalies = GoalieProjector(ds, cfg, date)
        gf = goalie_factors(ctx)
    for g in slate.itertuples():
        try:
            ctx.games[g.game_id] = ctx.teams.predict(g.home, g.away, date, gf)
        except KeyError as e:
            print(f"  skip {g.away}@{g.home}: {e}", file=sys.stderr)
    ctx.players = PlayerProjector(ds, cfg, date)
    ctx.proj = ctx.players.project_slate(slate, ctx.overrides)
    blend_bottom_up(ctx)
    if sport == "nhl":
        rows = []
        go = ctx.overrides.get("goalies", {}) or {}
        for g in slate.itertuples():
            m = ctx.games.get(g.game_id)
            if m is None:
                continue
            for team, opp, sa in ((g.home, g.away, m.sog_a), (g.away, g.home, m.sog_h)):
                p = ctx.goalies.project(team, opp, sa, go.get(team))
                if p:
                    p["game_id"] = g.game_id
                    rows.append(p)
        ctx.goalie_proj = pd.DataFrame(rows)
    return ctx


def blend_bottom_up(ctx: Context):
    """Team score = mix of team-rating model and the sum of that team's player projections
    (normalised to a full game of minutes). This is how injuries/overrides reach game lines."""
    w = ctx.cfg[ctx.sport].get("bottom_up_weight", 0.0)
    if not w or not len(ctx.proj):
        return
    stat, full = ("pts", 240.0) if ctx.sport == "nba" else ("goals", 300.0)
    bu = {}
    for (gid, team), p in ctx.proj.groupby(["game_id", "team"]):
        mins = p["proj_min"].sum()
        if mins > 0.6 * full:
            bu[(gid, team)] = p[stat].sum() * full / mins
    for g in ctx.slate.itertuples():
        m = ctx.games.get(g.game_id)
        h, a = bu.get((g.game_id, g.home)), bu.get((g.game_id, g.away))
        if m is not None and h and a:
            m.blend(h, a, w)


def goalie_factors(ctx: Context) -> dict:
    """Multiplier on goals ALLOWED by each team based on who is projected to start in net."""
    gp, out = ctx.goalies, {}
    go = ctx.overrides.get("goalies", {}) or {}
    if gp is None or not len(gp.gg):
        return out
    for team in set(ctx.slate["home"]) | set(ctx.slate["away"]):
        st = gp.likely_starter(team, go.get(team))
        if st is None:
            continue
        g = gp.gg[gp.gg["team"] == team]
        k = gp.cfg["goalie_shrink_shots"]
        team_sv = (g["saves"].sum() + k * gp.lg_sv) / (g["sa"].sum() + k)
        out[team] = float(np.clip((1 - gp.save_pct(st[0])) / (1 - team_sv), 0.85, 1.15))
    return out


def game_table(ctx: Context) -> pd.DataFrame:
    rows = []
    for g in ctx.slate.itertuples():
        m = ctx.games.get(g.game_id)
        if m is not None:
            rows.append({"game": f"{g.away}@{g.home}", "start_utc": g.start_utc, **m.summary()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------- value: games
def game_value(ctx: Context, odds: pd.DataFrame) -> pd.DataFrame:
    mt = market_table(odds[odds["market"].isin(["h2h", "spreads", "totals"])], ctx.cfg["odds"]["sharp_books"],
                      ctx.cfg["odds"].get("my_books"))
    if not len(mt):
        return mt
    by_teams = {(g.home, g.away): ctx.games.get(g.game_id) for g in ctx.slate.itertuples()}
    win, push, keep = [], [], []
    for r in mt.itertuples():
        m = by_teams.get((r.home, r.away))
        if m is None:
            keep.append(False); win.append(np.nan); push.append(np.nan)
            continue
        if r.market == "h2h":
            w, p = m.p_ml(r.name)
        elif r.market == "spreads":
            w, p = m.p_cover(r.name, r.point)
        else:
            o, p = m.p_total(r.point)
            w = o if r.name == "Over" else 1 - o - p
        keep.append(True); win.append(w); push.append(p)
    mt["model_win"], mt["model_push"] = win, push
    mt = mt[keep]
    mt["selection"] = [_label(r) for r in mt.itertuples()]
    return evaluate(mt, ctx.cfg["value"]["model_weight_games"], ctx.cfg["value"])


def _label(r) -> str:
    if r.market == "h2h":
        return f"{r.home if r.name == 'home' else r.away} ML"
    if r.market == "spreads":
        return f"{r.home if r.name == 'home' else r.away} {r.point:+g}"
    if r.market == "totals":
        return f"{r.away}@{r.home} {r.name} {r.point:g}"
    return f"{r.player} {r.name} {r.point:g} {r.market}"


# ---------------------------------------------------------------------- value: props
def prop_value(ctx: Context, odds: pd.DataFrame) -> pd.DataFrame:
    props = odds[~odds["market"].isin(["h2h", "spreads", "totals"])]
    mt = market_table(props, ctx.cfg["odds"]["sharp_books"],
                      ctx.cfg["odds"].get("my_books"))
    if not len(mt) or not len(ctx.proj):
        return pd.DataFrame()
    proj = ctx.proj.set_index("player_id")
    gproj = ctx.goalie_proj.set_index("player_id") if len(ctx.goalie_proj) else pd.DataFrame()
    pairs = list(zip(ctx.proj.player_id, ctx.proj.player, ctx.proj.team))
    if len(ctx.goalie_proj):
        pairs += list(zip(ctx.goalie_proj.player_id, ctx.goalie_proj.player, ctx.goalie_proj.team))
    matcher = PlayerMatcher(pairs)
    out, unmatched = [], set()
    for r in mt.itertuples():
        teams = {t for t in (r.home, r.away) if t}
        pid = matcher.match(r.player, teams or None)
        if pid is None:
            unmatched.add(r.player)
            continue
        if r.market == "saves":
            if not len(gproj) or pid not in gproj.index:
                continue
            gr = gproj.loc[pid]
            mean, (o, p, u) = gr["saves"], ctx.goalies.probs(gr["saves"], r.point)
            team, flags, mins = gr["team"], gr["flags"], np.nan
        else:
            if pid not in proj.index or r.market not in proj.columns:
                continue
            pr = proj.loc[pid]
            mean = pr[r.market]
            o, p, u = ctx.players.probs(r.market, mean, r.point)
            team, flags, mins = pr["team"], pr["flags"], pr["proj_min"]
        d = r._asdict()
        d.update({"player_id": pid, "team": team, "proj": mean, "proj_min": mins, "flags": flags,
                  "model_win": o if r.name == "Over" else u, "model_push": p})
        out.append(d)
    if unmatched:
        print(f"  note: {len(unmatched)} book player names not matched (not in projections): "
              f"{', '.join(sorted(unmatched)[:8])}{'...' if len(unmatched) > 8 else ''}", file=sys.stderr)
    df = pd.DataFrame(out)
    if not len(df):
        return df
    df = df.drop(columns=["Index"], errors="ignore")
    df["selection"] = [f"{r.player} {r.name} {r.point:g} {r.market}" for r in df.itertuples()]
    return evaluate(df, ctx.cfg["value"]["model_weight_props"], ctx.cfg["value"])


def recent_prop_snapshot(ctx: Context):
    """Prop prices bought earlier today (e.g. the NFL morning run) are reused by later runs the same day,
    so the same games aren't paid for twice. Controlled by odds.reuse_props_hours: {nfl: 12}."""
    import glob
    from pathlib import Path
    hours = (ctx.cfg["odds"].get("reuse_props_hours") or {}).get(ctx.sport)
    if not hours:
        return None
    files = sorted(glob.glob(str(Path(ctx.cfg["general"]["output_dir"]) / "odds_snapshots" / f"{ctx.sport}_props_*.csv")))
    if not files:
        return None
    ts = pd.Timestamp(Path(files[-1]).stem.split("_")[-1]).tz_localize("UTC")
    now = _now()
    if now - ts > pd.Timedelta(hours=float(hours)) or \
            ts.tz_convert("America/Toronto").date() != now.tz_convert("America/Toronto").date():
        return None
    from .data.odds import COLS
    df = pd.read_csv(files[-1])
    df["player"] = df["player"].where(df["player"].notna(), None)
    return df[[c for c in COLS if c in df]], ts.tz_convert("America/Toronto").strftime("%-I:%M %p")


def espn_props(ctx: Context) -> pd.DataFrame:
    """Free DraftKings player props from ESPN, with names filled in from our own box scores."""
    import os
    from .data.espn_props import fetch_props
    from .data.http import CachedClient
    http = CachedClient(os.path.join(ctx.cfg["general"]["cache_dir"], "espn_props"), delay=0.25)
    df = fetch_props(ctx.sport, ctx.slate, http)
    if not len(df):
        return df
    pg = ctx.ds.player_games.sort_values("date")
    names = dict(zip(pg["player_id"].astype(str), pg["player"]))
    if len(ctx.proj):
        names.update(dict(zip(ctx.proj["player_id"].astype(str), ctx.proj["player"])))
    df["player"] = df["player_id"].astype(str).map(names)
    df = df[df["player"].notna()]
    try:
        from pathlib import Path
        snap = Path(ctx.cfg["general"]["output_dir"]) / "odds_snapshots"
        snap.mkdir(parents=True, exist_ok=True)
        ts = _now().strftime("%Y%m%dT%H%M%S")
        df.drop(columns=["player_id"]).assign(snapshot_utc=ts).to_csv(snap / f"{ctx.sport}_props_{ts}.csv", index=False)
    except OSError:
        pass
    return df.drop(columns=["player_id"])


def fetch_odds(ctx: Context, provider, kind: str, demo: bool, lines_csv: str | None = None) -> pd.DataFrame:
    from .data.odds import COLS, OddsClient, et_date, load_manual_lines
    frames = []
    if lines_csv:
        frames.append(load_manual_lines(lines_csv, ctx.sport))
    if demo:
        frames.append(provider.odds(ctx.date, kind))
    else:
        oc = OddsClient(ctx.cfg)
        enabled = ctx.cfg["odds"].get("enabled_sports") or ["nba", "nhl", "nfl"]
        days = (ctx.cfg["odds"].get("prop_days") or {}).get(ctx.sport)
        today = pd.Timestamp.now(tz="America/Toronto").day_name()
        if kind == "games" and ctx.cfg["odds"].get("game_lines_source", "espn") == "espn" \
                and hasattr(provider, "espn_game_odds"):
            from .data.espn import odds_frame
            frames.append(odds_frame(provider.espn_game_odds()))
            print("  game lines: free ESPN feed (no credits used)", file=sys.stderr)
        elif kind == "props" and ctx.cfg["odds"].get("props_source", "espn") == "espn" and ctx.sport in ("nba", "nfl"):
            frames.append(espn_props(ctx))
        elif kind == "props" and days and today not in days:
            print(f"  ({ctx.sport.upper()} prop odds only pulled on {', '.join(days)} to save credits)", file=sys.stderr)
        elif ctx.sport not in enabled:
            print(f"  ({ctx.sport.upper()} odds turned off in config: projections only)", file=sys.stderr)
        elif kind == "props" and recent_prop_snapshot(ctx) is not None:
            snap, when = recent_prop_snapshot(ctx)
            frames.append(snap)
            print(f"  {ctx.sport.upper()} prop odds: reusing today's {when} prices (no credits used)", file=sys.stderr)
        elif oc.available:
            try:
                teams = set(ctx.slate["home"]) | set(ctx.slate["away"])
                frames.append(oc.game_odds(ctx.sport) if kind == "games" else oc.prop_odds(ctx.sport, ctx.date, teams))
            except Exception as e:  # network/API errors shouldn't kill the projections
                print(f"  warn: odds fetch failed: {e}", file=sys.stderr)
        elif not lines_csv:
            print("  (no ODDS_API_KEY set and no --lines file: showing projections only)", file=sys.stderr)
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame(columns=COLS)
    odds = pd.concat(frames, ignore_index=True)
    # manual lines join the API's event for the same matchup so books are compared side by side
    api = odds[~odds["event_id"].astype(str).str.startswith("manual-")]
    ev_map = {(h, a): e for e, h, a in zip(api["event_id"], api["home"], api["away"])}
    man = odds["event_id"].astype(str).str.startswith("manual-")
    odds.loc[man, "event_id"] = [ev_map.get((h, a), e) for e, h, a in
                                 zip(odds.loc[man, "event_id"], odds.loc[man, "home"], odds.loc[man, "away"])]
    if not demo:  # keep only games on the requested date (ET) that have NOT started yet
        d = ctx.date.date()
        days = {pd.Timestamp(x).date() for x in ctx.slate["date"]} if len(ctx.slate) else {d}
        now = _now()
        def ok(c):
            if c is None or (isinstance(c, float) and np.isnan(c)):
                return True  # manual lines have no time
            t = pd.Timestamp(c)
            t = t.tz_localize("UTC") if t.tzinfo is None else t
            return et_date(c) in days and t > now
        keep = [ok(c) for c in odds["commence"]]
        dropped = odds.loc[[not k for k in keep], "event_id"].nunique()
        odds = odds[keep]
        if dropped:
            print(f"  note: skipped odds for {dropped} game(s) already started or not on {d} (live prices aren't comparable)",
                  file=sys.stderr)
    return odds
