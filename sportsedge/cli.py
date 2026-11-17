"""sportsedge command line.

  sportsedge daily   nhl|nba [--bankroll 500]       EVERYTHING: props + ML/spreads/totals, tabs, parlays
  sportsedge slate   nhl|nba [--date YYYY-MM-DD]   game projections (+ ML/spread/total value)
  sportsedge props   nhl|nba [--date ...]          player projections (+ prop value)
  sportsedge player  nhl|nba "Name" [--line sog=3.5]  one player: projection, probabilities, trends
  sportsedge trends  nhl|nba                       hot/cold streaks + role changes on the slate
  sportsedge backtest nhl|nba --start --end        walk-forward accuracy check
  sportsedge grade   nhl|nba                       grade logged picks + closing line value

Add --demo to any command to run on a simulated league (no internet / API key needed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as bt
from . import ledger, pipeline, trends
from .config import PLAYER_STATS, load_config
from .data.names import PlayerMatcher
from .report import fmt, show, value_view, write_html

DISCLAIMER = ("Model output, not a guarantee. Sportsbook prices are usually efficient; treat flags as leads "
              "to investigate (injuries, lineups, goalie starters) and size bets small.")

KEY_STATS = {"nba": ["pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "pra"],
             "nfl": ["rec_yds", "rush_yds", "targets", "pass_yds", "rec", "rush_att", "pass_att", "td"],
             "nhl": ["sog", "attempts", "goals", "assists", "points", "hits", "blocks", "ppp"]}


def _ctx(a, cfg):
    prov = pipeline.get_provider(a.sport, cfg, a.demo)
    ov = pipeline.load_overrides(a.overrides, a.sport)
    return prov, pipeline.build(a.sport, a.date, cfg, prov, ov)


def _out(cfg, a, kind):
    tag = "demo_" if a.demo else ""
    return Path(cfg["general"]["output_dir"]) / f"{tag}{a.sport}_{kind}_{pd.Timestamp(a.date):%Y-%m-%d}"


def cmd_slate(a, cfg):
    prov, ctx = _ctx(a, cfg)
    gt = pipeline.game_table(ctx)
    pct = ("p_home_win", "p_ot", "p_home_-1.5", "p_away_-1.5")
    games_view = fmt(gt, [c for c in gt.columns if c != "start_utc"], pct=pct)
    show(f"{a.sport.upper()} game projections {ctx.date.date()}", games_view, None)
    odds = pipeline.fetch_odds(ctx, prov, "games", a.demo, a.lines)
    val = pipeline.game_value(ctx, odds) if len(odds) else pd.DataFrame()
    vv = value_view(val) if len(val) else val
    show("Game-line value (sorted by EV)", vv, a.top)
    _save(cfg, a, "slate", [("Game projections", games_view), ("Game-line value", vv)], {"games": gt, "value": val})
    if a.log and len(val):
        print(f"\nlogged {ledger.log_picks(val, a.sport, ctx.date, cfg['general']['picks_file'])} BET picks")


def cmd_props(a, cfg):
    prov, ctx = _ctx(a, cfg)
    stats = KEY_STATS[a.sport]
    if not len(ctx.proj):
        print("no projections (no games or no data)")
        return
    proj = ctx.proj.sort_values(stats[0], ascending=False)
    pv = fmt(proj, ["player", "team", "opp", "pos", "proj_min"] + stats + ["flags"], dec=2)
    show(f"{a.sport.upper()} player projections {ctx.date.date()} (top {a.top} by {stats[0]})", pv, a.top)
    gv = pd.DataFrame()
    if len(ctx.goalie_proj):
        gv = fmt(ctx.goalie_proj, ["player", "team", "opp", "proj_sa", "sv_pct", "saves", "flags"], dec=3)
        show("Projected starting goalies", gv, None)
    odds = pipeline.fetch_odds(ctx, prov, "props", a.demo, a.lines)
    val = pipeline.prop_value(ctx, odds) if len(odds) else pd.DataFrame()
    if a.stat and len(val):
        val = val[val["market"] == a.stat]
    vv = value_view(val) if len(val) else val
    show("Player-prop value (sorted by EV)", vv, a.top)
    _save(cfg, a, "props", [("Prop value", vv), ("Player projections", pv), ("Goalies", gv)],
          {"projections": ctx.proj, "goalies": ctx.goalie_proj, "value": val})
    if a.log and len(val):
        print(f"\nlogged {ledger.log_picks(val, a.sport, ctx.date, cfg['general']['picks_file'])} BET picks")


def cmd_daily(a, cfg):
    """Everything for today in one page: props + moneylines + spreads + totals, tabs, parlays."""
    from . import card as cardmod
    prov, ctx = _ctx(a, cfg)
    if not len(ctx.slate):
        print("no games on this date")
        return
    go = pipeline.fetch_odds(ctx, prov, "games", a.demo, a.lines)
    po = pipeline.fetch_odds(ctx, prov, "props", a.demo, a.lines)
    gv = pipeline.game_value(ctx, go) if len(go) else pd.DataFrame()
    pv = pipeline.prop_value(ctx, po) if len(po) else pd.DataFrame()
    card = cardmod.unify(ctx, gv, pv)
    parlays = cardmod.build_parlays(card, cfg["value"])
    lists = cardmod.select_lists(card)
    bankroll = a.bankroll or cfg["general"].get("bankroll")
    note = "" if (len(go) or len(po)) else "No odds loaded - showing projections only."
    from . import trends
    form = trends.form_scan(ctx.ds.player_games, ctx.proj, KEY_STATS.get(a.sport, [])[:4], a.sport) if len(ctx.proj) else None
    picks = cfg["general"]["picks_file"]
    if a.log:
        print(f"tracker: logged {ledger.log_card(lists, a.sport, picks)} picks")
    tracker = None
    if Path(picks).exists():
        log = pd.read_csv(picks)
        tracker = log[log["sport"] == a.sport]
    page = cardmod.render_page(ctx, card, lists, parlays, form=form, injuries=ctx.injuries, tracker=tracker,
                               bankroll=bankroll, demo=a.demo, note=note)
    out = Path(cfg["general"]["output_dir"]) / f"{'demo_' if a.demo else ''}{a.sport}_daily_{ctx.date:%Y-%m-%d}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    if len(card):
        card.drop(columns=["book_prices"]).to_csv(out.with_suffix(".csv"), index=False)
        counts = card["flag"].replace({"": "do not touch"}).value_counts().to_dict()
        print(f"\n{a.sport.upper()} {ctx.date.date()}: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
        top = card[card["flag"] == "BET"].head(10)
        if len(top):
            show("Top BETs", fmt(top.assign(odds=top["price"].map(cardmod.american),
                                            book=top["book"].map(cardmod.book_name)),
                                 ["type", "pick", "odds", "book", "final_p", "ev"], pct=("final_p", "ev")), None)
    print(f"\nsaved {out}")
    if not a.no_open:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())


def cmd_site(a, cfg):
    from .site import build_site
    build_site(cfg, a.out, a.date, [x.strip() for x in a.sports.split(",") if x.strip()], a.demo)


def cmd_player(a, cfg):
    prov, ctx = _ctx(a, cfg)
    pool = ctx.proj
    if not len(pool):
        print("no projections for that date")
        return
    pid = PlayerMatcher(list(zip(pool.player_id, pool.player, pool.team))).match(a.name)
    if pid is None:
        print(f"'{a.name}' not found on the {ctx.date.date()} slate")
        return
    r = pool[pool["player_id"] == pid].iloc[0].to_dict()
    print(f"\n{r['player']} ({r['team']} vs {r['opp']}, {'home' if r['home'] else 'away'}) "
          f"projected {r['proj_min']:.1f} min{'  [' + r['flags'] + ']' if r['flags'] else ''}")
    lines = dict(kv.split("=") for kv in (a.line or []))
    rows = []
    for s in KEY_STATS[a.sport]:
        mean = r[s]
        L = float(lines.get(s, np.floor(mean) + 0.5))
        o, p, u = ctx.players.probs(s, mean, L)
        tr = trends.prop_trend(ctx.ds.player_games, pid, s, L, r["opp"])
        rows.append({"stat": s, "proj": mean, "line": L, "P(over)": o, "P(under)": u,
                     "fair_over": 1 / max(o, 1e-6), "L5_avg": tr.get("L5_avg"), "L10_avg": tr.get("L10_avg"),
                     "season_avg": tr.get("season_avg"), "L10_over": tr.get("L10_over"),
                     "season_over_95ci": tr.get("over_rate_95ci"), "vs_opp_avg": tr.get("vs_opp_avg")})
    show("Projection vs line (pass --line stat=value to price a real line)",
         fmt(pd.DataFrame(rows), list(rows[0]), pct=("P(over)", "P(under)"), odds=("fair_over",)), None)


def cmd_trends(a, cfg):
    prov, ctx = _ctx(a, cfg)
    if not len(ctx.proj):
        print("no slate")
        return
    fs = trends.form_scan(ctx.ds.player_games, ctx.proj, KEY_STATS[a.sport], a.sport)
    fv = fmt(fs, ["type", "player", "team", "stat", "recent", "baseline", "z", "note"]) if len(fs) else fs
    show("Hot / cold / role changes on today's slate (|z| >= 2)", fv, a.top)
    tt = []
    for g in ctx.slate.itertuples():
        m = ctx.games.get(g.game_id)
        line = round(m.summary()["proj_total"] * 2) / 2 if m else 6.0
        for t in (g.away, g.home):
            d = trends.team_total_trend(ctx.ds.team_games, t, line)
            if d:
                tt.append({"game": f"{g.away}@{g.home}", "ref_line": line, **d})
    tv = fmt(pd.DataFrame(tt), list(tt[0]) if tt else []) if tt else pd.DataFrame()
    show("Team over/under history vs model total", tv, None)
    _save(cfg, a, "trends", [("Player form", fv), ("Team totals", tv)], {"form": fs})


def cmd_backtest(a, cfg):
    prov = pipeline.get_provider(a.sport, cfg, a.demo)
    end = pd.Timestamp(a.end or pd.Timestamp.today().normalize() - pd.Timedelta(days=1))
    start = pd.Timestamp(a.start or end - pd.Timedelta(days=30))
    ds = prov.load(end + pd.Timedelta(days=1))
    props, games = bt.run(ds, cfg, start, end, every=a.every)
    s = bt.summarize(props, games)
    show("Player projections: model vs baselines (lower MAE/Brier is better)", fmt(s.get("props", pd.DataFrame()),
         list(s.get("props", pd.DataFrame()).columns), dec=3), None)
    show("Probability calibration (predicted vs actual over rate)", fmt(s.get("calibration", pd.DataFrame()),
         ["bucket", "n", "predicted", "actual"], pct=("predicted", "actual")), None)
    show("Game model", fmt(s.get("games", pd.DataFrame()), list(s.get("games", pd.DataFrame()).columns), dec=3), None)
    if "props" in s:
        al = {r.stat: float(r.alpha_suggested) for r in s["props"].itertuples()}
        print(f"\nsuggested config.yaml ->  {a.sport}:\n  alpha: {al}")
    if "games" in s and a.sport == "nba":
        g = s["games"].iloc[0]
        print(f"  total_sd: {g.resid_sd_total:.1f}\n  margin_sd: {g.resid_sd_margin:.1f}")
    a.date = end
    _save(cfg, a, "backtest", [(k, v) for k, v in s.items()], {"props_detail": props, "games_detail": games})


def cmd_grade(a, cfg):
    prov = pipeline.get_provider(a.sport, cfg, a.demo)
    ds = prov.load(pd.Timestamp.today().normalize())
    log = ledger.grade(cfg["general"]["picks_file"], a.sport, ds, cfg)
    if not len(log):
        print("no picks logged yet (use --log on slate/props)")
        return
    g = log[(log["sport"] == a.sport) & log["result"].notna()]
    show("Graded picks", fmt(g, ["date", "selection", "best_price", "result", "profit_units", "ev", "clv_ev"],
                              pct=("ev", "clv_ev"), odds=("best_price",)), None)
    if len(g):
        clv = f"  avg CLV {g.clv_ev.mean():+.2%}" if g.clv_ev.notna().any() else "  (no closing snapshots yet)"
        print(f"\nrecord {(g.result == 'W').sum()}-{(g.result == 'L').sum()}-{(g.result == 'P').sum()}  "
              f"profit {g.profit_units.sum():+.2f} units (1u = 1% bankroll){clv}")


def _save(cfg, a, kind, sections, frames):
    base = _out(cfg, a, kind)
    base.parent.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        if df is not None and len(df):
            df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore").to_csv(
                f"{base}_{name}.csv", index=False)
    note = DISCLAIMER + ("  DEMO MODE: simulated players, teams and lines." if a.demo else "")
    write_html(Path(f"{base}.html"), f"{a.sport.upper()} {kind} - {pd.Timestamp(a.date):%Y-%m-%d}", sections, note)
    print(f"\nsaved {base}.html (+ CSVs)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="sportsedge", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, date=True):
        sp.add_argument("sport", choices=["nhl", "nba", "nfl"])
        if date:
            sp.add_argument("--date", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
        sp.add_argument("--demo", action="store_true", help="simulated league, no network")
        sp.add_argument("--config", default=None)
        sp.add_argument("--overrides", default=None, help="overrides.yaml (injuries, minutes, goalies)")
        sp.add_argument("--lines", default=None, help="manual lines CSV (see lines.example.csv)")
        sp.add_argument("--top", type=int, default=30)
        sp.add_argument("--log", action="store_true", help="append BET flags to picks.csv")

    for name, fn in (("slate", cmd_slate), ("props", cmd_props), ("trends", cmd_trends)):
        sp = sub.add_parser(name)
        common(sp)
        if name == "props":
            sp.add_argument("--stat", default=None, help="only this market, e.g. sog, pts, saves")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("daily", help="one page with every bet type, tabs and parlays")
    common(sp)
    sp.add_argument("--bankroll", type=float, default=None, help="show stakes in dollars, e.g. --bankroll 500")
    sp.add_argument("--no-open", action="store_true", help="don't open the page in the browser")
    sp.set_defaults(fn=cmd_daily)
    sp = sub.add_parser("site", help="build the website (used by the daily GitHub workflow)")
    sp.add_argument("--out", default="docs")
    sp.add_argument("--date", default=None)
    sp.add_argument("--sports", default="nfl,nba")
    sp.add_argument("--demo", action="store_true")
    sp.add_argument("--config", default=None)
    sp.set_defaults(fn=cmd_site)
    sp = sub.add_parser("player")
    common(sp)
    sp.add_argument("name")
    sp.add_argument("--line", nargs="*", help="e.g. sog=3.5 points=0.5")
    sp.set_defaults(fn=cmd_player)
    sp = sub.add_parser("backtest")
    common(sp, date=False)
    sp.add_argument("--start")
    sp.add_argument("--end")
    sp.add_argument("--every", type=int, default=1, help="test every Nth game day (faster)")
    sp.set_defaults(fn=cmd_backtest, date=None)
    sp = sub.add_parser("grade")
    common(sp, date=False)
    sp.set_defaults(fn=cmd_grade, date=pd.Timestamp.today())
    a = p.parse_args(argv)
    cfg = load_config(a.config)
    a.fn(a, cfg)


if __name__ == "__main__":
    main()
