"""Feature store v1 (P1-T10). Synthetic fixtures only; hand-computed numbers in the comments."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine_helpers import make_days
from vnstratlab.data.protocol import SourceError
from vnstratlab.data.store import MarketStore
from vnstratlab.features import (
    FEATURE_COLUMNS,
    FEATURE_GROUPS,
    FeatureError,
    calendar_span_sessions,
    compute_features,
    feature_version,
)
from vnstratlab.features.build import asof_view, load_features
from vnstratlab.features.core import FEATURES_CODE_VERSION
from vnstratlab.features.groups import wilder_rsi
from vnstratlab.risk.atr import atr

VERSION = "ratio-v2:abc123"


def synthetic_frames(
    ticker: str,
    closes: Sequence[float],
    volume: Sequence[float] | float = 1_000.0,
    days: Sequence[date] | None = None,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    exec_closes: Sequence[float] | None = None,
    exec_volume: Sequence[float] | None = None,
    version: str = VERSION,
    signal_ok: Sequence[bool] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(prices_adjusted rows, prices_exec rows)`` of one ticker; high = low = close by default."""
    n = len(closes)
    days = list(days) if days is not None else make_days(n)
    hi = list(highs) if highs is not None else list(closes)
    lo = list(lows) if lows is not None else list(closes)
    vol = list(volume) if isinstance(volume, Sequence) else [volume] * n
    adjusted = pd.DataFrame(
        {
            "ticker": ticker,
            "date": days,
            "adj_high": hi,
            "adj_close": list(closes),
            "adj_version": version,
            "signal_ok": list(signal_ok) if signal_ok is not None else [True] * n,
        }
    )
    ec = list(exec_closes) if exec_closes is not None else list(closes)
    executed = pd.DataFrame(
        {
            "ticker": ticker,
            "date": days,
            "high": hi if exec_closes is None else ec,
            "low": lo if exec_closes is None else ec,
            "close": ec,
            "volume": list(exec_volume) if exec_volume is not None else vol,
        }
    )
    return adjusted, executed


