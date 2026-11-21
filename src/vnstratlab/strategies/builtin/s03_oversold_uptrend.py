"""S03 oversold in an uptrend (card P1-T15; plan section 7; docs/strategies.md S03).

Rule: RSI(``rsi_len``) < ``rsi_max`` (strictly) while the close is above its 50-session average
(``close_vs_ma50`` > 0; ``ma_len`` must be 50). ``rsi_len`` 2 reads the feature ``rsi_2`` and 14
reads ``rsi_14`` (Wilder RSI on the adjusted close); other lengths are rejected. A NaN input
counts as "no". Buy up to ``max_n`` of the qualifiers with the lowest RSI (rounded to 12
decimals, then ticker symbol ascending), 1/``max_n`` each; fewer qualifiers leave the rest in
cash and none gives an empty Series. Only feature rows dated exactly ``asof`` are used; the
universe is the tickers in the features on ``asof`` (membership by date is P1-T05).

Basis: Jegadeesh (1990), short-term reversal; Moskowitz, Ooi & Pedersen (2012) for the trend
filter. Frozen params: ``{rsi_len: 2, rsi_max: 10, ma_len: 50, max_n: 3}`` and
``{rsi_len: 14, rsi_max: 30, ma_len: 50, max_n: 3}`` (one trial each; short horizon).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

RSI_FEATURES: dict[int, str] = {2: "rsi_2", 14: "rsi_14"}
MA_LEN = 50  # window of the feature close_vs_ma50
SCORE_DECIMALS = 12


def cross_section(features: pd.DataFrame, asof: pd.Timestamp, rsi_column: str) -> pd.DataFrame:
    """The feature rows dated exactly ``asof``, one per ticker, indexed by ticker."""
    required = ("ticker", "date", rsi_column, "close_vs_ma50")
    missing = [c for c in required if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
    if on_day["ticker"].duplicated().any():
        raise ValueError("more than one feature row per ticker on asof")
    return on_day.set_index("ticker")


@register_strategy
class S03OversoldUptrend(BaseStrategy):
    """Low RSI while above the 50-session average. See the module docstring."""

    id = "S03_oversold_uptrend"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"rsi_len", "rsi_max", "ma_len", "max_n"}:
            raise ValueError("S03 params must be exactly {rsi_len, rsi_max, ma_len, max_n}")
        rsi_len = params["rsi_len"]
        if not isinstance(rsi_len, int) or isinstance(rsi_len, bool) or rsi_len not in RSI_FEATURES:
            raise ValueError(f"rsi_len must be one of {sorted(RSI_FEATURES)}")
        rsi_max = params["rsi_max"]
        if (
            not isinstance(rsi_max, Real)
            or isinstance(rsi_max, bool)
            or not math.isfinite(float(rsi_max))
            or not 0 < float(rsi_max) <= 100
        ):
            raise ValueError("rsi_max must be a number in (0, 100]")
        ma_len = params["ma_len"]
        if not isinstance(ma_len, int) or isinstance(ma_len, bool) or ma_len != MA_LEN:
            raise ValueError(f"ma_len must be {MA_LEN}: it is the window of close_vs_ma50")
        max_n = params["max_n"]
        if not isinstance(max_n, int) or isinstance(max_n, bool) or max_n < 1:
            raise ValueError("max_n must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        column = RSI_FEATURES[self.params["rsi_len"]]
        section = cross_section(features, asof, column)
        rsi = pd.to_numeric(section[column], errors="coerce")
        trend = pd.to_numeric(section["close_vs_ma50"], errors="coerce")
        qualifies = (rsi < self.params["rsi_max"]) & (trend > 0)  # NaN compares False
        picked = rsi[qualifies].round(SCORE_DECIMALS).rename("rsi").reset_index()
        picked = picked.sort_values(["rsi", "ticker"], ascending=[True, True])
        names = [str(t) for t in picked["ticker"].head(self.params["max_n"])]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["max_n"], index=names, dtype=float)
