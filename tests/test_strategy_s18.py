"""S18 Hierarchical Risk Parity (P1-T19). Synthetic fixtures only; numpy cross-checks."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent
from test_strategy_s04 import sessions
from test_strategy_s08 import LONG_END, LONG_START, long_market
from vnstratlab.calendar import TradingCalendar, decision_days
from vnstratlab.config.models import AppConfig
from vnstratlab.engine import make_params, run_simulation
from vnstratlab.features import compute_features
from vnstratlab.strategies.base import LookaheadError, Strategy, asof_guard
from vnstratlab.strategies.builtin import s18_hrp
from vnstratlab.strategies.builtin.s18_hrp import (
    S18Hrp,
    drop_nan_pairs,
    min_observations,
    quasi_diagonal,
)
from vnstratlab.strategies.registry import (
    compute_trial_id,
    get_strategy_class,
    strategy_code_hash,
)

NAN = math.nan
WINDOW = 20
PACKAGED = {"window": 250}


def make(window: int = WINDOW) -> S18Hrp:
    return S18Hrp({"window": window}, ("long",))


def feature_frame(returns: dict[str, list[float]]) -> pd.DataFrame:
    """Long frame (ticker, date, ret_1d); a NaN return keeps its row."""
    days = sessions(len(next(iter(returns.values()))))
    return pd.concat(
        [pd.DataFrame({"ticker": t, "date": days, "ret_1d": v}) for t, v in returns.items()],
        ignore_index=True,
    )


def asof_of(frame: pd.DataFrame) -> pd.Timestamp:
    return pd.Timestamp(frame["date"].max())


# ------------------------------------------------------------------ independent HRP (numpy only)


def ivp_variance(cov: np.ndarray, idx: list[int]) -> float:
    sub = cov[np.ix_(idx, idx)]
    w = 1.0 / np.diag(sub)
    w /= w.sum()
    return float(w @ sub @ w)


def split_alpha(cov: np.ndarray, first: list[int], second: list[int]) -> float:
    """Weight share of ``first`` in a bisection step."""
    v1, v2 = ivp_variance(cov, first), ivp_variance(cov, second)
    return 1.0 - v1 / (v1 + v2)


def random_returns(seed: int = 3) -> dict[str, list[float]]:
    """Z: independent; A, B: both load on one factor x (A, B correlated about 0.99)."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 0.01, WINDOW)
    return {
        "A": list(x + rng.normal(0.0, 0.001, WINDOW)),
        "B": list(0.5 * x + rng.normal(0.0, 0.0005, WINDOW)),
        "Z": list(rng.normal(0.0, 0.02, WINDOW)),
    }


def test_two_correlated_assets_and_one_independent_match_numpy() -> None:
    rets = random_returns()
    data = np.array([rets["A"], rets["B"], rets["Z"]])
    cov = np.cov(data)  # ddof 1, like pandas
    corr = np.corrcoef(data)
    assert corr[0, 1] > 0.95
    assert abs(corr[0, 2]) < 0.6  # A-B merge first in single linkage
    # clusters: {A, B} and {Z}; top bisection splits them, then A | B
    a_top = split_alpha(cov, [2], [0, 1])  # share of Z
    a_ab = split_alpha(cov, [0], [1])  # share of A inside the pair
    want = {"Z": a_top, "A": (1 - a_top) * a_ab, "B": (1 - a_top) * (1 - a_ab)}
    got = make().target_weights(feature_frame(rets), asof_of(feature_frame(rets)))
    assert got.sum() == pytest.approx(1.0)
    assert sorted(got.index) == ["A", "B", "Z"]
    for ticker, weight in want.items():
        assert got[ticker] == pytest.approx(weight, rel=1e-9)
    # B has the lowest variance, so it gets more than A inside the pair; Z is alone and risky
    assert got["B"] > got["A"]


def test_independent_asset_named_first_gives_the_same_answer() -> None:
    rets = random_returns()
    renamed = {"A": rets["Z"], "B": rets["A"], "C": rets["B"]}
    got = make().target_weights(feature_frame(renamed), asof_of(feature_frame(renamed)))
    ref = make().target_weights(feature_frame(rets), asof_of(feature_frame(rets)))
    assert got["A"] == pytest.approx(ref["Z"])
    assert got["B"] == pytest.approx(ref["A"])
    assert got["C"] == pytest.approx(ref["B"])