def stack(*pairs: tuple[pd.DataFrame, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.concat([p[0] for p in pairs], ignore_index=True),
        pd.concat([p[1] for p in pairs], ignore_index=True),
    )


def row(out: pd.DataFrame, ticker: str, index: int) -> pd.Series:
    """The ``index``-th output row (0 based, date order) of ``ticker``."""
    return out[out["ticker"] == ticker].reset_index(drop=True).iloc[index]


# Made-up RSI series: 50, then 14 changes [+1, +1, -1, 0] x 3 + [+1, 0] (gains sum 7, losses sum 3),
# then -2 and +3. Wilder: first RSI (row 14) = 100 * 7 / (7 + 3) = 70 exactly; afterwards
# avg = (avg * 13 + x) / 14: row 15 avg gain 6.5 / 14 = 91 / 196, avg loss 67 / 196
# -> 100 * 91 / 158 = 57.5949; row 16 avg gain 1771 / 2744, avg loss 871 / 2744
# -> 100 * 1771 / 2642 = 67.0326.
RSI_SERIES = [50.0, 51, 52, 51, 51, 52, 53, 52, 52, 53, 54, 53, 53, 54, 54, 52, 55]
RSI_VALUES = [70.0, 57.5949, 67.0326]

# ------------------------------------------------------------------ 30-row hand fixture
# L: 100 for rows 0..9, then 101..120 (rows 10..29); volume 1000 + 10 * row
# M: 100 for rows 0..9, rises 1 per row to 115 (row 24), falls 1 per row to 110 (row 29)
# N: 95 for rows 0..9, then 95 + 0.2375 per row: 99.75 at row 29 (ret_20d = 0.05)
L_CLOSE = [100.0] * 10 + [float(100 + k) for k in range(1, 21)]
M_CLOSE = (
    [100.0] * 10 + [float(100 + k) for k in range(1, 16)] + [114.0, 113.0, 112.0, 111.0, 110.0]
)
N_CLOSE = [95.0] * 10 + [95.0 + 0.2375 * k for k in range(1, 21)]
L_VOLUME = [1000.0 + 10.0 * i for i in range(30)]


@pytest.fixture(scope="module")
def synthetic_hand() -> pd.DataFrame:
    adjusted, executed = stack(
        synthetic_frames("L", L_CLOSE, L_VOLUME),
        synthetic_frames("M", M_CLOSE),
        synthetic_frames("N", N_CLOSE),
    )
    return compute_features(adjusted, executed, ["L", "M", "N"])


def test_hand_close_vs_ma20_ret_20d_z_and_std(synthetic_hand: pd.DataFrame) -> None:
    last = row(synthetic_hand, "L", 29)
    # window rows 10..29 = 101..120: mean 110.5; 120 / 110.5 - 1 = 0.0859728507
    assert last["close_vs_ma20"] == pytest.approx(120 / 110.5 - 1, abs=1e-12)
    assert last["close_vs_ma20"] == pytest.approx(0.0859728507, abs=1e-9)
    # ret_20d: close[9] = 100 -> 120 / 100 - 1
    assert last["ret_20d"] == pytest.approx(0.2, abs=1e-12)
    # sample variance of 20 consecutive integers = n (n + 1) / 12 = 35; z = 9.5 / sqrt(35)
    assert last["z_ma20"] == pytest.approx(9.5 / math.sqrt(35), abs=1e-9)
    assert last["z_ma20"] == pytest.approx(1.6057, abs=1e-4)
    # std_20d: sample std of the 20 returns of rows 10..29 (1 / 100, 1 / 101, ... 1 / 119)
    rets = [(100 + k) / (99 + k) - 1 for k in range(1, 21)]
    mean = sum(rets) / 20
    expected = math.sqrt(sum((r - mean) ** 2 for r in rets) / 19)
    assert last["std_20d"] == pytest.approx(expected, abs=1e-12)
    assert last["std_20d"] == pytest.approx(0.000496426, abs=1e-9)  # hand value of the formula


def test_hand_vol_vs_avg20_and_value_traded(synthetic_hand: pd.DataFrame) -> None:
    last = row(synthetic_hand, "L", 29)
    # volume row 29 = 1290; mean of rows 10..29 = 1000 + 10 * 19.5 = 1195; 1290 / 1195 = 1.07950
    assert last["vol_vs_avg20"] == pytest.approx(1290 / 1195, abs=1e-12)
    # value traded: mean of close * volume over rows 10..29
    expected = sum((100 + k) * (1000 + 10 * (9 + k)) for k in range(1, 21)) / 20
    assert last["value_traded_20d"] == pytest.approx(expected, rel=1e-12)


def test_hand_high_20d_break(synthetic_hand: pd.DataFrame) -> None:
    # L: prior 20 highs (rows 9..28) peak at 119 < 120 -> break; M: peak 115 > 110 -> none
    assert row(synthetic_hand, "L", 29)["high_20d_break"] == 1.0
    assert row(synthetic_hand, "M", 29)["high_20d_break"] == 0.0
    assert math.isnan(
        row(synthetic_hand, "L", 19)["high_20d_break"]
    )  # 20 prior sessions needed (row 20)
    # row 20: rows 0..19 hold 100 and 101..110, so the prior high is 110 < close 111
    assert row(synthetic_hand, "L", 20)["high_20d_break"] == 1.0


def test_hand_close_20d_break_uses_prior_closes_not_highs() -> None:
    # H: close 100 for rows 0..19, then 101 (row 20), 101 (row 21), 102 (row 22); high = close + 5
    # high_20d_break: the prior 20 highs peak at 105 >= every close -> 0.0 at rows 20..22
    # close_20d_break: row 20: prior closes (rows 0..19) peak at 100 < 101 -> 1.0
    #                  row 21: prior closes (rows 1..20) peak at 101 == 101 -> 0.0 (not strictly)
    #                  row 22: prior closes (rows 2..21) peak at 101 < 102 -> 1.0
    #                  rows 0..19: fewer than 20 prior sessions -> NaN
    closes = [100.0] * 20 + [101.0, 101.0, 102.0]
    highs = [c + 5.0 for c in closes]
    out = compute_features(*synthetic_frames("H", closes, highs=highs), ["H"])
    got = out["close_20d_break"].tolist()
    assert all(math.isnan(v) for v in got[:20])
    assert got[20:] == [1.0, 0.0, 1.0]
    assert math.isnan(out["high_20d_break"].iloc[19])
    assert out["high_20d_break"].tolist()[20:] == [0.0, 0.0, 0.0]


def test_hand_close_20d_break_on_the_hand_fixture(synthetic_hand: pd.DataFrame) -> None:
    # L: prior 20 closes (rows 9..28) peak at 119 < 120 -> 1.0; M: peak 115 > 110 -> 0.0
    assert row(synthetic_hand, "L", 29)["close_20d_break"] == 1.0
    assert row(synthetic_hand, "M", 29)["close_20d_break"] == 0.0
    assert math.isnan(row(synthetic_hand, "L", 19)["close_20d_break"])
    assert row(synthetic_hand, "L", 20)["close_20d_break"] == 1.0


def test_close_20d_break_skips_missing_sessions() -> None:
    # a signal_ok = false session is missing: the window counts good sessions only
    closes = [100.0] * 20 + [500.0, 101.0]
    ok = [True] * 20 + [False, True]
    out = compute_features(*synthetic_frames("H", closes, signal_ok=ok), ["H"])
    assert len(out) == 21  # the bad row has no output row
    # last row: 20 prior good sessions are rows 0..19 (500 is missing) -> 101 > 100 -> 1.0
    assert out["close_20d_break"].iloc[-1] == 1.0


def test_hand_ret_1d_is_close_over_previous_good_close_minus_one() -> None:
    # closes 100, 110, 99, 99, 121: ret_1d = NaN, 110/100-1 = 0.1, 99/110-1 = -0.1, 0.0,
    # 121/99-1 = 0.2222...; the first good session has no previous close -> NaN
    out = compute_features(*synthetic_frames("R", [100.0, 110.0, 99.0, 99.0, 121.0]), ["R"])
    got = out["ret_1d"].tolist()
    assert math.isnan(got[0])
    assert got[1:] == pytest.approx([0.1, -0.1, 0.0, 121 / 99 - 1])
    assert "ret_1d" in FEATURE_COLUMNS
    assert "ret_1d" in FEATURE_GROUPS["returns"]


def test_hand_ret_6m_skip1m_is_close_21_back_over_close_126_back_minus_one() -> None:
    # closes 100 + i over 130 sessions: row t has close[t - 21] / close[t - 126] - 1
    closes = [100.0 + i for i in range(130)]
    out = compute_features(*synthetic_frames("M", closes), ["M"])
    got = out["ret_6m_skip1m"].to_numpy(dtype=float)
    assert np.isnan(got[:126]).all()  # warm-up: needs 126 prior sessions
    assert got[126] == pytest.approx(205.0 / 100.0 - 1)  # close[105] / close[0] - 1
    assert got[129] == pytest.approx(208.0 / 103.0 - 1)  # close[108] / close[3] - 1
    assert out["ret_12m_skip1m"].isna().all()  # 130 sessions are too few for the 250 window
    assert "ret_6m_skip1m" in FEATURE_GROUPS["trend_momentum"]
    cols = list(FEATURE_GROUPS["trend_momentum"])
    assert cols.index("ret_6m_skip1m") == cols.index("ret_12m_skip1m") + 1


def test_ret_1d_spans_a_missing_session_without_filling() -> None:
    # session 2 is signal_ok = false: it has no row and the next return is 3 vs 1 sessions back:
    # closes 100, 105, (999 missing), 126 -> ret_1d of the last row = 126 / 105 - 1 = 0.2
    ok = [True, True, False, True]
    out = compute_features(
        *synthetic_frames("R", [100.0, 105.0, 999.0, 126.0], signal_ok=ok), ["R"]
    )
    assert len(out) == 3
    assert out["ret_1d"].iloc[-1] == pytest.approx(0.2)


def test_features_code_version_is_v4() -> None:
    assert FEATURES_CODE_VERSION == "features-v4"


def test_hand_rs_20d_rank_and_group_median(synthetic_hand: pd.DataFrame) -> None:
    # ret_20d at row 29: L 120 / 100 - 1 = 0.2, M 110 / 100 - 1 = 0.1, N 99.75 / 95 - 1 = 0.05
    ranks = {t: row(synthetic_hand, t, 29)["rs_20d_rank"] for t in "LMN"}
    assert ranks == pytest.approx({"L": 1.0, "M": 2 / 3, "N": 1 / 3})
    # group median 0.1
    assert row(synthetic_hand, "L", 29)["rs_20d_vs_group_median"] == pytest.approx(0.1)
    assert row(synthetic_hand, "M", 29)["rs_20d_vs_group_median"] == pytest.approx(0.0, abs=1e-12)
    assert row(synthetic_hand, "N", 29)["rs_20d_vs_group_median"] == pytest.approx(-0.05)
    # ret_5d: L 120/115, M 110/115 (row 24 = 115), N 99.75/98.5625; median = M's
    r5 = {"L": 120 / 115 - 1, "M": 110 / 115 - 1, "N": 99.75 / 98.5625 - 1}
    median = sorted(r5.values())[1]
    assert row(synthetic_hand, "L", 29)["ret_5d_vs_group_median"] == pytest.approx(r5["L"] - median)


def test_wilder_rsi_matches_the_hand_computed_values() -> None:
    values = wilder_rsi(np.array(RSI_SERIES), 14)
    assert np.isnan(values[:14]).all()
    assert values[14] == pytest.approx(70.0, abs=1e-12)
    assert values[14:17] == pytest.approx(RSI_VALUES, abs=1e-4)


def test_rsi_14_and_rsi_2_columns_follow_the_hand_values() -> None:
    adjusted, executed = synthetic_frames("W", [*RSI_SERIES, *([55.0] * 10)])
    out = compute_features(adjusted, executed, ["W"])
    assert [row(out, "W", i)["rsi_14"] for i in (14, 15, 16)] == pytest.approx(RSI_VALUES, abs=1e-4)
    assert math.isnan(row(out, "W", 13)["rsi_14"])
    # rsi_2: changes +1, +1 -> no losses -> 100 at row 2; change -1 -> avg gain (1 + 0) / 2 = 0.5,
    # avg loss (0 + 1) / 2 = 0.5 -> 50 at row 3
    assert row(out, "W", 2)["rsi_2"] == 100.0
    assert row(out, "W", 3)["rsi_2"] == pytest.approx(50.0)
    assert math.isnan(row(out, "W", 1)["rsi_2"])


def test_rsi_edge_cases() -> None:
    assert wilder_rsi(np.array([1.0, 2.0, 3.0]), 2)[2] == 100.0  # no losses
    assert wilder_rsi(np.array([1.0, 1.0, 1.0]), 2)[2] == 50.0  # no moves


# ------------------------------------------------------------------ AC4 warm-up and missing
def test_warm_up_is_nan_and_never_backfilled(synthetic_hand: pd.DataFrame) -> None:
    rows = synthetic_hand[synthetic_hand["ticker"] == "L"].reset_index(drop=True)
    assert rows["ret_20d"].iloc[:20].isna().all()
    assert rows["ret_20d"].iloc[20:].notna().all()
    assert rows["close_vs_ma20"].iloc[:19].isna().all()
    assert not np.isnan(rows["close_vs_ma20"].iloc[19])
    assert rows["close_vs_ma50"].isna().all()  # 30 rows < 50
    assert rows["rsi_14"].iloc[:14].isna().all()
    assert rows["std_60d"].isna().all()


def test_a_missing_session_is_skipped_by_the_windows() -> None:
    days = make_days(25)
    kept = [d for i, d in enumerate(days) if i != 10]  # one session omitted
    closes = [float(100 + days.index(d)) for d in kept]
    adjusted, executed = synthetic_frames("S", closes, days=kept)
    out = compute_features(adjusted, executed, ["S"])
    assert len(out) == 24  # no row for the missing session, none invented
    # last row is day 24 = stored index 23; five stored sessions back is stored index 18 = day 19
    assert row(out, "S", 23)["ret_5d"] == pytest.approx(124 / 119 - 1)


def test_signal_ok_false_rows_are_missing_like_omitted_rows() -> None:
    days = make_days(30)
    closes = [100.0 + 2 * (i % 5) + i for i in range(30)]
    flag = [i != 25 for i in range(30)]
    adjusted, executed = synthetic_frames(
        "S", closes, list(range(1000, 1030)), days=days, signal_ok=flag
    )
    flagged = compute_features(adjusted, executed, ["S"])
    # the same data with the flagged row deleted from both inputs gives the same output
    keep = [i != 25 for i in range(30)]
    a2, e2 = adjusted[keep].reset_index(drop=True), executed[keep].reset_index(drop=True)
    pd.testing.assert_frame_equal(flagged, compute_features(a2, e2, ["S"]))
    assert len(flagged) == 29
    assert days[25] not in set(flagged["date"])
    # ret_5d at day 29 = stored index 28; five back = stored index 23 = day 23 (not day 24)
    assert row(flagged, "S", 28)["ret_5d"] == pytest.approx(closes[29] / closes[23] - 1)


def test_signal_ok_column_is_optional_and_null_counts_as_good() -> None:
    adjusted, executed = synthetic_frames("S", [100.0 + i for i in range(30)])
    full = compute_features(adjusted, executed, ["S"])
    pd.testing.assert_frame_equal(
        full, compute_features(adjusted.drop(columns="signal_ok"), executed, ["S"])
    )


def test_a_good_session_without_an_exec_row_has_nan_level_features_only() -> None:
    adjusted, executed = synthetic_frames("S", [100.0 + i for i in range(40)])
    executed = executed[executed.index != 30].reset_index(drop=True)
    out = compute_features(adjusted, executed, ["S"])
    assert len(out) == 40
    assert math.isnan(row(out, "S", 30)["value_traded_20d"])
    assert math.isnan(row(out, "S", 45 - 6)["value_traded_20d"])  # window still holds row 30
    assert row(out, "S", 39)["ret_20d"] == pytest.approx(139 / 119 - 1)  # adjusted unaffected
    assert not math.isnan(row(out, "S", 20)["value_traded_20d"])  # before the gap is fine


def test_sessions_in_window_sanity_note() -> None:
    days = make_days(40)
    assert calendar_span_sessions(days, 20) == 20.0
    sparse = [d for i, d in enumerate(days) if i % 5 != 2]  # one in five missing
    assert calendar_span_sessions(sparse, 20) > 20.0
    assert math.isnan(calendar_span_sessions(days[:5], 20))


# ------------------------------------------------------------------ AC5 / AC6 stock event
EVENT_AT = 255
EVENT_ROWS = 260


def synthetic_event_case() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[float]]:
    """Flat 100 (post-event basis); raw exec 110 and 1,000 shares before a 10 % stock dividend on
    row 255, 100 and 1,100 after. Adjusted rows before the event are divided by 1.1 -> 100."""
    n = EVENT_ROWS
    days = make_days(n)
    raw = [110.0 if i < EVENT_AT else 100.0 for i in range(n)]
    shares = [1000.0 if i < EVENT_AT else 1100.0 for i in range(n)]
    highs = [r + 1.0 for r in raw]
    lows = [r - 1.0 for r in raw]
    adjusted = pd.DataFrame(
        {
            "ticker": "S",
            "date": days,
            "adj_high": [h / 1.1 if i < EVENT_AT else h for i, h in enumerate(highs)],
            "adj_close": [100.0] * n,
            "adj_version": VERSION,
            "signal_ok": True,
        }
    )
    executed = pd.DataFrame(
        {"ticker": "S", "date": days, "high": highs, "low": lows, "close": raw, "volume": shares}
    )
    actions = pd.DataFrame(
        {
            "ticker": ["S", "S"],
            "ex_date": [days[EVENT_AT], days[10]],
            "type": ["stock", "cash"],
            "ratio_or_amount": [0.1, 500.0],
        }
    )
    factors = [1.1 if i == EVENT_AT else 1.0 for i in range(n)]
    return adjusted, executed, actions, factors


