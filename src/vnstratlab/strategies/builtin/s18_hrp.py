"""S18 Hierarchical Risk Parity (card P1-T19; plan section 7; docs/strategies.md S18).

Basis: Lopez de Prado (2016), Building Diversified Portfolios that Outperform Out of Sample
(Hierarchical Risk Parity). Frozen params: ``{window: 250}`` (one trial; long horizon).

History contract: ``lookback_sessions = window``. The strategy reads the feature ``ret_1d`` of
every feature row dated <= ``asof``. Sessions are the dates present in the frame (union over
tickers); a missing return stays NaN (no fill); a return that is infinite or <= -1 is NaN. Fewer
than ``window`` sessions in the frame gives all cash.

Rule as implemented (all steps deterministic; tickers are processed in sorted order)
1. Return matrix: ``ret_1d`` of the last ``window`` sessions <= ``asof`` (rows = sessions,
   columns = tickers sorted). Candidates are the tickers with a feature row on ``asof``.
2. Eligible: candidates with at least ``min_obs = ceil(0.8 * window)`` non-NaN returns in the
   window and non-zero variance.
3. Covariance and correlation are pairwise-complete with ``min_periods = min_obs``. While any
   correlation is NaN, drop the ticker with the most NaN pairs (ties: the later ticker
   alphabetically) and repeat.
4. No eligible ticker gives an empty Series; exactly one gets weight 1.0.
5. Distance ``d = sqrt(0.5 * (1 - rho))``; single-linkage clustering of the condensed distances
   (scipy); quasi-diagonal order from the leaves of the linkage tree; recursive bisection: each
   cluster is split in half (the first ``len // 2`` items vs the rest) and the weight is shared
   in inverse proportion to the two cluster variances, where a cluster variance is ``w' V w``
   with the cluster's inverse-variance weights ``w``.
6. Weights are long-only and sum to 1 (fully invested).

The module is self-contained on purpose: the trial id hashes the source of this module only.
scipy is imported inside the function (CLI import time).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from vnstratlab.strategies.base import BaseStrategy, Horizon
from vnstratlab.strategies.registry import register_strategy

FloatArray = npt.NDArray[np.float64]

FEATURE = "ret_1d"
FROZEN_WINDOW = 250
MIN_WINDOW = 3
MIN_OBSERVED_NUM, MIN_OBSERVED_DEN = 4, 5  # 80 % of the window
MIN_VARIANCE = 1e-18


def min_observations(window: int) -> int:
    """``ceil(0.8 * window)`` in integer arithmetic."""
    return -(-window * MIN_OBSERVED_NUM // MIN_OBSERVED_DEN)


def return_panel(features: pd.DataFrame, asof: pd.Timestamp, sessions: int) -> pd.DataFrame | None:
    """Daily returns of the last ``sessions`` sessions <= ``asof`` (columns = tickers, sorted).

    ``None`` when the frame has fewer than ``sessions`` sessions up to ``asof``.
    """
    missing = [c for c in ("ticker", "date", FEATURE) if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    frame = features[["ticker", "date", FEATURE]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[frame["date"] <= pd.Timestamp(asof).normalize()]
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("more than one feature row per ticker and date")
    dates = sorted(frame["date"].unique())
    if len(dates) < sessions:
        return None
    window = frame[frame["date"].isin(dates[-sessions:])]
    panel = window.pivot(index="date", columns="ticker", values=FEATURE)
    panel = panel.apply(pd.to_numeric, errors="coerce").sort_index().sort_index(axis=1)
    panel = panel.astype(float)
    cleaned: pd.DataFrame = panel.where(np.isfinite(panel) & (panel > -1.0))
    return cleaned


def drop_nan_pairs(corr: pd.DataFrame) -> list[str]:
    """Tickers kept after repeatedly dropping the one with the most NaN correlations.

    Ties drop the later ticker alphabetically. The result keeps the sorted order.
    """
    keep = sorted(str(t) for t in corr.columns)
    while len(keep) > 1:
        nans = corr.loc[keep, keep].isna().sum(axis=1)
        if int(nans.sum()) == 0:
            break
        worst = int(nans.max())
        keep.remove(max(t for t in keep if int(nans[t]) == worst))
    return keep


def quasi_diagonal(link: FloatArray, count: int) -> list[int]:
    """Leaf order of a scipy linkage matrix (the quasi-diagonalisation of Lopez de Prado)."""
    order = [int(link[-1, 0]), int(link[-1, 1])]
    while max(order) >= count:
        expanded: list[int] = []
        for item in order:
            if item >= count:
                row = item - count
                expanded.extend([int(link[row, 0]), int(link[row, 1])])
            else:
                expanded.append(item)
        order = expanded
    return order


def cluster_variance(cov: FloatArray, items: Sequence[int]) -> float:
    """``w' V w`` of the cluster with inverse-variance weights."""
    sub = cov[np.ix_(items, items)]
    inverse = 1.0 / np.diag(sub)
    w = inverse / inverse.sum()
    return float(w @ sub @ w)


