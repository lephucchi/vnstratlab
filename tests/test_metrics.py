"""Pure metrics (P1-T32). Every expected number is computed by hand in the comment."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from vnstratlab.lab.metrics import (
    ann_vol,
    avg_turnover,
    cagr,
    max_drawdown,
    sharpe,
    total_return,
)


def series(*values: float) -> pd.Series:
    return pd.Series(list(values), dtype=float)


def test_total_return_compounds() -> None:
    # 1.1 * 0.9 - 1 = -0.01
    assert total_return(series(0.1, -0.1)) == pytest.approx(-0.01)
    assert total_return(series()) == 0.0


def test_cagr_on_a_known_path() -> None:
    # two years (504 sessions) growing 1.44x: (1.44) ** (252 / 504) - 1 = 0.2
    daily = 1.44 ** (1 / 504) - 1
    assert cagr(pd.Series([daily] * 504)) == pytest.approx(0.2)
    # half a year of doubling: 2 ** 2 - 1 = 3
    assert cagr(pd.Series([2 ** (1 / 126) - 1] * 126)) == pytest.approx(3.0)
    assert math.isnan(cagr(series()))
    assert cagr(series(-1.0, 0.5)) == -1.0  # wiped out


def test_ann_vol() -> None:
    # +-0.01 alternating: sample std = 0.01 * sqrt(4 / 3); annualised x sqrt(252)
    expected = 0.01 * math.sqrt(4 / 3) * math.sqrt(252)
    assert ann_vol(series(0.01, -0.01, 0.01, -0.01)) == pytest.approx(expected)
    assert math.isnan(ann_vol(series(0.01)))


def test_sharpe_and_zero_vol_is_nan() -> None:
    # [0.02, 0]: mean 0.01, sample std 0.02 / sqrt(2); 0.01 / 0.0141421 * sqrt(252) = 11.2250
    assert sharpe(series(0.02, 0.0)) == pytest.approx(0.01 / (0.02 / math.sqrt(2)) * math.sqrt(252))
    assert math.isnan(sharpe(series(0.01, 0.01, 0.01)))
    assert math.isnan(sharpe(series(0.0, 0.0, 0.0)))
    assert math.isnan(sharpe(series(0.01)))


def test_max_drawdown_on_known_paths() -> None:
    # equity 1, 1.5, 0.75, 0.9: peak 1.5, trough 0.75 -> -0.5
    assert max_drawdown(series(0.5, -0.5, 0.2)) == pytest.approx(-0.5)
    # a loss from the start counts against the initial capital: 1, 0.8, 0.88 -> -0.2
    assert max_drawdown(series(-0.2, 0.1)) == pytest.approx(-0.2)
    assert max_drawdown(series(0.1, 0.1)) == 0.0
    assert math.isnan(max_drawdown(series()))


def test_avg_turnover_counts_sessions_with_fills_only() -> None:
    # sessions with fills: 0.2 and 0.4 -> 0.3 (the zero sessions do not dilute it)
    assert avg_turnover(series(0.0, 0.2, 0.0, 0.4)) == pytest.approx(0.3)
    assert avg_turnover(series(0.0, 0.0)) == 0.0
    assert avg_turnover(series()) == 0.0