def test_returns_use_adjusted_and_levels_use_exec_across_a_stock_event() -> None:
    adjusted, executed, actions, _ = synthetic_event_case()
    out = compute_features(adjusted, executed, ["S"], actions=actions)
    last = row(out, "S", EVENT_ROWS - 1)
    # adjusted closes are flat: no artificial -9.09 % gap (the raw gap is 100 / 110 - 1)
    assert last["ret_5d"] == pytest.approx(0.0, abs=1e-12)
    assert last["ret_20d"] == pytest.approx(0.0, abs=1e-12)
    assert last["std_20d"] == pytest.approx(0.0, abs=1e-12)
    # value traded on the execution basis: 110 * 1000 = 100 * 1100 = 110,000 (adjusted would be
    # 100 * 1000 or 100 * 1100)
    assert last["value_traded_20d"] == pytest.approx(110_000.0)
    # shares restated to the post-event basis: 1000 * 1.1 = 1100 -> ratio 1
    assert last["vol_vs_avg20"] == pytest.approx(1.0)
    # 52-week high / low in the execution basis, restated: pre-event highs 111 / 1.1 = 100.909,
    # post-event high 101; lows 109 / 1.1 = 99.09, post-event low 99; close 100
    assert last["dist_52w_high"] == pytest.approx(100.0 / 101.0 - 1)
    assert last["dist_52w_low"] == pytest.approx(100.0 / 99.0 - 1)
    # on the event row itself the prior-basis window shows no phantom drawdown from 110
    assert row(out, "S", EVENT_AT)["dist_52w_high"] > -0.02


