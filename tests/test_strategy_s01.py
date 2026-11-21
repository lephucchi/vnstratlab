"""S01 weekly reversal within the group (P1-T15). Synthetic fixtures only; numbers hand-computed."""

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
from vnstratlab.strategies.builtin import s01_weekly_reversal
from vnstratlab.strategies.builtin.s01_weekly_reversal import S01WeeklyReversal
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)


def synthetic_section(values: list[float] | None = None, tickers: str = "ABCDE") -> pd.DataFrame:
    """One day, ``ret_5d_vs_group_median`` A -0.04, B -0.02, C 0.00, D 0.01, E 0.05 (default)."""
    vals = values if values is not None else [-0.04, -0.02, 0.00, 0.01, 0.05]
    return pd.DataFrame(
        {"ticker": list(tickers), "date": [DAY] * len(tickers), "ret_5d_vs_group_median": vals}
    )


def make(n: int = 2) -> S01WeeklyReversal:
    return S01WeeklyReversal({"n": n}, ("short",))


def test_buys_the_n_most_negative_with_equal_weight() -> None:
    # sorted ascending: A -.04, B -.02, C 0, D .01, E .05
    assert make(2).target_weights(synthetic_section(), ASOF).to_dict() == {"A": 0.5, "B": 0.5}
    three = make(3).target_weights(synthetic_section(), ASOF)
    assert three.to_dict() == {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    assert three.sum() == pytest.approx(1.0)


def test_fewer_eligible_than_n_leaves_cash() -> None:
    # A and C are NaN (not eligible): only B, D, E remain; n = 3 -> three at 1/3 -> fully invested
    sec = synthetic_section([np.nan, -0.02, np.nan, 0.01, 0.05])
    assert sorted(make(3).target_weights(sec, ASOF).index) == ["B", "D", "E"]
    # two tickers only, n = 3 -> two names at 1/3 each, 1/3 in cash
    two = make(3).target_weights(synthetic_section([-0.1, 0.2], "AB"), ASOF)
    assert two.to_dict() == {"A": 1 / 3, "B": 1 / 3}
    assert two.sum() == pytest.approx(2 / 3)
    # one eligible of three, n = 2 -> A at 1/2, the rest cash
    one = make(2).target_weights(synthetic_section([np.nan, -0.5, np.nan], "ABC"), ASOF)
    assert one.to_dict() == {"B": 0.5}


def test_nan_is_not_eligible_even_if_it_would_sort_first() -> None:
    sec = synthetic_section([np.nan, np.nan, -0.01, 0.0, 0.02])
    assert make(2).target_weights(sec, ASOF).to_dict() == {"C": 0.5, "D": 0.5}


def test_no_eligible_ticker_means_all_cash() -> None:
    assert make().target_weights(synthetic_section([np.nan] * 5), ASOF).empty
    assert make().target_weights(synthetic_section().iloc[0:0], ASOF).empty
    stale = synthetic_section().assign(date=DAY - timedelta(days=1))
    assert make().target_weights(stale, ASOF).empty  # nothing dated asof


def test_sign_is_not_filtered() -> None:
    # the group rallied: all values positive, the two lowest are still bought
    sec = synthetic_section([0.03, 0.01, 0.02, 0.05, 0.04])
    assert sorted(make(2).target_weights(sec, ASOF).index) == ["B", "C"]


def test_tie_break_by_ticker_symbol() -> None:
    # X, Y, Z tie at -0.02; n = 2 -> X and Y; n = 1 -> X, whatever the row order
    sec = pd.DataFrame(
        {
            "ticker": ["Z", "Y", "X", "W"],
            "date": [DAY] * 4,
            "ret_5d_vs_group_median": [-0.02, -0.02, -0.02, 0.1],
        }
    )
    assert make(1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}
    assert sorted(make(2).target_weights(sec, ASOF).index) == ["X", "Y"]
    assert sorted(make(2).target_weights(sec.iloc[::-1], ASOF).index) == ["X", "Y"]


def test_only_rows_on_asof_are_used_and_bad_frames_are_refused() -> None:
    old = synthetic_section([-9.0, 9.0, 9.0, 9.0, 9.0]).assign(date=DAY - timedelta(days=7))
    both = pd.concat([old, synthetic_section()], ignore_index=True)
    assert (
        make().target_weights(both, ASOF).equals(make().target_weights(synthetic_section(), ASOF))
    )
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    with pytest.raises(ValueError, match="lack columns"):
        make().target_weights(synthetic_section().drop(columns=["ret_5d_vs_group_median"]), ASOF)


@pytest.mark.parametrize(
    "params",
    [{}, {"n": 0}, {"n": -1}, {"n": True}, {"n": 2.0}, {"n": "2"}, {"n": 2, "extra": 1}],
)
def test_bad_params_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"S01 params|n must be"):
        S01WeeklyReversal(params, ("short",))


def test_registered_and_identity_changes_with_params_and_code() -> None:
    assert get_strategy_class("S01_weekly_reversal") is S01WeeklyReversal
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S01WeeklyReversal)
    two = compute_trial_id("S01_weekly_reversal", {"n": 2}, "short", code, "f", "e")
    three = compute_trial_id("S01_weekly_reversal", {"n": 3}, "short", code, "f", "e")
    edited = compute_trial_id("S01_weekly_reversal", {"n": 2}, "short", code + "x", "f", "e")
    assert len({two, three, edited}) == 3
    doc = s01_weekly_reversal.__doc__ or ""
    assert "plan section 7" in doc
    assert "Jegadeesh (1990)" in doc  # rule and basis


@pytest.mark.parametrize("n", [1, 2, 3, 7])
def test_weights_are_long_only_finite_and_at_most_one(n: int) -> None:
    w = make(n).target_weights(synthetic_section(), ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section([9.0, -9.0, -9.0, -9.0, -9.0]).assign(date=DAY + timedelta(days=7))
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


def test_deterministic_and_row_order_independent() -> None:
    sec = synthetic_section()
    first = make(3).target_weights(sec, ASOF)
    assert make(3).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        again = make(3).target_weights(shuffled, ASOF)
        assert again.equals(first)  # same values and the same order


@pytest.mark.parametrize("n", [2, 3])
def test_smoke_backtest_on_the_synthetic_market(engine_cfg: AppConfig, n: int) -> None:
    result, targets = run_smoke(make(n), engine_cfg)
    assert len(targets) >= 20
    assert any(not t.empty for t in targets.values())
    assert not result.trades.empty
    assert_ledger_consistent(result)


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = synthetic_market(engine_cfg)
    asof = date(2024, 5, 31)
    visible = features[features["date"] <= asof]
    expected = make(3).target_weights(visible, pd.Timestamp(asof))
    assert len(visible) < len(features)
    perturbed = prices.copy()
    later = pd.to_datetime(perturbed["date"]).dt.date > asof
    perturbed.loc[later, ["open", "high", "low", "close"]] *= 1.5
    adjusted = perturbed.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = perturbed[["ticker", "date", "high", "low", "close", "volume"]]
    redone = compute_features(adjusted, exec_, sorted(prices["ticker"].unique()), actions=actions)
    got = make(3).target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
