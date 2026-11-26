"""S05 residual mean reversion (P1-T16). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s04 import long_market, sessions
from vnstratlab.config.models import AppConfig
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s05_residual_reversion
from vnstratlab.strategies.builtin.s05_residual_reversion import (
    S05ResidualReversion,
    residual_z,
)
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

NAN = math.nan

# Group story (window 6): u = +-0.01 alternating (mean 0). Six tickers hold u + e, and the e's
# sum to 0 in every session, so the group return is exactly u. Two shapes of e (scaled by 0.03):
#   P1 = [1, 1, 1, 1, 0, 0]     P4 = [0, 1, 1, 0, 0, 0]
#   A +P1, B -P1, C +P4, D -P4, E +P1, F -P1.
# cov(u, e) = 0 for both shapes, so beta = 1, alpha = mean(e) and the residual is e - mean(e).
#
# +P1: e = 0.03 x4, 0, 0; mean 0.02; residual +0.01 x4, -0.02 x2 (sums to 0)
#   X = 0.01 0.02 0.03 0.04 0.02 0.00; mean 0.02; deviations -0.01 0 0.01 0.02 0 -0.02
#   sum of squares 1e-3; variance 2e-4; std 0.0141421
#   z = (0 - 0.02) / 0.0141421 = -sqrt(2) = -1.41421  (A, E; the mirror -P1 gives +1.41421: B, F)
# +P4: e = 0, 0.03, 0.03, 0, 0, 0; mean 0.01; residual -0.01 +0.02 +0.02 -0.01 -0.01 -0.01
#   X = -0.01 0.01 0.03 0.02 0.01 0.00; mean 0.01; deviations -0.02 0 0.02 0.01 0 -0.01
#   sum of squares 1e-3; std 0.0141421; z = (0 - 0.01) / 0.0141421 = -0.70711 (C; D is +0.70711)
U = [0.01, -0.01] * 3
P1 = [1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
P4 = [0.0, 1.0, 1.0, 0.0, 0.0, 0.0]
SHAPES = {"A": (P1, 1), "B": (P1, -1), "C": (P4, 1), "D": (P4, -1), "E": (P1, 1), "F": (P1, -1)}
Z_P1 = math.sqrt(2.0)
Z_P4 = 1.0 / math.sqrt(2.0)


def make(window: int = 6, entry_z: float = 1.0, n: int = 2) -> S05ResidualReversion:
    return S05ResidualReversion({"window": window, "entry_z": entry_z, "n": n}, ("short",))


def feature_frame(returns: dict[str, list[float]]) -> pd.DataFrame:
    """Long frame (ticker, date, ret_1d) from simple daily returns."""
    days = sessions(len(next(iter(returns.values()))))
    return pd.concat(
        [pd.DataFrame({"ticker": t, "date": days, "ret_1d": v}) for t, v in returns.items()],
        ignore_index=True,
    )


def shaped_frame() -> pd.DataFrame:
    return feature_frame(
        {
            t: [u + sign * 0.03 * p for u, p in zip(U, shape, strict=True)]
            for t, (shape, sign) in SHAPES.items()
        }
    )


def asof_of(frame: pd.DataFrame) -> pd.Timestamp:
    return pd.Timestamp(frame["date"].max())


def test_residual_z_hand_numbers() -> None:
    g = np.array(U)
    e1 = 0.03 * np.array(P1)
    assert residual_z(g + e1, g, 6) == pytest.approx(-Z_P1, abs=1e-9)
    assert residual_z(g - e1, g, 6) == pytest.approx(Z_P1, abs=1e-9)
    assert pytest.approx(1.414214, abs=1e-6) == Z_P1
    e4 = 0.03 * np.array(P4)
    assert residual_z(g + e4, g, 6) == pytest.approx(-Z_P4, abs=1e-9)
    assert residual_z(g - e4, g, 6) == pytest.approx(Z_P4, abs=1e-9)
    assert pytest.approx(0.707107, abs=1e-6) == Z_P4


def test_the_intercept_is_part_of_the_residual() -> None:
    # a constant extra return is pure alpha: it leaves the residual (and z) unchanged
    g = np.array(U)
    e1 = 0.03 * np.array(P1)
    assert residual_z(g + e1 + 0.05, g, 6) == pytest.approx(residual_z(g + e1, g, 6), abs=1e-9)
    # and with no variation beyond alpha there is no residual at all
    assert math.isnan(residual_z(g + 0.02, g, 6))


def test_beta_is_estimated_not_assumed_to_be_one() -> None:
    # y = 2 g + e1: beta = 2 (cov(g, e1) = 0), residual is the same e1 - mean(e1)
    g = np.array(U)
    e1 = 0.03 * np.array(P1)
    assert residual_z(2.0 * g + e1, g, 6) == pytest.approx(-Z_P1, abs=1e-9)


def test_residual_z_matches_an_independent_regression() -> None:
    rng = np.random.default_rng(7)
    g = rng.normal(0.0, 0.01, 60)
    y = 1.7 * g + rng.normal(0.0, 0.005, 60) + 0.001
    design = np.column_stack([np.ones(60), g])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]  # [alpha, beta]
    residual = y - design @ coef
    cumulative = np.cumsum(residual)
    want = (cumulative[-1] - cumulative.mean()) / cumulative.std(ddof=1)
    assert abs(cumulative[-1]) < 1e-12  # OLS residuals sum to zero
    assert residual_z(y, g, 60) == pytest.approx(want, rel=1e-9)
    assert coef[1] == pytest.approx(1.7, abs=0.4)  # the data really have a non-unit beta


def test_residual_z_needs_observations_variation_and_the_last_session() -> None:
    g = np.array(U)
    y = g + 0.03 * np.array(P1)
    assert math.isfinite(residual_z(y, g, 6))
    assert math.isnan(residual_z(np.append(y[:-1], NAN), g, 6))  # not observed on asof
    thin = y.copy()
    thin[:2] = NAN  # 4 of 6 observed = 67 % < 80 %
    assert math.isnan(residual_z(thin, g, 6))
    assert math.isnan(residual_z(y, np.zeros(6), 6))  # the group did not move
    assert math.isnan(residual_z(np.full(6, 0.0), g, 6))  # residual is zero: no variation


def test_buys_the_n_most_negative_below_minus_entry_z() -> None:
    frame = shaped_frame()
    asof = asof_of(frame)
    # z: A -1.4142, E -1.4142 (tie), C -0.7071, D +0.7071, B +1.4142, F +1.4142
    # entry_z 1.0: A and E qualify (-1.4142 < -1); C (-0.7071) does not
    assert make(6, 1.0, 2).target_weights(frame, asof).to_dict() == {"A": 0.5, "E": 0.5}
    # n = 3 with two qualifiers: 1/3 each, the remaining 1/3 stays in cash
    three = make(6, 1.0, 3).target_weights(frame, asof)
    assert three.to_dict() == {"A": pytest.approx(1 / 3), "E": pytest.approx(1 / 3)}
    assert three.sum() == pytest.approx(2 / 3)
    # entry_z 0.5: A, E, C qualify; the 2 most negative are the tied A and E, not C
    assert sorted(make(6, 0.5, 2).target_weights(frame, asof).index) == ["A", "E"]
    # 3 names: C joins at 1/3
    assert sorted(make(6, 0.5, 3).target_weights(frame, asof).index) == ["A", "C", "E"]
    # tie-break by ticker symbol: n = 1 takes A (not E), whatever the row order
    assert make(6, 1.0, 1).target_weights(frame, asof).to_dict() == {"A": 1.0}
    reversed_rows = frame.iloc[::-1].reset_index(drop=True)
    assert make(6, 1.0, 1).target_weights(reversed_rows, asof).to_dict() == {"A": 1.0}


def test_nothing_below_the_threshold_means_all_cash() -> None:
    frame = shaped_frame()
    # |z| = 1.4142 is not below -1.5; exactly at the threshold is not enough either (strict)
    assert make(6, 1.5, 2).target_weights(frame, asof_of(frame)).empty
    assert make(6, Z_P1, 2).target_weights(frame, asof_of(frame)).empty


def test_a_thin_or_unobserved_ticker_is_not_eligible() -> None:
    returns = {
        t: [u + sign * 0.03 * p for u, p in zip(U, shape, strict=True)]
        for t, (shape, sign) in SHAPES.items()
    }
    returns["A"] = [NAN, NAN, *returns["A"][2:]]  # 67 % observed: skipped
    frame = feature_frame(returns)
    thin = make(6, 0.0001, 6).target_weights(frame, asof_of(frame))
    assert "A" not in thin.index
    assert not thin.empty
    gone = shaped_frame()
    last = gone["date"] == gone["date"].max()
    gone = gone[~(last & (gone["ticker"] == "A"))]  # A has no row on asof
    no_row = make(6, 0.0001, 6).target_weights(gone, asof_of(gone))
    assert "A" not in no_row.index
    assert not no_row.empty


def test_insufficient_history_is_all_cash() -> None:
    frame = shaped_frame()
    assert not make(6, 1.0, 2).target_weights(frame, asof_of(frame)).empty
    assert make(7, 1.0, 2).target_weights(frame, asof_of(frame)).empty  # 6 sessions < window 7
    assert make(6).target_weights(frame.iloc[0:0], pd.Timestamp("2026-03-10")).empty
    assert make(6).target_weights(frame, asof_of(frame) + timedelta(days=3)).empty


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"window": 60, "entry_z": 1.5},
        {"window": 60, "entry_z": 1.5, "n": 2, "extra": 1},
        {"window": True, "entry_z": 1.5, "n": 2},
        {"window": 60.0, "entry_z": 1.5, "n": 2},
        {"window": 2, "entry_z": 1.5, "n": 2},
        {"window": 60, "entry_z": 0.0, "n": 2},
        {"window": 60, "entry_z": -1.5, "n": 2},
        {"window": 60, "entry_z": math.nan, "n": 2},
        {"window": 60, "entry_z": math.inf, "n": 2},
        {"window": 60, "entry_z": True, "n": 2},
        {"window": 60, "entry_z": "1.5", "n": 2},
        {"window": 60, "entry_z": 1.5, "n": 0},
        {"window": 60, "entry_z": 1.5, "n": True},
    ],
)
def test_bad_params_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"S05 params|must be"):
        S05ResidualReversion(params, ("short",))


def test_lookback_sessions_is_the_window() -> None:
    assert make(60).lookback_sessions == 60
    assert make(6).lookback_sessions == 6
    assert S05ResidualReversion.lookback_sessions == 60  # the class carries the frozen window


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S05_residual_reversion") is S05ResidualReversion
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S05ResidualReversion)
    a = compute_trial_id(
        "S05_residual_reversion", {"window": 60, "entry_z": 1.5, "n": 2}, "short", code, "f", "e"
    )
    b = compute_trial_id(
        "S05_residual_reversion", {"window": 60, "entry_z": 1.5, "n": 3}, "short", code, "f", "e"
    )
    assert a != b
    doc = s05_residual_reversion.__doc__ or ""
    assert "plan section 7" in doc
    assert "Avellaneda & Lee (2010)" in doc  # rule and basis


def random_returns(seed: int, n: int = 40) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0, 0.01, n)
    return {
        t: list(base * (0.5 + i / 3) + rng.normal(0.0, 0.006, n)) for i, t in enumerate("ABCDEFG")
    }


def test_weights_are_long_only_finite_and_at_most_one() -> None:
    seen_open = False
    for seed in range(40):
        frame = feature_frame(random_returns(seed))
        w = make(30, 1.0, 2).target_weights(frame, asof_of(frame))
        assert (w >= 0).all()
        assert np.isfinite(w.to_numpy()).all()
        assert w.sum() <= 1 + 1e-9
        seen_open |= not w.empty
    assert seen_open


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    frame = feature_frame(random_returns(2))
    cut = sorted(frame["date"].unique())[-6]
    asof = pd.Timestamp(cut)
    with pytest.raises(LookaheadError):
        asof_guard(frame, asof)
    with pytest.raises(LookaheadError):
        make(30).target_weights(frame, asof)
    clean = frame[frame["date"] <= cut]
    expected = make(30, 0.5).target_weights(clean, asof)
    assert not expected.empty
    garbage = frame[frame["date"] > cut].assign(ret_1d=0.5)
    both = pd.concat([clean, garbage])
    clamped = both[pd.to_datetime(both["date"]) <= asof]
    assert make(30, 0.5).target_weights(clamped, asof).equals(expected)


def test_deterministic_and_row_order_independent() -> None:
    frame = feature_frame(random_returns(4))
    strategy = make(30, 0.5)
    first = strategy.target_weights(frame, asof_of(frame))
    assert not first.empty
    assert strategy.target_weights(frame, asof_of(frame)).equals(first)
    for seed in range(5):
        shuffled = frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert strategy.target_weights(shuffled, asof_of(frame)).equals(first)


def test_bad_frames_are_refused() -> None:
    frame = feature_frame(random_returns(1))
    with pytest.raises(ValueError, match="lack columns"):
        make(30).target_weights(frame.drop(columns=["ret_1d"]), asof_of(frame))
    with pytest.raises(ValueError, match="more than one"):
        make(30).target_weights(pd.concat([frame, frame]), asof_of(frame))


def packaged_s05() -> S05ResidualReversion:
    return S05ResidualReversion({"window": 60, "entry_z": 1.5, "n": 2}, ("short",))


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, names = long_market(engine_cfg)
    strategy = packaged_s05()
    days = sorted(features["date"].unique())
    asof = next(
        d
        for d in days[60:-20]
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