def test_atr_14_equals_the_risk_atr_with_the_same_ex_date_factors() -> None:
    adjusted, executed, actions, factors = synthetic_event_case()
    out = compute_features(adjusted, executed, ["S"], actions=actions)
    expected = atr(executed["high"], executed["low"], executed["close"], 14, factors)
    got = out["atr_14"].to_numpy()
    assert got == pytest.approx(expected.to_numpy(), nan_ok=True)
    assert np.isnan(got[:13]).all()
    # the factors matter: without the actions the ex-date drop would count as volatility
    plain = compute_features(adjusted, executed, ["S"])
    assert row(plain, "S", EVENT_AT)["atr_14"] > row(out, "S", EVENT_AT)["atr_14"]


def test_actions_after_the_last_row_and_cash_actions_are_ignored() -> None:
    adjusted, executed = synthetic_frames(
        "S", [100.0 + i for i in range(40)], highs=[101.0 + i for i in range(40)]
    )
    days = make_days(60)
    actions = pd.DataFrame(
        {
            "ticker": ["S", "S"],
            "ex_date": [days[50], days[5]],
            "type": ["stock", "cash"],
            "ratio_or_amount": [0.2, 100.0],
        }
    )
    pd.testing.assert_frame_equal(
        compute_features(adjusted, executed, ["S"], actions=actions),
        compute_features(adjusted, executed, ["S"]),
    )


