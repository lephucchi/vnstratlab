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
