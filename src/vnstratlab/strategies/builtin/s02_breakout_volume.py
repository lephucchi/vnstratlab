"""S02 20-day breakout with volume (card P1-T15; plan section 7; docs/strategies.md S02).

Rule: a ticker signals when its adjusted close is above the highest adjusted CLOSE of the previous
``lookback`` good sessions (feature ``close_20d_break`` = 1, added in features-v2; the older
``high_20d_break`` compares with prior HIGHS and is not used here) AND ``vol_vs_avg20`` (volume
over its 20-session average) is strictly above ``vol_mult``. A NaN in either input counts as "no".
Equal weight across the signals, at most ``max_n`` of them: ranked by ``vol_vs_avg20`` descending
(rounded to 12 decimals, then ticker symbol ascending) and 1/``max_n`` each; fewer signals than
``max_n`` leave the rest in cash and none gives an empty Series. Only feature rows dated exactly
``asof`` are used; the universe is the tickers in the features on ``asof`` (P1-T05).

``lookback`` must be 20: it is the window of the feature, so other values are rejected.

Basis: Brock, Lakonishok & LeBaron (1992), trading-range breakout. Breakouts often open near the
ceiling, so ceiling-blocked buys matter (check ``order_events``). Frozen params:
``{lookback: 20, vol_mult: 1.5, max_n: 3}`` (the only set; short horizon).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

LOOKBACK = 20  # window of the feature close_20d_break
SCORE_DECIMALS = 12
_REQUIRED = ("ticker", "date", "close_20d_break", "vol_vs_avg20")


def cross_section(features: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """The feature rows dated exactly ``asof``, one per ticker, indexed by ticker."""
    missing = [c for c in _REQUIRED if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
    if on_day["ticker"].duplicated().any():
        raise ValueError("more than one feature row per ticker on asof")
    return on_day.set_index("ticker")


@register_strategy
class S02BreakoutVolume(BaseStrategy):
    """Close-based 20-day breakout confirmed by volume. See the module docstring."""

    id = "S02_breakout_volume"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"lookback", "vol_mult", "max_n"}:
            raise ValueError("S02 params must be exactly {lookback, vol_mult, max_n}")
        lookback = params["lookback"]
        if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback != LOOKBACK:
            raise ValueError(
                f"lookback must be {LOOKBACK}: it is the window of the close_20d_break feature"
            )
        mult = params["vol_mult"]
        if (
            not isinstance(mult, Real)
            or isinstance(mult, bool)
            or not math.isfinite(mult)
            or mult <= 0
        ):
            raise ValueError("vol_mult must be a positive finite number")
        max_n = params["max_n"]
        if not isinstance(max_n, int) or isinstance(max_n, bool) or max_n < 1:
            raise ValueError("max_n must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        section = cross_section(features, asof)
        broke = pd.to_numeric(section["close_20d_break"], errors="coerce").fillna(0.0) > 0
        volume = pd.to_numeric(section["vol_vs_avg20"], errors="coerce")
        signal = broke & (volume > self.params["vol_mult"])  # NaN volume compares False
        picked = volume[signal].round(SCORE_DECIMALS).rename("volume").reset_index()
        picked = picked.sort_values(["volume", "ticker"], ascending=[False, True])
        names = [str(t) for t in picked["ticker"].head(self.params["max_n"])]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["max_n"], index=names, dtype=float)
