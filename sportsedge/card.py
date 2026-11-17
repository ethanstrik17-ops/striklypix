"""Daily betting card: every prop + moneyline + spread + total in one place, the day's
top-10 lists, long shots, streaks & injuries, parlays and the pick tracker, rendered as
one clean HTML page per sport.
"""
from __future__ import annotations

import html
import json
import math
from itertools import combinations

import numpy as np
import pandas as pd

from .data.odds import to_american

BOOK_NAMES = {"draftkings": "DraftKings", "fanduel": "FanDuel", "betrivers": "BetRivers", "espnbet": "theScore Bet",
              "bet99": "Bet99", "betano": "Betano", "pointsbet": "PointsBet", "pinnacle": "Pinnacle",
              "proline": "Proline+", "betmgm": "BetMGM", "demo_book_a": "Demo Book A",
              "demo_book_b": "Demo Book B", "demo_book_c": "Demo Book C", "manual": "Manual"}
STAT_NAMES = {"pts": "Points", "reb": "Rebounds", "ast": "Assists", "fg3m": "Threes", "pra": "Pts+Reb+Ast",
              "pr": "Pts+Reb", "pa": "Pts+Ast", "ra": "Reb+Ast", "blk": "Blocks", "stl": "Steals", "tov": "Turnovers",
              "sog": "Shots on goal", "points": "Points", "goals": "Goals", "assists": "Assists",
              "blocks": "Blocked shots", "saves": "Saves", "ppp": "Power-play points",
              "pass_yds": "Passing yards", "pass_att": "Pass attempts", "pass_cmp": "Completions",
              "pass_td": "Passing TDs", "rush_yds": "Rushing yards", "rush_att": "Rush attempts", "rec": "Receptions",
              "rec_yds": "Receiving yards", "targets": "Targets", "td": "Anytime TD"}
GROUPS = [("bet", "Bet", "BET"), ("check", "Check", "CHECK NEWS"), ("lean", "Leans", "lean"),
          ("dnt", "Do Not Touch", "")]
FLAG_NOTES = {"missed_last_game": "missed his team's last game", "minutes_bump": "extra minutes (teammate out)",
              "minutes_override": "your minutes override", "starter_unconfirmed": "starter not confirmed",
              "questionable": "QUESTIONABLE on the injury report", "role_bump": "bigger role (teammate out)",
              "starting_for_injured_qb": "starting for the injured QB"}
UNITS = {"nba": "points", "nfl": "points", "nhl": "goals"}
BRAND = "StriklyPix"
WORDMARK = "Strikly<span class=px>Pix</span>"


def book_name(b) -> str:
    return BOOK_NAMES.get(str(b), str(b).replace("_", " ").title())


def american(dec) -> str:
    if dec is None or (isinstance(dec, float) and np.isnan(dec)):
        return ""
    a = to_american(float(dec))
    return f"+{a}" if a > 0 else str(a)


def _flag_text(f) -> str:
    if not isinstance(f, str) or not f:
        return ""
    out = []
    for part in f.split(","):
        if part.startswith("only_"):
            out.append(f"small sample ({part.split('_')[1]} games)")
        elif part in FLAG_NOTES:
            out.append(FLAG_NOTES[part])
    return "; ".join(out)


# ---------------------------------------------------------------------- combine
def _move_note(mv: dict | None, team_side: str | None, market: str) -> str:
    if not mv:
        return ""
    if market == "spreads" and mv.get("spread_open") is not None and mv.get("spread_now") is not None \
            and mv["spread_open"] != mv["spread_now"]:
        return f" Line moved {mv['home']} {mv['spread_open']:+g} → {mv['spread_now']:+g} since open."
    if market == "totals" and mv.get("total_open") is not None and mv.get("total_now") is not None \
            and mv["total_open"] != mv["total_now"]:
        return f" Total moved {mv['total_open']:g} → {mv['total_now']:g} since open."
    if market == "h2h" and mv.get("ml_home_open") is not None and mv.get("ml_home_now") is not None \
            and mv["ml_home_open"] != mv["ml_home_now"]:
        return f" {mv['home']} moneyline moved {mv['ml_home_open']:+.0f} → {mv['ml_home_now']:+.0f}."
    return ""


