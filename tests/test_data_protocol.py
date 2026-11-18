from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.protocol import (
    SourceError,
    SourceInfo,
    TickTable,
    get_source,
    source_names,
    universe_tickers,
)


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    return load_config(tmp_path)


def _arr(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float64)


def test_data_section_defaults(cfg: AppConfig) -> None:
    assert cfg.data.source == "synthetic"
    syn = cfg.data.synthetic
    assert syn.seed == 20261118
    assert syn.start.isoformat() == "2015-01-01"
    assert syn.corporate_actions_per_ticker_per_year == 1.0
    assert syn.suspension_probability == 0.002


def test_source_info_is_frozen() -> None:
    info = SourceInfo("x", "raw", True, None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.name = "y"  # type: ignore[misc]


def test_registry_builds_synthetic_and_rejects_unknown(cfg: AppConfig) -> None:
    source = get_source("synthetic", cfg)
    assert source.info.name == "synthetic"
    assert source.info.price_basis == "synthetic"
    assert "synthetic" in source_names()
    with pytest.raises(SourceError, match="unknown source 'nope'"):
        get_source("nope", cfg)


def test_universe_tickers_include_known_exits(cfg: AppConfig) -> None:
    tickers = universe_tickers(cfg)
    assert "TPB" in tickers
    assert "VCB" in tickers
    assert tickers == sorted(set(tickers))


def test_tick_sizes_by_band(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    assert list(ticks.tick(_arr(5_000, 9_990, 10_000, 49_950, 50_000, 120_000))) == [
        10,
        10,
        50,
        50,
        100,
        100,
    ]


def test_limits_just_under_band_boundary(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    # 9,990 * 1.07 = 10,689.3 -> tick 50 -> down 10,650
    # 9,990 * 0.93 =  9,290.7 -> tick 10 -> up 9,300
    ceiling, floor = ticks.limits(_arr(9_990))
    assert ceiling[0] == 10_650
    assert floor[0] == 9_300
    # 9,400 * 1.07 = 10,058 -> 10,050 ; 9,400 * 0.93 = 8,742 -> 8,750
    ceiling, floor = ticks.limits(_arr(9_400))
    assert ceiling[0] == 10_050
    assert floor[0] == 8_750


def test_limits_exact_multiples_are_not_pushed_a_tick(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    ceiling, floor = ticks.limits(_arr(10_000))
    assert ceiling[0] == 10_700
    assert floor[0] == 9_300


def test_limits_around_the_50000_band_boundary(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    # 47,000 * 1.07 = 50,290 -> tick 100 above 50,000 -> 50,200 ; 47,000 * 0.93 = 43,710 -> 43,750
    ceiling, floor = ticks.limits(_arr(47_000))
    assert (ceiling[0], floor[0]) == (50_200, 43_750)
    # 53,700 * 1.07 = 57,459 -> 57,400 ; 53,700 * 0.93 = 49,941 -> tick 50 -> up 49,950
    ceiling, floor = ticks.limits(_arr(53_700))
    assert (ceiling[0], floor[0]) == (57_400, 49_950)


def test_is_on_grid(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    assert list(ticks.is_on_grid(_arr(9_990, 10_050, 10_025, 50_050))) == [True, True, False, False]
