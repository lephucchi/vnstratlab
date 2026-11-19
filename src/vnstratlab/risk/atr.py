"""Wilder's average true range (pure; causal: row ``t`` only uses rows ``<= t``)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

ATR_WINDOW = 14


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = ATR_WINDOW,
    ex_factor: Sequence[float] | None = None,
) -> pd.Series:
    """Wilder ATR of one ticker, aligned to the input index (rows in date order).

    ``TR_0 = high_0 - low_0``; ``TR_t = max(high_t - low_t, |high_t - close_{t-1}|,
    |low_t - close_{t-1}|)``. The first value (row ``n - 1``) is the mean of the first ``n`` true
    ranges; afterwards ``ATR_t = (ATR_{t-1} * (n - 1) + TR_t) / n``. Rows before ``n - 1`` are NaN.
    Every value depends only on rows up to and including its own, so truncating the data after a
    date leaves the ATR at that date unchanged (no lookahead).

    ``ex_factor`` (per row, default all 1): ``1 + ratio`` on the ex-date row of a stock dividend
    or bonus issue. On such a row the previous close and the accumulated ATR / true ranges are
    divided by the factor, so the mechanical price drop is not counted as volatility and the ATR
    is in the post-event share basis. Factors only ever act on their own row and later ones.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    highs = [float(v) for v in high]
    lows = [float(v) for v in low]
    closes = [float(v) for v in close]
    if not len(highs) == len(lows) == len(closes):
        raise ValueError("high, low and close must have the same length")
    factors = [1.0] * len(highs) if ex_factor is None else [float(f) for f in ex_factor]
    if len(factors) != len(highs):
        raise ValueError("ex_factor must have the same length as the prices")
    out: list[float] = []
    trs: list[float] = []
    value = math.nan
    for i, (h, lo) in enumerate(zip(highs, lows, strict=True)):
        f = factors[i]
        if f != 1.0:
            trs = [x / f for x in trs]
            value /= f  # NaN stays NaN
        tr = h - lo
        if i > 0:
            prev = closes[i - 1] / f
            tr = max(tr, abs(h - prev), abs(lo - prev))
        trs.append(tr)
        if i == n - 1:
            value = sum(trs) / n
        elif i >= n:
            value = (value * (n - 1) + tr) / n
        out.append(value if i >= n - 1 else math.nan)
    return pd.Series(out, index=close.index, dtype=float, name="atr")