def _game_day(commence) -> str:
    try:
        t = pd.Timestamp(commence)
        t = t.tz_localize("UTC") if t.tzinfo is None else t
        return t.tz_convert("America/Toronto").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def unify(ctx, game_val: pd.DataFrame, prop_val: pd.DataFrame) -> pd.DataFrame:
    unit = UNITS.get(ctx.sport, "points")
    summ, starts = {}, {}
    for g in ctx.slate.itertuples():
        m = ctx.games.get(g.game_id)
        starts[(g.home, g.away)] = g.start_utc
        if m is not None:
            summ[(g.home, g.away)] = m.summary()
    moves = getattr(ctx, "line_moves", {}) or {}
    rows = []
    for r in (game_val.itertuples() if len(game_val) else []):
        s = summ.get((r.home, r.away), {})
        game = f"{r.away} @ {r.home}"
        team = r.home if r.name == "home" else r.away
        margin = s.get("proj_margin", np.nan) * (1 if r.name == "home" else -1)
        if r.market == "h2h":
            typ, pick, proj = "Moneyline", f"{team} to win", np.nan
            why = f"Model gives {team} a {r.model_p:.0%} win chance; this price needs {1 / r.best_price:.0%}."
        elif r.market == "spreads":
            typ, pick, proj = "Spread", f"{team} {r.point:+g}", margin
            why = f"Projected margin {team} {margin:+.1f} vs spread {r.point:+g}."
        else:
            typ, pick, proj = "Total", f"{r.name} {r.point:g} {unit}", s.get("proj_total", np.nan)
            why = f"Projected total {proj:.1f} vs line {r.point:g}."
        why += _move_note(moves.get((r.home, r.away)), r.name, r.market)
        rows.append({"type": typ, "game": game, "pick": pick, "proj": proj, "r": r, "why": why,
                     "player_flags": "", "player": None, "side": r.name})
    notes = (getattr(ctx, "overrides", {}) or {}).get("injury_notes", {}) or {}
    for r in (prop_val.itertuples() if len(prop_val) else []):
        game = f"{r.away} @ {r.home}" if isinstance(r.away, str) else ""
        stat = STAT_NAMES.get(r.market, r.market)
        if r.market == "td":
            pick = f"{r.player} anytime TD" if r.name == "Over" else f"{r.player} no TD"
            why = f"Projects {r.proj:.2f} TDs → {r.model_p:.0%} chance to score."
        else:
            pick = f"{r.player} {r.name} {r.point:g} {stat}"
            why = f"Projects {r.proj:.1f} vs line {r.point:g} ({r.model_p:.0%} model, {r.market_p:.0%} books)."
        note = _flag_text(getattr(r, "flags", ""))
        from .data.names import norm as _n
        inj = notes.get(_n(r.player), "")
        if inj and "questionable" in str(getattr(r, "flags", "")):
            note = (note + "; " if note else "") + inj
        rows.append({"type": "Prop", "game": game, "pick": pick, "proj": r.proj, "r": r, "why": why,
                     "player_flags": note, "player": r.player, "side": r.name})
    out = []
    for d in rows:
        r = d.pop("r")
        flag = r.flag if isinstance(r.flag, str) else ""
        why = d["why"]
        if flag == "CHECK NEWS":
            why += " Big gap vs the books - check injuries and lineups first."
        if d["player_flags"]:
            why += f" Note: {d['player_flags']}."
        commence = r.commence if isinstance(r.commence, str) else starts.get((r.home, r.away))
        out.append({**d, "why": why, "flag": flag, "event_id": r.event_id, "market": r.market,
                    "point": r.point, "home": r.home, "away": r.away,
                    "price": r.best_price, "book": r.best_book, "model_p": r.model_p, "market_p": r.market_p,
                    "final_p": r.final_p, "ev": r.ev, "stake_pct": r.stake_pct,
                    "push": 0.0 if pd.isna(r.model_push) else float(r.model_push),
                    "book_prices": getattr(r, "book_prices", {}) or {}, "start": commence,
                    "game_date": _game_day(commence) or ctx.date.strftime("%Y-%m-%d")})
    df = pd.DataFrame(out)
    return df.sort_values("ev", ascending=False).reset_index(drop=True) if len(df) else df


def select_lists(card: pd.DataFrame, n: int = 10, n_long: int = 5) -> dict:
    """Today's 10 best bets (any type), 10 best props, and long shots. One pick per player,
    at most two per game, never a CHECK NEWS pick (those usually mean missing injury news)."""
    empty = card.iloc[0:0] if len(card) else pd.DataFrame()
    if not len(card):
        return {"best": empty, "props": empty, "long": empty}
    ok = card[card["flag"].isin(["BET", "lean"]) & (card["ev"] > 0)].sort_values("ev", ascending=False)

    def pick(df, limit, per_game=2):
        chosen, players, games = [], set(), {}
        for i, r in df.iterrows():
            if r["player"] and r["player"] in players:
                continue
            if games.get(r["game"], 0) >= per_game:
                continue
            chosen.append(i)
            if r["player"]:
                players.add(r["player"])
            games[r["game"]] = games.get(r["game"], 0) + 1
            if len(chosen) >= limit:
                break
        return df.loc[chosen]

    long_mask = ((ok["type"] == "Moneyline") & (ok["price"] >= 2.5)) | ((ok["type"] == "Prop") & (ok["price"] >= 3.0))
    return {"best": pick(ok, n), "props": pick(ok[ok["type"] == "Prop"], n, per_game=3),
            "long": pick(ok[long_mask], n_long, per_game=1)}


