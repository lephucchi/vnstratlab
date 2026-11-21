"""S00 composite score, 4-block v1 (P1-T14). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from vnstratlab.calendar import TradingCalendar, decision_days
from vnstratlab.config.models import AppConfig
from vnstratlab.data.protocol import universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource
from vnstratlab.engine import SimResult, make_params, run_simulation
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s00_composite
from vnstratlab.strategies.builtin.s00_composite import (
    BLOCKS,
    WEIGHT_SETS,
    S00Composite,
    block_ranks,
    cross_section,
    trigger,
)
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)


def synthetic_section(**over: dict[str, Any]) -> pd.DataFrame:
    """Five tickers A..E on one day. Percentile ranks (n = 5): 0.2, 0.4, 0.6, 0.8, 1.0.

    close_vs_ma20  A .05 B .04 C .03 D .02 E .01 -> ranks A 1.0 B .8 C .6 D .4 E .2
    close_vs_ma50  A .10 B .08 C .01 D .06 E -.05 -> A 1.0 B .8 C .4 D .6 E .2
    ret_60d        A .20 B .10 C -.05 D .15 E -.10 -> A 1.0 B .6 C .4 D .8 E .2
    rs_20d_vs_gm   A .03 B .01 C -.01 D .02 E -.04 -> A 1.0 B .6 C .4 D .8 E .2
    rsi_14         A 60 B 50 C 30 D 40 E 20 -> -z ranked: A .2 B .4 C .8 D .6 E 1.0
    vol_vs_avg20   A 1.0 B 1.5 C 2.0 D .5 E .8 -> A .6 B .8 C 1.0 D .2 E .4
    """
    data: dict[str, Any] = {
        "ticker": list("ABCDE"),
        "date": [DAY] * 5,
        "close_vs_ma20": [0.05, 0.04, 0.03, 0.02, 0.01],
        "close_vs_ma50": [0.10, 0.08, 0.01, 0.06, -0.05],
        "ret_60d": [0.20, 0.10, -0.05, 0.15, -0.10],
        "rs_20d_vs_group_median": [0.03, 0.01, -0.01, 0.02, -0.04],
        "rsi_14": [60.0, 50.0, 30.0, 40.0, 20.0],
        "vol_vs_avg20": [1.0, 1.5, 2.0, 0.5, 0.8],
        # Triggers: A, B breakout; C oversold in uptrend (rsi 30 < 35, ma50 +.01 > 0);
        # D none (rsi 40); E rsi 20 < 35 but close below MA50 -> no trigger.
        "high_20d_break": [True, True, False, False, False],
    }
    for column, values in over.items():
        data[column] = values
    return pd.DataFrame(data)


def make(weights: str = "equal", top_n: int = 3) -> S00Composite:
    return S00Composite({"weights": weights, "top_n": top_n}, ("short",))


# Blocks (mean of component ranks):
#   trend A (1+1+1)/3 = 1.0   B (.8+.8+.6)/3 = 2.2/3   C (.6+.4+.4)/3 = 1.4/3
#         D (.4+.6+.8)/3 = .6   E (.2+.2+.2)/3 = .2
#   rs    A 1.0 B .6 C .4 D .8 E .2 ; mean reversion A .2 B .4 C .8 D .6 E 1.0
#   vol   A .6 B .8 C 1.0 D .2 E .4
EXPECTED_BLOCKS = pd.DataFrame(
    {
        "trend": [1.0, 2.2 / 3, 1.4 / 3, 0.6, 0.2],
        "relative_strength": [1.0, 0.6, 0.4, 0.8, 0.2],
        "mean_reversion": [0.2, 0.4, 0.8, 0.6, 1.0],
        "volume": [0.6, 0.8, 1.0, 0.2, 0.4],
    },
    index=list("ABCDE"),
)


def test_block_ranks_hand_computed() -> None:
    ranks = block_ranks(cross_section(synthetic_section(), ASOF))
    pd.testing.assert_frame_equal(ranks, EXPECTED_BLOCKS, check_names=False)
    assert set(ranks.columns) == set(BLOCKS)


def test_mean_reversion_block_prefers_low_rsi_by_zscore() -> None:
    # rsi mean 40, std sqrt(250) = 15.81 -> z A +1.26 ... E -1.26; negated: E highest.
    ranks = block_ranks(cross_section(synthetic_section(), ASOF))["mean_reversion"]
    assert ranks.idxmax() == "E"
    assert ranks.idxmin() == "A"


def test_scores_for_both_weight_sets() -> None:
    ranks = EXPECTED_BLOCKS
    # equal 0.25 each: A 2.8/4 = .70, B 2.5333/4 = .6333, C 2.6667/4 = .6667, D .55, E .45
    equal = sum(ranks[b] * w for b, w in WEIGHT_SETS["equal"].items())
    assert equal.round(4).to_dict() == {"A": 0.7, "B": 0.6333, "C": 0.6667, "D": 0.55, "E": 0.45}
    # trend_heavy .4/.2/.2/.2: A .4 + .2*1.8 = .76, B .29333 + .2*1.8 = .65333,
    # C .18667 + .2*2.2 = .62667, D .24 + .2*1.6 = .56, E .08 + .2*1.6 = .40
    heavy = sum(ranks[b] * w for b, w in WEIGHT_SETS["trend_heavy"].items())
    assert heavy.round(4).to_dict() == {"A": 0.76, "B": 0.6533, "C": 0.6267, "D": 0.56, "E": 0.4}
    assert all(abs(sum(w.values()) - 1.0) < 1e-12 for w in WEIGHT_SETS.values())
    assert WEIGHT_SETS["trend_heavy"]["trend"] == 0.4


def test_trigger_logic() -> None:
    # A, B breakout; C oversold in uptrend; D neither; E oversold but below MA50 -> no.
    flags = trigger(cross_section(synthetic_section(), ASOF))
    assert flags.to_dict() == {"A": True, "B": True, "C": True, "D": False, "E": False}


def test_trigger_treats_nan_as_no_and_rsi_35_is_not_oversold() -> None:
    sec = synthetic_section(
        high_20d_break=[np.nan, False, False, False, False],
        rsi_14=[np.nan, 35.0, 34.99, 40.0, 20.0],
        close_vs_ma50=[0.1, 0.1, 0.1, np.nan, 0.1],
    )
    flags = trigger(cross_section(sec, ASOF))
    # A: NaN breakout and NaN rsi -> False; B: rsi == 35 not < 35; C: 34.99 and ma50 > 0 -> True;
    # D: rsi 40; E: rsi 20 < 35 and ma50 .1 > 0 -> True
    assert flags.to_dict() == {"A": False, "B": False, "C": True, "D": False, "E": True}


def test_equal_weights_top3_buys_the_three_triggered_names() -> None:
    # Qualifiers A, B, C (D and E have no trigger). Equal order A .70, C .667, B .633.
    w = make("equal", 3).target_weights(synthetic_section(), ASOF)
    assert w.to_dict() == {"A": pytest.approx(1 / 3), "B": pytest.approx(1 / 3), "C": 1 / 3}
    assert w.sum() == pytest.approx(1.0)


def test_weight_set_changes_the_pick_when_top_n_binds() -> None:
    # top 2 among qualifiers: equal A .70, C .667 (B .633); trend_heavy A .76, B .653 (C .627)
    equal = make("equal", 2).target_weights(synthetic_section(), ASOF)
    heavy = make("trend_heavy", 2).target_weights(synthetic_section(), ASOF)
    assert sorted(equal.index) == ["A", "C"]
    assert sorted(heavy.index) == ["A", "B"]
    assert equal.tolist() == [0.5, 0.5]
    assert heavy.tolist() == [0.5, 0.5]


def test_fewer_qualifiers_than_top_n_leaves_cash() -> None:
    # 3 qualifiers, top_n 5: three names at 1/5 each, 0.4 stays in cash.
    w = make("equal", 5).target_weights(synthetic_section(), ASOF)
    assert sorted(w.index) == ["A", "B", "C"]
    assert w.tolist() == [0.2, 0.2, 0.2]
    assert w.sum() == pytest.approx(0.6)


def test_no_qualifier_means_all_cash() -> None:
    sec = synthetic_section(high_20d_break=[False] * 5, close_vs_ma50=[0.1, 0.1, -0.1, 0.1, -0.1])
    # C and E oversold but C's ma50 is now negative -> nobody triggers
    w = make().target_weights(sec, ASOF)
    assert w.empty
    assert make().target_weights(synthetic_section().iloc[0:0], ASOF).empty


def test_tie_break_by_ticker_symbol() -> None:
    # X and Y have identical features (tie on score); Z is weaker. All three break out.
    sec = pd.DataFrame(
        {
            "ticker": ["Z", "Y", "X"],
            "date": [DAY] * 3,
            "close_vs_ma20": [0.0, 0.05, 0.05],
            "close_vs_ma50": [0.0, 0.05, 0.05],
            "ret_60d": [0.0, 0.05, 0.05],
            "rs_20d_vs_group_median": [-0.02, 0.01, 0.01],
            "rsi_14": [50.0, 50.0, 50.0],
            "vol_vs_avg20": [1.0, 2.0, 2.0],
            "high_20d_break": [True, True, True],
        }
    )
    # Y and X tie on every block (ranks 2.5/3), Z lowest on all but mean reversion (all tie) ->
    # top 1 is the alphabetically first of the tie: X.
    assert make("equal", 1).target_weights(sec, ASOF).to_dict() == {"X": 1.0}
    reversed_rows = sec.iloc[::-1].reset_index(drop=True)
    assert make("equal", 1).target_weights(reversed_rows, ASOF).to_dict() == {"X": 1.0}
    assert sorted(make("equal", 2).target_weights(sec, ASOF).index) == ["X", "Y"]


def test_nan_component_is_skipped_and_whole_nan_block_is_ineligible() -> None:
    skip = make("equal", 3).target_weights(
        synthetic_section(ret_60d=[0.20, np.nan, -0.05, 0.15, -0.10]), ASOF
    )
    assert "B" in skip.index  # trend of B = mean of its two remaining ranks, still eligible
    block = block_ranks(
        cross_section(synthetic_section(ret_60d=[0.20, np.nan, -0.05, 0.15, -0.10]), ASOF)
    )
    # close_vs_ma20 rank of B .8, close_vs_ma50 rank of B .8 -> trend (.8 + .8) / 2 = .8
    assert block.loc["B", "trend"] == pytest.approx(0.8)

    ineligible = make("equal", 3).target_weights(
        synthetic_section(vol_vs_avg20=[np.nan, 1.5, 2.0, 0.5, 0.8]), ASOF
    )
    assert "A" not in ineligible.index  # whole volume block NaN
    assert sorted(ineligible.index) == ["B", "C"]
    assert ineligible.tolist() == [1 / 3, 1 / 3]


def test_zero_rsi_spread_ties_the_mean_reversion_block() -> None:
    ranks = block_ranks(cross_section(synthetic_section(rsi_14=[50.0] * 5), ASOF))
    assert ranks["mean_reversion"].tolist() == [0.6] * 5  # average rank of five ties


def test_only_rows_on_asof_are_used_and_duplicates_are_refused() -> None:
    history = synthetic_section().assign(date=DAY - timedelta(days=7))
    history["ret_60d"] = [-1.0, 1.0, -1.0, 1.0, -1.0]  # garbage on an older day
    both = pd.concat([history, synthetic_section()], ignore_index=True)
    clean = make().target_weights(synthetic_section(), ASOF)
    assert make().target_weights(both, ASOF).equals(clean)
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([synthetic_section()] * 2, ignore_index=True), ASOF)
    with pytest.raises(ValueError, match="lack columns"):
        make().target_weights(synthetic_section().drop(columns=["ret_60d"]), ASOF)


# ------------------------------------------------------------------ params and identity


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"weights": "equal"},
        {"weights": "other", "top_n": 3},
        {"weights": "equal", "top_n": 0},
        {"weights": "equal", "top_n": True},
        {"weights": "equal", "top_n": 3, "extra": 1},
    ],
)
def test_bad_params_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"S00 params|weights must|top_n must"):
        S00Composite(params, ("short",))


def test_registered_and_trial_identity_depends_on_code_and_params() -> None:
    assert get_strategy_class("S00_composite") is S00Composite
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S00Composite)
    a = compute_trial_id("S00_composite", {"weights": "equal", "top_n": 3}, "short", code, "f", "e")
    b = compute_trial_id(
        "S00_composite", {"weights": "trend_heavy", "top_n": 3}, "short", code, "f", "e"
    )
    other = compute_trial_id(
        "S00_composite", {"weights": "equal", "top_n": 3}, "short", code + "x", "f", "e"
    )
    assert len({a, b, other}) == 3  # a new weight set or a code edit is a new trial
    assert "valuation" in (s00_composite.__doc__ or "")
    assert "plan section 7" in (s00_composite.__doc__ or "")


# ------------------------------------------------------------------ AC 2, 3, 4


@pytest.mark.parametrize("weights", ["equal", "trend_heavy"])
def test_weights_are_long_only_finite_and_at_most_one(weights: str) -> None:
    for top_n in (1, 2, 3, 5):
        w = make(weights, top_n).target_weights(synthetic_section(), ASOF)
        assert (w >= 0).all()
        assert np.isfinite(w.to_numpy()).all()
        assert w.sum() <= 1 + 1e-9


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    clean = synthetic_section()
    future = synthetic_section(
        ret_60d=[-9.0, 9.0, 9.0, -9.0, 9.0], high_20d_break=[False, False, False, True, True]
    ).assign(date=DAY + timedelta(days=7))
    late = pd.concat([clean, future], ignore_index=True)
    with pytest.raises(LookaheadError):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    # the same frame clamped by load_features(asof=) is the clean one: same weights
    clamped = late[pd.to_datetime(late["date"]) <= ASOF]
    assert make().target_weights(clamped, ASOF).equals(make().target_weights(clean, ASOF))


@pytest.mark.parametrize("weights", ["equal", "trend_heavy"])
def test_deterministic_and_row_order_independent(weights: str) -> None:
    sec = synthetic_section()
    first = make(weights, 2).target_weights(sec, ASOF)
    assert make(weights, 2).target_weights(sec, ASOF).equals(first)
    for seed in range(5):
        shuffled = sec.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        again = make(weights, 2).target_weights(shuffled, ASOF)
        assert again.sort_index().equals(first.sort_index())
        assert list(again.index) == list(first.index)  # even the order is stable


# ------------------------------------------------------------------ AC 6 smoke backtest

START, END = date(2024, 1, 2), date(2024, 6, 28)


def synthetic_market(cfg: AppConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, AppConfig]:
    syn = cfg.data.synthetic.model_copy(update={"start": START})
    cfg = cfg.model_copy(update={"data": cfg.data.model_copy(update={"synthetic": syn})})
    tickers = universe_tickers(cfg)[:8]
    source = SyntheticSource(cfg)
    prices = source.fetch_daily(tickers, START, END).assign(price_basis="synthetic")
    actions = source.fetch_corporate_actions(tickers, START, END)
    adjusted = prices.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = prices[["ticker", "date", "high", "low", "close", "volume"]]
    features = compute_features(adjusted, exec_, tickers, actions=actions)
    return prices, actions, features, cfg


def weekly_targets(
    strategy: Strategy, features: pd.DataFrame, calendar: TradingCalendar, sessions: set[date]
) -> dict[date, pd.Series]:
    targets: dict[date, pd.Series] = {}
    for day in decision_days(calendar, "short", START, END):
        if day in sessions:
            visible = features[features["date"] <= day]  # load_features(asof=) clamp
            targets[day] = strategy.target_weights(visible, pd.Timestamp(day))
    return targets


def assert_ledger_consistent(result: SimResult) -> None:
    eq = result.equity
    # equity = available + pending cash + positions (cash_reserved is an earmark, not a bucket)
    parts = eq["cash_available"] + eq["cash_pending"] + eq["positions_value"]
    assert np.allclose(eq["equity"], parts)
    assert (eq["cash_available"] >= -1e-6).all()
    assert (eq["cash_reserved"] >= 0).all()
    assert (eq["equity"] > 0).all()
    assert (result.positions["shares"] >= 0).all()
    assert np.isfinite(result.returns.to_numpy()).all()


def run_smoke(strategy: Strategy, cfg: AppConfig) -> tuple[SimResult, dict[date, pd.Series]]:
    prices, actions, features, cfg = synthetic_market(cfg)
    days = sorted(pd.to_datetime(prices["date"]).dt.date.unique())
    calendar = TradingCalendar.from_sessions(days)
    targets = weekly_targets(strategy, features, calendar, set(days))
    result = run_simulation(
        prices, actions, targets, calendar, make_params(cfg, "executable", 11_000_000)
    )
    return result, targets


@pytest.mark.parametrize("weights", ["equal", "trend_heavy"])
def test_smoke_backtest_on_the_synthetic_market(engine_cfg: AppConfig, weights: str) -> None:
    result, targets = run_smoke(make(weights, 3), engine_cfg)
    assert len(targets) >= 20
    assert any(not t.empty for t in targets.values())  # S00 picked something at some point
    assert not result.trades.empty
    assert_ledger_consistent(result)


def test_features_are_point_in_time_so_future_prices_cannot_change_a_target(
    engine_cfg: AppConfig,
) -> None:
    prices, actions, features, _ = synthetic_market(engine_cfg)
    asof = date(2024, 5, 31)
    visible = features[features["date"] <= asof]
    expected = make("equal", 3).target_weights(visible, pd.Timestamp(asof))
    assert len(visible) < len(features)  # there are rows after asof

    perturbed = prices.copy()
    later = pd.to_datetime(perturbed["date"]).dt.date > asof
    perturbed.loc[later, ["open", "high", "low", "close"]] *= 1.5
    adjusted = perturbed.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = perturbed[["ticker", "date", "high", "low", "close", "volume"]]
    tickers = sorted(prices["ticker"].unique())
    redone = compute_features(adjusted, exec_, tickers, actions=actions)
    redone_visible = redone[redone["date"] <= asof]
    got = make("equal", 3).target_weights(redone_visible, pd.Timestamp(asof))
    assert got.equals(expected)
