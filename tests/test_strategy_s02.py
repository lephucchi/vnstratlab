"""S02 20-day breakout with volume (P1-T15). Synthetic fixtures only; numbers hand-computed."""

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
from vnstratlab.strategies.builtin import s02_breakout_volume
from vnstratlab.strategies.builtin.s02_breakout_volume import S02BreakoutVolume
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)
PARAMS = {"lookback": 20, "vol_mult": 1.5, "max_n": 3}


def synthetic_section(**over: list[float]) -> pd.DataFrame:
    """Six tickers A..F on one day.

    close_20d_break  A 1  B 1  C 1  D 1  E 0  F 1
    vol_vs_avg20     A 2.0  B 3.0  C 1.5  D 1.6  E 5.0  F 1.2
    Signals need break = 1 AND volume > 1.5 (strict): A yes, B yes, C no (1.5 is not > 1.5),
    D yes, E no (no break), F no (volume 1.2). Ranked by volume desc: B 3.0, A 2.0, D 1.6.
    """
    data: dict[str, Any] = {
        "ticker": list("ABCDEF"),
        "date": [DAY] * 6,
        "close_20d_break": [1.0, 1.0, 1.0, 1.0, 0.0, 1.0],
        "vol_vs_avg20": [2.0, 3.0, 1.5, 1.6, 5.0, 1.2],
    }
    data.update(over)
    return pd.DataFrame(data)


def make(max_n: int = 3, vol_mult: float = 1.5) -> S02BreakoutVolume:
    return S02BreakoutVolume({**PARAMS, "max_n": max_n, "vol_mult": vol_mult}, ("short",))


def test_signals_need_a_close_breakout_and_volume_strictly_above_the_multiple() -> None:
    # signals A, B, D (see the fixture); max_n 3 -> 1/3 each; C (volume == 1.5) is excluded
    w = make(3).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"A": 1 / 3, "B": 1 / 3, "D": 1 / 3}
    assert w.sum() == pytest.approx(1.0)


def test_more_signals_than_max_n_keeps_the_highest_volume() -> None:
    # 3 signals, max_n 2: B (3.0) and A (2.0) at 1/2 each; D (1.6) is dropped
    assert make(2).target_weights(synthetic_section(), ASOF).to_dict() == {"A": 0.5, "B": 0.5}
    assert make(1).target_weights(synthetic_section(), ASOF).to_dict() == {"B": 1.0}


def test_fewer_signals_than_max_n_leaves_cash() -> None:
    # 3 signals, max_n 5: three names at 1/5, 2/5 in cash
    w = make(5).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"A": 0.2, "B": 0.2, "D": 0.2}
    assert w.sum() == pytest.approx(0.6)


def test_no_signal_means_all_cash() -> None:
    sec = synthetic_section(close_20d_break=[0.0] * 6)
    assert make().target_weights(sec, ASOF).empty
    assert make().target_weights(synthetic_section(vol_vs_avg20=[1.0] * 6), ASOF).empty
    assert make().target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_nan_inputs_count_as_no() -> None:
    sec = synthetic_section(
        close_20d_break=[np.nan, 1.0, 1.0, 1.0, 1.0, 1.0],
        vol_vs_avg20=[2.0, np.nan, 2.5, 1.6, 5.0, 1.2],
    )
    # A: NaN break -> no; B: NaN volume -> no; C 2.5 yes; D 1.6 yes; E 5.0 yes; F 1.2 no
    assert sorted(make(5).target_weights(sec, ASOF).index) == ["C", "D", "E"]


def test_vol_mult_is_a_parameter() -> None:
    # vol_mult 2.5 keeps only B (3.0); vol_mult 1.1 adds C (1.5), F (1.2): A B C D F, top 5
    assert make(3, 2.5).target_weights(synthetic_section(), ASOF).to_dict() == {"B": 1 / 3}
    assert sorted(make(5, 1.1).target_weights(synthetic_section(), ASOF).index) == list("ABCDF")


