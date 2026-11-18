"""SimExecutor: the simulator core behind the ``Executor`` protocol."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.engine import SimParams, SimResult, Simulator, run_simulation
from vnstratlab.engine.loop import TRADE_COLUMNS
from vnstratlab.engine.rules import Side


def _side(value: Any) -> Side:
    if value not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {value!r}")
    return "buy" if value == "buy" else "sell"


class SimExecutor:
    """Simulated fills on supplied prices. Steppable (``submit`` / ``fills``) or whole-run."""

    def __init__(
        self,
        prices: pd.DataFrame,
        corporate_actions: pd.DataFrame | None,
        calendar: TradingCalendar,
        params: SimParams,
    ) -> None:
        self._args = (prices, corporate_actions, calendar, params)
        self._sim = Simulator(prices, corporate_actions, calendar, params)
        self._done = 0  # sessions already processed
        self._last: date | None = None

    def submit(self, orders: pd.DataFrame) -> pd.DataFrame:
        """Queue orders created at the last processed close; they fill at the next open."""
        created = self._last or self._sim.sessions[0]
        rows: list[dict[Any, Any]] = orders.to_dict("records")
        ids = [
            self._sim.queue(str(r["ticker"]), _side(r["side"]), float(r["qty"]), created).order_id
            for r in rows
        ]
        return orders.assign(order_id=ids)

    def fills(self, trade_date: str) -> pd.DataFrame:
        """Process sessions up to ``trade_date`` and return that session's trades."""
        target = date.fromisoformat(trade_date)
        trades: list[tuple[object, ...]] = []
        while self._done < len(self._sim.sessions) and self._sim.sessions[self._done] <= target:
            day = self._sim.sessions[self._done]
            trades = self._sim.open_session(day)
            self._sim.mark(day)
            self._sim.record(day)
            self._done += 1
            self._last = day
        frame = pd.DataFrame(trades, columns=list(TRADE_COLUMNS))
        return frame[frame["session"] == target].reset_index(drop=True)

    def result(self) -> SimResult:
        return self._sim.result()

    def run(self, targets: Mapping[date, pd.Series]) -> SimResult:
        """Whole run from target weights (fresh state; independent of submit/fills)."""
        prices, actions, calendar, params = self._args
        return run_simulation(prices, actions, targets, calendar, params)
