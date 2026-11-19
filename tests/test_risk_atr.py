"""Wilder ATR14 on a hand-built frame (synthetic data only)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from vnstratlab.risk import atr


def synthetic_frame() -> pd.DataFrame:
    """20 rows. Rows 0-13: high 11, low 9, close 10 (TR = 2). Rows 14-19: high 15, low 13,
    close 14."""
    rows = [(11.0, 9.0, 10.0)] * 14 + [(15.0, 13.0, 14.0)] * 6
    return pd.DataFrame(rows, columns=["high", "low", "close"])


def test_atr14_matches_hand_computation() -> None:
    f = synthetic_frame()
    out = atr(f["high"], f["low"], f["close"])
    # Rows 0..12: fewer than 14 true ranges -> NaN.
    assert out.iloc[:13].isna().all()
    # Row 0: TR = 11 - 9 = 2; rows 1..13: max(2, |11-10|, |9-10|) = 2 -> ATR13 = 28 / 14 = 2.
    assert out.iloc[13] == pytest.approx(2.0)
    # Row 14: TR = max(15-13 = 2, |15-10| = 5, |13-10| = 3) = 5
    #   ATR14 = (2 * 13 + 5) / 14 = 31 / 14 = 2.2142857
    assert out.iloc[14] == pytest.approx(31 / 14)
    # Row 15: TR = max(2, |15-14| = 1, |13-14| = 1) = 2
    #   ATR15 = (31/14 * 13 + 2) / 14 = 431 / 196 = 2.1989796
    assert out.iloc[15] == pytest.approx(431 / 196)
    # Rows 16..19: TR = 2, so ATR_k - 2 = (3/14) * (13/14)^(k-14); k = 19:
    #   2 + 3/14 * (13/14)^5 = 2.1479346
    assert out.iloc[19] == pytest.approx(2 + 3 / 14 * (13 / 14) ** 5)


def test_atr_has_no_lookahead() -> None:
    f = synthetic_frame()
    full = atr(f["high"], f["low"], f["close"])
    for cut in (14, 15, 17):  # keep rows 0..cut
        part = f.iloc[: cut + 1]
        head = atr(part["high"], part["low"], part["close"])
        assert head.iloc[-1] == pytest.approx(full.iloc[cut])
        assert head.iloc[13:].tolist() == pytest.approx(full.iloc[13 : cut + 1].tolist())


def test_atr_short_history_is_nan_and_validates() -> None:
    f = synthetic_frame().iloc[:5]
    assert atr(f["high"], f["low"], f["close"]).isna().all()
    assert math.isnan(atr(f["high"], f["low"], f["close"], n=6).iloc[-1])
    assert atr(f["high"], f["low"], f["close"], n=5).iloc[-1] == pytest.approx(2.0)
    with pytest.raises(ValueError, match="n must be"):
        atr(f["high"], f["low"], f["close"], n=0)
    with pytest.raises(ValueError, match="same length"):
        atr(f["high"], f["low"].iloc[:3], f["close"])


def test_atr_ex_date_factor_removes_the_mechanical_gap() -> None:
    # Rows 0-19: close 30,000, range +/- 300 (TR = 600). Rows 20-29: close 20,000 after a 50 %
    # bonus (factor 1.5 on row 20). Without the factor TR_20 = max(600, 9,700, 10,300) =
    # 10,300 and ATR20 = (600 x 13 + 10,300) / 14 = 1,292.9 (still far above 400 later).
    # With it: previous close 30,000 / 1.5 = 20,000, ATR19 = 600 / 1.5 = 400, TR_20 = 600 ->
    # ATR20 = (400 x 13 + 600) / 14 = 414.29; then TR = 600 each row, so 600 - ATR_k shrinks
    # by 13/14 per session.
    close = pd.Series([30_000.0] * 20 + [20_000.0] * 10)
    high, low = close + 300, close - 300
    raw = atr(high, low, close)
    assert raw.iloc[20] == pytest.approx((600 * 13 + 10_300) / 14)
    factors = [1.0] * 20 + [1.5] + [1.0] * 9
    fixed = atr(high, low, close, ex_factor=factors)
    assert fixed.iloc[19] == pytest.approx(600)
    assert fixed.iloc[20] == pytest.approx((400 * 13 + 600) / 14)
    assert fixed.iloc[29] == pytest.approx(600 - (600 - (400 * 13 + 600) / 14) * (13 / 14) ** 9)
    with pytest.raises(ValueError, match="ex_factor"):
        atr(high, low, close, ex_factor=[1.0])


def test_atr_with_ex_factor_stays_causal() -> None:
    # Truncating after the ex-date row leaves every value up to it unchanged.
    close = pd.Series([30_000.0] * 20 + [20_000.0] * 10)
    high, low = close + 300, close - 300
    factors = [1.0] * 20 + [1.5] + [1.0] * 9
    full = atr(high, low, close, ex_factor=factors)
    cut = atr(high.iloc[:22], low.iloc[:22], close.iloc[:22], ex_factor=factors[:22])
    assert list(cut.iloc[19:]) == pytest.approx(list(full.iloc[19:22]))
