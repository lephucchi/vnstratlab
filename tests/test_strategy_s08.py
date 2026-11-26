"""S08 cross-sectional momentum (P1-T17). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent
from vnstratlab.calendar import TradingCalendar, decision_days
from vnstratlab.config.models import AppConfig
from vnstratlab.data.protocol import universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource
from vnstratlab.engine import SimResult, make_params, run_simulation
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s08_momentum
from vnstratlab.strategies.builtin.s08_momentum import S08Momentum
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)
SIX = {"L_months": 6, "n": 4}
TWELVE = {"L_months": 12, "n": 4}


def synthetic_section(**over: list[float]) -> pd.DataFrame:
    """Five tickers A..E on one day.

    ret_6m_skip1m   A 0.30  B -0.10  C 0.55  D 0.05  E 0.20
    ret_12m_skip1m  A -0.20 B 0.40   C 0.10  D 0.90  E 0.00
    6 months, n 2: C (0.55), A (0.30). 12 months, n 2: D (0.90), B (0.40).
    """
    data: dict[str, Any] = {
        "ticker": list("ABCDE"),
        "date": [DAY] * 5,
        "ret_6m_skip1m": [0.30, -0.10, 0.55, 0.05, 0.20],
        "ret_12m_skip1m": [-0.20, 0.40, 0.10, 0.90, 0.0],
    }
    data.update(over)
    return pd.DataFrame(data)


def make(params: dict[str, Any] | None = None, **over: Any) -> S08Momentum:
    return S08Momentum({**(params or SIX), **over}, ("medium",))


def test_six_month_variant_buys_the_top_n_equal_weight() -> None:
    w = make(SIX, n=2).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"C": 0.5, "A": 0.5}
    # the packaged n = 4 takes C, A, E, D (B is the weakest)
    w4 = make(SIX).target_weights(synthetic_section(), ASOF)
    assert sorted(w4.index) == ["A", "C", "D", "E"]
    assert w4.tolist() == [0.25] * 4


def test_twelve_month_variant_reads_its_own_feature() -> None:
    assert make(TWELVE, n=2).target_weights(synthetic_section(), ASOF).to_dict() == {
        "D": 0.5,
        "B": 0.5,
    }
    # the 12-month variant does not need the 6-month column, and vice versa
    only12 = synthetic_section().drop(columns=["ret_6m_skip1m"])
    assert not make(TWELVE).target_weights(only12, ASOF).empty
    with pytest.raises(ValueError, match="lack columns"):
        make(SIX).target_weights(only12, ASOF)


def test_fewer_eligible_than_n_leaves_cash_and_nan_is_not_eligible() -> None:
    sec = synthetic_section(ret_6m_skip1m=[np.nan, np.nan, 0.55, np.nan, 0.20])
    w = make(SIX).target_weights(sec, ASOF)  # n = 4, two eligible: C, E at 1/4 each
    assert w.to_dict() == {"C": 0.25, "E": 0.25}
    assert w.sum() == pytest.approx(0.5)
    all_nan = synthetic_section(ret_6m_skip1m=[np.nan] * 5)
    assert make(SIX).target_weights(all_nan, ASOF).empty
    assert make(SIX).target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_tie_break_by_ticker_symbol() -> None:
    sec = pd.DataFrame(
        {
            "ticker": ["Z", "Y", "X", "W"],
            "date": [DAY] * 4,
            "ret_6m_skip1m": [0.2, 0.2, 0.2, 0.1],
            "ret_12m_skip1m": [0.0] * 4,
        }
    )
    # X, Y, Z tie at the top (W is lower): n 2 -> X and Y, whatever the row order
    assert sorted(make(SIX, n=2).target_weights(sec, ASOF).index) == ["X", "Y"]
    assert sorted(make(SIX, n=2).target_weights(sec.iloc[::-1], ASOF).index) == ["X", "Y"]
    assert make(SIX, n=1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}


def test_only_rows_on_asof_are_used_and_bad_frames_are_refused() -> None:
    old = synthetic_section(ret_6m_skip1m=[9.0] * 5).assign(date=DAY - timedelta(days=30))
    both = pd.concat([old, synthetic_section()], ignore_index=True)
    assert (
        make().target_weights(both, ASOF).equals(make().target_weights(synthetic_section(), ASOF))
    )
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    assert make().lookback_sessions == 1


@pytest.mark.parametrize(
    "over",
    [
        {"L_months": 3},
        {"L_months": 6.0},
        {"L_months": True},
        {"L_months": "6"},
        {"n": 0},
        {"n": -1},
        {"n": 2.0},
        {"n": True},
    ],
)
def test_bad_param_values_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"L_months must|n must"):
        S08Momentum({**SIX, **over}, ("medium",))


@pytest.mark.parametrize("params", [{}, {"L_months": 6}, {**SIX, "extra": 1}])
def test_bad_param_keys_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="S08 params"):
        S08Momentum(params, ("medium",))


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S08_momentum") is S08Momentum
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S08Momentum)
    a = compute_trial_id("S08_momentum", SIX, "medium", code, "f", "e")
    b = compute_trial_id("S08_momentum", TWELVE, "medium", code, "f", "e")
    c = compute_trial_id("S08_momentum", SIX, "medium", code + "x", "f", "e")
    assert len({a, b, c}) == 3
    doc = s08_momentum.__doc__ or ""
    assert "plan section 7" in doc
    assert "Jegadeesh & Titman (1993)" in doc
    assert "ret_6m_skip1m" in doc
    assert "ret_12m_skip1m" in doc


@pytest.mark.parametrize("params", [SIX, TWELVE])
@pytest.mark.parametrize("n", [1, 2, 4, 9])
def test_weights_are_long_only_finite_and_at_most_one(params: dict[str, Any], n: int) -> None:
    w = make(params, n=n).target_weights(synthetic_section(), ASOF)
    assert (w >= 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(ret_6m_skip1m=[5.0] * 5).assign(date=DAY + timedelta(days=7))
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


@pytest.mark.parametrize("params", [SIX, TWELVE])
def test_deterministic_and_row_order_independent(params: dict[str, Any]) -> None:
    sec = synthetic_section()
    first = make(params, n=2).target_weights(sec, ASOF)
    assert make(params, n=2).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert make(params, n=2).target_weights(shuffled, ASOF).equals(first)


# ------------------------------------------------------------------ smoke backtest (long market)

LONG_START, LONG_END = date(2022, 1, 3), date(2023, 12, 29)  # ~520 sessions > 250 + 21 warm-up


def long_market(cfg: AppConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, AppConfig]:
    syn = cfg.data.synthetic.model_copy(update={"start": LONG_START})
    cfg = cfg.model_copy(update={"data": cfg.data.model_copy(update={"synthetic": syn})})
    tickers = universe_tickers(cfg)[:8]
    source = SyntheticSource(cfg)
    prices = source.fetch_daily(tickers, LONG_START, LONG_END).assign(price_basis="synthetic")
    actions = source.fetch_corporate_actions(tickers, LONG_START, LONG_END)
    adjusted = prices.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = prices[["ticker", "date", "high", "low", "close", "volume"]]
    features = compute_features(adjusted, exec_, tickers, actions=actions)
    return prices, actions, features, cfg


def monthly_targets(
    strategy: Strategy, features: pd.DataFrame, calendar: TradingCalendar, sessions: set[date]
) -> dict[date, pd.Series]:
    targets: dict[date, pd.Series] = {}
    for day in decision_days(calendar, "medium", LONG_START, LONG_END):
        if day in sessions:
            visible = features[features["date"] <= day]  # load_features(asof=) clamp
            targets[day] = strategy.target_weights(visible, pd.Timestamp(day))
    return targets


def run_long_smoke(
    strategy: Strategy, cfg: AppConfig
) -> tuple[SimResult, dict[date, pd.Series], int]:
    prices, actions, features, cfg = long_market(cfg)
    days = sorted(pd.to_datetime(prices["date"]).dt.date.unique())
    calendar = TradingCalendar.from_sessions(days)
    targets = monthly_targets(strategy, features, calendar, set(days))
    result = run_simulation(
        prices, actions, targets, calendar, make_params(cfg, "executable", 11_000_000)
    )
    return result, targets, len(days)


@pytest.mark.parametrize("params", [SIX])
def test_smoke_backtest_on_a_long_synthetic_market(
    engine_cfg: AppConfig, params: dict[str, Any]
) -> None:
    result, targets, sessions = run_long_smoke(make(params), engine_cfg)
    assert sessions >= 300
    invested = [t for t in targets.values() if not t.empty]
    assert invested  # the 12-month signal exists on some decision day
    assert all(t.sum() <= 1 + 1e-9 and (t >= 0).all() for t in targets.values())
    assert_ledger_consistent(result)
    assert not result.trades.empty


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = long_market(engine_cfg)
    asof = date(2023, 9, 29)
    visible = features[features["date"] <= asof]
    expected = make(TWELVE).target_weights(visible, pd.Timestamp(asof))
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
    got = make(TWELVE).target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