# ---------------------------------------------------------------------- parlays
def build_parlays(card: pd.DataFrame, vcfg: dict, max_pool: int = 8) -> list[dict]:
    """Cross-game parlays from +EV legs, priced at ONE book (you can't split a parlay across books).
    At most one leg per game, so legs are close to independent."""
    if not len(card):
        return []
    cands = card[card["flag"].isin(["BET", "lean"]) & (card["push"] < 0.02)]
    books = sorted({b for d in cands["book_prices"] for b in d})
    found = {}
    for book in books:
        legs = []
        for r in cands.itertuples():
            price = r.book_prices.get(book)
            if price and r.final_p * price - 1 > 0:
                legs.append({"pick": r.pick, "type": r.type, "game": r.game, "price": price, "p": r.final_p,
                             "ev": r.final_p * price - 1, "event_id": r.event_id})
        best = {}
        for leg in sorted(legs, key=lambda x: -x["ev"]):
            best.setdefault(leg["event_id"], leg)
        pool = sorted(best.values(), key=lambda x: -x["ev"])[:max_pool]
        for k in (2, 3):
            for combo in combinations(pool, k):
                p = math.prod(l["p"] for l in combo)
                dec = math.prod(l["price"] for l in combo)
                ev = p * dec - 1
                key = tuple(sorted(l["pick"] for l in combo))
                if ev > 0 and (key not in found or found[key]["ev"] < ev):
                    kelly = max(0.0, (p * dec - 1) / (dec - 1)) * vcfg["kelly_fraction"]
                    found[key] = {"legs": combo, "book": book, "p": p, "dec": dec, "ev": ev,
                                  "stake_pct": min(kelly, vcfg.get("max_parlay_stake_pct", 0.005)), "n": k}
    allp = sorted(found.values(), key=lambda x: -x["ev"])
    # spread picks across parlays: no single leg in more than 2 suggested parlays
    used, picked = {}, {2: [], 3: []}
    limit = {2: 4, 3: 3}
    for pl in allp:
        if len(picked[pl["n"]]) >= limit[pl["n"]]:
            continue
        if any(used.get(l["pick"], 0) >= 2 for l in pl["legs"]):
            continue
        picked[pl["n"]].append(pl)
        for l in pl["legs"]:
            used[l["pick"]] = used.get(l["pick"], 0) + 1
    return picked[2] + picked[3]


# ---------------------------------------------------------------------- HTML
CSS = """
:root{--bg:#f5f6f8;--card:#fff;--ink:#0f172a;--muted:#64748b;--line:#e5e7eb;--bet:#15803d;--bet-bg:#ecfdf3;
--check:#b45309;--check-bg:#fffbeb;--lean:#1d4ed8;--lean-bg:#eff6ff;--dnt:#6b7280;--dnt-bg:#f3f4f6;--red:#b91c1c}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:var(--bg);color:var(--ink);font-size:14px;line-height:1.45}
header{background:#0f172a;color:#fff;padding:20px}header h1{margin:0;font-size:22px;font-weight:800;letter-spacing:-.2px}
header h1 .px{color:#22c55e}header h1 .sp{font-size:13px;font-weight:700;letter-spacing:.6px;color:#0f172a;background:#fff;
border-radius:6px;padding:2px 7px;margin-left:6px;vertical-align:3px}
header .sub{color:#94a3b8;font-size:13px;margin-top:4px}
.hwrap{max-width:1280px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
nav{display:flex;gap:6px;flex-wrap:wrap}nav a{color:#cbd5e1;text-decoration:none;font-size:14px;font-weight:650;
padding:8px 16px;border-radius:9px;border:1px solid #1e293b}nav a.on{background:#fff;color:#0f172a;border-color:#fff}
nav a:hover{background:#1e293b;color:#fff}nav a.on:hover{background:#fff;color:#0f172a}
main{max-width:1280px;margin:0 auto;padding:20px 20px 60px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:18px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.tile .n{font-size:24px;font-weight:700}.tile .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 14px}
.tab{border:1px solid var(--line);background:var(--card);border-radius:999px;padding:8px 14px;cursor:pointer;font-weight:600;
color:var(--muted);font-size:13px}.tab .c{display:inline-block;margin-left:6px;padding:0 7px;border-radius:999px;background:var(--dnt-bg);font-size:12px}
.tab.active{color:#fff;background:var(--ink);border-color:var(--ink)}.tab.active .c{background:rgba(255,255,255,.18)}
.tab.hero.active{background:var(--bet);border-color:var(--bet)}
.panel{display:none}.panel.active{display:block}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:14px}
.box h2{font-size:15px;margin:0;padding:14px 16px 0}
.intro{padding:12px 16px;border-bottom:1px solid var(--line);color:var(--muted);font-size:13px}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line)}
.chip{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 10px;cursor:pointer;font-size:12px;color:var(--muted)}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}.sep{width:1px;height:20px;background:var(--line)}
.search{margin-left:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;min-width:180px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);background:#fafbfc;
padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}
td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}
td.nw{white-space:nowrap}td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}th.num{text-align:right}
.pick{font-weight:600}.why{color:var(--muted);font-size:12.5px;max-width:440px;min-width:180px}
.rank{display:inline-flex;width:24px;height:24px;border-radius:999px;align-items:center;justify-content:center;
background:var(--ink);color:#fff;font-size:12px;font-weight:700}
.badge{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--dnt-bg);color:var(--dnt);white-space:nowrap}
.b-Prop{background:#f5f3ff;color:#6d28d9}.b-Moneyline{background:#ecfeff;color:#0e7490}.b-Spread{background:#fff7ed;color:#c2410c}.b-Total{background:#f0fdf4;color:#15803d}
.v-BET{background:var(--bet-bg);color:var(--bet)}.v-CHECK{background:var(--check-bg);color:var(--check)}.v-lean{background:var(--lean-bg);color:var(--lean)}
.wi{background:var(--bet-bg);color:var(--bet)}.lo{background:#fef2f2;color:var(--red)}
.ev-pos{color:var(--bet);font-weight:700}.ev-neg{color:var(--red)}
.parlays{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;padding:16px}
.pl{border:1px solid var(--line);border-radius:12px;padding:14px}.pl h3{margin:0 0 6px;font-size:15px}
.pl ul{margin:8px 0;padding-left:18px}.pl li{margin:3px 0}.pl .meta{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12.5px}
.pl .meta b{color:var(--ink)}.empty{padding:28px;text-align:center;color:var(--muted)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
details{margin-top:18px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px}
summary{cursor:pointer;font-weight:600}details p,details li{color:var(--muted);font-size:13px}
.foot{color:var(--muted);font-size:12px;margin-top:18px}
@media (max-width:760px){main{padding:14px 12px 40px}.tiles{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}
.tile .n{font-size:20px}.search{margin-left:0;min-width:0;width:100%}
.bt thead{display:none}.bt tr{display:block;border-bottom:1px solid var(--line);padding:12px 14px}
.bt td{display:flex;justify-content:space-between;align-items:center;border:0;padding:3px 0;text-align:right;white-space:normal}
.bt td::before{content:attr(data-l);color:var(--muted);font-size:12px;text-align:left;margin-right:12px}
.bt td.pick{font-size:15px;justify-content:flex-start;text-align:left;padding:4px 0 6px}.bt td.pick::before{display:none}
.bt td.lead{justify-content:flex-start;gap:8px}.bt td.lead::before{display:none}
.bt td.why{display:block;text-align:left;max-width:none;padding-top:6px}.bt td.why::before{display:none}}
"""

