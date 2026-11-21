"""S09 medium-term reversal (card P1-T17; plan section 7; docs/strategies.md S09).

Rule: buy the BOTTOM ``n`` tickers by past return, skipping the last month.
The signal is the feature ``ret_6m_skip1m`` (``L_months`` 6: adjusted close 21 sessions back
over the adjusted close 126 sessions back, minus 1) or ``ret_12m_skip1m`` (``L_months`` 12: 21
over 250 sessions back); other ``L_months`` are rejected. Both skip the most
recent month. A NaN signal is not eligible. Fewer than ``n`` eligible tickers give fewer names and
the rest stays in cash; none gives an empty Series. Ties are broken by ticker symbol ascending
(signals rounded to 12 decimals first). Weights are equal, 1/``n`` each. Only feature rows dated
exactly ``asof`` are used (``lookback_sessions`` = 1: the window lives in the feature); the
universe is the tickers in the features on ``asof`` (membership by date is P1-T05).

S09 is the opposite ranking of S08 on the same signal; the lab decides which survives.

Basis: several Vietnamese market studies report reversal rather than momentum at
this horizon. Frozen params:
``{L_months: 6, n: 4}`` (one trial; medium horizon).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

SIGNAL_FEATURES: dict[int, str] = {6: "ret_6m_skip1m", 12: "ret_12m_skip1m"}
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
class S09Reversal(BaseStrategy):
    """Bottom ``n`` by skip-month return. See the module docstring."""

    id = "S09_reversal"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"L_months", "n"}:
            raise ValueError("S09 params must be exactly {L_months, n}")
        months = params["L_months"]
        if not isinstance(months, int) or isinstance(months, bool) or months not in SIGNAL_FEATURES:
            raise ValueError(f"L_months must be one of {sorted(SIGNAL_FEATURES)}")
        n = params["n"]
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        column = SIGNAL_FEATURES[self.params["L_months"]]
        signal = cross_section(features, asof, column).dropna().round(SCORE_DECIMALS)
        ranked = signal.rename("signal").reset_index()
        ranked = ranked.sort_values(["signal", "ticker"], ascending=[True, True])
        names = [str(t) for t in ranked["ticker"].head(self.params["n"])]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["n"], index=names, dtype=float)
