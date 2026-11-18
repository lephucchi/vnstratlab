"""HOSE rules as pure functions: ticks, limits, lots, settlement dates (engine.md section 5)."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

from vnstratlab.calendar import TradingCalendar

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

Side = Literal["buy", "sell"]
EPS = 1e-9


@dataclass(frozen=True)
class MarketRules:
    """Resolved HOSE rule values used by the engine."""

    tick_bands: tuple[tuple[int, int], ...]
    round_lot: int
    odd_lot_max: int
    settle_offset: int
    proceeds_offset: int
    dividend_lag_days: int
    listing_lag_sessions: int

    @classmethod
    def from_config(cls, cfg: AppConfig) -> MarketRules:
        rules = cfg.market.rules
        return cls(
            tick_bands=tuple(rules.tick_sizes.value),
            round_lot=rules.round_lot.value,
            odd_lot_max=rules.odd_lot.value.max,
            settle_offset=rules.earliest_sell_session_offset.value,
            proceeds_offset=rules.cash_proceeds_offset.value,
            dividend_lag_days=rules.cash_dividend_pay_lag_days.value,
            listing_lag_sessions=rules.stock_dividend_listing_lag_sessions.value,
        )


def tick_size(price: float, bands: Sequence[tuple[int, int]]) -> int:
    """Tick (VND) for a price: the band whose lower bound is the largest one <= price."""
    index = bisect_right([b[0] for b in bands], price) - 1
    return bands[max(index, 0)][1]


def round_limit_price(price: float, side: Side, bands: Sequence[tuple[int, int]]) -> float:
    """Recommended limit price on the tick grid: buy rounds down, sell rounds up."""
    tick = tick_size(price, bands)
    steps = round(price / tick, 6)
    steps = math.floor(steps) if side == "buy" else math.ceil(steps)
    return float(steps * tick)


def buy_blocked_by_ceiling(open_price: float, ceiling: float) -> bool:
    return open_price >= ceiling


def sell_blocked_by_floor(open_price: float, floor: float) -> bool:
    return open_price <= floor


def split_lots(qty: float, round_lot: int, odd_lots: bool) -> tuple[int, int]:
    """Whole shares as ``(round_part, odd_part)``; the odd part is 0 when odd lots are off."""
    whole = math.floor(qty + EPS)
    round_part = whole // round_lot * round_lot
    return round_part, (whole - round_part) if odd_lots else 0


def target_quantity(value: float, price: float, rules: MarketRules, lots: bool, odd: bool) -> float:
    """Shares to hold for a target value: fractional when ``lots`` is off, else whole shares
    (round lots only when odd lots are off)."""
    if not lots:
        return value / price
    round_part, odd_part = split_lots(value / price, rules.round_lot, odd)
    return float(round_part + odd_part)


def after_sessions(calendar: TradingCalendar, day: date, n: int) -> date:
    """The ``n``-th session after ``day`` (``day`` itself for 0); ``date.max`` past the data."""
    if n == 0:
        return day
    try:
        return calendar.next_trading_day(day, n)
    except ValueError:
        return date.max


def price_limits(
    ref_price: float, limit_pct: float, bands: Sequence[tuple[int, int]]
) -> tuple[float, float]:
    """``(ceiling, floor)`` from a reference price: ceiling rounds down, floor rounds up."""
    ceiling = round_limit_price(round(ref_price * (1 + limit_pct), 6), "buy", bands)
    floor = round_limit_price(round(ref_price * (1 - limit_pct), 6), "sell", bands)
    return ceiling, floor
