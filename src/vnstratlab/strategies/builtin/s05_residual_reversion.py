"""S05 residual mean reversion (card P1-T16; plan section 7; docs/strategies.md S05).

Basis: Avellaneda & Lee (2010), statistical arbitrage with residuals of a factor model. The factor
here is the group itself (the tradable universe, standing in for the bank group); this is the
short-horizon, long-only, one-factor version. Frozen params: ``{window: 60, entry_z: 1.5, n: 2}``.

History contract: ``lookback_sessions = window``. The strategy reads the feature ``ret_1d`` of
every feature row dated <= ``asof``. Sessions are the dates present in the frame (union over
tickers); a missing return stays NaN (no fill). Fewer than ``window`` sessions, or ``asof`` not
being the last session of the frame, gives all cash.

Rule as implemented
* Group return per session: the equal-weight mean of the available ``ret_1d`` of all tickers on
  that session (the ticker being scored is part of the group).
* Per ticker, over the last ``window`` sessions ending at ``asof`` and the days where both its
  return ``y`` and the group return ``g`` are observed (at least 80 % of the window, and the
  ticker must be observed on ``asof``): OLS ``y = alpha + beta * g`` with an intercept; the
  residuals are ``e = y - alpha - beta * g``. A ticker with no variation in ``g`` or in the
  cumulative residual is skipped.
* Cumulative residual ``X_t = sum(e)`` up to ``t``. Because the OLS residuals sum to zero, the
  last ``X`` is 0 (as in Avellaneda & Lee's s-score, ``-m / sigma``), so ``z = (X_last -
  mean(X)) / std(X)`` with the sample std (ddof 1) over the same days is ``-mean(X) / std(X)``:
  it is negative when the cumulative residual spent the window above where it ends.
* Buy the ``n`` tickers with the most negative ``z`` below ``-entry_z`` (strictly), 1/``n`` each;
  fewer qualifiers leave the rest in cash. Ties (z rounded to 12 decimals) by ticker symbol.

The module is self-contained on purpose: the trial id hashes the source of this module only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from vnstratlab.strategies.base import BaseStrategy, Horizon
from vnstratlab.strategies.registry import register_strategy

FloatArray = npt.NDArray[np.float64]

FEATURE = "ret_1d"
SCORE_DECIMALS = 12
MIN_OBSERVED_NUM, MIN_OBSERVED_DEN = 4, 5  # 80 % of the window
MIN_POINTS = 3
FROZEN_WINDOW = 60


def return_panel(features: pd.DataFrame, asof: pd.Timestamp, sessions: int) -> pd.DataFrame | None:
    """Daily returns (rows = the last ``sessions`` sessions ending at ``asof``, columns = tickers).

    Sessions are the dates present in ``features`` (union over tickers). Returns ``None`` when the
    frame has fewer than ``sessions`` sessions or ``asof`` is not its last session. A return
    that is NaN, infinite or <= -1 is NaN (not observed). No fill.
    """
    missing = [c for c in ("ticker", "date", FEATURE) if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    frame = features[["ticker", "date", FEATURE]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("more than one feature row per ticker and date")
    dates = sorted(frame["date"].unique())
    if len(dates) < sessions or pd.Timestamp(dates[-1]) != pd.Timestamp(asof).normalize():
        return None
    window = frame[frame["date"].isin(dates[-sessions:])]
    panel = window.pivot(index="date", columns="ticker", values=FEATURE)
    panel = panel.apply(pd.to_numeric, errors="coerce").sort_index().sort_index(axis=1)
    panel = panel.astype(float)
    cleaned: pd.DataFrame = panel.where(np.isfinite(panel) & (panel > -1.0))
    return cleaned


def enough_observed(count: int, sessions: int) -> bool:
    """At least 80 % of the window observed (integer arithmetic, no float fuzz)."""
    return count * MIN_OBSERVED_DEN >= sessions * MIN_OBSERVED_NUM


def residual_z(y: FloatArray, g: FloatArray, sessions: int) -> float:
    """z-score of the last cumulative OLS residual of ``y`` regressed on ``g`` (NaN if undefined).

    ``y`` and ``g`` cover the window (NaN = not observed). Needs the last session observed for
    both, at least 80 % of ``sessions`` observed, and variation in ``g`` and in the cumulative
    residual.
    """
    both = np.isfinite(y) & np.isfinite(g)
    if not bool(both[-1]) or not enough_observed(int(both.sum()), sessions):
        return math.nan
    yy, gg = y[both], g[both]
    var_g = float(np.var(gg, ddof=1))
    if len(yy) < MIN_POINTS or var_g <= 1e-18:
        return math.nan
    beta = float(np.cov(gg, yy, ddof=1)[0, 1]) / var_g
    alpha = float(np.mean(yy)) - beta * float(np.mean(gg))
    cumulative = np.cumsum(yy - alpha - beta * gg)
    std = float(np.std(cumulative, ddof=1))
    if not math.isfinite(std) or std <= 1e-12:
        return math.nan
    return (float(cumulative[-1]) - float(np.mean(cumulative))) / std


def positive_float(name: str, value: Any) -> None:
    if (
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be a positive finite number")


def positive_int(name: str, value: Any, minimum: int = 1) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@register_strategy
class S05ResidualReversion(BaseStrategy):
    """Buy the most negative cumulative-residual z-scores. See the module docstring."""

    id = "S05_residual_reversion"
    lookback_sessions = FROZEN_WINDOW  # the frozen param set; an instance carries its own window

    def __init__(self, params: Mapping[str, Any], horizons: Sequence[Horizon]) -> None:
        super().__init__(params, horizons)
        self.lookback_sessions = int(self.params["window"])

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"window", "entry_z", "n"}:
            raise ValueError("S05 params must be exactly {window, entry_z, n}")
        positive_int("window", params["window"], MIN_POINTS)
        positive_float("entry_z", params["entry_z"])
        positive_int("n", params["n"])

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        window = self.params["window"]
        panel = return_panel(features, asof, window)
        if panel is None:
            return pd.Series(dtype=float)  # not enough history: all cash
        group = panel.mean(axis=1, skipna=True).to_numpy(dtype=float)  # NaN if nobody observed
        scored: list[tuple[float, str]] = []
        for ticker in panel.columns:
            z = residual_z(panel[ticker].to_numpy(dtype=float), group, window)
            if math.isfinite(z) and z < -float(self.params["entry_z"]):
                scored.append((round(z, SCORE_DECIMALS), str(ticker)))
        scored.sort()
        names = [t for _, t in scored[: self.params["n"]]]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["n"], index=names, dtype=float)
