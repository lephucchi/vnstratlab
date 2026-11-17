"""Trading calendar and decision days.

Two clocks (docs/engine.md section 3): live code derives sessions from configured holidays
(``from_config``); history derives them from observed price dates (``from_sessions``).
Only dates are handled here: no sessions-of-the-day or timezone logic.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

from vnstratlab.config.models import Horizon

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

_ONE_DAY = timedelta(days=1)
_HORIZONS = ("short", "medium", "long")


class TradingCalendar:
    """Mon-Fri sessions minus holidays, or an explicit set of observed sessions."""

    def __init__(self, holidays: Iterable[date] = ()) -> None:
        self._holidays: frozenset[date] = frozenset(holidays)
        self._sessions: list[date] | None = None

    @classmethod
    def from_config(cls, cfg: AppConfig) -> TradingCalendar:
        """Calendar using every holiday listed in the config (all years)."""
        return cls(day.date for block in cfg.market.holidays.values() for day in block.days)

    @classmethod
    def from_sessions(cls, sessions: Iterable[date]) -> TradingCalendar:
        """Calendar from observed session dates (e.g. dates present in price data)."""
        ordered = sorted(set(sessions))
        if not ordered:
            raise ValueError("from_sessions needs at least one session date")
        cal = cls()
        cal._sessions = ordered
        return cal

    @property
    def observed_range(self) -> tuple[date, date] | None:
        """``(first, last)`` observed session for ``from_sessions`` calendars, else ``None``."""
        if self._sessions is None:
            return None
        return self._sessions[0], self._sessions[-1]

    def is_trading_day(self, d: date) -> bool:
        if self._sessions is not None:
            index = bisect_left(self._sessions, d)
            return index < len(self._sessions) and self._sessions[index] == d
        return d.weekday() < 5 and d not in self._holidays

    def next_trading_day(self, d: date, n: int = 1) -> date:
        """The ``n``-th session strictly after ``d`` (``d`` itself need not be a session)."""
        _check_n(n)
        if self._sessions is not None:
            index = bisect_right(self._sessions, d) + n - 1
            if index >= len(self._sessions):
                raise ValueError(f"no observed session {n} step(s) beyond {d}")
            return self._sessions[index]
        current = d
        for _ in range(n):
            current += _ONE_DAY
            while not self.is_trading_day(current):
                current += _ONE_DAY
        return current

    def previous_trading_day(self, d: date, n: int = 1) -> date:
        """The ``n``-th session strictly before ``d``."""
        _check_n(n)
        if self._sessions is not None:
            index = bisect_left(self._sessions, d) - n
            if index < 0:
                raise ValueError(f"no observed session {n} step(s) before {d}")
            return self._sessions[index]
        current = d
        for _ in range(n):
            current -= _ONE_DAY
            while not self.is_trading_day(current):
                current -= _ONE_DAY
        return current

    def trading_days(self, start: date, end: date) -> list[date]:
        """Sessions in ``[start, end]`` (inclusive); empty if ``end < start``."""
        if self._sessions is not None:
            return self._sessions[
                bisect_left(self._sessions, start) : bisect_right(self._sessions, end)
            ]
        days: list[date] = []
        current = start
        while current <= end:
            if self.is_trading_day(current):
                days.append(current)
            current += _ONE_DAY
        return days

    def sessions_between(self, a: date, b: date) -> int:
        """Number of sessions in the half-open range ``(a, b]`` (``a`` excluded, ``b`` included).

        This is how many sessions elapse going from ``a`` to ``b``; it equals ``n`` when
        ``next_trading_day(a, n) == b``. Returns 0 if ``b <= a``.
        """
        if b <= a:
            return 0
        return len(self.trading_days(a + _ONE_DAY, b))


def _check_n(n: int) -> None:
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")


def _last_session(cal: TradingCalendar, first: date, last: date) -> date | None:
    days = cal.trading_days(first, last)
    return days[-1] if days else None


def _weekday_bounds(first: date, last: date) -> tuple[date, date]:
    """First Mon-Fri on/after ``first`` and last Mon-Fri on/before ``last`` of a period."""
    while first.weekday() >= 5:
        first += _ONE_DAY
    while last.weekday() >= 5:
        last -= _ONE_DAY
    return first, last


def decision_days(
    calendar: TradingCalendar, horizon: Horizon, start: date, end: date
) -> list[date]:
    """Decision days in ``[start, end]`` for a horizon.

    - ``short``: last session of each ISO week;
    - ``medium`` and ``long``: last session of each calendar month.

    A period's decision day is computed from the whole period, then kept only if it lies in the
    window, so a window ending mid-week never reports a partial week's last day.

    On a ``from_sessions`` calendar a week or month is reported only if its first and last
    weekdays lie inside ``[first session, last session]``; a period cut off by the start or end
    of the data yields nothing.
    """
    if horizon not in _HORIZONS:
        raise ValueError(f"unknown horizon {horizon!r}; expected one of {_HORIZONS}")
    if end < start:
        return []
    observed = calendar.observed_range
    found: set[date] = set()

    def add_period(first: date, last: date) -> None:
        if observed is not None:
            weekday_first, weekday_last = _weekday_bounds(first, last)
            if weekday_first < observed[0] or weekday_last > observed[1]:
                return
        day = _last_session(calendar, first, last)
        if day is not None:
            found.add(day)

    if horizon == "short":
        monday = start - timedelta(days=start.weekday())
        while monday <= end:
            add_period(monday, monday + timedelta(days=6))
            monday += timedelta(days=7)
    else:
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            nxt = date(year + (month == 12), month % 12 + 1, 1)
            add_period(date(year, month, 1), nxt - _ONE_DAY)
            year, month = nxt.year, nxt.month
    return sorted(d for d in found if start <= d <= end)


def holiday_coverage(cfg: AppConfig, year: int) -> Literal["complete", "partial", "missing"]:
    """Holiday-data coverage for ``year``: ``missing`` when no days are listed at all."""
    block = cfg.market.holidays.get(year)
    if block is None or not block.days:
        return "missing"
    return block.coverage
