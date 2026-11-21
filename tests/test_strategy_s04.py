"""S04 long-only bank pairs (P1-T16). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

import math
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
from vnstratlab.strategies.base import BaseStrategy, LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s04_bank_pairs
from vnstratlab.strategies.builtin.s04_bank_pairs import (
    S04BankPairs,
    open_side,
    pair_correlation,
    return_panel,
    spread_z,
    top_pairs,
)
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

LONG_START, LONG_END = date(2023, 1, 2), date(2024, 6, 28)  # about 390 sessions (form = 250)
NAN = math.nan


def make(form: int = 10, k: int = 1, entry_z: float = 2.0, max_hold: int = 10) -> S04BankPairs:
    return S04BankPairs(
        {"form": form, "k": k, "entry_z": entry_z, "max_hold": max_hold}, ("short",)
    )


def sessions(n: int) -> list[date]:
    """``n`` consecutive weekdays from 2026-01-05."""
    return [d.date() for d in pd.bdate_range("2026-01-05", periods=n)]


def feature_frame(log_returns: dict[str, list[float]]) -> pd.DataFrame:
    """Long feature frame (ticker, date, ret_1d) from LOG returns; ret_1d = expm1(log return)."""
    n = len(next(iter(log_returns.values())))
    days = sessions(n)
    parts = [
        pd.DataFrame({"ticker": t, "date": days, "ret_1d": np.expm1(np.array(v, dtype=float))})
        for t, v in log_returns.items()
    ]
    return pd.concat(parts, ignore_index=True)


def asof_of(frame: pd.DataFrame) -> pd.Timestamp:
    return pd.Timestamp(frame["date"].max())


# ---- the spread story used by the end-to-end cases (10 sessions)
# Increment d of the log spread: 0 for 9 sessions, then +1. Cumulative spread = [0]*9 + [1];
# mean = 0.1; deviations -0.1 (x9) and 0.9; sum of squares = 9 * 0.01 + 0.81 = 0.9;
# sample variance = 0.9 / 9 = 0.1; std = 0.316228; z_last = 0.9 / 0.316228 = 2.8460 > 2;
# every earlier z = -0.1 / 0.316228 = -0.3162.
JUMP = [0.0] * 9 + [1.0]
SWING = [0.02, -0.02] * 5  # a log-return pattern with variance


def test_spread_z_hand_numbers() -> None:
    # B flat (0), A log returns 1, 1, 1, -3: spread cumsum = 1, 2, 3, 0; mean 1.5;
    # deviations -0.5, 0.5, 1.5, -1.5; sum of squares 5; sample variance 5 / 3; std 1.290994
    # z = -0.38730, 0.38730, 1.16190, -1.16190
    a = np.expm1(np.array([1.0, 1.0, 1.0, -3.0]))
    z = spread_z(a, np.zeros(4))
    assert z == pytest.approx([-0.5 / 1.290994, 0.5 / 1.290994, 1.5 / 1.290994, -1.5 / 1.290994])
    assert z[1] == pytest.approx(0.387298, abs=1e-6)
    assert z[2] == pytest.approx(1.161895, abs=1e-6)


def test_spread_uses_only_days_where_both_are_observed() -> None:
    # A log returns 1, (missing), 1, -3 with B flat: the missing day has no spread value;
    # the other three days give cumsum 1, 2, -1; mean 2/3; deviations 1/3, 4/3, -5/3;
    # sum of squares (1 + 16 + 25) / 9 = 4.6667; variance 2.3333; std 1.527525
    # z = 0.218218, 0.872872, -1.091089 and NaN on the missing day
    a = np.array([np.expm1(1.0), NAN, np.expm1(1.0), np.expm1(-3.0)])
    z = spread_z(a, np.zeros(4))
    assert math.isnan(z[1])
    assert z[[0, 2, 3]] == pytest.approx([0.218218, 0.872872, -1.091089], abs=1e-6)


def test_spread_z_is_undefined_without_variation_or_data() -> None:
    assert np.isnan(spread_z(np.array([0.01] * 6), np.array([0.01] * 6))).all()  # flat spread
    assert np.isnan(spread_z(np.array([0.01, 0.02]), np.array([0.0, 0.0]))).all()  # 2 points


# ---- pair selection
A_R = [0.01, 0.02, 0.03, 0.04, 0.05]
B_R = [0.02, 0.04, 0.06, 0.08, 0.10]  # = 2 * A: corr(A, B) = 1
C_R = [0.05, 0.01, 0.04, 0.02, 0.03]
D_R = [0.05, 0.04, 0.03, 0.02, 0.01]  # = 0.06 - A: corr(A, D) = corr(B, D) = -1


def panel_of(**cols: list[float]) -> pd.DataFrame:
    return pd.DataFrame(cols, index=pd.DatetimeIndex(sessions(len(next(iter(cols.values()))))))


def test_pair_correlation_hand_numbers() -> None:
    # A centred (x 0.01): -2 -1 0 1 2; C centred (x 0.01): 2 -2 1 -1 0 (mean 0.03)
    # cov sum = (-4 + 2 + 0 - 1 + 0) = -3 (x 1e-4); both sums of squares: 10 and 10 (x 1e-4)
    # corr(A, C) = -3 / 10 = -0.3
    a, c = np.array(A_R), np.array(C_R)
    assert pair_correlation(a, c, 5) == pytest.approx(-0.3)
    assert pair_correlation(a, np.array(B_R), 5) == pytest.approx(1.0)
    assert pair_correlation(a, np.array(D_R), 5) == pytest.approx(-1.0)
    # C and D: D centred 2 1 0 -1 -2 against C: 4 - 2 + 0 + 1 + 0 = 3 -> +0.3
    assert pair_correlation(c, np.array(D_R), 5) == pytest.approx(0.3)


def test_top_pairs_ranked_by_correlation_with_symbol_tie_break() -> None:
    panel = panel_of(A=A_R, B=B_R, C=C_R, D=D_R)
    # (A,B) 1.0, (C,D) 0.3, then (A,C) = (B,C) = -0.3 tie -> (A,C) first, then (A,D) / (B,D) -1
    got = top_pairs(panel, 3)
    assert [(a, b) for a, b, _ in got] == [("A", "B"), ("C", "D"), ("A", "C")]
    assert [round(c, 6) for _, _, c in got] == [1.0, 0.3, -0.3]
    assert [(a, b) for a, b, _ in top_pairs(panel, 1)] == [("A", "B")]
    assert [(a, b) for a, b, _ in top_pairs(panel[["D", "C", "B", "A"]], 4)][3] == ("B", "C")


def test_pair_needs_80_percent_of_the_window_for_both() -> None:
    # window 5: 4 observed (80 %) is enough, 3 is not
    ok = panel_of(A=[NAN, 0.02, 0.03, 0.04, 0.05], B=B_R, C=C_R)
    assert ("A", "B") in [(a, b) for a, b, _ in top_pairs(ok, 3)]
    short = panel_of(A=[NAN, NAN, 0.03, 0.04, 0.05], B=B_R, C=C_R)
    assert [(a, b) for a, b, _ in top_pairs(short, 3)] == [("B", "C")]
    # constant series: no variance, no correlation
    flat = panel_of(A=[0.01] * 5, B=B_R)
    assert top_pairs(flat, 3) == []


def test_pairwise_complete_correlation_uses_common_days_only() -> None:
    # A is missing on day 0 and B on day 4: the common days 1..3 are 3 of 5 -> skipped (< 80 %)
    a = np.array([NAN, 0.02, 0.03, 0.04, 0.05])
    b = np.array([0.02, 0.04, 0.06, 0.08, NAN])
    assert math.isnan(pair_correlation(a, b, 5))
    assert pair_correlation(a, b, 3) == pytest.approx(1.0)  # same days with a shorter window


# ---- entry and exit logic on z directly
def z_of(*values: float) -> np.ndarray:
    return np.array(values, dtype=float)


def test_entry_when_abs_z_exceeds_entry_z_and_side_is_the_laggard() -> None:
    # z = 0, 0.5, 2.5, 2.2, 1.0: entry at index 2 (2.5 > 2), z stays > 0 -> open, A ahead
    assert open_side(z_of(0.0, 0.5, 2.5, 2.2, 1.0), 2.0, 10) == 1  # buy B
    # mirror image: B ahead, buy A
    assert open_side(z_of(0.0, -0.5, -2.5, -2.2, -1.0), 2.0, 10) == -1
    # never beyond the threshold (2.0 exactly is not > 2.0) -> closed
    assert open_side(z_of(0.0, 1.0, 2.0, 1.5, 1.0), 2.0, 10) == 0


def test_exit_on_zero_cross() -> None:
    # entry at index 1 (2.5), z crosses to -0.5 at index 3 -> closed
    assert open_side(z_of(0.0, 2.5, 1.0, -0.5, -0.2), 2.0, 10) == 0
    # exactly 0 also ends it
    assert open_side(z_of(2.5, 1.0, 0.0, 0.5), 2.0, 10) == 0
    # after the cross a new entry on the other side opens a new position (B ahead -> buy A)
    assert open_side(z_of(2.5, 1.0, -0.5, -2.4, -2.1), 2.0, 10) == -1
    # a NaN session neither enters nor crosses
    assert open_side(z_of(2.5, NAN, 1.0), 2.0, 10) == 1
    assert open_side(z_of(2.5, 1.0, NAN), 2.0, 10) == 0  # asof itself has no spread value


def test_exit_after_max_hold_sessions() -> None:
    # z = 2.5, 1.5, 1.0, 0.8, 0.6 (index 4 is asof): the entry (index 0) is 4 sessions old.
    # max_hold 5: the window covers indices 0..4 (4 < 5 sessions elapsed) -> still open
    # max_hold 4: window indices 1..4 holds no |z| > 2 -> closed
    z = z_of(2.5, 1.5, 1.0, 0.8, 0.6)
    assert open_side(z, 2.0, 5) == 1
    assert open_side(z, 2.0, 4) == 0
    assert open_side(z, 2.0, 1) == 0
    # pinned behaviour: every session with |z| > entry_z is an entry session, so a spread that
    # STAYS beyond entry_z keeps the pair open for as long as it stays there (max_hold only
    # binds once z has decayed below entry_z without crossing 0)
    assert open_side(z_of(*[2.5] * 12), 2.0, 3) == 1


def test_entry_on_the_asof_session_counts() -> None:
    assert open_side(z_of(0.1, 0.2, 2.1), 2.0, 1) == 1


# ---- end to end on small histories
def test_end_to_end_entry_buys_the_laggard_of_the_top_pair() -> None:
    # A swings by +-0.02; B = A - JUMP (the spread A - B jumps by 1 in the last session);
    # C = a slower swing, uncorrelated with A. Top pair (A, B); z_last = 2.846 > 2 and A is
    # ahead, so the laggard B gets 1 / k = 1.
    logs = {
        "A": SWING,
        "B": [a - d for a, d in zip(SWING, JUMP, strict=True)],
        "C": [0.01, 0.01, -0.01, -0.01, 0.01, 0.01, -0.01, -0.01, 0.01, 0.01],
    }
    frame = feature_frame(logs)
    panel = return_panel(frame, asof_of(frame), 10)
    assert panel is not None
    assert [(a, b) for a, b, _ in top_pairs(panel, 1)] == [("A", "B")]
    assert make(10, 1).target_weights(frame, asof_of(frame)).to_dict() == {"B": 1.0}
    # mirrored (B is ahead): the laggard is A
    mirrored = feature_frame({**logs, "A": logs["B"], "B": logs["A"]})
    assert make(10, 1).target_weights(mirrored, asof_of(mirrored)).to_dict() == {"A": 1.0}
    # k = 5 weights each open pair 1 / 5. B fell by the jump against both A and C, so (A,B)
    # and (B,C) are both open with B as the laggard: 2 / 5 on B (the weights add)
    five = make(10, 5).target_weights(frame, asof_of(frame))
    assert five.to_dict() == {"B": pytest.approx(0.4)}


def test_end_to_end_zero_cross_closes_the_position() -> None:
    # spread increments 0 x 8, +1, -1.2: cumulative [0]*8, 1, -0.2; mean 0.08;
    # z_8 = 0.92 / 0.3293 = 2.79 (entry) but z_9 = -0.28 / 0.3293 = -0.85 crossed 0 -> all cash
    d = [0.0] * 8 + [1.0, -1.2]
    frame = feature_frame({"A": SWING, "B": [a - x for a, x in zip(SWING, d, strict=True)]})
    assert make(10, 1).target_weights(frame, asof_of(frame)).empty


def test_end_to_end_shared_laggard_weights_add() -> None:
    # A = B = C + JUMP: pairs (A,C) and (B,C) both have C as the laggard (z_last = 2.846);
    # (A,B) has a flat spread (no z). k = 3 -> 1/3 + 1/3 on C; the rest stays in cash.
    c = SWING
    ahead = [x + d for x, d in zip(c, JUMP, strict=True)]
    frame = feature_frame({"A": ahead, "B": ahead, "C": c})
    w = make(10, 3).target_weights(frame, asof_of(frame))
    assert w.to_dict() == {"C": pytest.approx(2 / 3)}
    assert w.sum() <= 1.0
    # mirrored: C ahead of both, so A and B are the laggards, 1/3 each... but (A,B) is flat and
    # the pairs are (A,C), (B,C): A gets 1/3 and B gets 1/3
    low = [x - d for x, d in zip(c, JUMP, strict=True)]
    frame2 = feature_frame({"A": low, "B": low, "C": c})
    w2 = make(10, 3).target_weights(frame2, asof_of(frame2))
    assert w2.to_dict() == {"A": pytest.approx(1 / 3), "B": pytest.approx(1 / 3)}


def test_insufficient_history_is_all_cash() -> None:
    logs = {
        "A": SWING,
        "B": [a - d for a, d in zip(SWING, JUMP, strict=True)],
        "C": SWING[::-1],
    }
    frame = feature_frame(logs)
    assert not make(10, 1).target_weights(frame, asof_of(frame)).empty
    assert make(11, 1).target_weights(frame, asof_of(frame)).empty  # 10 sessions < form 11
    assert make(10, 1).target_weights(frame.iloc[0:0], ASOF_DEFAULT).empty
    # asof later than the last session of the frame: nothing to trade on
    assert make(10, 1).target_weights(frame, asof_of(frame) + timedelta(days=3)).empty


ASOF_DEFAULT = pd.Timestamp("2026-03-10")


def test_missing_returns_stay_nan_and_do_not_open_a_pair() -> None:
    # B has no return on the last session: the pair has no spread value at asof -> cash
    logs = {"A": SWING, "B": [a - d for a, d in zip(SWING, JUMP, strict=True)], "C": SWING}
    frame = feature_frame(logs)
    last = frame["date"] == frame["date"].max()
    frame = frame[~(last & (frame["ticker"] == "B"))]
    assert make(10, 1).target_weights(frame, asof_of(frame)).empty


# ---- contract
@pytest.mark.parametrize(
    "params",
    [
        {},
        {"form": 250, "k": 5, "entry_z": 2.0},
        {"form": 250, "k": 5, "entry_z": 2.0, "max_hold": 10, "extra": 1},
        {"form": True, "k": 5, "entry_z": 2.0, "max_hold": 10},
        {"form": 250.0, "k": 5, "entry_z": 2.0, "max_hold": 10},
        {"form": 2, "k": 5, "entry_z": 2.0, "max_hold": 10},
        {"form": 250, "k": 0, "entry_z": 2.0, "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": 0.0, "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": -1.0, "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": math.nan, "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": math.inf, "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": True, "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": "2", "max_hold": 10},
        {"form": 250, "k": 5, "entry_z": 2.0, "max_hold": 0},
        {"form": 250, "k": 5, "entry_z": 2.0, "max_hold": True},
    ],
)
def test_bad_params_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"S04 params|must be"):
        S04BankPairs(params, ("short",))


def test_lookback_sessions_is_form_and_defaults_to_one() -> None:
    assert make(250).lookback_sessions == 250
    assert make(40).lookback_sessions == 40
    assert BaseStrategy.lookback_sessions == 1
    assert S04BankPairs.lookback_sessions == 250  # the class carries the frozen form


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S04_bank_pairs") is S04BankPairs
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S04BankPairs)
    p1 = {"form": 250, "k": 5, "entry_z": 2.0, "max_hold": 10}
    p2 = {**p1, "k": 4}
    one = compute_trial_id("S04_bank_pairs", p1, "short", code, "f", "e")
    two = compute_trial_id("S04_bank_pairs", p2, "short", code, "f", "e")
    assert one != two
    doc = s04_bank_pairs.__doc__ or ""
    assert "plan section 7" in doc
    assert "Gatev, Goetzmann & Rouwenhorst (2006)" in doc  # rule and basis
    assert "Long-only halves the hedge" in doc
    assert "short-term" in doc
    assert "reversal" in doc


def synthetic_logs(seed: int, n: int = 40) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0, 0.01, n)
    return {t: list(base * (1 + i / 5) + rng.normal(0.0, 0.004, n)) for i, t in enumerate("ABCDEF")}


def test_weights_are_long_only_finite_and_at_most_one() -> None:
    seen_open = False
    for seed in range(40):
        frame = feature_frame(synthetic_logs(seed))
        w = make(30, 3, entry_z=1.0, max_hold=10).target_weights(frame, asof_of(frame))
        assert (w >= 0).all()
        assert np.isfinite(w.to_numpy()).all()
        assert w.sum() <= 1 + 1e-9
        seen_open |= not w.empty
    assert seen_open  # the loop is not vacuous


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    frame = feature_frame(synthetic_logs(3))
    cut = sorted(frame["date"].unique())[-6]
    clean = frame[frame["date"] <= cut]
    asof = pd.Timestamp(cut)
    with pytest.raises(LookaheadError):
        asof_guard(frame, asof)
    with pytest.raises(LookaheadError):
        make(30, 3, 1.0).target_weights(frame, asof)
    expected = make(30, 3, 1.0).target_weights(clean, asof)
    garbage = frame[frame["date"] > cut].assign(ret_1d=0.5)
    clamped = pd.concat([clean, garbage])
    clamped = clamped[pd.to_datetime(clamped["date"]) <= asof]
    assert make(30, 3, 1.0).target_weights(clamped, asof).equals(expected)


def test_deterministic_and_row_order_independent() -> None:
    frame = feature_frame(synthetic_logs(5))
    strategy = make(30, 3, 1.0)
    first = strategy.target_weights(frame, asof_of(frame))
    assert not first.empty
    assert strategy.target_weights(frame, asof_of(frame)).equals(first)
    for seed in range(5):
        shuffled = frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert strategy.target_weights(shuffled, asof_of(frame)).equals(first)


def test_bad_frames_are_refused() -> None:
    frame = feature_frame(synthetic_logs(1))
    with pytest.raises(ValueError, match="lack columns"):
        make(30).target_weights(frame.drop(columns=["ret_1d"]), asof_of(frame))
    with pytest.raises(ValueError, match="more than one"):
        make(30).target_weights(pd.concat([frame, frame]), asof_of(frame))


# ---- backtest on the synthetic market (long enough for form = 250)
def long_market(
    cfg: AppConfig, tickers: int = 14
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    syn = cfg.data.synthetic.model_copy(update={"start": LONG_START})
    cfg = cfg.model_copy(update={"data": cfg.data.model_copy(update={"synthetic": syn})})
    names = universe_tickers(cfg)[:tickers]
    source = SyntheticSource(cfg)
    prices = source.fetch_daily(names, LONG_START, LONG_END).assign(price_basis="synthetic")
    actions = source.fetch_corporate_actions(names, LONG_START, LONG_END)
    adjusted = prices.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = prices[["ticker", "date", "high", "low", "close", "volume"]]
    return prices, actions, compute_features(adjusted, exec_, names, actions=actions), names


def run_long_smoke(
    strategy: Strategy, cfg: AppConfig
) -> tuple[SimResult, dict[date, pd.Series], pd.DataFrame]:
    prices, actions, features, _ = long_market(cfg)
    days = sorted(pd.to_datetime(prices["date"]).dt.date.unique())
    calendar = TradingCalendar.from_sessions(days)
    sessions_set = set(days)
    targets: dict[date, pd.Series] = {}
    for day in decision_days(calendar, "short", LONG_START, LONG_END):
        if day in sessions_set:
            visible = features[features["date"] <= day]  # load_features(asof=) clamp
            targets[day] = strategy.target_weights(visible, pd.Timestamp(day))
    result = run_simulation(
        prices, actions, targets, calendar, make_params(cfg, "executable", 11_000_000)
    )
    return result, targets, features


def packaged_s04() -> S04BankPairs:
    return S04BankPairs({"form": 250, "k": 5, "entry_z": 2.0, "max_hold": 10}, ("short",))


def test_smoke_backtest_on_the_synthetic_market(engine_cfg: AppConfig) -> None:
    result, targets, features = run_long_smoke(packaged_s04(), engine_cfg)
    assert features["date"].nunique() > 300
    assert len(targets) >= 40
    invested = [t for t in targets.values() if not t.empty]
    assert invested  # S04 opened a pair at some point
    assert all(t.sum() <= 1 + 1e-9 for t in invested)
    assert not result.trades.empty
    assert_ledger_consistent(result)


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, names = long_market(engine_cfg)
    strategy = packaged_s04()
    days = sorted(features["date"].unique())
    # the first asof (after 250 sessions) where S04 holds something, so the check is not vacuous
    asof = next(
        d
        for d in days[250:-20]
        if not strategy.target_weights(features[features["date"] <= d], pd.Timestamp(d)).empty
    )
    visible = features[features["date"] <= asof]
    expected = strategy.target_weights(visible, pd.Timestamp(asof))
    assert not expected.empty
    assert len(visible) < len(features)

    perturbed = prices.copy()
    later = pd.to_datetime(perturbed["date"]).dt.date > asof
    perturbed.loc[later, ["open", "high", "low", "close"]] *= 1.5
    adjusted = perturbed.rename(columns={"high": "adj_high", "close": "adj_close"})[
        ["ticker", "date", "adj_high", "adj_close"]
    ].assign(adj_version="synthetic", signal_ok=True)
    exec_ = perturbed[["ticker", "date", "high", "low", "close", "volume"]]
    redone = compute_features(adjusted, exec_, names, actions=actions)
    got = strategy.target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)


def test_benchmark_sanity_14_tickers_250_sessions_is_fast(engine_cfg: AppConfig) -> None:
    import time

    _, _, features, names = long_market(engine_cfg, 14)
    assert len(names) == 14
    asof = sorted(features["date"].unique())[249]
    visible = features[features["date"] <= asof]
    start = time.perf_counter()
    packaged_s04().target_weights(visible, pd.Timestamp(asof))
    assert time.perf_counter() - start < 5.0  # loose bound; measured about 0.02 s