def test_four_assets_in_two_correlated_pairs_match_numpy() -> None:
    rng = np.random.default_rng(11)
    x, y = rng.normal(0.0, 0.01, WINDOW), rng.normal(0.0, 0.02, WINDOW)
    rets = {
        "A": list(x + rng.normal(0.0, 0.001, WINDOW)),
        "B": list(2.0 * x + rng.normal(0.0, 0.002, WINDOW)),
        "C": list(y + rng.normal(0.0, 0.002, WINDOW)),
        "D": list(0.5 * y + rng.normal(0.0, 0.001, WINDOW)),
    }
    data = np.array([rets[t] for t in "ABCD"])
    cov, corr = np.cov(data), np.corrcoef(data)
    assert min(corr[0, 1], corr[2, 3]) > 0.95
    assert max(abs(corr[0, 2]), abs(corr[1, 3])) < 0.7
    top = split_alpha(cov, [0, 1], [2, 3])  # share of the pair A, B
    a_ab, a_cd = split_alpha(cov, [0], [1]), split_alpha(cov, [2], [3])
    want = [top * a_ab, top * (1 - a_ab), (1 - top) * a_cd, (1 - top) * (1 - a_cd)]
    frame = feature_frame(rets)
    got = make().target_weights(frame, asof_of(frame))
    assert got.sum() == pytest.approx(1.0)
    assert got.tolist() == pytest.approx(want, rel=1e-9)


def test_quasi_diagonal_expands_the_last_link() -> None:
    # 3 leaves: leaves 0, 1 merge into node 3; the root merges leaf 2 with node 3
    link = np.array([[0.0, 1.0, 0.1, 2.0], [2.0, 3.0, 0.5, 3.0]])
    assert quasi_diagonal(link, 3) == [2, 0, 1]
    # 4 leaves: (0, 1) -> 4, (2, 3) -> 5, root (4, 5)
    link4 = np.array([[0.0, 1.0, 0.1, 2.0], [2.0, 3.0, 0.2, 2.0], [4.0, 5.0, 0.9, 4.0]])
    assert quasi_diagonal(link4, 4) == [0, 1, 2, 3]


# ------------------------------------------------------------------ eligibility


def full_returns(seed: int = 1, tickers: str = "ABC", n: int = WINDOW) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    return {t: list(rng.normal(0.0, 0.01, n)) for t in tickers}


def test_min_observations_is_ceil_of_80_percent() -> None:
    assert min_observations(250) == 200
    assert min_observations(20) == 16
    assert min_observations(3) == 3
    assert min_observations(6) == 5


def test_a_ticker_with_too_few_observations_is_excluded() -> None:
    rets = full_returns(tickers="ABCD")
    short = list(rets["D"])
    short[:5] = [NAN] * 5  # 15 of 20 observed < 16 = ceil(0.8 * 20)
    rets["D"] = short
    frame = feature_frame(rets)
    got = make().target_weights(frame, asof_of(frame))
    assert sorted(got.index) == ["A", "B", "C"]
    assert got.sum() == pytest.approx(1.0)
    ok = list(rets["D"])
    ok[4] = 0.001  # 16 of 20 observed: eligible again
    rets["D"] = ok
    frame = feature_frame(rets)
    assert sorted(make().target_weights(frame, asof_of(frame)).index) == ["A", "B", "C", "D"]


def test_zero_variance_ticker_is_excluded() -> None:
    rets = full_returns(tickers="ABC")
    rets["F"] = [0.0] * WINDOW
    frame = feature_frame(rets)
    assert sorted(make().target_weights(frame, asof_of(frame)).index) == ["A", "B", "C"]


def test_only_tickers_with_a_row_on_asof_are_candidates() -> None:
    rets = full_returns(tickers="ABC")
    frame = feature_frame(rets)
    gone = feature_frame({"G": full_returns(seed=9, tickers="G")["G"]})
    gone = gone[gone["date"] < gone["date"].max()]  # G has no row on asof
    both = pd.concat([frame, gone], ignore_index=True)
    assert sorted(make().target_weights(both, asof_of(both)).index) == ["A", "B", "C"]


def test_zero_and_one_eligible_tickers() -> None:
    flat = feature_frame({"A": [0.0] * WINDOW, "B": [0.0] * WINDOW})
    assert make().target_weights(flat, asof_of(flat)).empty  # zero variance: 0 eligible
    one = feature_frame({"A": full_returns(tickers="A")["A"], "B": [0.0] * WINDOW})
    got = make().target_weights(one, asof_of(one))
    assert got.to_dict() == {"A": 1.0}  # exactly one eligible: all in it
    assert make().target_weights(one.iloc[0:0], pd.Timestamp("2026-03-10")).empty


