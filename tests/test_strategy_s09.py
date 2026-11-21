"""S09 medium-term reversal (P1-T17). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent
from test_strategy_s08 import (
    ASOF,
    DAY,
    SIX,
    TWELVE,
    long_market,
    run_long_smoke,
    synthetic_section,
)
from vnstratlab.config.models import AppConfig
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s09_reversal
from vnstratlab.strategies.builtin.s08_momentum import S08Momentum
from vnstratlab.strategies.builtin.s09_reversal import S09Reversal
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)


def make(params: dict[str, Any] | None = None, **over: Any) -> S09Reversal:
    return S09Reversal({**(params or SIX), **over}, ("medium",))


def test_buys_the_bottom_n_equal_weight() -> None:
    # ret_6m_skip1m A .30 B -.10 C .55 D .05 E .20: bottom 2 are B (-.10), D (.05)
    w = make(SIX, n=2).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"B": 0.5, "D": 0.5}
    # n 4: everything but the strongest (C)
    w4 = make(SIX).target_weights(synthetic_section(), ASOF)
    assert sorted(w4.index) == ["A", "B", "D", "E"]
    assert w4.tolist() == [0.25] * 4


def test_picks_the_opposite_end_of_the_same_data_as_s08() -> None:
    sec = synthetic_section()
    top = S08Momentum({"L_months": 6, "n": 2}, ("medium",)).target_weights(sec, ASOF)
    bottom = make(SIX, n=2).target_weights(sec, ASOF)
    assert set(top.index) == {"C", "A"}
    assert set(bottom.index) == {"B", "D"}
    assert not set(top.index) & set(bottom.index)
    # with n = the whole cross-section both hold everyone
    assert set(make(SIX, n=5).target_weights(sec, ASOF).index) == set("ABCDE")
    # 12 months: S08 takes D, B; S09 takes A (-.20), E (0.0)
    assert set(make(TWELVE, n=2).target_weights(sec, ASOF).index) == {"A", "E"}


def test_fewer_eligible_than_n_leaves_cash_and_nan_is_not_eligible() -> None:
    sec = synthetic_section(ret_6m_skip1m=[np.nan, np.nan, 0.55, np.nan, 0.20])
    w = make(SIX).target_weights(sec, ASOF)
    assert w.to_dict() == {"E": 0.25, "C": 0.25}
    assert w.sum() == pytest.approx(0.5)
    assert make(SIX).target_weights(synthetic_section(ret_6m_skip1m=[np.nan] * 5), ASOF).empty
    assert make(SIX).target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_tie_break_by_ticker_symbol() -> None:
    sec = pd.DataFrame(
        {
            "ticker": ["Z", "Y", "X", "W"],
            "date": [DAY] * 4,
            "ret_6m_skip1m": [-0.2, -0.2, -0.2, 0.1],
            "ret_12m_skip1m": [0.0] * 4,
        }
    )
    assert sorted(make(SIX, n=2).target_weights(sec, ASOF).index) == ["X", "Y"]
    assert sorted(make(SIX, n=2).target_weights(sec.iloc[::-1], ASOF).index) == ["X", "Y"]
    assert make(SIX, n=1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}


@pytest.mark.parametrize(
    "over", [{"L_months": 3}, {"L_months": True}, {"L_months": 12.0}, {"n": 0}, {"n": True}]
)
def test_bad_param_values_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"L_months must|n must"):
        S09Reversal({**SIX, **over}, ("medium",))


@pytest.mark.parametrize("params", [{}, {"n": 4}, {**SIX, "extra": 1}])
def test_bad_param_keys_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="S09 params"):
        S09Reversal(params, ("medium",))


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S09_reversal") is S09Reversal
    assert isinstance(make(), Strategy)
    assert make().lookback_sessions == 1
    code = strategy_code_hash(S09Reversal)
    assert code != strategy_code_hash(S08Momentum)
    a = compute_trial_id("S09_reversal", SIX, "medium", code, "f", "e")
    b = compute_trial_id("S09_reversal", SIX, "medium", code + "x", "f", "e")
    assert a != b
    doc = s09_reversal.__doc__ or ""
    assert "plan section 7" in doc
    assert "opposite ranking of S08" in doc
    assert "the lab decides which survives" in doc
    assert "Vietnamese" in doc


@pytest.mark.parametrize("params", [SIX, TWELVE])
@pytest.mark.parametrize("n", [1, 2, 4, 9])
def test_weights_are_long_only_finite_and_at_most_one(params: dict[str, Any], n: int) -> None:
    w = make(params, n=n).target_weights(synthetic_section(), ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(ret_6m_skip1m=[-5.0] * 5).assign(date=DAY + timedelta(days=7))
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))
    old = synthetic_section(ret_6m_skip1m=[-9.0] * 5).assign(date=DAY - timedelta(days=30))
    both = pd.concat([old, clean], ignore_index=True)
    assert make().target_weights(both, ASOF).equals(make().target_weights(clean, ASOF))


def test_deterministic_and_row_order_independent() -> None:
    sec = synthetic_section()
    first = make(SIX, n=2).target_weights(sec, ASOF)
    assert make(SIX, n=2).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert make(SIX, n=2).target_weights(shuffled, ASOF).equals(first)


def test_smoke_backtest_on_a_long_synthetic_market(engine_cfg: AppConfig) -> None:
    result, targets, sessions = run_long_smoke(make(SIX), engine_cfg)
    assert sessions >= 300
    assert any(not t.empty for t in targets.values())
    assert all(t.sum() <= 1 + 1e-9 and (t >= 0).all() for t in targets.values())
    assert_ledger_consistent(result)
    assert not result.trades.empty


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = long_market(engine_cfg)
    asof = date(2023, 9, 29)
    visible = features[features["date"] <= asof]
    expected = make(SIX).target_weights(visible, pd.Timestamp(asof))
    assert not expected.empty  # the comparison is not vacuous
    perturbed = prices.copy()
    later = pd.to_datetime(perturbed["date"]).dt.date > asof
    perturbed.loc[later, ["open", "high", "low", "close"]] *= 1.5
    adjusted = perturbed.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = perturbed[["ticker", "date", "high", "low", "close", "volume"]]
    redone = compute_features(adjusted, exec_, sorted(prices["ticker"].unique()), actions=actions)
    got = make(SIX).target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)


def test_bad_frames_are_refused() -> None:
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    with pytest.raises(ValueError, match="lack columns"):
        make().target_weights(synthetic_section().drop(columns=["ret_6m_skip1m"]), ASOF)
