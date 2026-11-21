"""S00 composite score, 4-block v1 (card P1-T14; plan section 7; docs/strategies.md S00).

Rule (design doc "Layer 1"): cross-sectional percentile rank of blocks, weighted sum -> score;
buy the top ``top_n`` that also show a trigger. Basis: design doc. Risk: many moving parts, so
each weight set is one trial and nothing is tuned.

**4 blocks, not 5 (owner decision 2026-11-21).** The design has a fifth block, valuation (P/B
gap). Fundamentals are unavailable (GAP-11, P1-T07), so v1 omits it. A future 5-block version is
a code change and therefore a NEW trial (new ``strategy_code_hash`` -> new ``trial_id``), not an
edit of this one.

Blocks, each the mean of the cross-sectional percentile ranks (``rank(pct=True)``, ties averaged,
1.0 = best, over the tickers that have the component on ``asof``) of its components:

* trend: ``close_vs_ma20``, ``close_vs_ma50``, ``ret_60d``;
* relative strength: ``rs_20d_vs_group_median`` (chosen over ``rs_20d_rank``: it is the same
  ordering, and the block ranks it like every other component);
* mean reversion: the cross-sectional z-score of ``rsi_14`` (ddof 1; 0 when the spread is 0),
  negated, then ranked: lower RSI = higher score;
* volume: ``vol_vs_avg20``.

Missing data: a NaN component is skipped inside its block; a ticker whose whole block is NaN is
not eligible. Score = sum of weight x block rank, rounded to 12 decimals so that float noise
cannot break an exact tie.

Trigger: breakout (``high_20d_break`` true) OR oversold-in-uptrend (``rsi_14 < 35`` and
``close_vs_ma50 > 0``); a NaN input is "no". Buy the ``top_n`` best-scored eligible tickers with a
trigger, 1/``top_n`` each; fewer qualifiers mean fewer names and the rest stays in cash (none:
an empty Series). Ties are broken by ticker symbol, ascending. The universe is the tickers in the
features on ``asof`` (membership by date is P1-T05).

Frozen constants (changing any of them edits this module and so makes a new trial): block weights
and ``RSI_OVERSOLD``. Params name the weight set (``equal`` / ``trend_heavy``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from vnstratlab.strategies.base import BaseStrategy
from vnstratlab.strategies.registry import register_strategy

BLOCKS: dict[str, tuple[str, ...]] = {
    "trend": ("close_vs_ma20", "close_vs_ma50", "ret_60d"),
    "relative_strength": ("rs_20d_vs_group_median",),
    "mean_reversion": ("rsi_14",),
    "volume": ("vol_vs_avg20",),
}
WEIGHT_SETS: dict[str, dict[str, float]] = {
    "equal": {"trend": 0.25, "relative_strength": 0.25, "mean_reversion": 0.25, "volume": 0.25},
    "trend_heavy": {"trend": 0.4, "relative_strength": 0.2, "mean_reversion": 0.2, "volume": 0.2},
}
RSI_OVERSOLD = 35.0
SCORE_DECIMALS = 12
_REQUIRED = (
    "ticker",
    "date",
    "close_vs_ma20",
    "close_vs_ma50",
    "ret_60d",
    "rs_20d_vs_group_median",
    "rsi_14",
    "vol_vs_avg20",
    "high_20d_break",
)


def _rank(values: pd.Series) -> pd.Series:
    return values.rank(pct=True, method="average")


def _negated_zscore(values: pd.Series) -> pd.Series:
    std = values.std(ddof=1)
    centred = values - values.mean()
    if not np.isfinite(std) or std == 0.0:
        return centred * 0.0  # no spread: every ticker ties (NaN stays NaN)
    return -centred / std


def cross_section(features: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """The feature rows dated exactly ``asof``, one per ticker, indexed by ticker."""
    missing = [c for c in _REQUIRED if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    on_day = features[pd.to_datetime(features["date"]) == pd.Timestamp(asof).normalize()]
    if on_day["ticker"].duplicated().any():
        raise ValueError("more than one feature row per ticker on asof")
    return on_day.set_index("ticker")


def block_ranks(section: pd.DataFrame) -> pd.DataFrame:
    """Block ranks per ticker (columns of ``BLOCKS``); NaN where the whole block is missing."""
    blocks: dict[str, pd.Series] = {}
    for name, columns in BLOCKS.items():
        parts = []
        for column in columns:
            values = section[column].astype(float)
            if column == "rsi_14":
                values = _negated_zscore(values)
            parts.append(_rank(values))
        blocks[name] = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    return pd.DataFrame(blocks, index=section.index)


def trigger(section: pd.DataFrame) -> pd.Series:
    """Breakout or oversold-in-uptrend; NaN inputs count as False."""
    breakout = pd.to_numeric(section["high_20d_break"], errors="coerce").fillna(0.0) > 0
    oversold = (section["rsi_14"] < RSI_OVERSOLD) & (section["close_vs_ma50"] > 0)
    return breakout | oversold


@register_strategy
class S00Composite(BaseStrategy):
    """S00 composite score, 4 blocks (valuation omitted, GAP-11). See the module docstring."""

    id = "S00_composite"

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"weights", "top_n"}:
            raise ValueError("S00 params must be exactly {weights, top_n}")
        if params["weights"] not in WEIGHT_SETS:
            raise ValueError(f"weights must be one of {sorted(WEIGHT_SETS)}")
        top_n = params["top_n"]
        if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
            raise ValueError("top_n must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        section = cross_section(features, asof)
        if section.empty:
            return pd.Series(dtype=float)
        ranks = block_ranks(section)
        eligible = ranks.notna().all(axis=1) & trigger(section)
        weights = WEIGHT_SETS[self.params["weights"]]
        score = pd.Series(0.0, index=ranks.index)
        for name, weight in weights.items():
            score = score + ranks[name] * weight
        picked = pd.DataFrame({"score": score.round(SCORE_DECIMALS)}).loc[eligible]
        picked = picked.reset_index().sort_values(["score", "ticker"], ascending=[False, True])
        names = [str(t) for t in picked["ticker"].head(self.params["top_n"])]
        if not names:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / self.params["top_n"], index=names, dtype=float)
