"""Build the public website: one daily-card page per sport, an archive of past days, and a
results page fed by an automatic pick log. Run by the GitHub Actions workflow every day.

    python -m sportsedge site --out docs            # today, NFL + NBA
    python -m sportsedge site --out docs --demo     # try it with simulated data
"""
from __future__ import annotations

import glob
import html
import os
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from . import card as cardmod
from . import ledger, pipeline

PAGE = {"nfl": "index.html", "nba": "nba.html", "nhl": "nhl.html"}
FORM_STATS = {"nba": ["pts", "reb", "ast", "fg3m"], "nfl": ["rec_yds", "rush_yds", "targets", "pass_yds"],
              "nhl": ["sog", "points", "hits", "blocks"]}


def _now_et() -> pd.Timestamp:
    return pd.Timestamp.now(tz="America/Toronto")


def _nav(active: str, sports: list[str]) -> list:
    items = [(s.upper(), PAGE.get(s, f"{s}.html"), s == active) for s in sports]
    return items + [("Past days", "archive/index.html", active == "archive")]


def _sub_nav(nav):
    """Same nav, but for pages inside archive/."""
    return [(t, ("../" + h) if not h.startswith("archive/") else h.split("/", 1)[1], on) for t, h, on in nav]


def build_sport(sport: str, date, cfg: dict, sports: list[str], demo: bool = False) -> str:
    from . import webapp
    prov = pipeline.get_provider(sport, cfg, demo)
    ctx = pipeline.build(sport, date, cfg, prov, {})
    nav = _nav(sport, sports)
    updated = _now_et().strftime("%a %-I:%M %p ET")
    picks = cfg["general"]["picks_file"]
    try:  # grade earlier picks with the freshly loaded results
        ledger.grade(picks, sport, ctx.ds, cfg)
    except Exception as e:  # never let grading break the page
        print(f"  warn: grading failed: {e}", file=sys.stderr)
    card = cardmod.unify(ctx, pd.DataFrame(), pd.DataFrame())
    lists, note = cardmod.select_lists(card), ""
    if len(ctx.slate):
        go = pipeline.fetch_odds(ctx, prov, "games", demo)
        po = pipeline.fetch_odds(ctx, prov, "props", demo)
        if len(po) and (po["market"] == "team_totals").any():  # team totals come with the prop feed
            go = pd.concat([go, po[po["market"] == "team_totals"]], ignore_index=True)
            po = po[po["market"] != "team_totals"]
        gv = pipeline.game_value(ctx, go) if len(go) else pd.DataFrame()
        pv = pipeline.prop_value(ctx, po) if len(po) else pd.DataFrame()
        card = cardmod.unify(ctx, gv, pv)
        try:
            card = webapp.tag_card(card, webapp.TrendBook(ctx))
        except Exception as e:  # trends are a bonus: never let them break the card
            print(f"  warn: trend tags failed: {e}", file=sys.stderr)
        lists = cardmod.select_lists(card)
        if not demo:
            n = ledger.log_card(lists, sport, picks)
            print(f"  tracker: logged {n} new picks", file=sys.stderr)
        if not len(po):
            note = "No player prop lines posted yet. They usually appear the day before the game."
    else:
        note = "No games on the schedule."
    tracker = None
    if Path(picks).exists():
        log = pd.read_csv(picks)
        tracker = log[log["sport"] == sport] if len(log) else None
    payload = webapp.build_payload(ctx, card, lists, tracker=tracker, updated=updated, note=note, demo=demo)
    return webapp.render(payload, sports, PAGE, version=_now_et().strftime("%m%d%H%M"))


def _error_page(sport: str, err: str, sports: list[str]) -> str:
    nav = "".join(f"<a href='{h}'>{t}</a> " for t, h, _ in _nav(sport, sports))
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>StriklyPix {sport.upper()}</title><body style='font-family:-apple-system,sans-serif;padding:24px'>"
            f"<p>{nav}</p><h2>{sport.upper()}: today's card couldn't be built</h2><p>Something went wrong while building it (details below for Claude). "
            f"The site will try again on the next scheduled run.</p><pre style='white-space:pre-wrap;color:#64748b;"
            f"font-size:12px'>{html.escape(err[-1500:])}</pre></body>")


