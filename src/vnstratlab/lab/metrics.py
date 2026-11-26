"""Pure performance metrics over a daily return series (P1-T32; reused by P1-T20).

No I/O. ``returns`` is a per-session simple return series (as ``SimResult.returns``); the year
is 252 sessions. Empty or degenerate inputs give ``nan`` (never a silent 0) except where noted.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

SESSIONS_PER_YEAR = 252
# below this a standard deviation is numerical noise of a constant series, not volatility
_ZERO_VOL = 1e-14


def _values(returns: pd.Series) -> np.ndarray:
    return np.asarray(returns, dtype=float)


def equity_curve(returns: pd.Series) -> pd.Series:
    """Compounded growth of 1 unit: ``prod(1 + r)`` up to each session."""
    return (1.0 + returns.astype(float)).cumprod()


def total_return(returns: pd.Series) -> float:
    """Compounded return over the whole series (0.0 for an empty series)."""
    return float(np.prod(1.0 + _values(returns)) - 1.0)


def cagr(returns: pd.Series) -> float:
    """Compound annual growth rate: ``(1 + total) ** (252 / n) - 1``; nan when empty."""
    n = len(returns)
    if n == 0:
        return math.nan
    growth = 1.0 + total_return(returns)
    if growth <= 0:
        return -1.0
    return float(growth ** (SESSIONS_PER_YEAR / n) - 1.0)


def ann_vol(returns: pd.Series) -> float:
    """Sample standard deviation (ddof 1) times sqrt(252); nan with fewer than 2 sessions."""
    if len(returns) < 2:
        return math.nan
    return float(np.std(_values(returns), ddof=1) * math.sqrt(SESSIONS_PER_YEAR))


def sharpe(returns: pd.Series) -> float:
    """Mean / std (ddof 1) times sqrt(252), risk-free rate 0; nan when the volatility is 0."""
    if len(returns) < 2:
        return math.nan
    values = _values(returns)
    std = float(np.std(values, ddof=1))
    if std < _ZERO_VOL:
        return math.nan
    return float(np.mean(values) / std * math.sqrt(SESSIONS_PER_YEAR))


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough fall of the compounded equity curve, a number <= 0.

    The curve starts at 1.0 before the first session, so a loss from the start counts.
    """
    if len(returns) == 0:
        return math.nan
    curve = np.concatenate(([1.0], np.cumprod(1.0 + _values(returns))))
    peak = np.maximum.accumulate(curve)
    return float(np.min(curve / peak - 1.0))


def avg_turnover(turnover: pd.Series) -> float:
    """Mean per-session turnover over sessions with fills (turnover > 0); 0.0 if none."""
    values = _values(turnover)
    traded = values[values > 0]
    return float(np.mean(traded)) if len(traded) else 0.0