JS = """
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
 document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===t));
 document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='p-'+t.dataset.t));
 window.scrollTo({top:0});});
function applyFilter(box){const q=((box.querySelector('.search')||{}).value||'').toLowerCase();
 box.querySelectorAll('tbody tr').forEach(r=>{let ok=!q||r.textContent.toLowerCase().includes(q);
  box.querySelectorAll('.chip.on').forEach(c=>{if(c.dataset.f!=='All'&&r.dataset[c.dataset.k]!==c.dataset.f)ok=false;});
  r.style.display=ok?'':'none';});}
document.querySelectorAll('.box').forEach(box=>{
 box.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
  box.querySelectorAll('.chip[data-k="'+c.dataset.k+'"]').forEach(x=>x.classList.toggle('on',x===c));applyFilter(box);});
 const s=box.querySelector('.search');if(s)s.oninput=()=>applyFilter(box);
 box.querySelectorAll('table').forEach(tbl=>tbl.querySelectorAll('th').forEach((th,i)=>th.onclick=()=>{
  const tb=tbl.querySelector('tbody');const rows=[...tb.rows];const dir=th.dataset.dir==='d'?'a':'d';th.dataset.dir=dir;
  rows.sort((a,b)=>{const x=a.cells[i].dataset.v??a.cells[i].textContent,y=b.cells[i].dataset.v??b.cells[i].textContent;
   const nx=parseFloat(x),ny=parseFloat(y);const c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y);return dir==='a'?c:-c;});
  rows.forEach(r=>tb.appendChild(r));}));});
"""


def _esc(x) -> str:
    return html.escape("" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x))


def _money(pct, bankroll):
    if bankroll and pct and pct > 0:
        return f"${pct * bankroll:,.2f}"
    return f"{pct:.1%}" if pct and pct > 0 else "-"