def test_non_psd_pairwise_covariance_falls_back_to_cash() -> None:
    # regression (G2): pairwise covariance is not PSD here, a cluster variance goes <= 0 and the
    # bisection would give negative weights; the rule is cash, never a repaired or short target
    n = 250
    rng = np.random.default_rng(2)
    x = 0.01 * rng.normal(size=n)
    aaa = x.copy()
    aaa[-50:] = 0.0
    bbb = -x
    bbb[-50:] = NAN
    ppp = 0.5 * x + 0.003 * rng.normal(size=n)
    qqq = 0.5 * x + 0.003 * rng.normal(size=n)
    frame = feature_frame({"AAA": list(aaa), "BBB": list(bbb), "PPP": list(ppp), "QQQ": list(qqq)})
    got = make(n).target_weights(frame, asof_of(frame))
    assert got.empty
    assert (got >= 0).all()  # long-only holds trivially for cash


def test_insufficient_history_is_all_cash() -> None:
    frame = feature_frame(full_returns(n=WINDOW - 1))
    assert make().target_weights(frame, asof_of(frame)).empty


def test_asof_without_rows_is_all_cash() -> None:
    frame = feature_frame(full_returns())
    later = asof_of(frame) + pd.Timedelta(days=3)  # no session on asof; the frame ends earlier
    assert make().target_weights(frame, later).empty
    assert not make().target_weights(frame, asof_of(frame)).empty


def test_ticker_with_the_most_nan_pairs_is_dropped_first() -> None:
    # A is observed on the first 16 sessions only, B and C on the last 16: A overlaps each of
    # them on 12 < 16 sessions (NaN correlation), B and C overlap on 16. A has 2 NaN pairs, B and
    # C one each, so A goes first even though it is alphabetically earliest.
    rets = full_returns(tickers="ABC")
    rets["A"] = list(rets["A"][:16]) + [NAN] * 4
    rets["B"] = [NAN] * 4 + list(rets["B"][4:])
    rets["C"] = [NAN] * 4 + list(rets["C"][4:])
    frame = feature_frame(rets)
    got = make().target_weights(frame, asof_of(frame))
    assert sorted(got.index) == ["B", "C"]
    assert got.sum() == pytest.approx(1.0)


def test_nan_pair_tie_drops_the_later_ticker_alphabetically() -> None:
    rets = full_returns(tickers="PQR")
    rets["P"] = list(rets["P"][:16]) + [NAN] * 4  # 16 observed, overlap with Q is 12
    rets["Q"] = [NAN] * 4 + list(rets["Q"][4:])
    frame = feature_frame(rets)
    got = make().target_weights(frame, asof_of(frame))
    assert sorted(got.index) == ["P", "R"]  # P-Q pair NaN: the later ticker (Q) is dropped
    corr = pd.DataFrame(
        [[1.0, NAN, 0.1], [NAN, 1.0, 0.2], [0.1, 0.2, 1.0]], index=list("PQR"), columns=list("PQR")
    )
    assert drop_nan_pairs(corr) == ["P", "R"]


def test_result_is_independent_of_row_and_column_order() -> None:
    frame = feature_frame(random_returns())
    first = make().target_weights(frame, asof_of(frame))
    assert not first.empty
    assert make().target_weights(frame, asof_of(frame)).equals(first)
    for seed in range(5):
        shuffled = frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        got = make().target_weights(shuffled, asof_of(frame))
        assert got.equals(first)  # same tickers in the same order, same floats
    wide = feature_frame(random_returns())
    reordered = pd.concat([wide[wide["ticker"] == t] for t in "ZBA"], ignore_index=True)
    assert make().target_weights(reordered, asof_of(frame)).equals(first)


# ------------------------------------------------------------------ params and contract


def test_history_contract_follows_the_window() -> None:
    assert S18Hrp.lookback_sessions == 250
    assert make(250).lookback_sessions == 250
    assert make(20).lookback_sessions == 20


@pytest.mark.parametrize(
    "over", [{"window": 2}, {"window": 250.0}, {"window": True}, {"window": "250"}]
)
def test_bad_param_values_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="window must"):
        S18Hrp(over, ("long",))


