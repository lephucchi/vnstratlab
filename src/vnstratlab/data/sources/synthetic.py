"""Deterministic synthetic HOSE market (ADR-006).

One ``numpy`` PCG64 generator seeded from config drives everything. The simulation always runs
forward from ``data.synthetic.start`` and draws a fixed set of random numbers per session, so a
given date's values never depend on the requested ``--from`` or ``--to``. Prices follow a
regime-switching market with a common bank factor plus idiosyncratic noise, stay on the HOSE
tick grid and inside the daily limits computed from the reference price.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.data.protocol import (
    FloatArray,
    SourceInfo,
    TickTable,
    universe_tickers,
)

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

SESSIONS_PER_YEAR = 252
MIN_PRICE = 2_000.0
MIN_EX_PRICE = 5_000.0
# Regimes: 0 calm bull, 1 normal, 2 stress. Daily drift, daily volatility, transition matrix.
_DRIFT = np.array([0.0006, 0.0002, -0.0010])
_VOL = np.array([0.009, 0.014, 0.025])
_TRANSITION = np.array([[0.985, 0.014, 0.001], [0.010, 0.980, 0.010], [0.002, 0.038, 0.960]])
_CASH_AMOUNTS = np.array([500.0, 1_000.0, 1_500.0, 2_000.0])
_STOCK_RATIOS = np.array([0.05, 0.10, 0.15])

_PRICE_COLUMNS = (
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ref_price",
    "ceiling",
    "floor",
)
_ACTION_COLUMNS = ("ticker", "ex_date", "type", "ratio_or_amount")


def ex_price(kind: str, prev_close: float, amount: float, ticks: TickTable) -> float:
    """Theoretical ex-date reference price, rounded down to the tick.

    Cash: previous close minus the dividend. Stock: previous close / (1 + ratio).
    """
    raw = prev_close - amount if kind == "cash" else prev_close / (1.0 + amount)
    return float(ticks.round_down(np.array([raw]))[0])


@dataclass
class _Simulation:
    prices: pd.DataFrame
    actions: pd.DataFrame
    suspended: frozenset[tuple[str, date]] = frozenset()


class SyntheticSource:
    """``DataSource`` producing a reproducible fake market; no network, no files."""

    def __init__(self, cfg: AppConfig) -> None:
        self.info = SourceInfo(
            name="synthetic",
            price_basis="synthetic",
            interim=False,
            terms_url=None,
            requires_extra=None,
        )
        self._cfg = cfg
        self._syn = cfg.data.synthetic
        self._ticks = TickTable.from_config(cfg)
        self._calendar = TradingCalendar.from_config(cfg)
        self._tickers = universe_tickers(cfg)
        self._cache: dict[date, _Simulation] = {}

    def symbols(self, universe: Sequence[str]) -> dict[str, str]:
        return {t: t for t in universe}

    def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
        prices = self._simulate(end).prices
        if prices.empty:
            return prices
        keep = prices["ticker"].isin(list(tickers)) & (prices["date"] >= start)
        return prices[keep].reset_index(drop=True)

    def fetch_corporate_actions(
        self, tickers: Sequence[str], start: date, end: date
    ) -> pd.DataFrame:
        actions = self._simulate(end).actions
        if actions.empty:
            return actions
        keep = actions["ticker"].isin(list(tickers)) & (actions["ex_date"] >= start)
        return actions[keep].reset_index(drop=True)

    def declared_suspensions(
        self, tickers: Sequence[str], start: date, end: date
    ) -> set[tuple[str, date]]:
        """``(ticker, session)`` pairs this source left without a bar on purpose.

        Optional hook of the ingest pipeline: the data-quality check downgrades a trailing gap
        made only of such sessions to a warning (docs/data-pipeline.md section 5a).
        """
        wanted = set(tickers)
        return {
            (t, d) for t, d in self._simulate(end).suspended if t in wanted and start <= d <= end
        }

    # ------------------------------------------------------------------ simulation

    def _simulate(self, end: date) -> _Simulation:
        if end not in self._cache:
            self._cache[end] = self._run(end)
        return self._cache[end]

    def _run(self, end: date) -> _Simulation:
        syn = self._syn
        ticks = self._ticks
        rng = np.random.Generator(np.random.PCG64(syn.seed))
        n = len(self._tickers)
        beta = rng.uniform(0.8, 1.2, n)
        base_volume = np.exp(rng.uniform(np.log(2e6), np.log(2e7), n))
        close = ticks.nearest(np.exp(rng.uniform(np.log(15_000), np.log(90_000), n)))
        event_prob = syn.corporate_actions_per_ticker_per_year / SESSIONS_PER_YEAR
        regime = 1
        price_chunks: list[pd.DataFrame] = []
        action_rows: list[tuple[str, date, str, float]] = []
        suspended: set[tuple[str, date]] = set()
        tickers = np.array(self._tickers, dtype=object)

        for day in self._calendar.trading_days(syn.start, end):
            draws = _Draws.take(rng, n)
            regime = int(np.searchsorted(np.cumsum(_TRANSITION[regime]), draws.regime))
            active = draws.suspension >= syn.suspension_probability
            suspended.update((self._tickers[i], day) for i in np.flatnonzero(~active))
            ref, events = self._reference(close, draws, event_prob, active)
            action_rows += [(self._tickers[i], day, kind, amount) for i, kind, amount in events]
            ceiling, floor = ticks.limits(ref)
            sigma = _VOL[regime]
            shock = _DRIFT[regime] + sigma * (beta * draws.factor + 0.8 * draws.idio)
            target = np.maximum(ref * np.exp(shock), MIN_PRICE)
            open_ = np.clip(ticks.nearest(ref * np.exp(0.3 * sigma * draws.gap)), floor, ceiling)
            close_ = np.clip(ticks.nearest(target), floor, ceiling)
            top = np.maximum(open_, close_)
            bottom = np.minimum(open_, close_)
            high = np.clip(ticks.nearest(top * (1 + 0.5 * sigma * draws.up)), floor, ceiling)
            low = np.clip(ticks.nearest(bottom * (1 - 0.5 * sigma * draws.down)), floor, ceiling)
            volume = np.maximum(base_volume * np.exp(0.4 * draws.volume), 100.0)
            price_chunks.append(
                pd.DataFrame(
                    {
                        "ticker": tickers[active],
                        "date": [day] * int(active.sum()),
                        "open": open_[active],
                        "high": np.maximum(high, top)[active],
                        "low": np.minimum(low, bottom)[active],
                        "close": close_[active],
                        "volume": (np.floor(volume / 100.0) * 100).astype(np.int64)[active],
                        "ref_price": ref[active],
                        "ceiling": ceiling[active],
                        "floor": floor[active],
                    }
                )
            )
            close = np.where(active, close_, close)
        return _Simulation(
            _finish_prices(price_chunks), _finish_actions(action_rows), frozenset(suspended)
        )

    def _reference(
        self,
        close: FloatArray,
        draws: _Draws,
        event_prob: float,
        active: npt.NDArray[np.bool_],
    ) -> tuple[FloatArray, list[tuple[int, str, float]]]:
        """Reference prices (ex-price on ex-dates) and the corporate actions of the session."""
        ref = close.copy()
        events: list[tuple[int, str, float]] = []
        for i in np.flatnonzero(active & (draws.action < event_prob)):
            kind = "stock" if draws.kind[i] >= 0.5 else "cash"
            pool = _STOCK_RATIOS if kind == "stock" else _CASH_AMOUNTS
            amount = float(pool[min(int(draws.size[i] * len(pool)), len(pool) - 1)])
            candidate = ex_price(kind, float(close[i]), amount, self._ticks)
            if candidate >= MIN_EX_PRICE:
                ref[i] = candidate
                events.append((int(i), kind, amount))
        return ref, events


@dataclass(frozen=True)
class _Draws:
    """The random numbers consumed per session, in a fixed order."""

    regime: float
    factor: float
    idio: FloatArray
    gap: FloatArray
    up: FloatArray
    down: FloatArray
    volume: FloatArray
    suspension: FloatArray
    action: FloatArray
    kind: FloatArray
    size: FloatArray

    @classmethod
    def take(cls, rng: np.random.Generator, n: int) -> _Draws:
        return cls(
            regime=float(rng.random()),
            factor=float(rng.standard_normal()),
            idio=rng.standard_normal(n),
            gap=rng.standard_normal(n),
            up=rng.random(n),
            down=rng.random(n),
            volume=rng.standard_normal(n),
            suspension=rng.random(n),
            action=rng.random(n),
            kind=rng.random(n),
            size=rng.random(n),
        )


def _finish_prices(chunks: list[pd.DataFrame]) -> pd.DataFrame:
    if not chunks:
        return _empty(_PRICE_COLUMNS)
    frame = pd.concat(chunks, ignore_index=True)
    frame["ticker"] = frame["ticker"].astype(str)
    frame["volume"] = frame["volume"].astype(np.int64)
    ordered = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    return ordered[list(_PRICE_COLUMNS)]


def _finish_actions(rows: list[tuple[str, date, str, float]]) -> pd.DataFrame:
    if not rows:
        return _empty(_ACTION_COLUMNS)
    frame = pd.DataFrame(rows, columns=list(_ACTION_COLUMNS))
    return frame.sort_values(["ticker", "ex_date"], kind="stable").reset_index(drop=True)


def _empty(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame({c: [] for c in columns})


def build(cfg: AppConfig) -> SyntheticSource:
    """Registry factory."""
    return SyntheticSource(cfg)
