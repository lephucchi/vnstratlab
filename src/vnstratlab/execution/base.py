"""Executor protocol (plan section 5.4): same interface for backtest and paper books."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class Executor(Protocol):
    """Only the fill source differs between executors. There is no broker executor (D12)."""

    def submit(self, orders: pd.DataFrame) -> pd.DataFrame:
        """Accept orders (``ticker, side, qty``); return them with an ``order_id`` column."""
        ...

    def fills(self, trade_date: str) -> pd.DataFrame:
        """Matched quantity and price for ``trade_date`` (ISO date)."""
        ...
