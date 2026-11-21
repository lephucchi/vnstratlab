"""Strategy protocol (plan 5.4) and the point-in-time guards every strategy goes through.

Pure: no file, database or network I/O (enforced by tests/test_data_boundary.py).

A strategy is a pure function of the features it is handed. ``BaseStrategy.target_weights`` is the
public entry point: it refuses any feature row dated after ``asof`` (``asof_guard``), calls the
subclass's ``compute_weights`` and validates the result (``validate_weights``), so a strategy that
looks ahead is rejected instead of silently scored.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Literal, Protocol, runtime_checkable

import pandas as pd

Horizon = Literal["short", "medium", "long"]
HORIZONS: tuple[Horizon, ...] = ("short", "medium", "long")

WEIGHT_SUM_TOLERANCE = 1e-9


class LookaheadError(ValueError):
    """A strategy was handed (or returned weights built from) data dated after ``asof``."""


class WeightError(ValueError):
    """Target weights are not long-only, finite and summing to at most 1."""


@runtime_checkable
class Strategy(Protocol):
    """One strategy with one frozen parameter set (plan 5.4)."""

    id: str  # e.g. "S02_breakout20"
    horizons: tuple[Horizon, ...]
    params: dict[str, Any]  # fixed; changing params = a new trial in the registry

    def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        """Return long-only target weights per ticker summing to <= 1.
        Must use only rows with date <= asof (point-in-time)."""
        ...


def _as_timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def asof_guard(features: pd.DataFrame, asof: date | datetime | pd.Timestamp) -> pd.DataFrame:
    """Return ``features`` unchanged; raise ``LookaheadError`` if any row is dated after ``asof``.

    Features come from ``load_features(..., asof=)`` already clamped; this is the second wall.
    """
    if "date" not in features.columns:
        raise LookaheadError("features have no 'date' column: cannot verify point-in-time")
    cutoff = _as_timestamp(asof)
    dates = pd.to_datetime(features["date"])
    if (dates.dt.tz is None) != (cutoff.tzinfo is None):
        raise LookaheadError(
            "timezone mismatch: feature dates are "
            f"{'naive' if dates.dt.tz is None else 'tz-aware'} but asof is "
            f"{'naive' if cutoff.tzinfo is None else 'tz-aware'}; cannot verify point-in-time"
        )
    late = dates > cutoff
    if bool(late.any()):
        raise LookaheadError(
            f"{int(late.sum())} feature row(s) dated after asof {cutoff.date()} "
            f"(latest {dates.max().date()}): strategies may use only rows with date <= asof"
        )
    return features


def validate_weights(weights: pd.Series, universe: Sequence[str] | None = None) -> pd.Series:
    """Check long-only target weights and return them as floats.

    Rejects non-Series input, a non-unique or non-string (ticker) index, NaN or infinite values,
    negative values and a sum above 1 (plus ``WEIGHT_SUM_TOLERANCE``). With ``universe`` the
    index must be a subset of it, so weights for a ticker that is not visible at ``asof`` fail.
    """
    if not isinstance(weights, pd.Series):
        raise WeightError(f"target weights must be a pandas Series, got {type(weights).__name__}")
    if not all(isinstance(t, str) for t in weights.index):
        raise WeightError("weight index must be ticker strings")
    if not weights.index.is_unique:
        raise WeightError("weight index has duplicate tickers")
    try:
        values = weights.astype(float)
    except (TypeError, ValueError):
        raise WeightError("weights must be numeric") from None
    if not all(math.isfinite(v) for v in values):
        raise WeightError("weights must be finite (no NaN or infinity)")
    if bool((values < 0).any()):
        negative = sorted(values.index[values < 0])
        raise WeightError(f"weights must be long-only (no negatives): {negative}")
    total = float(values.sum())
    if total > 1.0 + WEIGHT_SUM_TOLERANCE:
        raise WeightError(f"weights sum to {total:.6f} > 1")
    if universe is not None:
        unknown = sorted(set(values.index) - set(universe))
        if unknown:
            raise WeightError(f"weights for tickers not in the visible universe: {unknown}")
    return values


class BaseStrategy(ABC):
    """Convenience base: holds the frozen id/horizons/params and wraps the guards.

    Subclasses set the class attribute ``id`` and implement ``compute_weights``; they may override
    ``validate_params`` to reject malformed parameters (raise ``ValueError``).
    """

    id: str

    def __init__(self, params: Mapping[str, Any], horizons: Sequence[Horizon]) -> None:
        self.params: dict[str, Any] = dict(params)
        self.horizons: tuple[Horizon, ...] = tuple(horizons)
        self.validate_params(self.params)

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        """Raise ``ValueError`` for malformed params. Default: accept any mapping."""
        return None

    @abstractmethod
    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        """Weights from ``features`` (rows dated <= ``asof``). Pure: no I/O, no hidden state."""

    def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        visible = asof_guard(features, asof)
        weights = self.compute_weights(visible, asof)
        universe = [str(t) for t in visible["ticker"].unique()] if "ticker" in visible else None
        return validate_weights(weights, universe)
