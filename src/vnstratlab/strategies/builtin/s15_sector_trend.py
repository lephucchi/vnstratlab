"""S15 sector trend filter (card P1-T19; plan section 7; docs/strategies.md S15).

Rule: if the equal-weight group index return over the look-back is > 0, hold every ticker with a
feature row on ``asof`` equally (1/N, the same universe rule as S17); otherwise hold cash.
The signal is the market-context feature ``group_ret_12m`` (``lookback_months`` 12, 250 index
sessions) or ``group_ret_6m`` (``lookback_months`` 6, 126 index sessions); other values are
rejected. The signal is one number per date, so a signal that is <= 0 or NaN, rows that disagree
on it, or no row on ``asof`` give an empty Series (all cash). Only feature rows dated exactly
``asof`` are used (``lookback_sessions`` = 1: the window lives in the feature).

Basis: Moskowitz, Ooi & Pedersen (2012), time-series momentum. Frozen params:
``{lookback_months: 12}`` and ``{lookback_months: 6}`` (one trial each; medium horizon).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

SIGNAL_FEATURES: dict[int, str] = {6: "group_ret_6m", 12: "group_ret_12m"}
AGREE_TOLERANCE = 1e-12


@register_strategy
class S15SectorTrend(BaseStrategy):
    """All-in 1/N when the group trend is up, else cash. See the module docstring."""

    id = "S15_sector_trend"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"lookback_months"}:
            raise ValueError("S15 params must be exactly {lookback_months}")
        months = params["lookback_months"]
        if not isinstance(months, int) or isinstance(months, bool) or months not in SIGNAL_FEATURES:
            raise ValueError(f"lookback_months must be one of {sorted(SIGNAL_FEATURES)}")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        column = SIGNAL_FEATURES[self.params["lookback_months"]]
        missing = [c for c in ("ticker", "date", column) if c not in features.columns]
        if missing:
            raise ValueError(f"features lack columns {missing}")
        on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
        if on_day["ticker"].duplicated().any():
            raise ValueError("more than one feature row per ticker on asof")
        tickers = sorted({str(t) for t in on_day["ticker"]})
        if not tickers:
            return pd.Series(dtype=float)
        values = pd.to_numeric(on_day[column], errors="coerce")
        if not bool(values.map(math.isfinite).all()):
            return pd.Series(dtype=float)  # NaN or infinite on any row: no signal or disagreement
        if float(values.max() - values.min()) > AGREE_TOLERANCE:
            return pd.Series(dtype=float)  # the rows disagree: cash
        signal = float(values.iloc[0])
        if signal <= 0.0:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / len(tickers), index=tickers, dtype=float)