def _archive_index(out: Path, sports: list[str]):
    files = sorted(glob.glob(str(out / "archive" / "*_*.html")), reverse=True)
    rows = {}
    for f in files:
        name = Path(f).stem
        if name == "index":
            continue
        sport, day = name.split("_", 1)
        rows.setdefault(day, []).append((sport, Path(f).name))
    items = "".join(
        f"<li><b>{pd.Timestamp(day):%a %b %-d, %Y}</b> &nbsp; " +
        " &middot; ".join(f"<a href='{fn}'>{s.upper()}</a>" for s, fn in sorted(v)) + "</li>"
        for day, v in sorted(rows.items(), reverse=True))
    nav = "".join(f"<a href='{h}' class='{'on' if on else ''}'>{t}</a>" for t, h, on in _sub_nav(_nav("archive", sports)))
    (out / "archive" / "index.html").write_text(
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>StriklyPix &middot; past days</title><style>{cardmod.CSS}"
        "ul{list-style:none;padding:0}li{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;"
        "margin:8px 0}li a{color:var(--lean);font-weight:600;text-decoration:none}</style></head><body>"
        f"<header><div class=hwrap><div><h1>{cardmod.WORDMARK} <span class=sp>PAST DAYS</span></h1><div class=sub>Every daily card the site "
        f"has published</div></div><nav>{nav}</nav></div></header><main><ul>{items or '<li>Nothing yet.</li>'}</ul></main>"
        "</body></html>")


def _fix_archive_links(page: str) -> str:
    """Archived copies live one folder down, so point the nav back up."""
    import re
    page = re.sub(r"href='((?:index|nba|nhl)\.html(?:\?v=\d+)?)'", r"href='../\1'", page)
    return page.replace("href='archive/index.html'", "href='index.html'").replace(
        'href="archive/index.html', 'href="index.html')


def prune_snapshots(cfg: dict, keep_days: int = 21):
    snap = Path(cfg["general"]["output_dir"]) / "odds_snapshots"
    cutoff = time.time() - keep_days * 86400
    for f in snap.glob("*.csv"):
        if f.stat().st_mtime < cutoff:
            f.unlink()


def build_site(cfg: dict, out: str, date=None, sports=("nfl", "nba"), demo: bool = False):
    """Build pages for `sports`. If the SITE_PASSWORD environment variable is set, every page is
    encrypted behind a password prompt and the pick log is stored encrypted (data/picks.csv.enc)."""
    from .protect import decrypt_bytes, encrypt_bytes, lock_page
    out = Path(out)
    (out / "archive").mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("")
    sports = list(sports)
    nav_sports = list(dict.fromkeys(list(cfg.get("site", {}).get("sports") or []) + sports))
    date = pd.Timestamp(date) if date else pd.Timestamp(_now_et().date())
    password = os.environ.get(cfg.get("site", {}).get("password_env", "SITE_PASSWORD")) or None
    picks = Path(cfg["general"]["picks_file"])
    enc = picks.with_name(picks.name + ".enc")
    if password and enc.exists():
        picks.parent.mkdir(parents=True, exist_ok=True)
        picks.write_bytes(decrypt_bytes(enc.read_bytes(), password))
    # One salt kept across builds (saved next to the picks log): a phone that unlocked once keeps opening every
    # page instantly, even after the site rebuilds 6 times a day. Changing SITE_PASSWORD still locks everyone out.
    salt_file = picks.with_name("site_salt.txt")
    try:
        build_salt = bytes.fromhex(salt_file.read_text().strip())
        assert len(build_salt) == 16
    except Exception:
        build_salt = os.urandom(16)
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        salt_file.write_text(build_salt.hex())
    lock = (lambda h: lock_page(h, password, salt=build_salt)) if password else (lambda h: h)
    for sport in sports:
        print(f"== building {sport.upper()} {date.date()}", file=sys.stderr)
        try:
            page = build_sport(sport, date, cfg, nav_sports, demo)
        except Exception:
            err = traceback.format_exc()
            print(err, file=sys.stderr)
            page = _error_page(sport, err, nav_sports)
        (out / PAGE.get(sport, f"{sport}.html")).write_text(lock(page))
        (out / "archive" / f"{sport}_{date:%Y-%m-%d}.html").write_text(lock(_fix_archive_links(page)))
    _archive_index(out, nav_sports)
    idx = out / "archive" / "index.html"
    idx.write_text(lock(idx.read_text()))
    prune_snapshots(cfg)
    if password and picks.exists():
        enc.write_bytes(encrypt_bytes(picks.read_bytes(), password))
        picks.unlink()
    print(f"site written to {out.resolve()}" + (" (password protected)" if password else ""), file=sys.stderr)
