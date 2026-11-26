"""S15 sector trend filter (P1-T19). Synthetic fixtures only; numbers hand-computed."""

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
from vnstratlab.strategies.builtin import s15_sector_trend
from vnstratlab.strategies.builtin.s15_sector_trend import S15SectorTrend
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)
TWELVE = {"lookback_months": 12}
SIX = {"lookback_months": 6}


def synthetic_section(g12: float = 0.10, g6: float = -0.05, tickers: str = "ABCD") -> pd.DataFrame:
    """One day, the same group signal on every row: group_ret_12m ``g12``, group_ret_6m ``g6``."""
    n = len(tickers)
    return pd.DataFrame(
        {
            "ticker": list(tickers),
            "date": [DAY] * n,
            "group_ret_12m": [g12] * n,
            "group_ret_6m": [g6] * n,
        }
    )


def make(params: dict[str, Any] | None = None) -> S15SectorTrend:
    return S15SectorTrend(params or TWELVE, ("medium",))


def test_positive_signal_holds_the_whole_cross_section_equally() -> None:
    w = make(TWELVE).target_weights(synthetic_section(g12=0.10), ASOF)
    assert w.to_dict() == {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    five = make(TWELVE).target_weights(synthetic_section(g12=0.01, tickers="EDCBA"), ASOF)
    assert sorted(five.index) == list("ABCDE")
    assert five.tolist() == [0.2] * 5
    assert five.sum() == pytest.approx(1.0)


@pytest.mark.parametrize("signal", [0.0, -0.0001, -0.5])
def test_non_positive_signal_is_cash(signal: float) -> None:
    assert make(TWELVE).target_weights(synthetic_section(g12=signal), ASOF).empty


def test_nan_signal_is_cash_and_disagreeing_rows_are_cash() -> None:
    assert make(TWELVE).target_weights(synthetic_section(g12=np.nan), ASOF).empty
    mixed = synthetic_section(g12=0.1)
    mixed.loc[0, "group_ret_12m"] = 0.2  # rows disagree on a one-number signal
    assert make(TWELVE).target_weights(mixed, ASOF).empty
    assert make(TWELVE).target_weights(synthetic_section(g12=np.inf), ASOF).empty
    assert make(TWELVE).target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_a_mix_of_finite_and_non_finite_rows_is_cash() -> None:
    for bad in (np.nan, np.inf):
        mixed = synthetic_section(g12=0.1)
        mixed.loc[0, "group_ret_12m"] = bad
        assert make(TWELVE).target_weights(mixed, ASOF).empty


def test_six_and_twelve_month_variants_read_their_own_column() -> None:
    sec = synthetic_section(g12=0.10, g6=-0.05)  # 12m up, 6m down
    assert not make(TWELVE).target_weights(sec, ASOF).empty
    assert make(SIX).target_weights(sec, ASOF).empty
    flipped = synthetic_section(g12=-0.10, g6=0.05)
    assert make(TWELVE).target_weights(flipped, ASOF).empty
    assert make(SIX).target_weights(flipped, ASOF).to_dict() == {t: 0.25 for t in "ABCD"}
    # each variant needs only its own column
    only6 = synthetic_section(g6=0.05).drop(columns=["group_ret_12m"])
    assert not make(SIX).target_weights(only6, ASOF).empty
    with pytest.raises(ValueError, match="lack columns"):
        make(TWELVE).target_weights(only6, ASOF)


def test_only_rows_on_asof_are_used_and_bad_frames_are_refused() -> None:
    old = synthetic_section(g12=-0.9, tickers="ABCDEFG").assign(date=DAY - timedelta(days=30))
    both = pd.concat([old, synthetic_section()], ignore_index=True)
    assert (
        make().target_weights(both, ASOF).equals(make().target_weights(synthetic_section(), ASOF))
    )
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    assert make().lookback_sessions == 1


@pytest.mark.parametrize(
    "params",
    [
        {"lookback_months": 3},
        {"lookback_months": 12.0},
        {"lookback_months": True},
        {"lookback_months": "12"},
    ],
)
def test_bad_param_values_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="lookback_months must"):
        S15SectorTrend(params, ("medium",))


@pytest.mark.parametrize("params", [{}, {**TWELVE, "n": 4}, {"n": 4}])
def test_bad_param_keys_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="S15 params"):
        S15SectorTrend(params, ("medium",))


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S15_sector_trend") is S15SectorTrend
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S15SectorTrend)
    a = compute_trial_id("S15_sector_trend", TWELVE, "medium", code, "f", "e")
    b = compute_trial_id("S15_sector_trend", SIX, "medium", code, "f", "e")
    c = compute_trial_id("S15_sector_trend", TWELVE, "medium", code + "x", "f", "e")
    assert len({a, b, c}) == 3
    doc = s15_sector_trend.__doc__ or ""
    assert "plan section 7" in doc
    assert "Moskowitz, Ooi & Pedersen (2012)" in doc
    assert "group_ret_6m" in doc
    assert "group_ret_12m" in doc


@pytest.mark.parametrize("params", [TWELVE, SIX])
@pytest.mark.parametrize("signal", [-0.1, 0.1, np.nan])
def test_weights_are_long_only_finite_and_at_most_one(
    params: dict[str, Any], signal: float
) -> None:
    sec = synthetic_section(g12=signal, g6=signal)
    w = make(params).target_weights(sec, ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(g12=-0.9).assign(date=DAY + timedelta(days=7))
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


def test_deterministic_and_row_order_independent() -> None:
    sec = synthetic_section(tickers="ABCDE")
    first = make().target_weights(sec, ASOF)
    assert make().target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert make().target_weights(shuffled, ASOF).equals(first)


# ------------------------------------------------------------------ smoke backtest (long market)


@pytest.mark.parametrize("params", [SIX])
def test_smoke_backtest_on_a_long_synthetic_market(
    engine_cfg: AppConfig, params: dict[str, Any]
) -> None:
    result, targets, sessions = run_long_smoke(make(params), engine_cfg)
    assert sessions >= 300
    invested = [t for t in targets.values() if not t.empty]
    assert invested  # the group trend is up on some decision day
    assert all(t.sum() <= 1 + 1e-9 and (t >= 0).all() for t in targets.values())
    assert_ledger_consistent(result)
    assert not result.trades.empty


@pytest.mark.parametrize("params", [TWELVE, SIX])
def test_future_prices_cannot_change_a_target(
    engine_cfg: AppConfig, params: dict[str, Any]
) -> None:
    prices, actions, features, _ = long_market(engine_cfg)
    strategy = make(params)
    days = sorted(features["date"].unique())
    asof = next(
        d
        for d in days[260:-20]
        if not strategy.target_weights(features[features["date"] <= d], pd.Timestamp(d)).empty
    )
    visible = features[features["date"] <= asof]
    expected = strategy.target_weights(visible, pd.Timestamp(asof))
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
    got = strategy.target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
