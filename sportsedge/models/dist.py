"""Count distributions used to turn a projected mean into over/under probabilities."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats


def nb_probs(mean: float, alpha: float, line: float) -> tuple[float, float, float]:
    """(P(over), P(push), P(under)) for a count with given mean and NB overdispersion alpha.

    alpha = 0 -> Poisson.  Var = mean + alpha * mean^2.
    """
    mean = max(float(mean), 1e-6)
    if alpha <= 1e-6:
        dist = stats.poisson(mean)
    else:
        r = 1.0 / alpha
        dist = stats.nbinom(r, r / (r + mean))
    if float(line).is_integer():
        k = int(line)
        push = float(dist.pmf(k))
        under = float(dist.cdf(k - 1))
    else:
        k = math.floor(line)
        push = 0.0
        under = float(dist.cdf(k))
    over = max(0.0, 1.0 - under - push)
    return over, push, under


def fit_alpha(groups, min_games: int = 8, min_mean: float = 0.2, default: float = 0.05) -> float:
    """Method-of-moments NB overdispersion, median across players."""
    vals = []
    for x in groups:
        x = np.asarray(x, dtype=float)
        if len(x) < min_games:
            continue
        m, v = x.mean(), x.var(ddof=1)
        if m < min_mean:
            continue
        vals.append(max(0.0, (v - m) / (m * m)))
    if len(vals) < 25:
        return default
    return float(np.clip(np.median(vals), 0.0, 1.0))


def normal_probs(mean: float, sd: float, line: float) -> tuple[float, float, float]:
    """Continuous approx with half-point continuity correction for integer lines (NBA totals)."""
    if float(line).is_integer():
        under = stats.norm.cdf((line - 0.5 - mean) / sd)
        over = 1 - stats.norm.cdf((line + 0.5 - mean) / sd)
        return float(over), float(1 - over - under), float(under)
    over = 1 - stats.norm.cdf((line - mean) / sd)
    return float(over), 0.0, float(1 - over)
