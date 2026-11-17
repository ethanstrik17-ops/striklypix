"""Console tables + CSV + a single self-contained HTML report per run."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
from tabulate import tabulate

from .data.odds import to_american


def fmt(df: pd.DataFrame, cols: list[str], pct: tuple = (), odds: tuple = (), dec: int = 2) -> pd.DataFrame:
    d = df[[c for c in cols if c in df]].copy()
    for c in d.columns:
        if c in pct:
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{v:.1%}")
        elif c in odds:
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{to_american(v):+d} ({v:.2f})")
        elif pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(dec)
    return d


def show(title: str, df: pd.DataFrame, n: int | None = 30):
    print(f"\n=== {title} ===")
    if df is None or not len(df):
        print("(none)")
        return
    print(tabulate(df.head(n) if n else df, headers="keys", tablefmt="simple", showindex=False))


VALUE_COLS = ["flag", "selection", "best_price", "best_book", "proj", "model_p", "market_p", "final_p",
              "fair_odds", "ev", "stake_pct", "market_src", "n_books", "flags"]


def value_view(df: pd.DataFrame) -> pd.DataFrame:
    return fmt(df, VALUE_COLS, pct=("model_p", "market_p", "final_p", "ev", "stake_pct"),
               odds=("best_price", "fair_odds"))


CSS = """body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#1d2433;background:#f7f8fa}
h1{font-size:22px}h2{font-size:17px;margin-top:28px}table{border-collapse:collapse;font-size:13px;background:#fff}
th,td{padding:5px 9px;border-bottom:1px solid #e3e6ec;text-align:left;white-space:nowrap}
th{background:#eef1f6;position:sticky;top:0}tr.BET td{background:#e7f6ec}tr.CHECK td{background:#fff5df}
.wrap{overflow-x:auto;max-width:100%}.note{color:#5b6475;font-size:13px;max-width:900px}"""


def write_html(path: Path, title: str, sections: list[tuple[str, pd.DataFrame]], note: str = ""):
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
             f"initial-scale=1'><title>{html.escape(title)}</title><style>{CSS}</style></head><body>",
             f"<h1>{html.escape(title)}</h1><p class='note'>{html.escape(note)}</p>"]
    for name, df in sections:
        parts.append(f"<h2>{html.escape(name)}</h2>")
        if df is None or not len(df):
            parts.append("<p class='note'>(none)</p>")
            continue
        rows = ["<div class='wrap'><table><tr>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns) + "</tr>"]
        for _, r in df.iterrows():
            cls = str(r.get("flag", "")).split(" ")[0]
            rows.append(f"<tr class='{cls}'>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r.values) + "</tr>")
        parts.append("".join(rows) + "</table></div>")
    parts.append("</body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts))
