"""Order model and the ``order_events`` log (engine.md section 6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from vnstratlab.engine.rules import Side

EventKind = Literal[
    "blocked_ceiling",
    "blocked_floor",
    "blocked_cash",
    "carried",
    "queued_until_sellable",
    "stale_order",
    "cancelled",
]
EVENT_COLUMNS = ("order_id", "ticker", "side", "session", "event", "reason", "qty")


@dataclass
class Order:
    """A pending order. ``carried`` counts sessions it was carried after being blocked."""

    order_id: int
    ticker: str
    side: Side
    qty: float
    created: date
    carried: int = 0


class EventLog:
    def __init__(self) -> None:
        self._rows: list[tuple[int, str, str, date, str, str, float]] = []

    def add(self, order: Order, session: date, event: EventKind, reason: str) -> None:
        row = (order.order_id, order.ticker, order.side, session, event, reason, order.qty)
        self._rows.append(row)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self._rows, columns=list(EVENT_COLUMNS))
