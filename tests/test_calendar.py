from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from vnstratlab.calendar import TradingCalendar, decision_days, holiday_coverage
from vnstratlab.config.loader import load_config

D = date


@pytest.fixture
def synthetic_calendar() -> TradingCalendar:
    # 2030-01-01 is a Tuesday. Holidays: Fri 2030-01-04 + Mon 2030-01-07 (spans a weekend),
    # Fri 2030-03-29 and Fri 2030-05-31 (month ends), Mon 2030-04-15.
    return TradingCalendar(
        [D(2030, 1, 4), D(2030, 1, 7), D(2030, 3, 29), D(2030, 4, 15), D(2030, 5, 31)]
    )


def test_weekend_and_holiday_are_not_trading_days(synthetic_calendar: TradingCalendar) -> None:
    cal = synthetic_calendar
    assert cal.is_trading_day(D(2030, 1, 3))
    assert not cal.is_trading_day(D(2030, 1, 4))  # holiday
    assert not cal.is_trading_day(D(2030, 1, 5))  # Saturday
    assert not cal.is_trading_day(D(2030, 1, 6))  # Sunday


def test_next_and_previous_skip_holiday_spanning_weekend(
    synthetic_calendar: TradingCalendar,
) -> None:
    cal = synthetic_calendar
    assert cal.next_trading_day(D(2030, 1, 3)) == D(2030, 1, 8)
    assert cal.previous_trading_day(D(2030, 1, 8)) == D(2030, 1, 3)
    assert cal.next_trading_day(D(2030, 1, 5)) == D(2030, 1, 8)  # from a non-session
    assert cal.previous_trading_day(D(2030, 1, 6)) == D(2030, 1, 3)


def test_n_steps(synthetic_calendar: TradingCalendar) -> None:
    cal = synthetic_calendar
    assert cal.next_trading_day(D(2030, 1, 3), n=3) == D(2030, 1, 10)
    assert cal.previous_trading_day(D(2030, 1, 10), n=3) == D(2030, 1, 3)
    with pytest.raises(ValueError, match="n must be"):
        cal.next_trading_day(D(2030, 1, 3), n=0)
    with pytest.raises(ValueError, match="n must be"):
        cal.previous_trading_day(D(2030, 1, 3), n=0)


def test_trading_days_inclusive_and_sessions_between(
    synthetic_calendar: TradingCalendar,
) -> None:
    cal = synthetic_calendar
    days = cal.trading_days(D(2030, 1, 3), D(2030, 1, 9))
    assert days == [D(2030, 1, 3), D(2030, 1, 8), D(2030, 1, 9)]
    assert cal.trading_days(D(2030, 1, 9), D(2030, 1, 3)) == []
    # sessions in (a, b]
    assert cal.sessions_between(D(2030, 1, 3), D(2030, 1, 9)) == 2
    assert cal.sessions_between(D(2030, 1, 3), D(2030, 1, 3)) == 0
    assert cal.sessions_between(D(2030, 1, 9), D(2030, 1, 3)) == 0


def test_from_sessions_uses_observed_dates() -> None:
    cal = TradingCalendar.from_sessions([D(2030, 1, 3), D(2030, 1, 8), D(2030, 1, 9)])
    assert cal.is_trading_day(D(2030, 1, 8))
    assert not cal.is_trading_day(D(2030, 1, 4))
    assert cal.next_trading_day(D(2030, 1, 3)) == D(2030, 1, 8)
    assert cal.previous_trading_day(D(2030, 1, 9), n=2) == D(2030, 1, 3)
    assert cal.trading_days(D(2030, 1, 1), D(2030, 1, 31)) == [
        D(2030, 1, 3),
        D(2030, 1, 8),
        D(2030, 1, 9),
    ]
    assert cal.sessions_between(D(2030, 1, 3), D(2030, 1, 9)) == 2
    with pytest.raises(ValueError, match="beyond"):
        cal.next_trading_day(D(2030, 1, 9))
    with pytest.raises(ValueError, match="before"):
        cal.previous_trading_day(D(2030, 1, 3))


def test_from_sessions_empty_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        TradingCalendar.from_sessions([])


def test_decision_days_short_thursday_when_friday_holiday(
    synthetic_calendar: TradingCalendar,
) -> None:
    days = decision_days(synthetic_calendar, "short", D(2030, 1, 1), D(2030, 1, 20))
    assert days == [D(2030, 1, 3), D(2030, 1, 11), D(2030, 1, 18)]
    assert D(2030, 1, 3).weekday() == 3


def test_decision_days_window_does_not_peek_past_end(
    synthetic_calendar: TradingCalendar,
) -> None:
    # Window ends Wednesday: the week's decision day (Friday) is outside, so not returned.
    assert decision_days(synthetic_calendar, "short", D(2030, 1, 14), D(2030, 1, 16)) == []
    # Window starts after the week's decision day: not returned either.
    assert decision_days(synthetic_calendar, "short", D(2030, 1, 12), D(2030, 1, 14)) == []