# ------------------------------------------------------------------ AC7 market context
def test_market_context_is_the_equal_weight_universe_index() -> None:
    n = 260
    up = [100.0 * 1.03**i for i in range(n)]
    flat_a = [100.0] * n
    flat_b = [50.0] * n
    adjusted, executed = stack(
        synthetic_frames("X", up), synthetic_frames("Y", flat_a), synthetic_frames("Z", flat_b)
    )
    out = compute_features(adjusted, executed, ["X", "Y", "Z"])
    # mean daily return = 0.03 / 3 = 0.01; the index is 1.01 ** i from row 1 on (row 0 = 1.0)
    last = row(out, "X", n - 1)
    assert last["group_ret_12m"] == pytest.approx(1.01**250 - 1)  # index[259] / index[9]
    window = [1.01**i for i in range(n - 50, n)]
    assert last["group_ew_vs_ma50"] == pytest.approx(1.01 ** (n - 1) / (sum(window) / 50) - 1)
    # all three tickers see the same market columns on a date
    for column in ("group_ew_vs_ma50", "group_ret_12m", "group_breadth_ma50"):
        assert row(out, "Y", n - 1)[column] == pytest.approx(last[column])
    # breadth: only X is above its MA50 (flat closes are not above) -> 1 / 3
    assert last["group_breadth_ma50"] == pytest.approx(1 / 3)


