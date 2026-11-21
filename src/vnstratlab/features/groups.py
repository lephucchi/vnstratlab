"""Feature definitions: windows, column groups and the per-ticker formulas (pure, causal).

Every function takes arrays of ONE ticker in date order and returns arrays of the same length in
which element ``t`` uses elements ``<= t`` only (trailing windows, never centred, no negative
shifts). A window is NaN until it is full (``min_periods == window``); nothing is back-filled.
Window lengths are in AVAILABLE (stored, good) sessions of the ticker, never calendar days.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pandas as pd

from vnstratlab.risk.atr import ATR_WINDOW

FloatArray = npt.NDArray[np.float64]

# ---------------------------------------------------------------- windows (sessions)
MA_SHORT = 20
MA_LONG = 50
RET_WINDOWS = (5, 20, 60, 120, 250)
MOM_LOOKBACK = 250  # ret_12m_skip1m: close[t - 21] / close[t - 250] - 1
MOM_SKIP = 21
YEAR_WINDOW = 250  # 52-week high / low
BREAK_WINDOW = 20  # high_20d_break: close above the highest high of the 20 sessions before t
# close_20d_break (features-v2, S02) uses the same window over the previous CLOSES
RSI_LONG = 14
RSI_SHORT = 2
Z_WINDOW = 20
STD_SHORT = 20
STD_LONG = 60
VOLUME_WINDOW = 20
VALUE_WINDOW = 20
RS_WINDOW = 20  # relative strength vs the group (ret_20d)
INDEX_MA = 50  # equal-weight index moving average (sessions of the index)
INDEX_RET = 250  # group_ret_12m (sessions of the index)

WINDOWS: dict[str, int] = {
    "ma_short": MA_SHORT,
    "ma_long": MA_LONG,
    "mom_lookback": MOM_LOOKBACK,
    "mom_skip": MOM_SKIP,
    "year": YEAR_WINDOW,
    "break": BREAK_WINDOW,
    "rsi_long": RSI_LONG,
    "rsi_short": RSI_SHORT,
    "z": Z_WINDOW,
    "atr": ATR_WINDOW,
    "std_short": STD_SHORT,
    "std_long": STD_LONG,
    "volume": VOLUME_WINDOW,
    "value": VALUE_WINDOW,
    "rs": RS_WINDOW,
    "index_ma": INDEX_MA,
    "index_ret": INDEX_RET,
    **{f"ret_{n}": n for n in RET_WINDOWS},
}

# ---------------------------------------------------------------- columns
FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "trend_momentum": (
        "close_vs_ma20",
        "close_vs_ma50",
        "ret_5d",
        "ret_20d",
        "ret_60d",
        "ret_120d",
        "ret_250d",
        "ret_12m_skip1m",
        "dist_52w_high",
        "dist_52w_low",
        "high_20d_break",
        "close_20d_break",
    ),
    "relative_strength": ("rs_20d_vs_group_median", "rs_20d_rank"),
    "mean_reversion": ("rsi_14", "rsi_2", "z_ma20", "ret_5d_vs_group_median"),
    "volatility": ("atr_14", "std_20d", "std_60d"),
    "volume_liquidity": ("vol_vs_avg20", "value_traded_20d"),
    "market_context": ("group_ew_vs_ma50", "group_breadth_ma50", "group_ret_12m"),
}
FEATURE_COLUMNS: tuple[str, ...] = tuple(c for cols in FEATURE_GROUPS.values() for c in cols)


def _series(values: FloatArray) -> pd.Series:
    return pd.Series(values, dtype=float)


def rolling_mean(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def rolling_std(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).std(ddof=1)


def wilder_rsi(close: FloatArray, n: int) -> FloatArray:
    """Wilder RSI. The first value (row ``n``) uses the plain mean of the first ``n`` gains and
    losses; afterwards ``avg = (avg * (n - 1) + x) / n``. ``RSI = 100`` when the average loss is
    0 (50 when the average gain is 0 too). Rows before ``n`` are NaN; a NaN close restarts it."""
    out = np.full(len(close), math.nan)
    avg_gain = avg_loss = math.nan
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(close)):
        change = close[i] - close[i - 1]
        if math.isnan(change):
            gains, losses = [], []
            avg_gain = avg_loss = math.nan
            continue
        gain, loss = max(change, 0.0), max(-change, 0.0)
        if math.isnan(avg_gain):
            gains.append(gain)
            losses.append(loss)
            if len(gains) < n:
                continue
            avg_gain, avg_loss = sum(gains) / n, sum(losses) / n
        else:
            avg_gain = (avg_gain * (n - 1) + gain) / n
            avg_loss = (avg_loss * (n - 1) + loss) / n
        if avg_loss == 0.0:
            out[i] = 50.0 if avg_gain == 0.0 else 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def price_features(
    adj_close: FloatArray,
    adj_high: FloatArray,
    exec_close: FloatArray,
    exec_high: FloatArray,
    exec_low: FloatArray,
    exec_volume: FloatArray,
    basis: FloatArray,
    atr: FloatArray,
) -> dict[str, FloatArray]:
    """Per-ticker features, aligned to the good sessions.

    Return features and ratios read the ADJUSTED arrays (``adj_close`` / ``adj_high``). Level and
    liquidity features read the EXECUTION arrays (NaN where the execution series has no row).
    ``basis`` is the running product of stock ex-date factors (``1 + ratio`` on the ex-date row,
    causal): a past execution price is restated into the basis of day ``t`` as ``price *
    basis[s] / basis[t]`` and a past share count as ``volume * basis[t] / basis[s]``, so the 52-week
    distances and the volume ratio carry no artificial step at a stock event. Value traded
    (``close * volume``) is invariant to it. ``atr`` is the ATR-14 of the execution series.
    """
    c = _series(adj_close)
    out: dict[str, FloatArray] = {}

    def put(name: str, values: pd.Series) -> None:
        out[name] = values.to_numpy(dtype=np.float64)

    put("close_vs_ma20", c / rolling_mean(c, MA_SHORT) - 1.0)
    put("close_vs_ma50", c / rolling_mean(c, MA_LONG) - 1.0)
    for n in RET_WINDOWS:
        put(f"ret_{n}d", c / c.shift(n) - 1.0)
    put("ret_12m_skip1m", c.shift(MOM_SKIP) / c.shift(MOM_LOOKBACK) - 1.0)

    # 52-week distances on the execution series, restated into today's share basis
    b = _series(basis)
    ec = _series(exec_close)
    hi = (_series(exec_high) * b).rolling(YEAR_WINDOW, min_periods=YEAR_WINDOW).max()
    lo = (_series(exec_low) * b).rolling(YEAR_WINDOW, min_periods=YEAR_WINDOW).min()
    put("dist_52w_high", ec * b / hi - 1.0)
    put("dist_52w_low", ec * b / lo - 1.0)

    prior_high = _series(adj_high).shift(1).rolling(BREAK_WINDOW, min_periods=BREAK_WINDOW).max()
    brk = (c > prior_high).astype(float)
    put("high_20d_break", brk.where(prior_high.notna()))
    # close-based breakout (S02, Brock et al. 1992): adjusted close above the highest adjusted
    # close of the previous BREAK_WINDOW good sessions; NaN until those sessions exist
    prior_close = c.shift(1).rolling(BREAK_WINDOW, min_periods=BREAK_WINDOW).max()
    put("close_20d_break", (c > prior_close).astype(float).where(prior_close.notna()))

    put("rsi_14", _series(wilder_rsi(adj_close, RSI_LONG)))
    put("rsi_2", _series(wilder_rsi(adj_close, RSI_SHORT)))
    z_std = rolling_std(c, Z_WINDOW)
    put("z_ma20", (c - rolling_mean(c, Z_WINDOW)) / z_std)

    out["atr_14"] = atr
    daily = c / c.shift(1) - 1.0
    put("std_20d", rolling_std(daily, STD_SHORT))
    put("std_60d", rolling_std(daily, STD_LONG))

    shares = _series(exec_volume) / b
    put("vol_vs_avg20", shares / rolling_mean(shares, VOLUME_WINDOW))
    put("value_traded_20d", rolling_mean(ec * _series(exec_volume), VALUE_WINDOW))

    # helpers for the cross-section (not stored)
    out["_ret_1d"] = np.asarray(daily, dtype=np.float64)
    ma50 = rolling_mean(c, MA_LONG)
    above = (c > ma50).astype(float)
    out["_above_ma50"] = np.asarray(above.where(ma50.notna()), dtype=np.float64)
    return out
