"""S03 oversold in an uptrend (P1-T15). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent, run_smoke, synthetic_market
from vnstratlab.config.models import AppConfig
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s03_oversold_uptrend
from vnstratlab.strategies.builtin.s03_oversold_uptrend import S03OversoldUptrend
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)
FAST = {"rsi_len": 2, "rsi_max": 10, "ma_len": 50, "max_n": 3}
SLOW = {"rsi_len": 14, "rsi_max": 30, "ma_len": 50, "max_n": 3}


def synthetic_section(**over: list[float]) -> pd.DataFrame:
    """Six tickers A..F on one day.

    rsi_2          A 3   B 8   C 12  D 1   E 9.99 F 5
    rsi_14         A 25  B 28  C 20  D 35  E 10   F 29.9
    close_vs_ma50  A .02 B .01 C .05 D .03 E -.02 F .04
    RSI(2) < 10 and ma50 > 0: A (3), B (8), D (1), F (5); C (12 >= 10) and E (below MA50) no.
        lowest first: D 1, A 3, F 5, B 8.
    RSI(14) < 30 and ma50 > 0: A (25), B (28), C (20), F (29.9); D (35 >= 30), E (below MA50) no.
        lowest first: C 20, A 25, B 28, F 29.9.
    """
    data: dict[str, Any] = {
        "ticker": list("ABCDEF"),
        "date": [DAY] * 6,
        "rsi_2": [3.0, 8.0, 12.0, 1.0, 9.99, 5.0],
        "rsi_14": [25.0, 28.0, 20.0, 35.0, 10.0, 29.9],
        "close_vs_ma50": [0.02, 0.01, 0.05, 0.03, -0.02, 0.04],
    }
    data.update(over)
    return pd.DataFrame(data)


def make(params: dict[str, Any] | None = None, **over: Any) -> S03OversoldUptrend:
    return S03OversoldUptrend({**(params or FAST), **over}, ("short",))


def test_rsi2_variant_buys_the_lowest_rsi_qualifiers() -> None:
    # qualifiers D 1, A 3, F 5, B 8; max_n 3 -> D, A, F at 1/3 each
    w = make(FAST).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"D": 1 / 3, "A": 1 / 3, "F": 1 / 3}
    assert w.sum() == pytest.approx(1.0)


def test_rsi14_variant_reads_rsi_14_and_its_own_threshold() -> None:
    # qualifiers C 20, A 25, B 28, F 29.9; max_n 3 -> C, A, B
    w = make(SLOW).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"C": 1 / 3, "A": 1 / 3, "B": 1 / 3}


def test_threshold_is_strict_and_trend_must_be_positive() -> None:
    sec = synthetic_section(
        rsi_2=[10.0, 9.9, 1.0, 1.0, 1.0, 1.0], close_vs_ma50=[0.1, 0.1, 0.0, 0.1, -0.1, 0.1]
    )
    # A rsi 10 is not < 10; B 9.9 yes; C ma50 == 0 is not > 0; D yes; E below MA50; F yes
    assert sorted(make(FAST, max_n=5).target_weights(sec, ASOF).index) == ["B", "D", "F"]


def test_max_n_binds_and_fewer_qualifiers_leave_cash() -> None:
    assert make(FAST, max_n=2).target_weights(synthetic_section(), ASOF).to_dict() == {
        "D": 0.5,
        "A": 0.5,
    }
    # 4 qualifiers, max_n 6: four names at 1/6 each, 2/6 in cash
    w = make(FAST, max_n=6).target_weights(synthetic_section(), ASOF)
    assert sorted(w.index) == ["A", "B", "D", "F"]
    assert w.tolist() == [1 / 6] * 4
    assert w.sum() == pytest.approx(4 / 6)


def test_no_qualifier_means_all_cash() -> None:
    sec = synthetic_section(close_vs_ma50=[-0.1] * 6)
    assert make(FAST).target_weights(sec, ASOF).empty
    assert make(SLOW).target_weights(sec, ASOF).empty
    assert make(FAST).target_weights(synthetic_section(rsi_2=[50.0] * 6), ASOF).empty
    assert make(FAST).target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_nan_inputs_count_as_no() -> None:
    sec = synthetic_section(
        rsi_2=[np.nan, 8.0, 12.0, 1.0, 9.99, 5.0],
        close_vs_ma50=[0.02, np.nan, 0.05, 0.03, -0.02, 0.04],
    )
    # A: NaN rsi; B: NaN trend; C: rsi 12; D yes; E below MA50; F yes
    assert sorted(make(FAST).target_weights(sec, ASOF).index) == ["D", "F"]


def test_tie_break_by_ticker_symbol() -> None:
    sec = pd.DataFrame(
        {
            "ticker": ["Z", "Y", "X", "W"],
            "date": [DAY] * 4,
            "rsi_2": [4.0, 4.0, 4.0, 9.0],
            "rsi_14": [20.0] * 4,
            "close_vs_ma50": [0.1] * 4,
        }
    )
    # X, Y, Z tie at RSI 4 (W 9 is higher): max_n 2 -> X and Y, whatever the row order
    assert sorted(make(FAST, max_n=2).target_weights(sec, ASOF).index) == ["X", "Y"]
    assert sorted(make(FAST, max_n=2).target_weights(sec.iloc[::-1], ASOF).index) == ["X", "Y"]
    assert make(FAST, max_n=1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}


def test_only_rows_on_asof_are_used_and_bad_frames_are_refused() -> None:
    old = synthetic_section(rsi_2=[0.0] * 6).assign(date=DAY - timedelta(days=7))
    both = pd.concat([old, synthetic_section()], ignore_index=True)
    assert (
        make().target_weights(both, ASOF).equals(make().target_weights(synthetic_section(), ASOF))
    )
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    with pytest.raises(ValueError, match="lack columns"):
        make(FAST).target_weights(synthetic_section().drop(columns=["rsi_2"]), ASOF)
    # the RSI-14 variant does not need rsi_2
    assert not make(SLOW).target_weights(synthetic_section().drop(columns=["rsi_2"]), ASOF).empty


@pytest.mark.parametrize(
    "over",
    [
        {"rsi_len": 3},
        {"rsi_len": 2.0},
        {"rsi_len": True},
        {"rsi_max": 0},
        {"rsi_max": -5},
        {"rsi_max": 101},
        {"rsi_max": float("nan")},
        {"rsi_max": True},
        {"rsi_max": "10"},
        {"ma_len": 20},
        {"ma_len": 50.0},
        {"max_n": 0},
        {"max_n": True},
    ],
)
def test_bad_param_values_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"rsi_len must|rsi_max must|ma_len must|max_n must"):
        S03OversoldUptrend({**FAST, **over}, ("short",))


@pytest.mark.parametrize("params", [{}, {"rsi_len": 2, "rsi_max": 10}, {**FAST, "extra": 1}])
def test_bad_param_keys_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="S03 params"):
        S03OversoldUptrend(params, ("short",))


def test_registered_and_identity_changes_with_params_and_code() -> None:
    assert get_strategy_class("S03_oversold_uptrend") is S03OversoldUptrend
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S03OversoldUptrend)
    a = compute_trial_id("S03_oversold_uptrend", FAST, "short", code, "f", "e")
    b = compute_trial_id("S03_oversold_uptrend", SLOW, "short", code, "f", "e")
    c = compute_trial_id("S03_oversold_uptrend", FAST, "short", code + "x", "f", "e")
    assert len({a, b, c}) == 3
    doc = s03_oversold_uptrend.__doc__ or ""
    assert "plan section 7" in doc
    assert "Jegadeesh (1990)" in doc
    assert "Moskowitz, Ooi & Pedersen (2012)" in doc


@pytest.mark.parametrize("params", [FAST, SLOW])
@pytest.mark.parametrize("max_n", [1, 2, 3, 9])
def test_weights_are_long_only_finite_and_at_most_one(params: dict[str, Any], max_n: int) -> None:
    w = make(params, max_n=max_n).target_weights(synthetic_section(), ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(rsi_2=[0.0] * 6, close_vs_ma50=[0.5] * 6).assign(
        date=DAY + timedelta(days=7)
    )
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


@pytest.mark.parametrize("params", [FAST, SLOW])
def test_deterministic_and_row_order_independent(params: dict[str, Any]) -> None:
    sec = synthetic_section()
    first = make(params, max_n=2).target_weights(sec, ASOF)
    assert make(params, max_n=2).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert make(params, max_n=2).target_weights(shuffled, ASOF).equals(first)


@pytest.mark.parametrize("params", [FAST])
def test_smoke_backtest_on_the_synthetic_market(
    engine_cfg: AppConfig, params: dict[str, Any]
) -> None:
    result, targets = run_smoke(make(params), engine_cfg)
    assert len(targets) >= 20
    assert_ledger_consistent(result)
    if params is FAST:
        assert any(not t.empty for t in targets.values())  # RSI(2) dips in an uptrend occur
    assert all((t >= 0).all() and t.sum() <= 1 + 1e-9 for t in targets.values())


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = synthetic_market(engine_cfg)
    asof = date(2024, 5, 31)
    visible = features[features["date"] <= asof]
    expected = make(SLOW, rsi_max=60).target_weights(visible, pd.Timestamp(asof))
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
    got = make(SLOW, rsi_max=60).target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
