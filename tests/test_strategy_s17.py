"""S17 equal weight (P1-T14). Synthetic fixtures only."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from test_strategy_s00 import assert_ledger_consistent, run_smoke
from vnstratlab.config.models import AppConfig
from vnstratlab.strategies.base import LookaheadError, Strategy
from vnstratlab.strategies.builtin import s17_equal_weight
from vnstratlab.strategies.builtin.s17_equal_weight import S17EqualWeight
from vnstratlab.strategies.registry import get_strategy_class, load_strategies

ASOF = pd.Timestamp("2026-03-10")
DAY = date(2026, 3, 10)


def make() -> S17EqualWeight:
    return S17EqualWeight({}, ("short", "medium", "long"))


def frame(tickers: list[str], day: date = DAY, **extra: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"ticker": tickers, "date": [day] * len(tickers), "ret_60d": np.nan}
    ).assign(**extra)


def test_one_over_n_over_the_cross_section_on_asof() -> None:
    # 4 tickers on asof -> 1/4 each, sum 1; NaN features do not exclude anyone
    w = make().target_weights(frame(["DDD", "AAA", "CCC", "BBB"]), ASOF)
    assert w.to_dict() == {"AAA": 0.25, "BBB": 0.25, "CCC": 0.25, "DDD": 0.25}
    assert w.sum() == pytest.approx(1.0)
    assert (w >= 0).all()


def test_tickers_without_a_row_on_asof_are_left_out() -> None:
    old = frame(["OLD"], DAY - timedelta(days=7))
    both = pd.concat([old, frame(["AAA", "BBB", "CCC"])], ignore_index=True)
    w = make().target_weights(both, ASOF)
    assert w.to_dict() == {"AAA": pytest.approx(1 / 3), "BBB": 1 / 3, "CCC": 1 / 3}


def test_empty_cross_section_is_all_cash() -> None:
    assert make().target_weights(frame([]), ASOF).empty
    assert make().target_weights(frame(["AAA"], DAY - timedelta(days=3)), ASOF).empty


def test_future_rows_are_refused_and_order_does_not_matter() -> None:
    clean = frame(["AAA", "BBB"])
    late = pd.concat([clean, frame(["ZZZ"], DAY + timedelta(days=1))], ignore_index=True)
    with pytest.raises(LookaheadError):
        make().target_weights(late, ASOF)
    shuffled = frame(["BBB", "AAA"])
    first = make().target_weights(clean, ASOF)
    assert make().target_weights(shuffled, ASOF).equals(first)
    assert make().target_weights(clean, ASOF).equals(first)


def test_no_params_and_registration() -> None:
    with pytest.raises(ValueError, match="no params"):
        S17EqualWeight({"n": 1}, ("short",))
    assert get_strategy_class("S17_equal_weight") is S17EqualWeight
    assert isinstance(make(), Strategy)
    assert "DeMiguel" in (s17_equal_weight.__doc__ or "")


def test_packaged_config_loads_every_builtin_strategy(engine_cfg: AppConfig) -> None:
    loaded = load_strategies(engine_cfg)
    assert [(s.id, s.params, s.horizons) for s in loaded] == [
        ("S00_composite", {"weights": "equal", "top_n": 3}, ("short",)),
        ("S00_composite", {"weights": "trend_heavy", "top_n": 3}, ("short",)),
        ("S17_equal_weight", {}, ("short", "medium", "long")),
        ("S01_weekly_reversal", {"n": 2}, ("short",)),
        ("S01_weekly_reversal", {"n": 3}, ("short",)),
        ("S02_breakout_volume", {"lookback": 20, "vol_mult": 1.5, "max_n": 3}, ("short",)),
        (
            "S03_oversold_uptrend",
            {"rsi_len": 2, "rsi_max": 10, "ma_len": 50, "max_n": 3},
            ("short",),
        ),
        (
            "S03_oversold_uptrend",
            {"rsi_len": 14, "rsi_max": 30, "ma_len": 50, "max_n": 3},
            ("short",),
        ),
        ("S04_bank_pairs", {"form": 250, "k": 5, "entry_z": 2.0, "max_hold": 10}, ("short",)),
        ("S05_residual_reversion", {"window": 60, "entry_z": 1.5, "n": 2}, ("short",)),
    ]


def test_smoke_backtest_on_the_synthetic_market(engine_cfg: AppConfig) -> None:
    result, targets = run_smoke(make(), engine_cfg)
    invested = [t for t in targets.values() if not t.empty]
    assert invested
    assert all(t.sum() == pytest.approx(1.0) for t in invested)
    assert not result.trades.empty
    assert_ledger_consistent(result)
