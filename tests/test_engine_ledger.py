from __future__ import annotations

from datetime import date

import pytest

from vnstratlab.engine import EventLog, Ledger, Order

MON, TUE, WED, THU = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5)


def test_shares_become_sellable_on_their_date() -> None:
    led = Ledger(1_000)
    led.add_shares("AAA", 100, THU)
    led.add_shares("AAA", 50, WED)
    assert led.shares("AAA") == 150
    assert led.sellable("AAA", TUE) == 0
    assert led.sellable("AAA", WED) == 50
    assert led.sellable("AAA", THU) == 150
    assert led.next_sellable_date("AAA") == WED
    assert led.next_sellable_date("ZZZ") is None


def test_remove_sells_earliest_first_and_refuses_unsellable() -> None:
    led = Ledger(0)
    led.add_shares("AAA", 100, THU)
    led.add_shares("AAA", 50, WED)
    with pytest.raises(ValueError, match="sellable"):
        led.remove_shares("AAA", 60, WED)  # only 50 sellable on Wednesday
    led.remove_shares("AAA", 70, THU)  # 50 (Wed tranche) then 20 of the Thu tranche
    assert led.shares("AAA") == 80
    assert led.holdings() == {"AAA": 80}
    led.remove_shares("AAA", 80, THU)
    assert led.holdings() == {}


def test_cash_buckets_release_by_date() -> None:
    led = Ledger(1_000)
    led.credit_pending(WED, 200)
    led.credit_pending(THU, 300)
    assert (led.cash_available, led.cash_pending) == (1_000, 500)
    led.release_cash(TUE)
    assert (led.cash_available, led.cash_pending) == (1_000, 500)
    led.release_cash(WED)  # release date on or before today
    assert (led.cash_available, led.cash_pending) == (1_200, 300)
    led.release_cash(date(2026, 11, 9))
    assert (led.cash_available, led.cash_pending) == (1_500, 0)


def test_event_log_frame() -> None:
    log = EventLog()
    assert list(log.frame().columns) == [
        "order_id",
        "ticker",
        "side",
        "session",
        "event",
        "reason",
        "qty",
    ]
    log.add(Order(7, "AAA", "buy", 100, MON), TUE, "cancelled", "why")
    row = log.frame().iloc[0]
    assert (row["order_id"], row["ticker"], row["event"], row["reason"]) == (
        7,
        "AAA",
        "cancelled",
        "why",
    )
