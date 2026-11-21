"""S01 weekly reversal within the group (card P1-T15; plan section 7; docs/strategies.md S01).

Rule: the feature ``ret_5d_vs_group_median`` is last week's return (5 good sessions, adjusted
close) minus the median of that return over the universe on the same day. Buy the ``n`` tickers
with the most negative value (the biggest losers vs the group), equal weight 1/``n``; fewer than
``n`` eligible tickers leave the rest in cash and none gives an empty Series. A ticker with a NaN
value is not eligible. The sign is not filtered: the ``n`` lowest values are bought even when
they are positive (a strong week for the whole group). Ties (after rounding to 12 decimals, so
float noise cannot break an exact tie) are broken by ticker symbol, ascending. Only feature rows
dated exactly ``asof`` are used; the universe is the tickers in the features on ``asof``
(membership by date is P1-T05).

Basis: Jegadeesh (1990), short-term reversal. Sensitive to costs, so read it with the x2 cost
stress test. Frozen params: ``{n: 2}`` and ``{n: 3}`` (one trial each; short horizon only).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

FEATURE = "ret_5d_vs_group_median"
SCORE_DECIMALS = 12


def cross_section(features: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """The feature rows dated exactly ``asof``, one per ticker, indexed by ticker."""
    missing = [c for c in ("ticker", "date", FEATURE) if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
    if on_day["ticker"].duplicated().any():
        raise ValueError("more than one feature row per ticker on asof")
    return on_day.set_index("ticker")


@register_strategy
class S01WeeklyReversal(BaseStrategy):
    """Buy the ``n`` biggest weekly losers vs the group median. See the module docstring."""

    id = "S01_weekly_reversal"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"n"}:
            raise ValueError("S01 params must be exactly {n}")
        n = params["n"]
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        section = cross_section(features, asof)
        values = pd.to_numeric(section[FEATURE], errors="coerce").dropna()
        ranked = values.round(SCORE_DECIMALS).rename("value").reset_index()
        ranked = ranked.sort_values(["value", "ticker"], ascending=[True, True])
        names = [str(t) for t in ranked["ticker"].head(self.params["n"])]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["n"], index=names, dtype=float)
