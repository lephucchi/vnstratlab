"""S14 low volatility (P1-T19). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent
from test_strategy_s08 import long_market, run_long_smoke
from vnstratlab.config.models import AppConfig
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s14_low_volatility
from vnstratlab.strategies.builtin.s14_low_volatility import S14LowVolatility
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)
PARAMS = {"window": 60, "n": 4}


def synthetic_section(**over: list[float]) -> pd.DataFrame:
    """Five tickers A..E on one day.

    std_60d  A 0.020  B 0.050  C 0.010  D 0.030  E 0.040
    Lowest first: C (0.010), A (0.020), D (0.030), E (0.040), B (0.050).
    """
    data: dict[str, Any] = {
        "ticker": list("ABCDE"),
        "date": [DAY] * 5,
        "std_60d": [0.02, 0.05, 0.01, 0.03, 0.04],
    }
    data.update(over)
    return pd.DataFrame(data)


def make(**over: Any) -> S14LowVolatility:
    return S14LowVolatility({**PARAMS, **over}, ("medium",))


def test_buys_the_n_lowest_volatility_equal_weight() -> None:
    w = make(n=2).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"C": 0.5, "A": 0.5}
    w4 = make().target_weights(synthetic_section(), ASOF)  # packaged n = 4: B is left out
    assert sorted(w4.index) == ["A", "C", "D", "E"]
    assert w4.tolist() == [0.25] * 4
    assert make(n=1).target_weights(synthetic_section(), ASOF).to_dict() == {"C": 1.0}


def test_fewer_eligible_than_n_leaves_cash_and_nan_is_not_eligible() -> None:
    sec = synthetic_section(std_60d=[np.nan, np.nan, 0.01, np.nan, 0.04])
    w = make().target_weights(sec, ASOF)  # n = 4, two eligible: C, E at 1/4 each
    assert w.to_dict() == {"C": 0.25, "E": 0.25}
    assert w.sum() == pytest.approx(0.5)
    assert make().target_weights(synthetic_section(std_60d=[np.nan] * 5), ASOF).empty
    assert make().target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_tie_break_by_ticker_symbol() -> None:
    sec = pd.DataFrame(
        {"ticker": ["Z", "Y", "X", "W"], "date": [DAY] * 4, "std_60d": [0.1, 0.1, 0.1, 0.2]}
    )
    # X, Y, Z tie at the lowest (W is higher): n 2 -> X and Y, whatever the row order
    assert sorted(make(n=2).target_weights(sec, ASOF).index) == ["X", "Y"]
    assert sorted(make(n=2).target_weights(sec.iloc[::-1], ASOF).index) == ["X", "Y"]
    assert make(n=1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}


def test_only_rows_on_asof_are_used_and_bad_frames_are_refused() -> None:
    old = synthetic_section(std_60d=[0.0] * 5).assign(date=DAY - timedelta(days=30))
    both = pd.concat([old, synthetic_section()], ignore_index=True)
    assert (
        make().target_weights(both, ASOF).equals(make().target_weights(synthetic_section(), ASOF))
    )
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    with pytest.raises(ValueError, match="lack columns"):
        make().target_weights(synthetic_section().drop(columns=["std_60d"]), ASOF)
    assert make().lookback_sessions == 1


@pytest.mark.parametrize(
    "over",
    [
        {"window": 20},
        {"window": 60.0},
        {"window": True},
        {"window": "60"},
        {"n": 0},
        {"n": -1},
        {"n": 2.0},
        {"n": True},
    ],
)
def test_bad_param_values_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"window must|n must"):
        S14LowVolatility({**PARAMS, **over}, ("medium",))


@pytest.mark.parametrize("params", [{}, {"window": 60}, {**PARAMS, "extra": 1}])
def test_bad_param_keys_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="S14 params"):
        S14LowVolatility(params, ("medium",))


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S14_low_volatility") is S14LowVolatility
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S14LowVolatility)
    a = compute_trial_id("S14_low_volatility", PARAMS, "medium", code, "f", "e")
    b = compute_trial_id("S14_low_volatility", {**PARAMS, "n": 3}, "medium", code, "f", "e")
    c = compute_trial_id("S14_low_volatility", PARAMS, "medium", code + "x", "f", "e")
    assert len({a, b, c}) == 3
    doc = s14_low_volatility.__doc__ or ""
    assert "plan section 7" in doc
    assert "Frazzini & Pedersen (2014)" in doc
    assert "std_60d" in doc


@pytest.mark.parametrize("n", [1, 2, 4, 9])
def test_weights_are_long_only_finite_and_at_most_one(n: int) -> None:
    w = make(n=n).target_weights(synthetic_section(), ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(std_60d=[0.0] * 5).assign(date=DAY + timedelta(days=7))
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


def test_deterministic_and_row_order_independent() -> None:
    sec = synthetic_section()
    first = make(n=2).target_weights(sec, ASOF)
    assert make(n=2).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert make(n=2).target_weights(shuffled, ASOF).equals(first)


# ------------------------------------------------------------------ smoke backtest (long market)


def test_smoke_backtest_on_a_long_synthetic_market(engine_cfg: AppConfig) -> None:
    result, targets, sessions = run_long_smoke(make(), engine_cfg)
    assert sessions >= 300
    invested = [t for t in targets.values() if not t.empty]
    assert invested  # std_60d exists after 60 sessions
    assert all(t.sum() <= 1 + 1e-9 and (t >= 0).all() for t in targets.values())
    assert_ledger_consistent(result)
    assert not result.trades.empty


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = long_market(engine_cfg)
    asof = date(2023, 9, 29)
    visible = features[features["date"] <= asof]
    expected = make().target_weights(visible, pd.Timestamp(asof))
    assert not expected.empty  # the comparison is not vacuous
    assert len(visible) < len(features)
    perturbed = prices.copy()
    later = pd.to_datetime(perturbed["date"]).dt.date > asof
    perturbed.loc[later, ["open", "high", "low", "close"]] *= 1.5
    adjusted = perturbed.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = perturbed[["ticker", "date", "high", "low", "close", "volume"]]
    redone = compute_features(adjusted, exec_, sorted(prices["ticker"].unique()), actions=actions)
    got = make().target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