def test_no_column_name_says_vn30() -> None:
    assert not [c for c in FEATURE_COLUMNS if "vn30" in c.lower()]
    assert not [g for g in FEATURE_GROUPS if "vn30" in g.lower()]
    assert len(set(FEATURE_COLUMNS)) == len(FEATURE_COLUMNS)


def test_deferred_groups_have_no_columns() -> None:
    for name in ("pb", "ep", "roe", "npl", "coverage"):
        assert not [c for c in FEATURE_COLUMNS if name in c.lower().split("_")]


# ------------------------------------------------------------------ AC3 version
def test_feature_version_is_stable_and_follows_adj_version() -> None:
    adjusted, executed = stack(synthetic_frames("A", L_CLOSE), synthetic_frames("B", M_CLOSE))
    first = compute_features(adjusted, executed, ["A", "B"])
    again = compute_features(adjusted, executed, ["A", "B"])
    pd.testing.assert_frame_equal(first, again)  # reproducible
    assert first["feature_version"].nunique() == 1
    assert first["feature_version"].iloc[0] == feature_version(adjusted, ["A", "B"])
    changed = adjusted.copy()
    changed.loc[changed["ticker"] == "B", "adj_version"] = "ratio-v2:other"
    second = compute_features(changed, executed, ["A", "B"])
    # one value for the whole build, different for every row (cross-sectional features)
    assert second["feature_version"].nunique() == 1
    assert second["feature_version"].iloc[0] != first["feature_version"].iloc[0]
    assert first["feature_version"].iloc[0].startswith("features-v4:")


