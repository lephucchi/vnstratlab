"""Hand-built ``synthetic_*`` frames and drivers for the engine tests (no data, no network)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.engine import SimParams, Simulator
from vnstratlab.engine.rules import Side


def make_days(n: int, start: date = date(2026, 10, 30)) -> list[date]:
    """``n`` consecutive weekdays from ``start`` (Fri 2026-10-30, then Mon 2026-11-02, ...).

    No HOSE holiday falls in this stretch, so these are sessions of the default calendar.
    """
    days: list[date] = []
    day = start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def bars(
    ticker: str,
    days: list[date],
    open_: float,
    close: float | None = None,
    over: Mapping[int, Mapping[str, float]] | None = None,
    basis: str = "synthetic",
) -> list[dict[str, Any]]:
    """One row per day: constant prices; ceiling/floor = open +/- 7 % unless overridden.

    ``over`` maps a day index to column overrides (open, close, ceiling, floor).
    """
    rows = []
    for i, day in enumerate(days):
        row: dict[str, Any] = {
            "ticker": ticker,
            "date": day,
            "open": open_,
            "close": open_ if close is None else close,
            "ceiling": open_ * 1.07,
            "floor": open_ * 0.93,
            "price_basis": basis,
        }
        row.update((over or {}).get(i, {}))
        row["high"] = max(row["open"], row["close"])
        row["low"] = min(row["open"], row["close"])
        row["volume"] = 1_000_000
        row["ref_price"] = row["open"]
        rows.append(row)
    return rows


def frame(*parts: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([row for part in parts for row in part])


def actions(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def drive(
    prices: pd.DataFrame,
    params: SimParams,
    orders: Mapping[int, list[tuple[str, Side, float]]] | None = None,
    corporate: pd.DataFrame | None = None,
) -> Simulator:
    """Run all sessions; ``orders[i]`` are queued at the close of session ``i - 1`` so that
    they fill at the open of session ``i``."""
    sim = Simulator(prices, corporate, TradingCalendar(), params)
    for i, day in enumerate(sim.sessions):
        prev = sim.sessions[max(i - 1, 0)]
        for ticker, side, qty in (orders or {}).get(i, []):
            sim.queue(ticker, side, qty, prev)
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    return sim