def test_decision_days_medium_last_session_of_month(
    synthetic_calendar: TradingCalendar,
) -> None:
    days = decision_days(synthetic_calendar, "medium", D(2030, 1, 1), D(2030, 6, 30))
    # Mar 31 is Sunday and Mar 29 a holiday -> Mar 28; May 31 holiday -> May 30;
    # Jun 30 is Sunday -> Jun 28.
    assert days == [
        D(2030, 1, 31),
        D(2030, 2, 28),
        D(2030, 3, 28),
        D(2030, 4, 30),
        D(2030, 5, 30),
        D(2030, 6, 28),
    ]


def test_decision_days_unknown_horizon() -> None:
    with pytest.raises(ValueError, match="horizon"):
        decision_days(TradingCalendar([]), "weekly", D(2030, 1, 1), D(2030, 2, 1))


def test_decision_days_end_before_start_is_empty() -> None:
    assert decision_days(TradingCalendar([]), "short", D(2030, 2, 1), D(2030, 1, 1)) == []


def test_packaged_2026_holidays(tmp_path: Path) -> None:
    cal = TradingCalendar.from_config(load_config(tmp_path))
    assert not cal.is_trading_day(D(2026, 2, 18))
    assert cal.next_trading_day(D(2026, 2, 13)) == D(2026, 2, 23)
    assert not cal.is_trading_day(D(2026, 8, 22))  # Saturday make-up day not traded
    assert not cal.is_trading_day(D(2026, 8, 31))
    assert cal.is_trading_day(D(2026, 8, 21))


def test_holiday_coverage(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert holiday_coverage(cfg, 2026) == "complete"
    assert holiday_coverage(cfg, 2027) == "partial"
    assert holiday_coverage(cfg, 2099) == "missing"


# ---------------------------------------------------------------- G2 review fixes


def test_from_sessions_truncated_periods_yield_nothing() -> None:
    base = TradingCalendar([])
    s = TradingCalendar.from_sessions(base.trading_days(D(2026, 11, 2), D(2026, 11, 17)))
    assert decision_days(s, "short", D(2026, 11, 16), D(2026, 11, 17)) == []
    assert decision_days(s, "medium", D(2026, 11, 1), D(2026, 11, 17)) == []
    # the complete weeks before the truncated one are still reported
    assert decision_days(s, "short", D(2026, 11, 2), D(2026, 11, 17)) == [
        D(2026, 11, 6),
        D(2026, 11, 13),
    ]


def test_from_sessions_complete_period_ending_on_friday_is_reported() -> None:
    base = TradingCalendar([])
    s = TradingCalendar.from_sessions(base.trading_days(D(2026, 11, 2), D(2026, 11, 13)))
    assert decision_days(s, "short", D(2026, 11, 9), D(2026, 11, 13)) == [D(2026, 11, 13)]
    m = TradingCalendar.from_sessions(base.trading_days(D(2026, 10, 1), D(2026, 11, 30)))
    assert decision_days(m, "medium", D(2026, 10, 1), D(2026, 11, 30)) == [
        D(2026, 10, 30),
        D(2026, 11, 30),
    ]


def test_long_horizon_is_monthly(synthetic_calendar: TradingCalendar) -> None:
    for horizon in ("medium", "long"):
        assert decision_days(
            synthetic_calendar,
            horizon,
            D(2030, 3, 1),
            D(2030, 5, 31),  # type: ignore[arg-type]
        ) == [D(2030, 3, 28), D(2030, 4, 30), D(2030, 5, 30)]


def test_from_sessions_truncated_month_yields_nothing_for_long() -> None:
    base = TradingCalendar([])
    s = TradingCalendar.from_sessions(base.trading_days(D(2026, 11, 2), D(2026, 11, 17)))
    assert decision_days(s, "long", D(2026, 11, 1), D(2026, 11, 17)) == []


# ---------------------------------------------------------------- G2 round 2


def test_packaged_2026_decision_days(tmp_path: Path) -> None:
    cal = TradingCalendar.from_config(load_config(tmp_path))
    assert decision_days(cal, "medium", D(2026, 4, 1), D(2026, 4, 30)) == [D(2026, 4, 29)]
    assert decision_days(cal, "medium", D(2026, 8, 1), D(2026, 8, 31)) == [D(2026, 8, 28)]
    # Tet week (Feb 16-20) is entirely closed: no decision day for that week
    assert decision_days(cal, "short", D(2026, 2, 9), D(2026, 2, 27)) == [
        D(2026, 2, 13),
        D(2026, 2, 27),
    ]


def test_from_sessions_period_truncated_at_start_yields_nothing() -> None:
    base = TradingCalendar([])
    s = TradingCalendar.from_sessions(base.trading_days(D(2026, 11, 4), D(2026, 11, 27)))
    # week of Nov 2 starts before the data (data begins Wednesday)
    assert decision_days(s, "short", D(2026, 11, 1), D(2026, 11, 27)) == [
        D(2026, 11, 13),
        D(2026, 11, 20),
        D(2026, 11, 27),
    ]
    m = TradingCalendar.from_sessions(base.trading_days(D(2026, 11, 10), D(2026, 12, 31)))
    assert decision_days(m, "medium", D(2026, 11, 1), D(2026, 12, 31)) == [D(2026, 12, 31)]
    assert decision_days(m, "long", D(2026, 11, 1), D(2026, 12, 31)) == [D(2026, 12, 31)]