def test_tie_break_by_ticker_symbol() -> None:
    sec = pd.DataFrame(
        {
            "ticker": ["Z", "Y", "X", "W"],
            "date": [DAY] * 4,
            "close_20d_break": [1.0] * 4,
            "vol_vs_avg20": [2.0, 2.0, 2.0, 1.0],
        }
    )
    # X, Y, Z tie at 2.0 (W has no volume signal): max_n 2 -> X and Y in any row order
    assert sorted(make(2).target_weights(sec, ASOF).index) == ["X", "Y"]
    assert sorted(make(2).target_weights(sec.iloc[::-1], ASOF).index) == ["X", "Y"]
    assert make(1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}


def test_only_rows_on_asof_are_used_and_bad_frames_are_refused() -> None:
    old = synthetic_section(close_20d_break=[0.0] * 6).assign(date=DAY - timedelta(days=7))
    both = pd.concat([old, synthetic_section()], ignore_index=True)
    assert (
        make().target_weights(both, ASOF).equals(make().target_weights(synthetic_section(), ASOF))
    )
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    with pytest.raises(ValueError, match="lack columns"):
        make().target_weights(synthetic_section().drop(columns=["close_20d_break"]), ASOF)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"lookback": 20, "vol_mult": 1.5},
        {**PARAMS, "extra": 1},
        {**PARAMS, "max_n": 0},
        {**PARAMS, "max_n": True},
        {**PARAMS, "vol_mult": 0},
        {**PARAMS, "vol_mult": -1.0},
        {**PARAMS, "vol_mult": float("nan")},
        {**PARAMS, "vol_mult": True},
        {**PARAMS, "vol_mult": "1.5"},
    ],
)
def test_bad_params_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"S02 params|vol_mult must|max_n must"):
        S02BreakoutVolume(params, ("short",))


@pytest.mark.parametrize("lookback", [10, 19, 21, 50, 20.0, True, "20"])
def test_lookback_other_than_the_feature_window_is_rejected(lookback: Any) -> None:
    with pytest.raises(ValueError, match=r"lookback must be 20.*close_20d_break"):
        S02BreakoutVolume({**PARAMS, "lookback": lookback}, ("short",))


def test_registered_and_identity_changes_with_params_and_code() -> None:
    assert get_strategy_class("S02_breakout_volume") is S02BreakoutVolume
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S02BreakoutVolume)
    a = compute_trial_id("S02_breakout_volume", PARAMS, "short", code, "f", "e")
    b = compute_trial_id(
        "S02_breakout_volume", {**PARAMS, "vol_mult": 2.0}, "short", code, "f", "e"
    )
    c = compute_trial_id("S02_breakout_volume", PARAMS, "short", code + "x", "f", "e")
    assert len({a, b, c}) == 3
    doc = s02_breakout_volume.__doc__ or ""
    assert "plan section 7" in doc
    assert "Brock, Lakonishok & LeBaron (1992)" in doc
    assert "close_20d_break" in doc


@pytest.mark.parametrize("max_n", [1, 2, 3, 9])
def test_weights_are_long_only_finite_and_at_most_one(max_n: int) -> None:
    w = make(max_n).target_weights(synthetic_section(), ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(close_20d_break=[1.0] * 6, vol_vs_avg20=[9.0] * 6).assign(
        date=DAY + timedelta(days=7)
    )
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


def test_deterministic_and_row_order_independent() -> None:
    sec = synthetic_section()
    first = make(2).target_weights(sec, ASOF)
    assert make(2).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert make(2).target_weights(shuffled, ASOF).equals(first)


def test_smoke_backtest_on_the_synthetic_market(engine_cfg: AppConfig) -> None:
    result, targets = run_smoke(make(), engine_cfg)
    assert len(targets) >= 20
    assert_ledger_consistent(result)
    assert any(not t.empty for t in targets.values())  # breakouts with volume do occur
    assert all((t >= 0).all() and t.sum() <= 1 + 1e-9 for t in targets.values())


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = synthetic_market(engine_cfg)
    asof = date(2024, 5, 10)  # a day with a breakout signal
    visible = features[features["date"] <= asof]
    expected = make(vol_mult=0.5).target_weights(visible, pd.Timestamp(asof))
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
    got = make(vol_mult=0.5).target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
