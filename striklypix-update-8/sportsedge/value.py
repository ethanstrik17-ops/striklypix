"""Turning model probabilities + sportsbook prices into value decisions.

1. Remove the vig from each book's two-way market -> fair probability.
2. Market consensus = sharp book if present, else median of books' fair probs.
3. Blend model with market (markets are efficient; the model is a nudge, not gospel).
4. Shop for the best price, compute EV and fractional-Kelly stake, flag.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def devig_power(p1: float, p2: float) -> tuple[float, float]:
    """Power method: find k with p1^k + p2^k = 1. Handles favourite-longshot bias better than
    proportional scaling."""
    if p1 <= 0 or p2 <= 0:
        s = p1 + p2
        return p1 / s, p2 / s
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        if p1 ** k + p2 ** k > 1:
            lo = k
        else:
            hi = k
    return p1 ** k, p2 ** k


OPPOSITE = {"Over": "Under", "Under": "Over", "home": "away", "away": "home"}


def selection_key(row) -> tuple:
    """Two sides of the same bet share a key. Spreads use the home-perspective point."""
    pt = row.point
    if row.market == "spreads":
        pt = pt if row.name == "home" else -pt
    if row.market == "h2h":
        pt = 0.0
    player = row.player if isinstance(row.player, str) else ""
    return (row.event_id, row.market, player, round(float(pt), 2) if pd.notna(pt) else 0.0)


def market_table(odds: pd.DataFrame, sharp_books: list[str], my_books: list[str] | None = None) -> pd.DataFrame:
    """One row per selection side with best price and no-vig consensus probability.

    Every book is used to estimate the fair price; if `my_books` is given, the best price
    (the one you'd actually bet) is only taken from those books."""
    mine = {b.strip().lower() for b in (my_books or []) if b and b.strip()}
    if not len(odds):
        return pd.DataFrame()
    o = odds.copy()
    o["key"] = [selection_key(r) for r in o.itertuples()]
    o["imp"] = 1 / o["price"]
    out = []
    for key, g in o.groupby("key", sort=False):
        fair_by_book = {}
        for book, b in g.groupby("book"):
            sides = b.drop_duplicates("name").set_index("name")["imp"]
            if len(sides) == 2:
                n1, n2 = sides.index
                f1, f2 = devig_power(sides[n1], sides[n2])
                fair_by_book[book] = {n1: f1, n2: f2}
        for name, s in g.groupby("name"):
            bettable = s[s["book"].str.lower().isin(mine)] if mine else s
            if not len(bettable):
                continue  # none of your books offers this side
            best = bettable.loc[bettable["price"].idxmax()]
            book_prices = bettable.groupby("book")["price"].max().to_dict()
            fairs = [fb[name] for fb in fair_by_book.values() if name in fb]
            sharp = [fair_by_book[b][name] for b in sharp_books if b in fair_by_book and name in fair_by_book[b]]
            if sharp:
                fair, src = float(np.mean(sharp)), "sharp"
            elif fairs:
                fair, src = float(np.median(fairs)), f"consensus({len(fairs)})"
            else:  # one-sided market (e.g. only an Over posted): assume ~4.5% margin
                fair, src = float(best["imp"] / 1.045), "one-sided"
            out.append({"event_id": key[0], "market": key[1], "player": key[2] or None,
                        "point": best["point"], "name": name, "home": best["home"], "away": best["away"],
                        "commence": best["commence"], "best_price": float(best["price"]),
                        "best_book": best["book"], "n_books": s["book"].nunique(), "book_prices": book_prices,
                        "market_p": fair, "market_src": src})
    return pd.DataFrame(out)


def evaluate(df: pd.DataFrame, model_weight: float, vcfg: dict) -> pd.DataFrame:
    """df needs: model_win, model_push, market_p, best_price. Adds blended prob, EV, Kelly and a flag."""
    if not len(df):
        return df
    df = df.copy()
    push = df["model_push"].fillna(0)
    cond = (df["model_win"] / (1 - push)).clip(0.001, 0.999)       # P(win | no push)
    df["model_p"] = cond
    df["final_p"] = model_weight * cond + (1 - model_weight) * df["market_p"]
    dec = df["best_price"]
    df["ev"] = (1 - push) * (df["final_p"] * (dec - 1) - (1 - df["final_p"]))
    b = dec - 1
    kelly = ((df["final_p"] * b - (1 - df["final_p"])) / b).clip(lower=0)
    df["stake_pct"] = (kelly * vcfg["kelly_fraction"]).clip(upper=vcfg["max_stake_pct"])
    df["edge_vs_market"] = df["model_p"] - df["market_p"]
    df["fair_odds"] = 1 / df["final_p"]

    def flag(r):
        if r.ev >= vcfg["min_ev"] and abs(r.edge_vs_market) > vcfg["max_disagreement"]:
            return "CHECK NEWS"  # big gap usually = injury/lineup info the model doesn't have
        if r.ev >= vcfg["min_ev"]:
            return "BET"
        if r.ev >= 0:
            return "lean"
        return ""

    df["flag"] = [flag(r) for r in df.itertuples()]
    return df.sort_values("ev", ascending=False)