@pytest.mark.parametrize("params", [{}, {"window": 250, "extra": 1}, {"n": 4}])
def test_bad_param_keys_are_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="S18 params"):
        S18Hrp(params, ("long",))


def test_missing_column_and_duplicates_are_refused() -> None:
    frame = feature_frame(full_returns())
    with pytest.raises(ValueError, match="lack columns"):
        make().target_weights(frame.drop(columns=["ret_1d"]), asof_of(frame))
    with pytest.raises(ValueError, match="more than one"):
        make().target_weights(pd.concat([frame, frame]), asof_of(frame))


def test_registered_identity_and_docstring() -> None:
    assert get_strategy_class("S18_hrp") is S18Hrp
    assert isinstance(make(), Strategy)
    code = strategy_code_hash(S18Hrp)
    a = compute_trial_id("S18_hrp", PACKAGED, "long", code, "f", "e")
    b = compute_trial_id("S18_hrp", {"window": 120}, "long", code, "f", "e")
    c = compute_trial_id("S18_hrp", PACKAGED, "long", code + "x", "f", "e")
    assert len({a, b, c}) == 3
    doc = s18_hrp.__doc__ or ""
    assert "plan section 7" in doc
    assert "Lopez de Prado (2016)" in doc
    assert "single-linkage" in doc
    assert "min_obs" in doc


def test_weights_are_long_only_finite_and_sum_to_one() -> None:
    frame = feature_frame(random_returns())
    w = make().target_weights(frame, asof_of(frame))
    assert (w > 0).all()
    assert np.isfinite(w.to_numpy()).all()
    assert w.sum() == pytest.approx(1.0)


def test_future_rows_are_refused_and_cannot_change_the_output() -> None:
    frame = feature_frame(full_returns(n=WINDOW + 5))
    cut = sorted(frame["date"].unique())[-6]
    asof = pd.Timestamp(cut)
    with pytest.raises(LookaheadError):
        asof_guard(frame, asof)
    with pytest.raises(LookaheadError):
        make().target_weights(frame, asof)
    clean = frame[frame["date"] <= cut]
    expected = make().target_weights(clean, asof)
    assert not expected.empty
    garbage = frame[frame["date"] > cut].assign(ret_1d=0.5)
    both = pd.concat([clean, garbage])
    clamped = both[pd.to_datetime(both["date"]) <= asof]
    assert make().target_weights(clamped, asof).equals(expected)
    # the module itself also ignores rows after asof (the guard sits in target_weights)
    assert make().compute_weights(both, asof).equals(expected)


def test_deterministic() -> None:
    frame = feature_frame(random_returns())
    first = make().target_weights(frame, asof_of(frame))
    assert make().target_weights(frame, asof_of(frame)).equals(first)


# ------------------------------------------------------------------ smoke backtest (long market)


def packaged_s18() -> S18Hrp:
    return S18Hrp(PACKAGED, ("long",))


def test_smoke_backtest_on_a_long_synthetic_market(engine_cfg: AppConfig) -> None:
    prices, actions, features, cfg = long_market(engine_cfg)
    days = sorted(pd.to_datetime(prices["date"]).dt.date.unique())
    assert len(days) >= 300
    calendar = TradingCalendar.from_sessions(days)
    strategy = packaged_s18()
    targets: dict[date, pd.Series] = {}
    for day in decision_days(calendar, "long", LONG_START, LONG_END):
        if day in set(days):
            visible = features[features["date"] <= day]
            targets[day] = strategy.target_weights(visible, pd.Timestamp(day))
    invested = [t for t in targets.values() if not t.empty]
    assert invested  # 250 sessions of returns exist on late decision days
    for t in invested:
        assert (t > 0).all()
        assert t.sum() == pytest.approx(1.0)
    result = run_simulation(
        prices, actions, targets, calendar, make_params(cfg, "executable", 11_000_000)
    )
    assert_ledger_consistent(result)
    assert not result.trades.empty


def test_future_prices_cannot_change_a_target(engine_cfg: AppConfig) -> None:
    prices, actions, features, _ = long_market(engine_cfg)
    asof = date(2023, 9, 29)
    visible = features[features["date"] <= asof]
    expected = packaged_s18().target_weights(visible, pd.Timestamp(asof))
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
    got = packaged_s18().target_weights(redone[redone["date"] <= asof], pd.Timestamp(asof))
    assert got.equals(expected)
