"""Simple location-based expected-goals (xG) model for NHL unblocked shot attempts.

Features: distance, angle, rebound, strength state, shot type. Fitted with logistic
regression on the current season's shots; falls back to a fixed curve when data is thin.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SHOT_TYPES = ["wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around"]


def features(shots: pd.DataFrame) -> pd.DataFrame:
    x = shots["x"].astype(float).fillna(60).abs()
    y = shots["y"].astype(float).fillna(0)
    dx = 89 - x
    dist = np.hypot(dx, y)
    angle = np.degrees(np.arctan2(y.abs(), dx.clip(lower=-20)))
    f = pd.DataFrame({
        "dist": dist, "logdist": np.log1p(dist), "angle": angle,
        "rebound": shots["rebound"].astype(float),
        "pp": (shots["strength"] == "PP").astype(float), "sh": (shots["strength"] == "SH").astype(float),
    })
    st = shots["shot_type"].fillna("unknown").str.lower()
    for t in SHOT_TYPES:
        f[f"t_{t}"] = (st == t).astype(float)
    return f


class XGModel:
    def __init__(self):
        self.model = None

    def fit(self, shots: pd.DataFrame, min_shots: int = 3000) -> "XGModel":
        s = shots[(shots["event"] != "block") & (~shots["empty_net"])]
        if len(s) < min_shots:
            return self
        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError:
            return self
        X, y = features(s), (s["event"] == "goal").astype(int)
        self.model = LogisticRegression(C=1.0, max_iter=500).fit(X, y)
        return self

    def predict(self, shots: pd.DataFrame) -> np.ndarray:
        f = features(shots)
        if self.model is not None:
            p = self.model.predict_proba(f)[:, 1]
        else:  # hand-set fallback curve, roughly league-like
            z = -0.6 - 0.055 * f["dist"] - 0.008 * f["angle"] + 0.9 * f["rebound"] + 0.35 * f["pp"]
            p = 1 / (1 + np.exp(-z))
        p = np.where(shots["event"] == "block", 0.0, p)          # blocked shots carry no xG
        p = np.where(shots["empty_net"], 0.6, p)
        return np.asarray(p, dtype=float)
