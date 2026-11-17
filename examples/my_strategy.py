"""Example user strategy (illustrative; the Strategy protocol lands in P1-T13).

Copy this file to `<app home>/strategies/` once P1-T13 is merged. The lab registers
every (strategy, params) pair as a trial *before* backtesting it, and counts it in
the Deflated Sharpe Ratio, so adding strategies raises the bar for all of them.
"""

from __future__ import annotations

from typing import ClassVar

import pandas as pd  # type: ignore[import-untyped]


class LowRsiInUptrend:
    id = "U01_low_rsi_uptrend"
    horizons = ("short",)
    params: ClassVar[dict[str, int]] = {"rsi_max": 30, "ma_days": 50, "top_n": 2}

    def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        """Equal-weight the `top_n` lowest-RSI tickers that trade above their MA.

        Uses only rows with date <= asof (point-in-time).
        """
        today = features[features["date"] == asof]
        picks = today[(today["rsi14"] < self.params["rsi_max"]) & (today["close_vs_ma50"] > 0)]
        picks = picks.nsmallest(self.params["top_n"], "rsi14")
        if picks.empty:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / len(picks), index=picks["ticker"])