def hrp_weights(cov: FloatArray, corr: FloatArray) -> FloatArray:
    """HRP weights (sum 1) for a covariance and correlation matrix of at least two assets."""
    from scipy.cluster.hierarchy import linkage  # local: keep scipy off the CLI import path
    from scipy.spatial.distance import squareform

    count = cov.shape[0]
    dist = np.sqrt(0.5 * np.clip(1.0 - corr, 0.0, 2.0))
    dist = (dist + dist.T) / 2.0
    np.fill_diagonal(dist, 0.0)
    link = np.asarray(linkage(squareform(dist, checks=False), method="single"), dtype=float)
    weights = np.ones(count)
    clusters: list[list[int]] = [quasi_diagonal(link, count)]
    while clusters:
        split: list[list[int]] = []
        for cluster in clusters:
            half = len(cluster) // 2
            first, second = cluster[:half], cluster[half:]
            v_first, v_second = cluster_variance(cov, first), cluster_variance(cov, second)
            alpha = 1.0 - v_first / (v_first + v_second)
            weights[first] *= alpha
            weights[second] *= 1.0 - alpha
            split.extend(c for c in (first, second) if len(c) > 1)
        clusters = split
    normalised: FloatArray = weights / weights.sum()
    return normalised


@register_strategy
class S18Hrp(BaseStrategy):
    """Hierarchical Risk Parity on ``window`` sessions of returns. See the module docstring."""

    id = "S18_hrp"
    lookback_sessions = FROZEN_WINDOW  # the frozen param set; an instance carries its own window

    def __init__(self, params: Mapping[str, Any], horizons: Sequence[Horizon]) -> None:
        super().__init__(params, horizons)
        self.lookback_sessions = int(self.params["window"])

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"window"}:
            raise ValueError("S18 params must be exactly {window}")
        window = params["window"]
        if not isinstance(window, int) or isinstance(window, bool) or window < MIN_WINDOW:
            raise ValueError(f"window must be an integer >= {MIN_WINDOW}")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        window = int(self.params["window"])
        panel = return_panel(features, asof, window)
        if panel is None:
            return pd.Series(dtype=float)  # not enough history: all cash
        asof_day = pd.Timestamp(asof).normalize()
        on_day = features[pd.to_datetime(features["date"]) == asof_day]
        in_panel = {str(t) for t in panel.columns}
        candidates = sorted({str(t) for t in on_day["ticker"]} & in_panel)
        min_obs = min_observations(window)
        eligible = [
            t
            for t in candidates
            if int(panel[t].count()) >= min_obs and float(panel[t].var(ddof=1)) > MIN_VARIANCE
        ]
        if not eligible:
            return pd.Series(dtype=float)
        sub = panel[eligible]
        keep = drop_nan_pairs(sub.corr(min_periods=min_obs))
        if len(keep) < 2:
            return pd.Series(1.0, index=keep, dtype=float) if keep else pd.Series(dtype=float)
        sub = sub[keep]
        cov = sub.cov(min_periods=min_obs).to_numpy(dtype=float)
        rho = sub.corr(min_periods=min_obs).to_numpy(dtype=float)
        weights = hrp_weights(cov, rho)
        if not (
            np.isfinite(weights).all() and math.isclose(float(weights.sum()), 1.0, abs_tol=1e-9)
        ):
            return pd.Series(dtype=float)
        return pd.Series(weights, index=keep, dtype=float)
