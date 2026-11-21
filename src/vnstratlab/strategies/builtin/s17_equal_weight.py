"""S17 equal weight, the benchmark and a selectable strategy (card P1-T14; plan section 7).

Rule: 1/N across the tickers that have a feature row on ``asof``; no other filter (a NaN feature
does not exclude a ticker). Weights sum to 1; no row on ``asof`` gives an empty Series. The
universe is the one visible in the features (membership by date is P1-T05). Basis: DeMiguel,
Garlappi & Uppal (2009), 1/N; docs/strategies.md S17. No parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy


@register_strategy
class S17EqualWeight(BaseStrategy):
    """1/N of the cross-section on ``asof``. See the module docstring."""

    id = "S17_equal_weight"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if params:
            raise ValueError("S17 takes no params")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
        tickers = sorted({str(t) for t in on_day["ticker"]})
        if not tickers:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / len(tickers), index=tickers, dtype=float)
