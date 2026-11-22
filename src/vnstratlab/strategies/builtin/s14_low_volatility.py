"""S14 low volatility (card P1-T19; plan section 7; docs/strategies.md S14).

Rule: buy the ``n`` tickers with the LOWEST 60-session volatility, equal weight 1/``n`` each.
The signal is the feature ``std_60d`` (standard deviation of the daily returns over 60 sessions)
on ``asof``; ``window`` must be 60 (the feature's window), other values are rejected. A NaN signal
is not eligible. Fewer than ``n`` eligible tickers give fewer names and the rest stays in cash;
none gives an empty Series. Ties are broken by ticker symbol ascending (signals rounded to 12
decimals first). Only feature rows dated exactly ``asof`` are used (``lookback_sessions`` = 1: the
window lives in the feature); the universe is the tickers in the features on ``asof``
(membership by date is P1-T05).

Basis: Frazzini & Pedersen (2014), betting against beta (low-risk stocks earn more per unit of
risk). Frozen params: ``{window: 60, n: 4}`` (one trial; medium horizon).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

SIGNAL_FEATURE = "std_60d"
FROZEN_WINDOW = 60
SCORE_DECIMALS = 12


def cross_section(features: pd.DataFrame, asof: pd.Timestamp, column: str) -> pd.Series:
    """The ``column`` values of the feature rows dated exactly ``asof``, indexed by ticker."""
    required = ("ticker", "date", column)
    missing = [c for c in required if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
    if on_day["ticker"].duplicated().any():
        raise ValueError("more than one feature row per ticker on asof")
    return pd.to_numeric(on_day.set_index("ticker")[column], errors="coerce")


@register_strategy
class S14LowVolatility(BaseStrategy):
    """Bottom ``n`` by 60-session volatility. See the module docstring."""

    id = "S14_low_volatility"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"window", "n"}:
            raise ValueError("S14 params must be exactly {window, n}")
        window = params["window"]
        if not isinstance(window, int) or isinstance(window, bool) or window != FROZEN_WINDOW:
            raise ValueError(f"window must be {FROZEN_WINDOW} (the std_60d feature)")
        n = params["n"]
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        signal = cross_section(features, asof, SIGNAL_FEATURE).dropna().round(SCORE_DECIMALS)
        ranked = signal.rename("signal").reset_index()
        ranked = ranked.sort_values(["signal", "ticker"], ascending=[True, True])
        names = [str(t) for t in ranked["ticker"].head(self.params["n"])]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["n"], index=names, dtype=float)