def test_recomputing_a_past_date_gives_identical_values(synthetic_hand: pd.DataFrame) -> None:
    adjusted, executed = stack(
        synthetic_frames("L", L_CLOSE, L_VOLUME),
        synthetic_frames("M", M_CLOSE),
        synthetic_frames("N", N_CLOSE),
    )
    past = make_days(30)[22]
    only = compute_features(adjusted, executed, ["L", "M", "N"], asof_dates=[past])
    assert len(only) == 3
    expected = synthetic_hand[synthetic_hand["date"] == past].reset_index(drop=True)
    pd.testing.assert_frame_equal(only, expected)


def test_tickers_outside_the_universe_are_ignored() -> None:
    adjusted, executed = stack(synthetic_frames("A", L_CLOSE), synthetic_frames("B", M_CLOSE))
    out = compute_features(adjusted, executed, ["A"])
    assert set(out["ticker"]) == {"A"}


def test_empty_input_gives_an_empty_frame_with_all_columns() -> None:
    adjusted, executed = synthetic_frames("A", L_CLOSE)
    out = compute_features(adjusted.iloc[0:0], executed.iloc[0:0], ["A"])
    assert out.empty
    assert list(out.columns)[2:-1] == list(FEATURE_COLUMNS)


def test_missing_columns_raise() -> None:
    adjusted, executed = synthetic_frames("A", L_CLOSE)
    with pytest.raises(FeatureError, match="adj_close"):
        compute_features(adjusted.drop(columns="adj_close"), executed, ["A"])


