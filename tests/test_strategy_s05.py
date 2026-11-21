"""S05 residual mean reversion (P1-T16). Synthetic fixtures only; numbers hand-computed."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent
from test_strategy_s04 import long_market, run_long_smoke, sessions
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

# Group story (window 6): u = +-0.01 alternating (mean 0). Five tickers hold u + e with a
# CONSTANT e per ticker and the e's sum to 0, so the group return is exactly u:
#   e = A -0.02, B -0.04, C +0.01, D +0.02, E +0.03.
# For every ticker cov(u, e) = 0, so beta = 1 and the residual (alpha left out) is e itself.
# X_k = k * e (k = 1..6): last 6e, mean 3.5e, std |e| * 1.870829 (std of 1..6, ddof 1)
# z = 2.5 e / (|e| * 1.870829) = sign(e) * 1.336306: A and B -1.3363 (tie), C, D, E +1.3363.
U = [0.01, -0.01] * 3
E_CONST = {"A": -0.02, "B": -0.04, "C": 0.01, "D": 0.02, "E": 0.03}
Z_CONST = 2.5 / math.sqrt(3.5)  # 1.336306 = 2.5 / 1.870829 (std of 1..6 with ddof 1 is sqrt(3.5))


def make(window: int = 6, entry_z: float = 1.0, n: int = 2) -> S05ResidualReversion:
    return S05ResidualReversion({"window": window, "entry_z": entry_z, "n": n}, ("short",))


def feature_frame(returns: dict[str, list[float]]) -> pd.DataFrame:
    """Long frame (ticker, date, ret_1d) from simple daily returns."""
    days = sessions(len(next(iter(returns.values()))))
    return pd.concat(
        [pd.DataFrame({"ticker": t, "date": days, "ret_1d": v}) for t, v in returns.items()],
        ignore_index=True,
    )


def const_frame() -> pd.DataFrame:
    return feature_frame({t: [u + e for u in U] for t, e in E_CONST.items()})


def asof_of(frame: pd.DataFrame) -> pd.Timestamp:
    return pd.Timestamp(frame["date"].max())


def test_residual_z_hand_numbers() -> None:
    # g = u; y = u - 0.02 for 6 sessions -> beta 1, residual -0.02 each,
    # X = -0.02, -0.04, ..., -0.12; mean -0.07; last - mean = -0.05; std = 0.02 * 1.870829
    g = np.array(U)
    z = residual_z(g - 0.02, g, 6)
    assert z == pytest.approx(-Z_CONST, abs=1e-9)
    assert z == pytest.approx(-1.336306, abs=1e-6)
    assert residual_z(g + 0.01, g, 6) == pytest.approx(Z_CONST, abs=1e-9)


def test_residual_z_with_non_constant_residual() -> None:
    # two tickers: e_A = -0.03 for 4 sessions then 0, e_B = +0.03 then 0 (cov with u is 0 again)
    # X_A = -0.03 -0.06 -0.09 -0.12 -0.12 -0.12; mean -0.09
    # deviations 0.06 0.03 0 -0.03 -0.03 -0.03; sum of squares 0.0072; variance 0.00144
    # std 0.037947; z = (-0.12 + 0.09) / 0.037947
    g = np.array(U)
    e = np.array([-0.03, -0.03, -0.03, -0.03, 0.0, 0.0])
    assert residual_z(g + e, g, 6) == pytest.approx(-0.790569, abs=1e-6)
    assert residual_z(g - e, g, 6) == pytest.approx(0.790569, abs=1e-6)


def test_residual_z_matches_an_independent_regression() -> None:
    rng = np.random.default_rng(7)
    g = rng.normal(0.0, 0.01, 60)
    y = 1.7 * g + rng.normal(0.0, 0.005, 60) + 0.001
    design = np.column_stack([np.ones(60), g])
    beta = float(np.linalg.lstsq(design, y, rcond=None)[0][1])  # [alpha, beta]
    cumulative = np.cumsum(y - beta * g)  # alpha is not part of the residual
    want = (cumulative[-1] - cumulative.mean()) / cumulative.std(ddof=1)
    assert residual_z(y, g, 60) == pytest.approx(want, rel=1e-9)
    assert beta == pytest.approx(1.7, abs=0.4)  # the data really have a non-unit beta


def test_residual_z_needs_observations_variation_and_the_last_session() -> None:
    g = np.array(U)
    y = g - 0.02
    assert math.isnan(residual_z(np.append(y[:-1], NAN), g, 6))  # not observed on asof
    thin = y.copy()
    thin[:2] = NAN  # 4 of 6 observed = 67 % < 80 %
    assert math.isnan(residual_z(thin, g, 6))
    assert math.isnan(residual_z(y, np.zeros(6), 6))  # the group did not move
    assert math.isnan(residual_z(np.full(6, 0.0), g, 6))  # residual is zero: no variation


def test_buys_the_n_most_negative_below_minus_entry_z() -> None:
    frame = const_frame()
    asof = asof_of(frame)
    # A and B tie at -1.3363 < -1.0: both qualify; C, D, E are positive
    assert make(6, 1.0, 2).target_weights(frame, asof).to_dict() == {"A": 0.5, "B": 0.5}
    # n = 3: only two qualifiers -> 1/3 each, the remaining 1/3 stays in cash
    three = make(6, 1.0, 3).target_weights(frame, asof)
    assert three.to_dict() == {"A": pytest.approx(1 / 3), "B": pytest.approx(1 / 3)}
    assert three.sum() == pytest.approx(2 / 3)
    # tie-break by ticker symbol: n = 1 takes A
    assert make(6, 1.0, 1).target_weights(frame, asof).to_dict() == {"A": 1.0}
    reversed_rows = frame.iloc[::-1].reset_index(drop=True)
    assert make(6, 1.0, 1).target_weights(reversed_rows, asof).to_dict() == {"A": 1.0}


def test_nothing_below_the_threshold_means_all_cash() -> None:
    frame = const_frame()
    # |z| = 1.3363 is not below -1.5
    assert make(6, 1.5, 2).target_weights(frame, asof_of(frame)).empty
    # exactly at the threshold is not enough either (strict)
    assert make(6, Z_CONST, 2).target_weights(frame, asof_of(frame)).empty


def test_a_thin_or_unobserved_ticker_is_not_eligible() -> None:
    returns = {t: [u + e for u in U] for t, e in E_CONST.items()}
    returns["A"] = [NAN, NAN, *returns["A"][2:]]  # 67 % observed: skipped, B wins
    frame = feature_frame(returns)
    assert make(6, 1.0, 1).target_weights(frame, asof_of(frame)).to_dict() == {"B": 1.0}
    gone = const_frame()
    last = gone["date"] == gone["date"].max()
    gone = gone[~(last & (gone["ticker"] == "A"))]  # A has no row on asof
    assert make(6, 1.0, 1).target_weights(gone, asof_of(gone)).to_dict() == {"B": 1.0}


def test_insufficient_history_is_all_cash() -> None:
    frame = const_frame()
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


def test_smoke_backtest_on_the_synthetic_market(engine_cfg: AppConfig) -> None:
    result, targets, _ = run_long_smoke(packaged_s05(), engine_cfg)
    assert len(targets) >= 40
    invested = [t for t in targets.values() if not t.empty]
    assert invested
    assert all(t.sum() <= 1 + 1e-9 for t in invested)
    assert not result.trades.empty
    assert_ledger_consistent(result)


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
