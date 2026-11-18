"""Property tests on the synthetic market (P1-T36): ideal equals executable with lots off."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from vnstratlab.calendar import TradingCalendar, decision_days
from vnstratlab.config.models import AppConfig
from vnstratlab.data.protocol import universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource
from vnstratlab.engine import make_params, run_simulation

START, END = date(2024, 1, 2), date(2024, 5, 31)
SEEDS = range(20260101, 20260101 + 22)  # >= 20 random synthetic seeds


def _market(cfg: AppConfig, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, AppConfig]:
    syn = cfg.data.synthetic.model_copy(update={"seed": seed, "start": START})
    cfg = cfg.model_copy(update={"data": cfg.data.model_copy(update={"synthetic": syn})})
    tickers = universe_tickers(cfg)[:4]
    source = SyntheticSource(cfg)
    prices = source.fetch_daily(tickers, START, END).assign(price_basis="synthetic")
    corporate = source.fetch_corporate_actions(tickers, START, END)
    return prices, corporate, cfg


def _targets(
    tickers: list[str], seed: int, calendar: TradingCalendar, sessions: set[date]
) -> dict[date, pd.Series]:
    """Random long-only targets on weekly decision days; invested share <= 0.4 so that cash is
    never binding (the proceeds offset then cannot change returns)."""
    rng = np.random.default_rng(seed)
    out: dict[date, pd.Series] = {}
    for day in decision_days(calendar, "short", START, END):
        raw = rng.random(len(tickers)) * (rng.random(len(tickers)) > 0.4)
        total = raw.sum()
        w = raw / total * rng.uniform(0.05, 0.4) if total > 0 else raw
        if day in sessions:
            out[day] = pd.Series(w, index=tickers)
    return out


def _inputs(
    engine_cfg: AppConfig, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, AppConfig, TradingCalendar, dict[date, pd.Series]]:
    prices, corporate, cfg = _market(engine_cfg, seed)
    tickers = sorted(prices["ticker"].unique())
    days = sorted(pd.to_datetime(prices["date"]).dt.date.unique())
    calendar = TradingCalendar.from_sessions(days)
    return prices, corporate, cfg, calendar, _targets(tickers, seed, calendar, set(days))


@pytest.mark.parametrize("seed", SEEDS)
def test_executable_without_lots_equals_ideal(engine_cfg: AppConfig, seed: int) -> None:
    prices, corporate, cfg, calendar, targets = _inputs(engine_cfg, seed)
    ideal = make_params(cfg, "ideal")
    # Executable with lots off and the ideal capital: only the proceeds offset (2 vs 0)
    # differs, and with cash slack it cannot change a return.
    executable = make_params(cfg, "executable", cfg.engine.ideal_capital_vnd, lots=False)
    assert executable.proceeds_offset == 2
    a = run_simulation(prices, corporate, targets, calendar, ideal).returns
    b = run_simulation(prices, corporate, targets, calendar, executable).returns
    assert len(a) > 50
    assert a.abs().sum() > 0  # the run actually traded
    assert np.abs(a.to_numpy() - b.to_numpy()).max() < 1e-10


def test_executable_with_lots_differs_from_ideal(engine_cfg: AppConfig) -> None:
    """Sanity: the equality above is not vacuous; with lots on and 11M capital returns differ."""
    prices, corporate, cfg, calendar, targets = _inputs(engine_cfg, SEEDS[0])
    ideal = run_simulation(prices, corporate, targets, calendar, make_params(cfg, "ideal"))
    real = run_simulation(
        prices, corporate, targets, calendar, make_params(cfg, "executable", 11_000_000)
    )
    assert np.abs(ideal.returns.to_numpy() - real.returns.to_numpy()).max() > 1e-6