# ------------------------------------------------------------------ AC2 no lookahead
def synthetic_world(
    seed: int, known_until: int | None, n: int = 300
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Random 3-ticker world of ``n`` sessions with gaps, flagged rows and stock events.

    ``known_until`` truncates it to rows ``<= known_until`` AS KNOWN THEN: events after the cut are
    unknown, so earlier adjusted prices are not divided by their future factors (backward
    adjustment), while the full world divides them."""
    rng = np.random.default_rng(seed)
    days = make_days(n)
    cut = n - 1 if known_until is None else known_until
    adj_parts, exec_parts, action_rows = [], [], []
    for ticker in ("A", "B", "C"):
        base = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n)))  # final-basis prices
        vol = rng.integers(500, 5000, n).astype(float)
        events = sorted(int(e) for e in rng.integers(30, n, size=int(rng.integers(0, 3))))
        events = sorted(set(events))
        ratios = {e: float(rng.choice([0.1, 0.2, 0.5])) for e in events}
        later = np.ones(n)  # product of factors of ALL events after each row
        known = np.ones(n)  # same, over events known at the cut
        for e, r in ratios.items():
            later[:e] *= 1 + r
            if e <= cut:
                known[:e] *= 1 + r
        raw = base * later
        shares = vol / later
        spread = rng.uniform(0.0, 0.02, n)
        keep = rng.random(n) > 0.15  # missing sessions
        flag = rng.random(n) > 0.05  # signal_ok
        rows = np.flatnonzero(keep & (np.arange(n) <= cut))
        for i in rows:
            adj_parts.append(
                (
                    ticker,
                    days[i],
                    base[i] * later[i] / known[i] * (1 + spread[i]),
                    base[i] * later[i] / known[i],
                    bool(flag[i]),
                )
            )
            exec_parts.append(
                (
                    ticker,
                    days[i],
                    raw[i] * (1 + spread[i]),
                    raw[i] * (1 - spread[i]),
                    raw[i],
                    shares[i],
                )
            )
        action_rows += [(ticker, days[e], "stock", r) for e, r in ratios.items() if e <= cut]
    adjusted = pd.DataFrame(
        adj_parts, columns=["ticker", "date", "adj_high", "adj_close", "signal_ok"]
    )
    adjusted["adj_version"] = VERSION
    executed = pd.DataFrame(
        exec_parts, columns=["ticker", "date", "high", "low", "close", "volume"]
    )
    actions = pd.DataFrame(action_rows, columns=["ticker", "ex_date", "type", "ratio_or_amount"])
    return adjusted, executed, actions


LOOKAHEAD_SESSIONS = 700


def test_no_lookahead_truncated_features_equal_full_history_features() -> None:
    universe = ["A", "B", "C"]
    n = LOOKAHEAD_SESSIONS
    days = make_days(n)
    seen: set[str] = set()  # columns that held a value at the cut in at least one seed
    for seed in range(24):
        cut = int(np.random.default_rng(1000 + seed).integers(400, n - 1))
        f_adj, f_exec, f_act = synthetic_world(seed, None, n)
        t_adj, t_exec, t_act = synthetic_world(seed, cut, n)
        full = compute_features(f_adj, f_exec, universe, actions=f_act)
        truncated = compute_features(t_adj, t_exec, universe, actions=t_act)
        got = truncated[truncated["date"] == days[cut]].reset_index(drop=True)
        want = full[full["date"] == days[cut]].reset_index(drop=True)
        assert len(got) == len(want)
        assert list(got["ticker"]) == list(want["ticker"])
        for column in FEATURE_COLUMNS:
            np.testing.assert_allclose(
                got[column].to_numpy(dtype=float),
                want[column].to_numpy(dtype=float),
                rtol=1e-9,
                atol=1e-12,
                equal_nan=True,
                err_msg=f"{column} (seed {seed}, cut {cut})",
            )
            if got[column].notna().any():
                seen.add(column)
    # the comparison is not vacuous: every column (250-session windows included) was filled
    assert seen == set(FEATURE_COLUMNS)


def test_the_property_world_exercises_long_windows_and_events() -> None:
    adjusted, executed, actions = synthetic_world(0, None)
    out = compute_features(adjusted, executed, ["A", "B", "C"], actions=actions)
    late = out[out["date"] == make_days(300)[299]]
    assert late[list(FEATURE_COLUMNS)].notna().to_numpy().mean() > 0.8
    assert (~adjusted["signal_ok"]).any()


def test_features_are_deterministic_across_input_order() -> None:
    adjusted, executed, actions = synthetic_world(3, None)
    first = compute_features(adjusted, executed, ["A", "B", "C"], actions=actions)
    shuffled = compute_features(
        adjusted.sample(frac=1.0, random_state=1),
        executed.sample(frac=1.0, random_state=2),
        ["C", "B", "A"],
        actions=actions,
    )
    pd.testing.assert_frame_equal(first, shuffled)


# ------------------------------------------------------------------ loader guards
def synthetic_feature_frame(version: str, days: Sequence[date]) -> pd.DataFrame:
    frame = pd.DataFrame({"ticker": "A", "date": list(days)})
    for column in FEATURE_COLUMNS:
        frame[column] = 1.0
    frame["feature_version"] = version
    return frame


def test_asof_view_drops_later_rows() -> None:
    days = make_days(5)
    frame = synthetic_feature_frame("v", days)
    assert list(asof_view(frame, days[2])["date"]) == days[:3]
    assert len(asof_view(frame, days[0] - pd.Timedelta(days=1))) == 0


def test_load_features_clamps_to_asof_and_refuses_mixed_versions(tmp_path: Path) -> None:
    days = make_days(5)
    with MarketStore(tmp_path / "m.duckdb", "synthetic") as store:
        with pytest.raises(SourceError, match="features build"):
            load_features(store, days[0], days[-1])
        store.replace_features(synthetic_feature_frame("v1", days))
        got = load_features(store, days[0], days[-1], ["rsi_14"], asof=days[2])
        assert list(got.columns) == ["ticker", "date", "rsi_14", "feature_version"]
        assert list(got["date"]) == days[:3]  # rows after asof cannot be received
        assert len(load_features(store, days[0], days[-1])) == 5
        mixed = pd.concat(
            [synthetic_feature_frame("v1", days[:2]), synthetic_feature_frame("v2", days[2:])]
        )
        store.replace_features(mixed)
        with pytest.raises(FeatureError, match="mixed feature versions"):
            load_features(store, days[0], days[-1])
        assert len(load_features(store, days[0], days[1])) == 2  # a single-version slice is fine