def _fmt_proj(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == 0:
        return ""
    return f"{v:.2f}" if abs(v) < 1 else f"{v:.1f}"


def _pick_table(df: pd.DataFrame, bankroll, ranked=True, verdict=False, empty="Nothing here today.") -> str:
    if df is None or not len(df):
        return f"<div class='empty'>{empty}</div>"
    head = ("<tr>" + ("<th>#</th>" if ranked else "") + ("<th>Verdict</th>" if verdict else "") +
            "<th>Type</th><th>Game</th><th>Pick</th><th class=num>Odds</th><th>Book</th><th class=num>Proj</th>"
            "<th class=num>Our chance</th><th class=num>Needs</th><th class=num>Edge</th><th class=num>Stake</th>"
            "<th>Why</th></tr>")
    body = []
    for i, r in enumerate(df.itertuples(), 1):
        evc = "ev-pos" if r.ev > 0 else "ev-neg"
        need = 1 / r.price if r.price else np.nan
        vflag = (r.flag or "Do not touch").split(" ")[0]
        lead = f"<span class=rank>{i}</span> " if ranked else ""
        if verdict:
            lead += f"<span class='badge v-{vflag}'>{_esc(r.flag or 'Do not touch')}</span> "
        body.append(
            f"<tr data-type='{r.type}' data-flag='{_esc(r.flag or 'none')}'>"
            + (f"<td class=lead data-v='{i}'>{lead}<span class='badge b-{r.type}'>{r.type}</span></td>" if (ranked or verdict)
               else f"<td class=lead><span class='badge b-{r.type}'>{r.type}</span></td>")
            + ("" if not (ranked or verdict) else "")
            + f"<td class=nw data-l='Game'>{_esc(r.game)}</td><td class=pick data-l='Pick'>{_esc(r.pick)}</td>"
            f"<td class=num data-l='Odds' data-v='{r.price:.4f}'>{american(r.price)}</td>"
            f"<td class=nw data-l='Book'>{_esc(book_name(r.book))}</td>"
            f"<td class=num data-l='Projection'>{_fmt_proj(r.proj)}</td>"
            f"<td class=num data-l='Our chance' data-v='{r.final_p:.4f}'>{r.final_p:.0%}</td>"
            f"<td class=num data-l='Needs to win' data-v='{need:.4f}'>{need:.0%}</td>"
            f"<td class='num {evc}' data-l='Edge (EV)' data-v='{r.ev:.4f}'>{r.ev:+.1%}</td>"
            f"<td class=num data-l='Stake' data-v='{r.stake_pct:.4f}'>{_money(r.stake_pct, bankroll)}</td>"
            f"<td class=why>{_esc(r.why)}</td></tr>")
    head = head.replace("<th>#</th>", "<th>#</th>") if ranked else head
    if ranked or verdict:  # the rank/verdict live inside the Type cell to keep mobile cards compact
        head = head.replace("<th>#</th>", "").replace("<th>Verdict</th>", "")
        head = head.replace("<th>Type</th>", "<th>" + ("# " if ranked else "") + ("Verdict / " if verdict else "") + "Type</th>")
    return f"<div class=scroll><table class=bt><thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"


def _chips(key: str, values: list[str], label_all="All") -> str:
    return "".join(f"<button class='chip{' on' if v == 'All' else ''}' data-k='{key}' data-f='{v}'>"
                   f"{label_all if v == 'All' else v}</button>" for v in ["All"] + values)


def _tools(types, flags=None) -> str:
    out = _chips("type", types, "All types")
    if flags:
        out += "<span class=sep></span>" + _chips("flag", flags, "All verdicts")
    return f"<div class=tools>{out}<input class=search placeholder='Search player or team'></div>"


def _parlay_html(parlays, bankroll) -> str:
    if not parlays:
        return "<div class='empty'>No +EV cross-game parlays from today's picks.</div>"
    cards = []
    for p in parlays:
        legs = "".join(f"<li><b>{_esc(l['pick'])}</b> <span style='color:var(--muted)'>({_esc(l['game'])}, "
                       f"{american(l['price'])})</span></li>" for l in p["legs"])
        cards.append(
            f"<div class=pl><h3>{p['n']}-leg parlay at {_esc(book_name(p['book']))}</h3><ul>{legs}</ul>"
            f"<div class=meta><span>Odds <b>{american(p['dec'])}</b></span><span>Hit chance <b>{p['p']:.0%}</b></span>"
            f"<span>Edge <b class=ev-pos>{p['ev']:+.0%}</b></span><span>Stake <b>{_money(p['stake_pct'], bankroll)}</b></span>"
            f"</div></div>")
    note = ("<div class=intro>Built only from value picks in <b>different games</b>, priced at one book. Parlays "
            "multiply the edge and the risk: even good ones lose most of the time, so keep stakes small.</div>")
    return note + f"<div class=parlays>{''.join(cards)}</div>"


def _games_html(ctx) -> str:
    rows = []
    for g in ctx.slate.sort_values("start_utc").itertuples():
        m = ctx.games.get(g.game_id)
        if m is None:
            continue
        s = m.summary()
        fav = g.home if s["proj_margin"] >= 0 else g.away
        try:
            start = pd.Timestamp(g.start_utc).tz_convert("America/Toronto").strftime("%a %-I:%M %p")
        except (TypeError, ValueError):
            start = ""
        mv = (getattr(ctx, "line_moves", {}) or {}).get((g.home, g.away), {})
        line = ""
        if mv.get("spread_now") is not None:
            line = f"{g.home} {mv['spread_now']:+g}" + (f" / {mv['total_now']:g}" if mv.get("total_now") else "")
        rows.append(f"<tr><td class=nw>{start}</td><td class=pick>{g.away} @ {g.home}</td>"
                    f"<td class=num>{s['proj_away']:.1f} - {s['proj_home']:.1f}</td>"
                    f"<td class=num>{s['proj_total']:.1f}</td><td class=nw>{fav} by {abs(s['proj_margin']):.1f}</td>"
                    f"<td class=num>{1 - s['p_home_win']:.0%} / {s['p_home_win']:.0%}</td><td class=nw>{_esc(line)}</td></tr>")
    if not rows:
        return "<div class='empty'>No games.</div>"
    return ("<div class=scroll><table><thead><tr><th>Start (ET)</th><th>Game</th><th class=num>Proj score</th>"
            "<th class=num>Proj total</th><th>Proj margin</th><th class=num>Win % away / home</th><th>Book line</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


PLAYER_COLS = {"nba": ["pts", "reb", "ast", "fg3m", "pra", "fga", "fg3a", "fta"],
               "nfl": ["targets", "rec", "rec_yds", "rush_att", "rush_yds", "pass_att", "pass_yds", "pass_td", "td"],
               "nhl": ["sog", "attempts", "points", "goals", "assists", "hits", "blocks"]}


def _players_html(ctx) -> str:
    if not len(ctx.proj):
        return "<div class='empty'>No projections.</div>"
    stats = [s for s in PLAYER_COLS.get(ctx.sport, []) if s in ctx.proj.columns]
    key = "rec_yds" if ctx.sport == "nfl" else stats[0]
    p = ctx.proj.sort_values(key, ascending=False)
    lead = "<th>Pos</th>" if ctx.sport == "nfl" else "<th class=num>Min</th>"
    head = "<tr><th>Player</th><th>Team</th><th>Opp</th>" + lead + "".join(
        f"<th class=num>{_esc(STAT_NAMES.get(s, s.upper()))}</th>" for s in stats) + "<th>Notes</th></tr>"
    body = "".join(
        f"<tr><td class=pick>{_esc(r['player'])}</td><td>{r['team']}</td><td>{r['opp']}</td>"
        + (f"<td>{_esc(r.get('pos'))}</td>" if ctx.sport == "nfl" else f"<td class=num>{r['proj_min']:.1f}</td>")
        + "".join(f"<td class=num>{_fmt_proj(r[s])}</td>" for s in stats)
        + f"<td class=why>{_esc(_flag_text(r['flags']))}</td></tr>" for _, r in p.iterrows())
    return (f"<div class=tools><input class=search placeholder='Search player or team'></div>"
            f"<div class=scroll><table><thead>{head}</thead><tbody>{body}</tbody></table></div>")


def _news_html(ctx, form: pd.DataFrame | None, injuries: pd.DataFrame | None) -> str:
    inj_rows = ""
    if injuries is not None and len(injuries):
        teams = set(ctx.slate["home"]) | set(ctx.slate["away"])
        d = injuries[injuries["team"].isin(teams)].sort_values(["team", "level"])
        inj_rows = "".join(
            f"<tr><td class=nw>{_esc(r.team)}</td><td class=pick>{_esc(r.player)}</td>"
            f"<td><span class='badge {'lo' if r.level == 'out' else 'v-CHECK'}'>{_esc(r.status)}</span></td>"
            f"<td class=why>{_esc(r.comment)}</td></tr>" for r in d.itertuples())
    inj = ("<div class=box><h2>Injury report (today's teams)</h2><div class=intro>Players marked OUT are removed "
           "automatically and their minutes / targets go to teammates. Questionable players are flagged on their "
           "picks.</div>" + (f"<div class=scroll><table><thead><tr><th>Team</th><th>Player</th><th>Status</th>"
                              f"<th>Note</th></tr></thead><tbody>{inj_rows}</tbody></table></div>" if inj_rows
                              else "<div class=empty>No injuries listed for today's teams.</div>") + "</div>")
    st_rows = ""
    if form is not None and len(form):
        for r in form.head(40).itertuples():
            label = STAT_NAMES.get(r.stat, r.stat)
            if r.type.startswith("ROLE"):
                txt = f"Playing time {'up' if 'UP' in r.type else 'down'}: {r.recent:.1f} recently vs {r.baseline:.1f} before"
            else:
                txt = f"Last 5 games {r.recent:.1f} {label.lower()} vs {r.baseline:.1f} before"
            cls = "wi" if ("HOT" in r.type or "UP" in r.type) else "lo"
            st_rows += (f"<tr><td><span class='badge {cls}'>{_esc(r.type)}</span></td><td class=pick>{_esc(r.player)}</td>"
                        f"<td>{_esc(r.team)}</td><td>{_esc(txt)}</td><td class=num>{abs(r.z):.1f}</td></tr>")
    streak = ("<div class=box><h2>Hot / cold streaks & role changes</h2><div class=intro>Only changes too big to be "
              "random noise (strength 2+). Hot streaks usually cool off, so the projections already lean back toward "
              "normal; a role change (more minutes or targets) is the kind that tends to stick.</div>"
              + (f"<div class=scroll><table><thead><tr><th>Signal</th><th>Player</th><th>Team</th><th>What changed</th>"
                 f"<th class=num>Strength</th></tr></thead><tbody>{st_rows}</tbody></table></div>" if st_rows
                 else "<div class=empty>No strong streaks today.</div>") + "</div>")
    return inj + streak


def tracker_summary(t: pd.DataFrame) -> dict:
    g = t[t["result"].isin(["W", "L", "P"])] if len(t) else t
    w, l, p = (g["result"] == "W").sum(), (g["result"] == "L").sum(), (g["result"] == "P").sum()
    units = float(g["profit_units"].sum()) if len(g) else 0.0
    n = w + l
    return {"w": int(w), "l": int(l), "p": int(p), "units": units, "roi": units / max(len(g), 1),
            "hit": w / n if n else 0.0, "pending": int((t["result"].isna()).sum()) if len(t) else 0}


def _tracker_html(t: pd.DataFrame | None) -> str:
    if t is None or not len(t):
        return ("<div class=box><div class=empty>Nothing tracked yet. Every pick in Top 10 Bets, Top 10 Props and "
                "Long shots is logged automatically and graded after the game, flat 1 unit each.</div></div>")
    s = tracker_summary(t)
    tiles = (f"<div class=tiles style='padding:16px;margin:0'>"
             f"<div class=tile><div class=n>{s['w']}-{s['l']}{'-' + str(s['p']) if s['p'] else ''}</div><div class=l>Record</div></div>"
             f"<div class=tile><div class=n style='color:{'var(--bet)' if s['units'] >= 0 else 'var(--red)'}'>{s['units']:+.1f}u</div>"
             f"<div class=l>Profit, 1 unit per pick</div></div>"
             f"<div class=tile><div class=n>{s['roi']:+.1%}</div><div class=l>Return per pick</div></div>"
             f"<div class=tile><div class=n>{s['hit']:.0%}</div><div class=l>Hit rate</div></div>"
             f"<div class=tile><div class=n>{s['pending']}</div><div class=l>Waiting on result</div></div></div>")
    graded = t[t["result"].isin(["W", "L", "P"])]

    def split(col, title):
        if not len(graded) or col not in graded:
            return ""
        rows = ""
        for k, g in graded.groupby(col):
            ss = tracker_summary(g)
            rows += (f"<tr><td class=pick>{_esc(k)}</td><td class=num>{ss['w']}-{ss['l']}</td>"
                     f"<td class=num>{ss['hit']:.0%}</td><td class='num {'ev-pos' if ss['units'] >= 0 else 'ev-neg'}'>"
                     f"{ss['units']:+.1f}u</td></tr>")
        return (f"<div><h2>{title}</h2><div class=scroll><table><thead><tr><th></th><th class=num>Record</th>"
                f"<th class=num>Hit</th><th class=num>Profit</th></tr></thead><tbody>{rows}</tbody></table></div></div>")

    splits = f"<div class=grid2 style='padding:0 0 12px'>{split('type', 'By bet type')}{split('category', 'By list')}</div>"
    recent = t.sort_values(["date", "logged_utc"], ascending=False).head(300)
    body = "".join(
        f"<tr data-type='{_esc(r.type)}'><td class=nw>{_esc(r.date)}</td><td><span class='badge b-{_esc(r.type)}'>{_esc(r.type)}</span></td>"
        f"<td class=pick>{_esc(r.selection)}</td><td class=num>{american(r.best_price)}</td>"
        f"<td class=nw>{_esc(r.category)}</td>"
        f"<td>{'<span class=\"badge wi\">W</span>' if r.result == 'W' else ('<span class=\"badge lo\">L</span>' if r.result == 'L' else ('<span class=badge>Push</span>' if r.result == 'P' else '<span class=badge>Pending</span>'))}</td>"
        f"<td class=num>{'' if pd.isna(r.profit_units) else f'{r.profit_units:+.2f}u'}</td></tr>" for r in recent.itertuples())
    table = (f"<div class=scroll><table><thead><tr><th>Game date</th><th>Type</th><th>Pick</th><th class=num>Odds</th>"
             f"<th>List</th><th>Result</th><th class=num>Profit</th></tr></thead><tbody>{body}</tbody></table></div>")
    return (f"<div class=box><div class=intro>Every pick from the Top 10 Bets, Top 10 Props and Long shots lists is "
            f"logged at the odds shown and graded after the game, 1 unit each, whether or not you bet it. Give it a few "
            f"weeks before trusting it; 50 picks can swing a lot on luck alone.</div>{tiles}{splits}</div>"
            f"<div class=box><h2>Pick log</h2>{table}</div>")


def render_page(ctx, card: pd.DataFrame, lists: dict, parlays: list, *, form=None, injuries=None, tracker=None,
                bankroll=None, demo=False, note="", nav=None, updated="") -> str:
    sport = ctx.sport.upper()
    if ctx.sport == "nfl":
        when = "This week's games"
        if len(ctx.slate):
            d0, d1 = ctx.slate["date"].min(), ctx.slate["date"].max()
            when += f" &middot; {pd.Timestamp(d0):%a %b %-d} – {pd.Timestamp(d1):%a %b %-d}"
    else:
        when = f"Tonight &middot; {ctx.date:%A, %B %-d}"
    ts = tracker_summary(tracker) if tracker is not None and len(tracker) else None
    tiles = (f"<div class=tile><div class=n>{len(ctx.slate)}</div><div class=l>Games</div></div>"
             f"<div class=tile><div class=n style='color:var(--bet)'>{len(lists['best'])}</div><div class=l>Best bets</div></div>"
             f"<div class=tile><div class=n>{len(lists['long'])}</div><div class=l>Long shots</div></div>")
    if ts:
        tiles += (f"<div class=tile><div class=n>{ts['w']}-{ts['l']}</div><div class=l>{sport} tracker record</div></div>"
                  f"<div class=tile><div class=n style='color:{'var(--bet)' if ts['units'] >= 0 else 'var(--red)'}'>"
                  f"{ts['units']:+.1f}u</div><div class=l>Tracker profit</div></div>")
    types = [t for t in ["Prop", "Moneyline", "Spread", "Total"] if len(card) and (card["type"] == t).any()]
    flags = [f for f in ["BET", "CHECK NEWS", "lean", "none"] if len(card) and
             ((card["flag"].replace("", "none")) == f).any()]
    allp = card.assign(flag=card["flag"]) if len(card) else card
    tabs = [("best", "Top 10 Bets", len(lists["best"]), True), ("props", "Top 10 Props", len(lists["props"]), False),
            ("long", "Long shots", len(lists["long"]), False), ("news", "Streaks &amp; injuries", None, False),
            ("track", "Tracker", None, False), ("parlay", "Parlays", len(parlays), False),
            ("all", "All picks", len(card), False), ("games", "Games", len(ctx.slate), False),
            ("players", "Players", None, False)]
    tabhtml = "".join(f"<button class='tab{' hero' if hero else ''}{' active' if k == 'best' else ''}' data-t='{k}'>{label}"
                      + (f"<span class=c>{n}</span>" if n is not None else "") + "</button>" for k, label, n, hero in tabs)
    intro_best = ("The strongest value on the board right now, any bet type, ranked by edge. <b>Our chance</b> is the "
                  "model's estimate; <b>Needs</b> is how often the bet must win to break even at these odds. Bigger gap = "
                  "more value. Always check the price in your app first.")
    intro_props = "The best player props only, one per player."
    intro_long = ("Big-payout bets (underdogs at +150 or longer, props at +200 or longer) where the model thinks the "
                  "odds are too long. These lose more often than not by design: size them small.")
    panels = [
        ("best", f"<div class=box><div class=intro>{intro_best}</div>{_pick_table(lists['best'], bankroll, empty='No bets cleared the bar today. That happens; passing is a position.')}</div>"),
        ("props", f"<div class=box><div class=intro>{intro_props}</div>{_pick_table(lists['props'], bankroll, empty='No prop value today (or no prop odds were pulled today).')}</div>"),
        ("long", f"<div class=box><div class=intro>{intro_long}</div>{_pick_table(lists['long'], bankroll, empty='No long shots with value today.')}</div>"),
        ("news", _news_html(ctx, form, injuries)),
        ("track", _tracker_html(tracker)),
        ("parlay", f"<div class=box>{_parlay_html(parlays, bankroll)}</div>"),
        ("all", f"<div class=box><div class=intro>Every line the model priced. <b>BET</b> = 3%+ edge, <b>lean</b> = small "
                f"edge, <b>CHECK NEWS</b> = big disagreement with the books (usually injury news), none = no value."
                f"</div>{_tools(types, flags)}{_pick_table(allp, bankroll, ranked=False, verdict=True)}</div>"),
        ("games", f"<div class=box>{_games_html(ctx)}</div>"),
        ("players", f"<div class=box>{_players_html(ctx)}</div>"),
    ]
    panelhtml = "".join(f"<section class='panel{' active' if k == 'best' else ''}' id='p-{k}'>{body}</section>"
                        for k, body in panels)
    navhtml = ("<nav>" + "".join(f"<a href='{h}' class='{'on' if on else ''}'>{_esc(t)}</a>" for t, h, on in nav) +
               "</nav>") if nav else ""
    demo_note = " &middot; <b style='color:#fbbf24'>DEMO DATA</b>" if demo else ""
    upd = f" &middot; updated {_esc(updated)}" if updated else ""
    foot = ("Model output, not a guarantee. Lines move, so confirm every price in your app. Bet only what you can "
            "afford to lose. ConnexOntario: 1-866-531-2600." + (f" {_esc(note)}" if note else ""))
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content="noindex,nofollow">
<title>{BRAND} &middot; {sport}</title><style>{CSS}</style></head><body>
<header><div class=hwrap><div><h1>{WORDMARK} <span class=sp>{sport}</span></h1><div class=sub>{when}{upd}{demo_note}</div></div>{navhtml}</div></header>
<main><div class=tiles>{tiles}</div><div class=tabs>{tabhtml}</div>{panelhtml}<p class=foot>{foot}</p></main>
<script>{JS}</script></body></html>"""
