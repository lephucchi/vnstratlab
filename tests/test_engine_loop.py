"""Session loop: settlement, limits, lots, costs, cash, corporate actions, ideal mode.

Every expectation is hand-computed in the comments (open 50,000 unless stated; fee 0.15 %,
sales tax 0.1 %, slippage 0.1 % round lot / 0.3 % odd lot; settlement offset 3; HOSE +/-7 %).
"""

from __future__ import annotations

import dataclasses
import random
from datetime import date

import pandas as pd
import pytest

from engine_helpers import (
    drive,
    make_days,
    synthetic_actions,
    synthetic_bars,
    synthetic_prices,
)
from vnstratlab.calendar import TradingCalendar
from vnstratlab.config.models import AppConfig
from vnstratlab.engine import (
    SimParams,
    SimResult,
    Simulator,
    make_params,
    period_returns,
    period_turnover,
    run_simulation,
)
from vnstratlab.execution.base import Executor
from vnstratlab.execution.sim import SimExecutor
from vnstratlab.risk import RiskLayer

CAL = TradingCalendar()
NONE = pd.Series(dtype=float)


def weights(**w: float) -> pd.Series:
    return pd.Series(w, dtype=float)


def executable(cfg: AppConfig, capital: float = 100_000_000, **kw: bool) -> SimParams:
    return make_params(cfg, "executable", capital, **kw)


def events(result_events: pd.DataFrame, order_id: int | None = None) -> list[tuple[date, str]]:
    rows = result_events
    if order_id is not None:
        rows = rows[rows["order_id"] == order_id]
    return [(r.session, r.event) for r in rows.itertuples()]


# ---------------------------------------------------------------- criterion 1, 6, 7


def test_settlement_queue_then_sell_costs(engine_cfg: AppConfig) -> None:
    days = make_days(8)  # idx0 Fri 10-30, idx1 Mon 11-02 ... idx4 Thu 11-05
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    # Fri close: target 50 % of 100,000,000 = 50,000,000 -> 1,000 shares (cash is ample).
    # Tue close (idx2): empty target -> sell order for Wed.
    targets = {days[0]: weights(AAA=0.5), days[2]: NONE}
    res = run_simulation(prices, None, targets, CAL, executable(engine_cfg))
    buy, sell = res.trades.iloc[0], res.trades.iloc[1]
    # Buy fills Monday open: price 50,000 x 1.001 = 50,050 ; notional 1,000 x 50,050 = 50,050,000
    # fee 0.15 % = 75,075 ; slippage 1,000 x 50 = 50,000.
    assert (buy["session"], buy["side"], buy["qty"]) == (date(2026, 11, 2), "buy", 1_000)
    assert buy["price"] == pytest.approx(50_050)
    assert buy["fee"] == pytest.approx(75_075)
    assert buy["tax"] == 0
    assert buy["slippage"] == pytest.approx(50_000)
    # Buy Monday + 3 sessions = Thursday. Wednesday: queued; Thursday open: sells.
    assert events(res.order_events) == [(date(2026, 11, 4), "queued_until_sellable")]
    assert "2026-11-05" in res.order_events.iloc[0]["reason"]
    assert (sell["session"], sell["side"]) == (date(2026, 11, 5), "sell")
    # Sell fill 50,000 x 0.999 = 49,950 (a loss vs 50,050): notional 49,950,000,
    # fee 74,925, sales tax 0.1 % = 49,950 (paid on a loss), slippage 50,000.
    assert sell["price"] == pytest.approx(49_950)
    assert sell["fee"] == pytest.approx(74_925)
    assert sell["tax"] == pytest.approx(49_950)
    assert sell["slippage"] == pytest.approx(50_000)
    # Equity Thursday: 100,000,000 - slippage 100,000 - fees 150,000 - tax 49,950 = 99,700,050
    # of which sale proceeds 49,825,125 are pending (offset 3).
    thu = res.equity[res.equity["date"] == date(2026, 11, 5)].iloc[0]
    assert thu["equity"] == pytest.approx(99_700_050)
    assert thu["cash_available"] == pytest.approx(49_874_925)  # 100,000,000 - 50,125,075
    assert thu["cash_pending"] == pytest.approx(49_825_125)  # 49,950,000 - 74,925 - 49,950
    assert thu["positions_value"] == 0
    # Turnover = sum |notional| of the session's fills / equity at the PREVIOUS close
    # (first session: initial capital); other sessions 0.
    # Monday: buy 50,050,000 / Friday close equity 100,000,000 (= capital) = 0.5005
    #   (the old same-session denominator 99,874,925 gave 0.50113...).
    # Thursday: sell 49,950,000 / Wednesday close equity (49,874,925 cash + 1,000 x 50,000)
    #   99,874,925 = 0.50012...  (the old denominator 99,700,050 gave 0.50100...).
    to = res.turnover
    assert to[date(2026, 11, 2)] == pytest.approx(0.5005)
    assert to[date(2026, 11, 5)] == pytest.approx(49_950_000 / 99_874_925)
    assert to.sum() == pytest.approx(to[date(2026, 11, 2)] + to[date(2026, 11, 5)])
    per = period_turnover(to, [date(2026, 11, 3), date(2026, 11, 6)])
    assert per.iloc[0] == pytest.approx(0.5005)  # up to Tuesday
    assert per.iloc[1] == pytest.approx(49_950_000 / 99_874_925)  # Wed..Fri


def test_turnover_first_session_uses_initial_capital(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    res = drive(prices, executable(engine_cfg), {0: [("AAA", "buy", 1_000)]}).result()
    # Buy fills on the first session: notional 1,000 x 50,050 = 50,050,000 over capital
    # 100,000,000 = 0.5005 (the session's own closing equity 99,874,925 would give 0.50113...).
    assert res.turnover[days[0]] == pytest.approx(0.5005)
    assert res.turnover[days[1]] == 0


# ---------------------------------------------------------------- criterion 2


def test_ceiling_open_blocks_buy_then_cancels(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    # ref 50,000 -> ceiling 53,500; Monday opens at the ceiling.
    over = {1: {"open": 53_500, "close": 53_500, "ref_price": 50_000, "ceiling": 53_500}}
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    res = run_simulation(prices, None, {days[0]: weights(AAA=0.5)}, CAL, executable(engine_cfg))
    assert res.trades.empty
    assert events(res.order_events) == [
        (date(2026, 11, 2), "blocked_ceiling"),
        (date(2026, 11, 2), "cancelled"),
    ]
    assert "unfilled_buy=cancel" in res.order_events.iloc[1]["reason"]
    assert res.equity["equity"].iloc[-1] == pytest.approx(100_000_000)


def test_buy_below_ceiling_is_not_blocked(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    over = {1: {"open": 53_400, "close": 53_400, "ceiling": 53_500}}  # one tick below
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    res = run_simulation(prices, None, {days[0]: weights(AAA=0.5)}, CAL, executable(engine_cfg))
    assert len(res.trades) >= 1
    assert res.order_events.empty


# ---------------------------------------------------------------- criterion 3


def test_floor_open_carries_sell_then_stale_after_five(engine_cfg: AppConfig) -> None:
    days = make_days(11)
    # Wed close (idx3): sell for Thu (idx4, first sellable session). Floor 46,500 on idx4..idx9.
    over = {
        i: {"open": 46_500, "close": 46_500, "ref_price": 50_000, "floor": 46_500}
        for i in range(4, 10)
    }
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    targets = {days[0]: weights(AAA=0.5), days[3]: NONE}
    res = run_simulation(prices, None, targets, CAL, executable(engine_cfg))
    ev = res.order_events
    assert list(ev["event"]) == ["blocked_floor", "carried"] * 5 + ["blocked_floor", "stale_order"]
    assert list(ev["session"][::2]) == days[4:10]  # Thu .. next Thu: 6 blocked sessions
    assert ev["reason"].iloc[1].endswith("carry 1/5")
    assert ev["reason"].iloc[9].endswith("carry 5/5")
    assert len(res.trades) == 1  # only the entry; the stale sell never filled
    assert res.positions.iloc[-1]["shares"] == 1_000


def test_unfilled_sell_cancel_and_buy_carry_policies(engine_cfg: AppConfig) -> None:
    days = make_days(6)
    over = {
        i: {"open": 46_500, "close": 46_500, "ref_price": 50_000, "floor": 46_500} for i in (4, 5)
    }
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    targets = {days[0]: weights(AAA=0.5), days[3]: NONE}
    params = dataclasses.replace(executable(engine_cfg), unfilled_sell="cancel")
    res = run_simulation(prices, None, targets, CAL, params)
    assert list(res.order_events["event"]) == ["blocked_floor", "cancelled"]
    # buy carry with a limit of 1 session: blocked, carried, blocked again, stale
    over_buy = {i: {"open": 53_500, "close": 53_500, "ceiling": 53_500} for i in (1, 2, 3)}
    prices_buy = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over_buy))
    carry = dataclasses.replace(executable(engine_cfg), unfilled_buy="carry", max_carry=1)
    res2 = run_simulation(prices_buy, None, {days[0]: weights(AAA=0.5)}, CAL, carry)
    assert list(res2.order_events["event"]) == [
        "blocked_ceiling",
        "carried",
        "blocked_ceiling",
        "stale_order",
    ]


# ---------------------------------------------------------------- criteria 4, 5


def test_lots_two_round_plus_odd_remainder(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    prices = synthetic_prices(synthetic_bars("AAA", days, 52_700))
    # Fri close: 11,000,000 / 52,700 = 208.7 -> 208 shares = 2 round lots + 8 odd (not 3 lots).
    res = run_simulation(
        prices, None, {days[0]: weights(AAA=1.0)}, CAL, executable(engine_cfg, 11_000_000)
    )
    round_t, odd_t = res.trades.iloc[0], res.trades.iloc[1]
    assert (round_t["lot_type"], round_t["qty"]) == ("round", 200)
    assert round_t["price"] == pytest.approx(52_752.7)  # 52,700 x 1.001
    assert (odd_t["lot_type"], odd_t["qty"]) == ("odd", 8)
    assert odd_t["price"] == pytest.approx(52_858.1)  # 52,700 x 1.003
    # cash: 11,000,000 - (200 x 52,752.7 x 1.0015 = 10,566,365.81)
    #                  - (8 x 52,858.1 x 1.0015 = 423,499.0972) = 10,135.0928
    mon = res.equity[res.equity["date"] == date(2026, 11, 2)].iloc[0]
    assert mon["cash_available"] == pytest.approx(10_135.0928, abs=1e-6)
    assert res.positions.iloc[0]["shares"] == 208


def test_lots_only_when_odd_lots_off(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    prices = synthetic_prices(synthetic_bars("AAA", days, 52_700))
    params = executable(engine_cfg, 11_000_000, odd_lots=False)
    res = run_simulation(prices, None, {days[0]: weights(AAA=1.0)}, CAL, params)
    assert list(res.trades["qty"]) == [200]
    mon = res.equity[res.equity["date"] == date(2026, 11, 2)].iloc[0]
    assert mon["cash_available"] == pytest.approx(433_634.19)  # 11,000,000 - 10,566,365.81


def test_odd_lot_150_shares_each_with_own_slippage(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    sim = drive(prices, executable(engine_cfg), {1: [("AAA", "buy", 150)]})
    t = sim.result().trades
    # 100 round at 50,000 x 1.001 = 50,050: notional 5,005,000, fee 7,507.5, slippage 5,000.
    # 50 odd at 50,000 x 1.003 = 50,150: notional 2,507,500, fee 3,761.25, slippage 7,500.
    assert list(t["lot_type"]) == ["round", "odd"]
    assert list(t["qty"]) == [100, 50]
    assert list(t["price"]) == pytest.approx([50_050, 50_150])
    assert list(t["fee"]) == pytest.approx([7_507.5, 3_761.25])
    assert list(t["slippage"]) == pytest.approx([5_000, 7_500])
    assert t["tax"].sum() == 0


def test_round_lot_sell_fills_with_odd_lots_off(engine_cfg: AppConfig) -> None:
    days = make_days(7)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    params = executable(engine_cfg, odd_lots=False)
    sim = drive(prices, params, {1: [("AAA", "buy", 300)], 4: [("AAA", "sell", 300)]})
    trades = sim.result().trades
    assert list(trades["side"]) == ["buy", "sell"]
    assert list(trades["qty"]) == [300, 300]


# ---------------------------------------------------------------- criterion 8


def _proceeds_setup(cfg: AppConfig, offset: int | None) -> pd.DataFrame:
    days = make_days(8)
    prices = synthetic_prices(
        synthetic_bars("AAA", days, 50_000), synthetic_bars("BBB", days, 90_000)
    )
    params = executable(cfg, 10_000_000, odd_lots=False)
    if offset is not None:
        params = dataclasses.replace(params, proceeds_offset=offset)
    orders = {
        1: [("AAA", "buy", 100)],
        4: [("AAA", "sell", 100), ("BBB", "buy", 100)],
        5: [("BBB", "buy", 100)],
        6: [("BBB", "buy", 100)],
        7: [("BBB", "buy", 100)],
    }
    sim = drive(prices, params, orders)
    res = sim.result()
    res.trades.attrs["events"] = res.order_events
    res.trades.attrs["equity"] = res.equity
    return res.trades


def test_sale_proceeds_fund_buys_only_after_the_offset(engine_cfg: AppConfig) -> None:
    trades = _proceeds_setup(engine_cfg, None)  # config offset = 3
    ev, eq = trades.attrs["events"], trades.attrs["equity"]
    # After Monday's AAA buy: 10,000,000 - (5,005,000 + 7,507.5) = 4,987,492.5.
    # Thursday AAA sell: 4,995,000 - 7,492.5 - 4,995 = 4,982,512.5 pending until Tuesday
    # (Thu + 3 sessions: Fri, Mon, Tue). BBB lot: 100 x 90,090 x 1.0015 = 9,022,513.5 > cash.
    # Thursday, Friday, Monday: blocked_cash then cancelled.
    # Tuesday: cash 4,987,492.5 + 4,982,512.5 = 9,970,005 >= 9,022,513.5 -> fills.
    blocked = [date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9)]
    assert events(ev) == [(d, e) for d in blocked for e in ("blocked_cash", "cancelled")]
    bbb = trades[trades["ticker"] == "BBB"]
    assert list(bbb["session"]) == [date(2026, 11, 10)]
    assert bbb.iloc[0]["fee"] == pytest.approx(13_513.5)  # 9,009,000 x 0.0015
    thu = eq[eq["date"] == date(2026, 11, 5)].iloc[0]
    assert thu["cash_available"] == pytest.approx(4_987_492.5)
    assert thu["cash_pending"] == pytest.approx(4_982_512.5)
    mon = eq[eq["date"] == date(2026, 11, 9)].iloc[0]
    assert mon["cash_pending"] == pytest.approx(4_982_512.5)  # still not released on Monday
    tue = eq[eq["date"] == date(2026, 11, 10)].iloc[0]
    assert tue["cash_pending"] == 0
    assert tue["cash_available"] == pytest.approx(9_970_005 - 9_022_513.5)


def test_monday_sell_proceeds_usable_from_thursday(engine_cfg: AppConfig) -> None:
    days = make_days(10)
    prices = synthetic_prices(
        synthetic_bars("AAA", days, 50_000), synthetic_bars("BBB", days, 90_000)
    )
    params = executable(engine_cfg, 10_000_000, odd_lots=False)
    orders = {
        1: [("AAA", "buy", 100)],  # Mon 11-02, sellable from Thu 11-05
        6: [("AAA", "sell", 100)],  # Mon 11-09: net 4,982,512.5, released Thu 11-12 (Mon + 3)
        7: [("BBB", "buy", 100)],  # Tue 11-10: cash 4,987,492.5 < 9,022,513.5 -> blocked_cash
        8: [("BBB", "buy", 100)],  # Wed 11-11: still blocked
        9: [("BBB", "buy", 100)],  # Thu 11-12: 4,987,492.5 + 4,982,512.5 = 9,970,005 -> fills
    }
    res = drive(prices, params, orders).result()
    blocked = [date(2026, 11, 10), date(2026, 11, 11)]
    assert events(res.order_events) == [
        (d, e) for d in blocked for e in ("blocked_cash", "cancelled")
    ]
    bbb = res.trades[res.trades["ticker"] == "BBB"]
    assert list(bbb["session"]) == [date(2026, 11, 12)]


def test_with_offset_zero_the_sell_funds_the_same_session_buy(engine_cfg: AppConfig) -> None:
    trades = _proceeds_setup(engine_cfg, 0)
    ev = trades.attrs["events"]
    # Thursday's BBB buy is funded by the sell (no event). It leaves 9,970,005 - 9,022,513.5 =
    # 947,491.5, so only the later duplicate buys (Fri, Mon, Tue) are blocked.
    blocked = [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]
    assert list(ev["session"]) == [d for d in blocked for _ in range(2)]
    thu = trades[trades["session"] == date(2026, 11, 5)]
    # Sells fill before buys: AAA sell first, then the BBB buy it funds (9,970,005 >= 9,022,513.5).
    assert list(thu["side"]) == ["sell", "buy"]


# ---------------------------------------------------------------- criteria 9, 10


def test_cash_dividend_receivable_then_available_on_pay_date(engine_cfg: AppConfig) -> None:
    days = make_days(30)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    div = synthetic_actions(
        {
            "ticker": "AAA",
            "ex_date": date(2026, 11, 4),
            "type": "cash",
            "ratio_or_amount": 1_000.0,
            "pay_date": date(2026, 11, 6),
        }
    )
    eq = drive(prices, executable(engine_cfg), {1: [("AAA", "buy", 1_000)]}, div).result().equity
    row = {r.date: r for r in eq.itertuples()}
    # 1,000 shares x 1,000 VND = 1,000,000 booked on ex-date 11-04, available from 11-06.
    # Cash after the buy: 100,000,000 - 50,125,075 = 49,874,925.
    assert row[date(2026, 11, 3)].cash_pending == 0
    assert row[date(2026, 11, 4)].cash_pending == pytest.approx(1_000_000)
    assert row[date(2026, 11, 5)].cash_pending == pytest.approx(1_000_000)
    assert row[date(2026, 11, 6)].cash_pending == 0
    assert row[date(2026, 11, 6)].cash_available == pytest.approx(50_874_925)


def test_cash_dividend_pay_lag_fallback_is_30_days(engine_cfg: AppConfig) -> None:
    days = make_days(30)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    div = synthetic_actions(
        {"ticker": "AAA", "ex_date": date(2026, 11, 4), "type": "cash", "ratio_or_amount": 1_000.0}
    )
    eq = drive(prices, executable(engine_cfg), {1: [("AAA", "buy", 1_000)]}, div).result().equity
    row = {r.date: r for r in eq.itertuples()}
    # ex-date 2026-11-04 + 30 days = 2026-12-04 (a Friday session).
    assert row[date(2026, 12, 3)].cash_pending == pytest.approx(1_000_000)
    assert row[date(2026, 12, 4)].cash_pending == 0


def _stock_dividend_run(cfg: AppConfig, listing: date | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = make_days(32)
    # Ex-date Monday 11-09 (idx6): ref 50,000 / 1.1 = 45,454.5 -> tick 50 down = 45,450.
    over = {
        i: {
            "open": 45_450,
            "close": 45_450,
            "ref_price": 45_450,
            "ceiling": 48_600,
            "floor": 42_300,
        }
        for i in range(6, 32)
    }
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    row: dict[str, object] = {
        "ticker": "AAA",
        "ex_date": date(2026, 11, 9),
        "type": "stock",
        "ratio_or_amount": 0.10,
    }
    if listing is not None:
        row["listing_date"] = listing
    res = drive(
        prices, executable(cfg), {1: [("AAA", "buy", 1_000)]}, synthetic_actions(row)
    ).result()
    return res.positions, res.equity


def test_stock_dividend_shares_and_sellable_from_listing_date(engine_cfg: AppConfig) -> None:
    pos, equity = _stock_dividend_run(engine_cfg, date(2026, 11, 13))
    row = {r.date: r for r in pos.itertuples()}
    before, ex = row[date(2026, 11, 6)], row[date(2026, 11, 9)]
    assert before.shares == 1_000
    assert ex.shares == 1_100  # 1,000 + floor(1,000 x 0.10)
    assert ex.sellable == 1_000  # the 100 new shares are not listed yet
    assert row[date(2026, 11, 12)].sellable == 1_000
    assert row[date(2026, 11, 13)].sellable == 1_100
    # Equity continuity: 1,000 x 50,000 = 50,000,000 before; 1,100 x 45,450 = 49,995,000 after;
    # the difference 5,000 is below one tick of the position (1,100 x 50 = 55,000).
    assert before.value == pytest.approx(50_000_000)
    assert ex.value == pytest.approx(49_995_000)
    assert abs(before.value - ex.value) < 1_100 * 50
    # The same on the equity frame: cash 49,874,925 is unchanged across the ex-date, so equity
    # goes from 99,874,925 to 99,869,925 (-5,000, i.e. -0.005 %).
    eq = {r.date: r.equity for r in equity.itertuples()}
    assert eq[date(2026, 11, 6)] == pytest.approx(99_874_925)
    assert eq[date(2026, 11, 9)] == pytest.approx(99_869_925)


def test_stock_dividend_listing_lag_fallback_is_20_sessions(engine_cfg: AppConfig) -> None:
    pos, _ = _stock_dividend_run(engine_cfg, None)
    row = {r.date: r for r in pos.itertuples()}
    # ex 11-09 + 20 sessions (11-10 is #1 ... 12-04 is #19) = Monday 12-07.
    assert row[date(2026, 12, 4)].sellable == 1_000
    assert row[date(2026, 12, 7)].sellable == 1_100


def test_pending_sell_is_rescaled_and_partly_queued_on_stock_dividend(
    engine_cfg: AppConfig,
) -> None:
    days = make_days(10)
    # ex-date limits from ref 45,450: ceiling 48,600, floor 42,300 (7 %, tick 50)
    over = {
        i: {
            "open": 45_450,
            "close": 45_450,
            "ref_price": 45_450,
            "ceiling": 48_600,
            "floor": 42_300,
        }
        for i in range(6, 10)
    }
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    row = {
        "ticker": "AAA",
        "ex_date": date(2026, 11, 9),
        "type": "stock",
        "ratio_or_amount": 0.10,
        "listing_date": date(2026, 11, 13),
    }
    orders = {1: [("AAA", "buy", 1_000)], 6: [("AAA", "sell", 1_000)]}
    res = drive(prices, executable(engine_cfg), orders, synthetic_actions(row)).result()
    # Sell order of 1,000 (pre-event shares) becomes 1,100 on the ex-date; only 1,000 are
    # sellable, so 1,000 sell and 100 stay queued until the new shares list.
    sells = res.trades[res.trades["side"] == "sell"]
    assert list(sells["qty"]) == [1_000]
    assert events(res.order_events)[0] == (date(2026, 11, 9), "queued_until_sellable")
    assert sells.iloc[0]["session"] == date(2026, 11, 9)


def test_rights_are_ignored_by_policy(engine_cfg: AppConfig) -> None:
    days = make_days(5)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    rights = synthetic_actions(
        {"ticker": "AAA", "ex_date": date(2026, 11, 4), "type": "rights", "ratio_or_amount": 0.2}
    )
    res = drive(prices, executable(engine_cfg), {1: [("AAA", "buy", 100)]}, rights).result()
    assert res.positions["shares"].iloc[-1] == 100


# ---------------------------------------------------------------- criterion 12 (ideal mode)


def test_ideal_mode_is_fractional_with_large_capital(engine_cfg: AppConfig) -> None:
    days = make_days(4)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    params = make_params(engine_cfg, "ideal")
    assert (params.capital, params.lots, params.proceeds_offset) == (1.0e12, False, 0)
    res = run_simulation(prices, None, {days[0]: weights(AAA=0.5)}, CAL, params)
    t = res.trades.iloc[0]
    # 0.5 x 1e12 / 50,000 = 1e7 shares (fractional lot type), fill 50,050, fee 0.15 % of
    # 1e7 x 50,050 = 750,750,000.
    assert t["lot_type"] == "fractional"
    assert t["qty"] == pytest.approx(1e7)
    assert t["fee"] == pytest.approx(750_750_000)


def test_make_params_requires_capital_for_executable(engine_cfg: AppConfig) -> None:
    with pytest.raises(ValueError, match="capital_vnd"):
        make_params(engine_cfg, "executable")


# ---------------------------------------------------------------- criteria 13, 14


def test_determinism_same_inputs_same_digest(engine_cfg: AppConfig) -> None:
    days = make_days(8)
    prices = synthetic_prices(
        synthetic_bars("AAA", days, 50_000), synthetic_bars("BBB", days, 90_000)
    )
    targets = {days[0]: weights(AAA=0.4, BBB=0.4), days[3]: weights(AAA=0.2)}
    a = run_simulation(prices, None, targets, CAL, executable(engine_cfg))
    b = run_simulation(prices.copy(), None, targets, CAL, executable(engine_cfg))
    assert a.digest() == b.digest()
    for name, fr in a.frames().items():
        assert fr.equals(b.frames()[name]), name
    other = run_simulation(prices, None, {days[0]: weights(AAA=0.5)}, CAL, executable(engine_cfg))
    assert other.digest() != a.digest()


def test_split_adjusted_prices_are_refused(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, basis="split_adjusted"))
    with pytest.raises(ValueError, match=r"split_adjusted.*P1-T06"):
        run_simulation(prices, None, {}, CAL, executable(engine_cfg))


def test_exec_reconstructed_prices_are_accepted(engine_cfg: AppConfig) -> None:
    days = make_days(3)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, basis="exec_reconstructed"))
    res = run_simulation(prices, None, {days[0]: weights(AAA=0.5)}, CAL, executable(engine_cfg))
    assert len(res.trades) >= 1


def test_every_unfilled_order_has_an_event_row(engine_cfg: AppConfig) -> None:
    days = make_days(12)
    over = {1: {"open": 53_500, "close": 53_500, "ref_price": 50_000, "ceiling": 53_500}}
    prices = synthetic_prices(
        synthetic_bars("AAA", days, 50_000, over=over), synthetic_bars("BBB", days, 40_000)
    )
    targets = {days[0]: weights(AAA=0.4, BBB=0.4), days[3]: weights(BBB=0.4)}
    res = run_simulation(prices, None, targets, CAL, executable(engine_cfg))
    ordered = {1, 2, 3}  # AAA buy, BBB buy, AAA sell
    assert ordered >= set(res.trades["order_id"]) | set(res.order_events["order_id"])
    unfilled = ordered - set(res.trades["order_id"])
    assert unfilled
    assert unfilled <= set(res.order_events["order_id"])


def test_new_decision_supersedes_a_queued_order(engine_cfg: AppConfig) -> None:
    days = make_days(7)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    # Tue close: sell for Wed -> queued (unsettled). Wed close: equity is 99,874,925 after fees,
    # so a 50 % target would be floor(49,937,462 / 50,000) = 998 shares, i.e. a 2-share SELL that
    # would keep the old order alive (same ticker and side). 60 % is 1,198 shares: a 198-share
    # BUY, so the queued sell is superseded.
    targets = {days[0]: weights(AAA=0.5), days[2]: NONE, days[3]: weights(AAA=0.6)}
    res = run_simulation(prices, None, targets, CAL, executable(engine_cfg))
    ev = res.order_events
    assert list(ev["event"]) == ["queued_until_sellable", "cancelled"]
    assert ev.iloc[1]["reason"] == "superseded by new decision"
    assert set(res.trades["side"]) == {"buy"}


def test_suspended_ticker_buy_is_cancelled(engine_cfg: AppConfig) -> None:
    days = make_days(7)
    full = synthetic_prices(
        synthetic_bars("AAA", days, 50_000), synthetic_bars("BBB", days, 40_000)
    )
    prices = full[~((full["ticker"] == "BBB") & (full["date"] == days[1]))]  # no BBB Monday
    res = run_simulation(prices, None, {days[0]: weights(BBB=0.2)}, CAL, executable(engine_cfg))
    assert events(res.order_events) == [(days[1], "cancelled")]
    assert "not tradable" in res.order_events.iloc[0]["reason"]
    assert res.trades.empty


def test_suspended_ticker_sell_is_carried_then_fills(engine_cfg: AppConfig) -> None:
    days = make_days(7)
    full = synthetic_prices(
        synthetic_bars("AAA", days, 50_000), synthetic_bars("BBB", days, 40_000)
    )
    prices = full[~((full["ticker"] == "BBB") & (full["date"] == days[4]))]  # no BBB Thursday
    orders = {1: [("BBB", "buy", 100)], 4: [("BBB", "sell", 100)]}
    res = drive(prices, executable(engine_cfg), orders).result()
    # Thursday is the first sellable session but BBB does not trade: carried; fills Friday.
    assert events(res.order_events) == [(days[4], "carried")]
    assert res.order_events.iloc[0]["reason"].endswith("carry 1/5")
    assert list(res.trades["session"]) == [days[1], days[5]]


# ---------------------------------------------------------------- input validation


def test_invalid_inputs_raise_clear_errors(engine_cfg: AppConfig) -> None:
    days = make_days(4)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    params = executable(engine_cfg)
    with pytest.raises(ValueError, match="missing columns: ceiling"):
        run_simulation(prices.drop(columns=["ceiling"]), None, {}, CAL, params)
    with pytest.raises(ValueError, match="unknown price_basis"):
        run_simulation(prices.assign(price_basis="adjusted"), None, {}, CAL, params)
    with pytest.raises(ValueError, match="not sessions"):
        run_simulation(prices, None, {date(2026, 12, 25): NONE}, CAL, params)
    with pytest.raises(ValueError, match="sum to"):
        run_simulation(prices, None, {days[0]: weights(AAA=0.8, BBB=0.4)}, CAL, params)
    with pytest.raises(ValueError, match="long-only"):
        run_simulation(prices, None, {days[0]: weights(AAA=-0.1)}, CAL, params)
    with pytest.raises(ValueError, match="no price for BBB"):
        run_simulation(prices, None, {days[0]: weights(BBB=0.1)}, CAL, params)
    saturday = prices.assign(date=date(2026, 11, 7))
    with pytest.raises(ValueError, match="not trading days"):
        run_simulation(saturday, None, {}, CAL, params)
    bad = synthetic_actions(
        {"ticker": "AAA", "ex_date": days[1], "type": "warrant", "ratio_or_amount": 1.0}
    )
    with pytest.raises(ValueError, match="unknown corporate action type"):
        run_simulation(prices, bad, {}, CAL, params)
    with pytest.raises(ValueError, match="missing columns"):
        run_simulation(prices, bad.drop(columns=["type"]), {}, CAL, params)


# ---------------------------------------------------------------- returns and executor


def test_returns_and_period_helper(engine_cfg: AppConfig) -> None:
    days = make_days(6)
    over = {2: {"close": 51_000}, 3: {"close": 52_020}}
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over))
    res = run_simulation(prices, None, {days[0]: weights(AAA=0.5)}, CAL, executable(engine_cfg))
    r = res.returns
    assert r.iloc[0] == 0  # nothing held before the first fill
    assert (1.0 + r).prod() - 1.0 == pytest.approx(res.equity["equity"].iloc[-1] / 1e8 - 1.0)
    per = period_returns(r, [days[2], days[5]])
    assert per.iloc[0] == pytest.approx((1 + r.iloc[1]) * (1 + r.iloc[2]) - 1)  # 11-02..11-03
    assert per.iloc[1] == pytest.approx(
        (1 + r.iloc[3]) * (1 + r.iloc[4]) * (1 + r.iloc[5]) - 1
    )  # (11-03, 11-06]
    assert list(per.index) == [days[2], days[5]]


def test_sim_executor_submit_and_fills(engine_cfg: AppConfig) -> None:
    days = make_days(6)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    ex: Executor = SimExecutor(prices, None, CAL, executable(engine_cfg))
    assert ex.fills("2026-10-30").empty
    out = ex.submit(pd.DataFrame({"ticker": ["AAA"], "side": ["buy"], "qty": [100]}))
    assert list(out["order_id"]) == [1]
    fills = ex.fills("2026-11-02")
    assert list(fills["qty"]) == [100]
    assert fills.iloc[0]["price"] == pytest.approx(50_050)
    assert list(ex.fills("2026-11-02")["qty"]) == [100]  # asking again returns the same fills
    assert ex.fills("2026-11-03").empty
    with pytest.raises(ValueError, match="side"):
        ex.submit(pd.DataFrame({"ticker": ["AAA"], "side": ["short"], "qty": [1]}))


def test_sim_executor_run_matches_run_simulation(engine_cfg: AppConfig) -> None:
    days = make_days(6)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    params = executable(engine_cfg)
    targets = {days[0]: weights(AAA=0.5)}
    ex = SimExecutor(prices, None, CAL, params)
    assert ex.run(targets).digest() == run_simulation(prices, None, targets, CAL, params).digest()
    assert ex.result().trades.empty  # the stepping state is independent of run()


def test_late_published_action_is_applied_once_on_first_visible_session(
    engine_cfg: AppConfig,
) -> None:
    days = make_days(10)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    sim = Simulator(prices, None, CAL, executable(engine_cfg))
    late = synthetic_actions(
        {
            "ticker": "AAA",
            "ex_date": days[3],  # Wed 11-04
            "type": "cash",
            "ratio_or_amount": 1_000.0,
            "pay_date": date(2026, 11, 20),
        }
    )
    for i, day in enumerate(sim.sessions):
        if i == 1:
            sim.queue("AAA", "buy", 1_000, days[0])
        if i == 5:  # first appears two sessions after its ex-date (Fri 11-06)
            sim.add_actions(late)
        if i == 6:
            sim.add_actions(late)  # published again: must not apply twice
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    eq = {r.date: r.cash_pending for r in sim.result().equity.itertuples()}
    assert eq[days[4]] == 0  # not visible yet
    # 1,000 shares x 1,000 VND = 1,000,000 booked once, on the first visible session.
    assert eq[days[5]] == pytest.approx(1_000_000)
    assert eq[days[6]] == pytest.approx(1_000_000)  # not 2,000,000
    assert eq[days[9]] == pytest.approx(1_000_000)


# ---------------------------------------------------------------- late actions (P1-T11b)


def _late_run(
    cfg: AppConfig,
    action: dict[str, object],
    buy_session: int,
    sell_session: int | None,
    apply_session: int,
    extra: list[tuple[int, str, float, int]] | None = None,
) -> Simulator:
    """Buy 1,000 AAA filled at ``buy_session``; optional sell filled at ``sell_session``;
    the action is published at the pre-open of ``apply_session``. ``extra`` orders are
    ``(queue_session, side, qty, created_idx)`` queued before that session opens."""
    days = make_days(12)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    sim = Simulator(prices, None, CAL, executable(cfg))
    for i, day in enumerate(sim.sessions):
        if i == buy_session:
            sim.queue("AAA", "buy", 1_000, days[max(i - 1, 0)])
        if i == sell_session:
            sim.queue("AAA", "sell", 1_000, days[i - 1])
        for at, side, qty, created in extra or []:
            if at == i:
                sim.queue("AAA", "buy" if side == "buy" else "sell", qty, days[created])
        if i == apply_session:
            sim.add_actions(synthetic_actions(action))
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    return sim


def _cash_action(ex: date) -> dict[str, object]:
    return {
        "ticker": "AAA",
        "ex_date": ex,
        "type": "cash",
        "ratio_or_amount": 1_000.0,
        "pay_date": date(2026, 11, 20),
    }


def test_late_cash_dividend_uses_ex_date_holdings_even_if_sold_since(
    engine_cfg: AppConfig,
) -> None:
    # days idx: 1 Mon 11-02, 3 Wed 11-04 (ex-date), 5 Fri 11-06, 7 Tue 11-10.
    # Buy fills 11-02 (1,000 held at the ex-date pre-open); the sell fills Fri 11-06, two
    # sessions after the ex-date; the action is published on 11-10, when nothing is held.
    # Receivable = 1,000 x 1,000 = 1,000,000 (not 0).
    sim = _late_run(engine_cfg, _cash_action(date(2026, 11, 4)), 1, 5, 7)
    eq = {r.date: r.cash_pending for r in sim.result().equity.itertuples()}
    assert sim.ledger.shares("AAA") == 0
    # Sale proceeds 49,825,125 (49,950,000 - fee 74,925 - tax 49,950) are pending until 11-11;
    # the dividend adds 1,000,000 on top on 11-10.
    assert eq[date(2026, 11, 6)] == pytest.approx(49_825_125)
    assert eq[date(2026, 11, 9)] == pytest.approx(49_825_125)
    assert eq[date(2026, 11, 10)] == pytest.approx(50_825_125)


def test_late_cash_dividend_ignores_shares_bought_after_ex_date(engine_cfg: AppConfig) -> None:
    # Ex-date Wed 11-04; the 1,000 shares are bought at Thu 11-05 (after it); the action is
    # published Mon 11-09. Held at ex-date pre-open: 0 -> no receivable.
    sim = _late_run(engine_cfg, _cash_action(date(2026, 11, 4)), 4, None, 6)
    assert sim.ledger.shares("AAA") == 1_000
    assert (sim.result().equity["cash_pending"] == 0).all()


def _stock_action(listing: date | None) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": "AAA",
        "ex_date": date(2026, 11, 4),
        "type": "stock",
        "ratio_or_amount": 0.10,
    }
    if listing is not None:
        row["listing_date"] = listing
    return row


@pytest.mark.parametrize(
    ("listing", "sellable_on_apply"),
    [
        # listing date already past when the action is applied: sellable from the apply session
        (date(2026, 11, 5), 1_100),
        # listing date after the apply session: the 100 new shares wait for it
        (date(2026, 11, 10), 1_000),
    ],
)
def test_late_stock_dividend_adds_shares_from_ex_date_holdings(
    engine_cfg: AppConfig, listing: date, sellable_on_apply: float
) -> None:
    # 1,000 AAA held at the Wed 11-04 ex-date pre-open; applied two sessions late on Fri 11-06:
    # +floor(1,000 x 0.10) = +100 shares, sellable from max(listing, 11-06).
    sim = _late_run(engine_cfg, _stock_action(listing), 1, None, 5)
    pos = {r.date: r for r in sim.result().positions.itertuples()}
    assert pos[date(2026, 11, 5)].shares == 1_000
    assert pos[date(2026, 11, 6)].shares == 1_100
    assert pos[date(2026, 11, 6)].sellable == sellable_on_apply
    assert pos[date(2026, 11, 10)].sellable == 1_100


def test_late_stock_dividend_still_adds_shares_after_position_was_sold(
    engine_cfg: AppConfig,
) -> None:
    # Held 1,000 at the 11-04 ex-date, sold on 11-05, action applied 11-09: +100 shares appear
    # anyway (entitlement is fixed at the ex-date); sellable from the apply session 11-09.
    sim = _late_run(engine_cfg, _stock_action(date(2026, 11, 5)), 1, 4, 6)
    assert sim.ledger.shares("AAA") == 100
    assert sim.ledger.sellable("AAA", date(2026, 11, 9)) == 100
    assert sim.ledger.sellable("AAA", date(2026, 11, 6)) == 0


def test_late_stock_dividend_rescales_only_orders_created_before_ex_date(
    engine_cfg: AppConfig,
) -> None:
    # Ex-date Wed 11-04 (idx 3); applied Fri 11-06 (idx 5). Two buys are pending at that moment:
    #  - 200 created Tue 11-03 (before the ex-date, sized pre-event): x 1.1 = 220
    #  - 500 created Thu 11-05 (after the ex-date, sized on post-event prices): stays 500
    extra = [(5, "buy", 200, 2), (5, "buy", 500, 4)]
    sim = _late_run(engine_cfg, _stock_action(date(2026, 11, 5)), 1, None, 5, extra)
    buys = sim.result().trades
    on_apply = buys[buys["session"] == date(2026, 11, 6)]
    # the 220 fill as a 200 round lot + a 20 odd lot
    assert list(on_apply.groupby("order_id")["qty"].sum()) == [220, 500]


@pytest.mark.parametrize("apply_session", [3, 5])
def test_stock_dividend_rescales_pending_buy_when_no_shares_are_held(
    engine_cfg: AppConfig, apply_session: int
) -> None:
    # Nothing held at the ex-date; a buy of 1,000 created Tue 11-03 (before the ex-date) is
    # pending when the action is applied (on time, or two sessions late): 1,000 x 1.1 = 1,100.
    # The buy is queued at the open where the action is applied, so it is rescaled first.
    extra = [(apply_session, "buy", 1_000, 2)]
    sim = _late_run(engine_cfg, _stock_action(date(2026, 11, 5)), 99, None, apply_session, extra)
    trades = sim.result().trades
    assert list(trades["qty"]) == [1_100]
    assert sim.ledger.shares("AAA") == 1_100  # no bonus shares: none held at the ex-date


def test_replaced_order_counts_as_created_at_the_new_decision(engine_cfg: AppConfig) -> None:
    # A decision at Thu 11-05 close re-sizes a pending order of the same ticker and side; the
    # order keeps its id and carry count but counts as created on 11-05, so a stock event with
    # ex-date 11-04 applied late (via the decide() path) does not rescale it again.
    days = make_days(8)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    sim = Simulator(prices, None, CAL, executable(engine_cfg))
    old = sim.queue("AAA", "buy", 10, days[2])  # created Tue 11-03, before the ex-date
    old.carried = 2
    sim.mark(days[4])
    sim.decide(days[4], weights(AAA=0.0005))  # 0.05 % of 100,000,000 = 50,000 -> 1 share
    assert (old.order_id, old.carried, old.created, old.qty) == (1, 2, days[4], 1)
    assert sim._pending == [old]
    sim.add_actions(synthetic_actions(_stock_action(None)))  # ex 11-04, published after
    sim._snapshot_preopen(days[5])
    sim._apply_actions(days[5])
    assert old.qty == 1  # sized on post-event prices: not 1 x 1.1


@pytest.mark.parametrize("apply_session", [2, 7])
def test_cash_dividend_after_a_stock_dividend_includes_the_bonus_shares(
    engine_cfg: AppConfig, apply_session: int
) -> None:
    # 1,000 AAA bought 11-02; stock 10 % ex Wed 11-04 (+100, listing 11-05); cash 1,000 VND ex
    # Fri 11-06. Entitlement of the cash action is 1,100 shares, whether both actions are known
    # up front (session 2) or both arrive late in one batch (session 7, Tue 11-10):
    # 1,100 x 1,000 = 1,100,000.
    cash = {**_cash_action(date(2026, 11, 6)), "pay_date": date(2026, 11, 30)}
    both = synthetic_actions(_stock_action(date(2026, 11, 5)), cash)
    days = make_days(12)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    sim = Simulator(prices, None, CAL, executable(engine_cfg))
    for i, day in enumerate(sim.sessions):
        if i == 1:
            sim.queue("AAA", "buy", 1_000, days[0])
        if i == apply_session:
            sim.add_actions(both)
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    assert sim.result().equity["cash_pending"].iloc[-1] == pytest.approx(1_100_000)
    assert sim.ledger.shares("AAA") == 1_100


@pytest.mark.parametrize("apply_session", [2, 8])
def test_bonus_on_bonus_compounds_from_ex_date_holdings(
    engine_cfg: AppConfig, apply_session: int
) -> None:
    # 1,000 -> +10 % ex 11-04 = 1,100 -> +10 % ex 11-06 = +110 -> 1,210, on time or all late.
    second = {**_stock_action(date(2026, 11, 5)), "ex_date": date(2026, 11, 6)}
    both = synthetic_actions(_stock_action(date(2026, 11, 5)), second)
    days = make_days(12)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    sim = Simulator(prices, None, CAL, executable(engine_cfg))
    for i, day in enumerate(sim.sessions):
        if i == 1:
            sim.queue("AAA", "buy", 1_000, days[0])
        if i == apply_session:
            sim.add_actions(both)
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    assert sim.ledger.shares("AAA") == 1_210


def test_sales_tax_in_hose_yaml_equals_costs_default(engine_cfg: AppConfig) -> None:
    assert engine_cfg.market.rules.sales_tax_pct.value == engine_cfg.costs.sales_tax_pct


@pytest.mark.parametrize("order", ["stock_first", "cash_first"])
@pytest.mark.parametrize("apply_session", [2, 7])
def test_same_ex_date_actions_never_feed_each_other_when_ex_date_is_not_a_session(
    engine_cfg: AppConfig, order: str, apply_session: int
) -> None:
    # Ex-date Wed 11-04 is absent from the price frame. Stock 10 % and cash 1,000 VND share it:
    # entitlement for both is the 1,000 held at the next session's pre-open, in either row
    # order, on time or late. Cash = 1,000 x 1,000 = 1,000,000 (not 1,100 x 1,000); shares 1,100.
    acts = [_stock_action(date(2026, 11, 5)), _cash_action(date(2026, 11, 4))]
    if order == "cash_first":
        acts.reverse()
    days = make_days(12)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    prices = prices[prices["date"] != date(2026, 11, 4)]
    sim = Simulator(prices, None, CAL, executable(engine_cfg))
    for i, day in enumerate(sim.sessions):
        if i == 1:
            sim.queue("AAA", "buy", 1_000, sim.sessions[0])
        if i == apply_session:
            sim.add_actions(synthetic_actions(*acts))
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    assert sim.ledger.shares("AAA") == 1_100
    assert sim.ledger.cash_pending == pytest.approx(1_000_000)


def test_late_bonus_does_not_leak_into_another_ticker(engine_cfg: AppConfig) -> None:
    # AAA bonus (late) must not change the BBB cash entitlement: 500 BBB x 1,000 = 500,000
    # (500 shares each, so cash is ample).
    days = make_days(12)
    prices = synthetic_prices(
        synthetic_bars("AAA", days, 50_000), synthetic_bars("BBB", days, 50_000)
    )
    sim = Simulator(prices, None, CAL, executable(engine_cfg))
    bbb = {**_cash_action(date(2026, 11, 6)), "ticker": "BBB", "pay_date": date(2026, 11, 30)}
    for i, day in enumerate(sim.sessions):
        if i == 1:
            sim.queue("AAA", "buy", 500, days[0])
            sim.queue("BBB", "buy", 500, days[0])
        if i == 7:
            sim.add_actions(synthetic_actions(_stock_action(date(2026, 11, 5)), bbb))
        sim.open_session(day)
        sim.mark(day)
        sim.record(day)
    assert sim.ledger.shares("AAA") == 550
    assert sim.ledger.cash_pending == pytest.approx(500_000)


# ---------------------------------------------------------------- risk layer (P1-T12)


def wide(prices: pd.DataFrame) -> pd.DataFrame:
    """Give every bar a +/- 750 range around its open/close: constant prices then have
    TR = 1,500 on every row, hence ATR14 = 1,500 (hand-computed)."""
    out = prices.copy()
    out["high"] = out[["open", "close"]].max(axis=1) + 750
    out["low"] = out[["open", "close"]].min(axis=1) - 750
    return out


def run_risk(
    cfg: AppConfig,
    prices: pd.DataFrame,
    targets: dict[date, pd.Series],
    cooldown: int | None = 2,
    **risk: float | None,
) -> SimResult:
    layer = RiskLayer(cfg.risk.model_copy(update=risk))
    return run_simulation(
        prices, None, targets, CAL, executable(cfg), risk=layer, cooldown_sessions=cooldown
    )


def stop_scenario(shock_idx: int) -> tuple[list[date], pd.DataFrame]:
    """AAA flat at 50,000 (ATR 1,500) until the close of ``shock_idx``, then 47,000."""
    days = make_days(26)
    over: dict[int, dict[str, float]] = {shock_idx: {"close": 47_000}}
    for i in range(shock_idx + 1, len(days)):
        over[i] = {"open": 47_000, "close": 47_000}
    return days, wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))


def test_stop_hit_on_close_sells_at_next_open(engine_cfg: AppConfig) -> None:
    days, prices = stop_scenario(17)
    # Close of idx 14: ATR14 = 1,500; equity 100,000,000; weight 0.15 -> 15,000,000 / 50,000
    # = 300 shares (sizing cap 0.01 x 50,000 / (2 x 1,500) = 0.1667 does not bind).
    # Buy fills idx 15 open 50,000 x 1.001 = 50,050 -> stop = 50,050 - 2 x 1,500 = 47,050.
    # Shares sellable from idx 18. Close idx 17 = 47,000 <= 47,050 -> stop -> sell at idx 18.
    res = run_risk(engine_cfg, prices, {days[14]: weights(AAA=0.15)})
    sell = res.trades[res.trades["side"] == "sell"].iloc[0]
    assert (sell["session"], sell["qty"]) == (days[18], 300)
    assert sell["price"] == pytest.approx(47_000 * 0.999)  # 46,953
    assert res.order_events.empty  # sellable on time: no queueing event
    ev = res.risk_events
    assert ev is not None
    assert [(r.session, r.event, r.ticker) for r in ev.itertuples()] == [
        (days[17], "stop_triggered", "AAA")
    ]
    assert res.positions[res.positions["date"] == days[18]].empty


def test_stop_before_sellable_waits_for_t3(engine_cfg: AppConfig) -> None:
    days, prices = stop_scenario(16)
    # Same entry (idx 15, sellable idx 18). Close idx 16 = 47,000 <= 47,050 -> stop order for
    # idx 17: shares not sellable -> logged stop_pending_settlement; sold at idx 18 (T+3).
    res = run_risk(engine_cfg, prices, {days[14]: weights(AAA=0.15)})
    assert [(r.session, r.event) for r in res.order_events.itertuples()] == [
        (days[17], "stop_pending_settlement")
    ]
    sells = res.trades[res.trades["side"] == "sell"]
    assert [(r.session, r.qty) for r in sells.itertuples()] == [(days[18], 300)]
    # The loss is real: bought at 50,050, sold at 46,953 -> equity below capital by more than
    # 300 x 3,097 = 929,100.
    assert res.equity.iloc[-1]["equity"] < 100_000_000 - 300 * (50_050 - 46_953)


def test_stop_beats_same_day_rebalance_and_cooldown_blocks_rebuy(engine_cfg: AppConfig) -> None:
    days, prices = stop_scenario(17)
    keep = weights(AAA=0.15)
    # Stop at close idx 17 while the strategy still asks for AAA at that very close.
    # Cooldown 2 sessions: decisions at idx 17 (same day), 18, 19 are blocked; idx 20 is free.
    targets = {days[14]: keep, days[17]: keep, days[18]: keep, days[19]: keep, days[20]: keep}
    res = run_risk(engine_cfg, prices, targets, cooldown=2)
    sells = res.trades[res.trades["side"] == "sell"]
    assert [(r.session, r.qty) for r in sells.itertuples()] == [(days[18], 300)]
    buys = res.trades[res.trades["side"] == "buy"]
    # (a re-buy can split into a round lot and an odd lot: compare the sessions)
    assert sorted(set(buys["session"])) == [days[15], days[21]]  # no re-buy before 21


def test_cooldown_must_be_resolved_by_the_caller(engine_cfg: AppConfig) -> None:
    days, prices = stop_scenario(17)
    assert engine_cfg.risk.stop_cooldown_sessions is None
    with pytest.raises(ValueError, match="stop_cooldown_sessions"):
        run_risk(engine_cfg, prices, {days[14]: weights(AAA=0.15)}, cooldown=None)
    # A configured value is used when the caller passes none.
    res = run_risk(
        engine_cfg, prices, {days[14]: weights(AAA=0.15)}, cooldown=None, stop_cooldown_sessions=3
    )
    assert len(res.trades) == 2


def test_sizing_applies_in_loop(engine_cfg: AppConfig) -> None:
    days = make_days(20)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000)))
    # Request 0.30; ATR 1,500 -> cap 0.1667 -> 16,666,667 / 50,000 = 333 shares.
    res = run_risk(engine_cfg, prices, {days[14]: weights(AAA=0.30)})
    assert res.trades["qty"].sum() == 333  # 300 round lot + 33 odd lot


def test_no_atr_history_means_no_new_entry(engine_cfg: AppConfig) -> None:
    days = make_days(12)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000)))
    res = run_risk(engine_cfg, prices, {days[5]: weights(AAA=0.15)})  # only 6 rows: ATR is NaN
    assert res.trades.empty


def test_circuit_breaker_blocks_new_buys_then_rearms(engine_cfg: AppConfig) -> None:
    days = make_days(26)
    over = {17: {"close": 48_000}}  # AAA -4 % at the close of idx 17; back to 50,000 at idx 18
    prices = wide(
        synthetic_prices(
            synthetic_bars("AAA", days, 50_000, over=over), synthetic_bars("BBB", days, 30_000)
        )
    )
    # Breaker at 0.5 % drawdown. 300 AAA bought at 50,050: equity after the buy
    # = 100,000,000 - slippage 300 x 50 (15,000) - fee 22,522.5 = 99,962,477.5 < the peak, which
    # stays at the initial capital 100,000,000 -> threshold 100,000,000 x 0.995 = 99,500,000.
    # Idx 17 close: 300 x 48,000 = 14,400,000 (-600,000) -> equity 99,362,477.5 <= threshold.
    # Idx 18 close: back at 50,000 -> equity about 99.94 million > threshold -> re-armed.
    both = weights(AAA=0.10, BBB=0.08)
    targets = {days[14]: weights(AAA=0.15), days[17]: both, days[19]: both}
    res = run_risk(engine_cfg, prices, targets, circuit_breaker_drawdown_pct=0.005)
    ev = res.risk_events
    assert ev is not None
    assert [(r.session, r.event) for r in ev.itertuples()] == [
        (days[17], "circuit_breaker_on"),
        (days[18], "circuit_breaker_off"),
    ]
    buys = res.trades[res.trades["side"] == "buy"]
    # Decision idx 17 (breaker on): BBB not bought. Decision idx 19 (re-armed): BBB buys at 20.
    # (a buy can split into a round lot and an odd lot: compare ticker and session only)
    assert sorted(set(zip(buys["ticker"], buys["session"], strict=True))) == [
        ("AAA", days[15]),
        ("BBB", days[20]),
    ]


def test_circuit_breaker_cancels_pending_buys(engine_cfg: AppConfig) -> None:
    days = make_days(26)
    over = {17: {"close": 48_000}}
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))
    layer = RiskLayer(engine_cfg.risk.model_copy(update={"circuit_breaker_drawdown_pct": 0.005}))
    sim = Simulator(prices, None, CAL, executable(engine_cfg), risk=layer, cooldown_sessions=2)
    for i, day in enumerate(sim.sessions):
        sim.open_session(day)
        if i == 17:  # a buy still pending when the breaker turns on at this close
            sim.queue("AAA", "buy", 10, days[16])
        sim.mark(day)
        if i == 14:
            sim.decide(day, weights(AAA=0.15))
        sim.record(day)
    kinds = [(r.event, r.reason) for r in sim.result().order_events.itertuples()]
    assert ("cancelled", "circuit breaker active") in kinds


def test_rebalance_threshold_skips_small_changes(engine_cfg: AppConfig) -> None:
    days = make_days(22)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000)))
    # 300 shares held; equity at close idx 16 = 99,962,477.5 (cash 84,962,477.5 + 15,000,000).
    # New weight 0.1575 -> 15,744,090 / 50,000 -> 314 shares: +14 shares = 700,000 of a
    # 15,700,000 target (4.5 %).  Threshold 10 % -> skipped; threshold 2 % -> bought at idx 17.
    targets = {days[14]: weights(AAA=0.15), days[16]: weights(AAA=0.1575)}
    skipped = run_risk(engine_cfg, prices, targets)
    assert [(r.session, r.qty) for r in skipped.trades.itertuples()] == [(days[15], 300)]
    traded = run_risk(engine_cfg, prices, targets, rebalance_threshold_pct=0.02)
    assert [(r.session, r.qty) for r in traded.trades.itertuples()] == [
        (days[15], 300),
        (days[17], 14),
    ]


def test_rebalance_threshold_never_skips_exits_or_entries(engine_cfg: AppConfig) -> None:
    days = make_days(22)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000)))
    # Entry at idx 14 (0 -> 300 shares) and full exit decided at idx 17 (sellable from 18):
    # both are 100 % changes and ignore the 10 % threshold.
    res = run_risk(engine_cfg, prices, {days[14]: weights(AAA=0.15), days[17]: NONE})
    assert [(r.side, r.session, r.qty) for r in res.trades.itertuples()] == [
        ("buy", days[15], 300),
        ("sell", days[18], 300),
    ]


def test_risk_off_by_default_has_no_risk_output(engine_cfg: AppConfig) -> None:
    days = make_days(20)
    prices = synthetic_prices(synthetic_bars("AAA", days, 50_000))
    res = run_simulation(prices, None, {days[2]: weights(AAA=0.5)}, CAL, executable(engine_cfg))
    assert res.risk_events is None
    assert "risk_events" not in res.frames()


# ---------------------------------------------------------------- risk layer review fixes


def _flat(lo: int, hi: int, px: float) -> dict[int, dict[str, float]]:
    return {
        i: {"open": px, "close": px, "ceiling": px * 1.07, "floor": px * 0.93, "ref_price": px}
        for i in range(lo, hi)
    }


def _risk_sim(cfg: AppConfig, prices: pd.DataFrame, n: int = 2) -> Simulator:
    return Simulator(
        prices, None, CAL, executable(cfg), risk=RiskLayer(cfg.risk), cooldown_sessions=n
    )


def test_partial_sell_then_add_keeps_the_right_average(engine_cfg: AppConfig) -> None:
    days = make_days(26)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=_flat(20, 26, 60_000))))
    sim = _risk_sim(engine_cfg, prices)
    plan = {14: [("AAA", "buy", 300)], 18: [("AAA", "sell", 200)], 20: [("AAA", "buy", 200)]}
    for i, d in enumerate(sim.sessions):
        sim.open_session(d)
        sim.mark(d)
        for ticker, side, qty in plan.get(i, []):
            sim.queue(ticker, side, qty, d)
        sim.record(d)
    # Buy 300 @ 50,050 (ATR 1,500); sell 200 -> 100 @ 50,050 left; add 200 @ 60,060 (ATR
    # about 2,160.7): entry = (100 x 50,050 + 200 x 60,060) / 300 = 56,723.33,
    # ATR = (100 x 1,500 + 200 x 2,160.7) / 300 = 1,940.5 -> stop 56,723.33 - 3,881 = 52,842.
    qty, price, atr_avg = sim._entries["AAA"]
    assert qty == sim.ledger.shares("AAA") == 300
    assert price == pytest.approx(56_723.33, abs=0.01)
    assert atr_avg == pytest.approx(1_940.5, rel=1e-3)
    assert price - 2 * atr_avg == pytest.approx(52_842, rel=1e-3)


def test_carried_buy_is_cancelled_when_the_stop_fires(engine_cfg: AppConfig) -> None:
    days = make_days(26)
    over = _flat(18, 26, 47_000)
    over[16] = {"open": 53_500, "close": 50_000, "ceiling": 53_500}  # open at the ceiling
    over[17] = {"open": 53_500, "close": 47_000, "ceiling": 53_500}
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))
    params = dataclasses.replace(executable(engine_cfg), unfilled_buy="carry")
    targets = {days[14]: weights(AAA=0.10), days[15]: weights(AAA=0.15)}
    res = run_simulation(
        prices, None, targets, CAL, params, risk=RiskLayer(engine_cfg.risk), cooldown_sessions=10
    )
    # The idx 16 / 17 opens sit at the ceiling: the extra buy is carried. The stop fires at the
    # idx 17 close: carried buys are cancelled and nothing is bought after it.
    late = res.trades[(res.trades["side"] == "buy") & (res.trades["session"] > days[17])]
    assert late.empty
    assert "stop triggered" in set(res.order_events["reason"])


def test_cooldown_starts_when_the_stop_exit_completes(engine_cfg: AppConfig) -> None:
    days, prices = stop_scenario(16)  # stop at close idx 16, shares only sellable at idx 18
    keep = weights(AAA=0.15)
    # Exit completes at idx 18; n = 2 -> decisions at closes 18 and 19 blocked, 20 free (a
    # cooldown counted from the trigger at 16 would have expired before the exit).
    targets = {days[14]: keep, days[19]: keep, days[20]: keep}
    res = run_risk(engine_cfg, prices, targets, cooldown=2)
    buys = res.trades[res.trades["side"] == "buy"]
    assert sorted(set(buys["session"])) == [days[15], days[21]]


def test_buy_order_in_cooldown_is_refused_at_resolution(engine_cfg: AppConfig) -> None:
    days, prices = stop_scenario(17)
    sim = _risk_sim(engine_cfg, prices)
    for i, d in enumerate(sim.sessions):
        if i == 14:
            sim.queue("AAA", "buy", 300, days[13])
        if i == 19:  # stop exit completed at idx 18: a stray buy for idx 19 is refused
            sim.queue("AAA", "buy", 100, days[18])
        sim.open_session(d)
        sim.mark(d)
        sim.record(d)
    res = sim.result()
    assert (res.trades["side"] == "buy").sum() == 1
    assert ("cancelled", "stop cooldown") in {
        (r.event, r.reason) for r in res.order_events.itertuples()
    }


def test_late_stock_action_rescales_only_pre_ex_entries(engine_cfg: AppConfig) -> None:
    days = make_days(26)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=_flat(16, 26, 40_000))))
    sim = _risk_sim(engine_cfg, prices)
    act = synthetic_actions(
        {"ticker": "AAA", "ex_date": days[16], "type": "stock", "ratio_or_amount": 0.25}
    )
    for i, d in enumerate(sim.sessions):
        if i == 18:
            sim.add_actions(act)  # published two sessions after its ex-date
        sim.open_session(d)
        sim.mark(d)
        if i == 16:
            sim.queue("AAA", "buy", 100, d)
        sim.record(d)
    # 100 shares bought at the idx 17 open: 40,000 x 1.001 = 40,040, after the ex-date, so the
    # late action must not touch them (the bonus applies to nothing held at the ex-date).
    qty, price, _ = sim._entries["AAA"]
    assert (qty, price) == (sim.ledger.shares("AAA"), pytest.approx(40_040))


def test_stock_ex_date_rescales_entry_and_stop(engine_cfg: AppConfig) -> None:
    days = make_days(26)
    over = _flat(17, 26, 40_000)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))
    act = synthetic_actions(
        {"ticker": "AAA", "ex_date": days[17], "type": "stock", "ratio_or_amount": 0.25}
    )
    sim = Simulator(
        prices,
        act,
        CAL,
        executable(engine_cfg),
        risk=RiskLayer(engine_cfg.risk),
        cooldown_sessions=2,
    )
    for i, d in enumerate(sim.sessions):
        if i == 15:
            sim.queue("AAA", "buy", 400, days[14])
        sim.open_session(d)
        sim.mark(d)
        sim.record(d)
    # 400 @ 50,050, ATR 1,500; ex-date 25 %: 500 shares, entry 50,050 / 1.25 = 40,040,
    # ATR 1,500 / 1.25 = 1,200 (the gap to 40,000 is not volatility) -> no stop at close 40,000
    # (stop 40,040 - 2 x about 1,200 = 37,640).
    assert sim.ledger.shares("AAA") == 500
    qty, price, _ = sim._entries["AAA"]
    assert (qty, price) == (pytest.approx(500), pytest.approx(40_040))
    assert sim.result().risk_events is not None
    assert sim.result().risk_events.empty  # no stop fired


def test_simulator_requires_cooldown_of_at_least_one(engine_cfg: AppConfig) -> None:
    _days, prices = stop_scenario(17)
    with pytest.raises(ValueError, match="stop_cooldown_sessions"):
        _risk_sim(engine_cfg, prices, n=0)


# ---------------------------------------------------------------- risk follow-ups (P1-T12b)


def _bonus_prices(ex_idx: int, factor: float, n: int = 30) -> pd.DataFrame:
    """AAA flat 50,000 (wide: TR = 1,500) until the ex-date row, then 50,000 / factor."""
    days = make_days(n)
    post = 50_000 / factor
    return wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=_flat(ex_idx, n, post))))


def _bonus_action(days: list[date], ex_idx: int, ratio: float) -> pd.DataFrame:
    return synthetic_actions(
        {"ticker": "AAA", "ex_date": days[ex_idx], "type": "stock", "ratio_or_amount": ratio}
    )


Plan = dict[int, list[tuple[str, str, float]]]


def _drive(
    cfg: AppConfig,
    prices: pd.DataFrame,
    up_front: pd.DataFrame | None,
    late: tuple[int, pd.DataFrame] | None,
    plan: Plan,
) -> tuple[Simulator, dict[int, float]]:
    sim = Simulator(
        prices, up_front, CAL, executable(cfg), risk=RiskLayer(cfg.risk), cooldown_sessions=2
    )
    atr_seen: dict[int, float] = {}
    for i, d in enumerate(sim.sessions):
        if late is not None and i == late[0]:
            sim.add_actions(late[1])
        sim.open_session(d)
        sim.mark(d)
        atr_seen[i] = sim._atr_now["AAA"]
        for ticker, side, qty in plan.get(i, []):
            sim.queue(ticker, side, qty, d)  # type: ignore[arg-type]
        sim.record(d)
    return sim, atr_seen


def test_late_action_gives_the_same_digest_and_atr_as_known_up_front(
    engine_cfg: AppConfig,
) -> None:
    days = make_days(30)
    prices = _bonus_prices(20, 1.5)
    act = _bonus_action(days, 20, 0.5)
    plan: Plan = {14: [("AAA", "buy", 300)]}
    base, atr_base = _drive(engine_cfg, prices, act, None, plan)
    # ATR: flat 50,000 with TR 1,500 -> ATR19 = 1,500. Ex-date row 20, factor 1.5: previous close
    # 50,000 / 1.5 = 33,333, ATR19 / 1.5 = 1,000, TR_20 = 1,500 -> ATR20 = (1,000 x 13 + 1,500)
    # / 14 = 1,035.7. Without the factor TR_20 = |32,583 - 50,000| = 17,417 and
    # ATR20 = (1,500 x 13 + 17,417) / 14 = 2,636.9.
    assert atr_base[20] == pytest.approx(1_035.7, abs=0.05)
    assert base.ledger.shares("AAA") == 450  # 300 x 1.5
    for idx in (18, 22):  # known before the ex-date / two sessions after it
        sim, seen = _drive(engine_cfg, prices, None, (idx, act), plan)
        if idx < 20:  # known before the ex-date: identical run
            assert sim.result().digest() == base.result().digest()
        # (after the ex-date the unadjusted marks of idx 20-21 already happened and a stop fires
        # on them: history is not rewritten, so only the state from the apply session on matches)
        if idx < 20:
            assert sim.ledger.shares("AAA") == 450
        for i in range(idx, 30):  # values from the apply session on equal the up-front run's
            assert seen[i] == pytest.approx(atr_base[i], nan_ok=True)
        assert sim._atr_series["AAA"][days[20]] == pytest.approx(1_035.7, abs=0.05)
        if idx < 20:
            assert sim._entries["AAA"] == pytest.approx(base._entries["AAA"])
    # reads before the apply session keep the old basis (no rewrite of what was already used)
    _sim, seen = _drive(engine_cfg, prices, None, (22, act), plan)
    assert seen[20] == pytest.approx(2_636.9, abs=0.05)


def test_late_action_with_an_entry_between_ex_date_and_apply_rebases_its_atr(
    engine_cfg: AppConfig,
) -> None:
    days = make_days(30)
    prices = _bonus_prices(20, 1.5)
    act = _bonus_action(days, 20, 0.5)
    plan: Plan = {21: [("AAA", "buy", 100)]}  # fills at the idx 22 open, after the ex-date
    base, _ = _drive(engine_cfg, prices, act, None, plan)
    sim, _ = _drive(engine_cfg, prices, None, (23, act), plan)
    # In the late run the lot's ATR was first read from the old series (about 2,000) but must
    # be the post-event ATR21 of the up-front run (about 1,000-1,100).
    assert sim._lots["AAA"][0].atr == pytest.approx(base._lots["AAA"][0].atr)
    assert sim._lots["AAA"][0].atr < 1_100
    assert sim.result().digest() == base.result().digest()


def test_exact_shrink_after_a_floored_bonus_and_partial_sell(engine_cfg: AppConfig) -> None:
    days = make_days(30)
    prices = _bonus_prices(18, 1.15)
    act = _bonus_action(days, 18, 0.15)
    plan: Plan = {14: [("AAA", "buy", 110)], 20: [("AAA", "sell", 26)]}
    sim, _ = _drive(engine_cfg, prices, act, None, plan)
    # 110 held at the ex-date: 110 x 0.15 = 16.5 -> floor 16 -> 126 shares (lots alone would
    # say 126.5). Sell 26 -> 100 left: lots shrink to the ledger's 100, not 126.5 - 26 = 100.5.
    qty, _, _ = sim._entries["AAA"]
    assert sim.ledger.shares("AAA") == 100
    assert qty == pytest.approx(100)
    assert sum(x.qty for x in sim._lots["AAA"]) == pytest.approx(100)


def test_late_bonus_on_a_fully_sold_position_gets_a_lot_and_a_stop(engine_cfg: AppConfig) -> None:
    days = make_days(30)
    over = _flat(18, 30, 40_000)  # 25 % bonus at idx 18: 50,000 / 1.25
    over.update({i: {**over[i], "close": 30_000} for i in range(23, 30)})
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))
    act = _bonus_action(days, 18, 0.25)
    plan: Plan = {14: [("AAA", "buy", 100)], 18: [("AAA", "sell", 100)]}
    # 100 bought at the idx 15 open (held at the idx 18 pre-open), sold in full at idx 19. The
    # bonus (25 shares) is published at idx 21, after the position is gone.
    sim, _ = _drive(engine_cfg, prices, None, (21, act), plan)
    assert sim.ledger.shares("AAA") == 25
    lots = sim._lots["AAA"]
    assert len(lots) == 1
    assert lots[0].qty == pytest.approx(25)
    # Entry = last close before the apply session (idx 20): 40,000. ATR = ATR20 of the series:
    # 1,500 / 1.25 = 1,200 at idx 17, then (1,200 x 13 + 1,500) / 14 = 1,221.4 (18),
    # 1,241.3 (19), 1,259.8 (20).
    assert lots[0].price == pytest.approx(40_000)
    assert lots[0].atr == pytest.approx(1_259.8, abs=0.1)
    # Close 30,000 at idx 23 <= stop 40,000 - 2 x ATR: the stop fires on the bonus lot.
    stops = sim.result().risk_events
    assert stops is not None
    fired = [r for r in stops.itertuples() if r.event == "stop_triggered"]
    # (the old position was already stopped out at idx 18 on the unadjusted drop: history stays)
    assert fired[-1].ticker == "AAA"
    assert fired[-1].session == days[23]
    assert fired[-1].detail.startswith("close 30000.00 <= stop 37480")  # 40,000 - 2 x 1,259.8


def test_lot_totals_always_equal_ledger_shares(engine_cfg: AppConfig) -> None:
    days = make_days(40)
    for seed in range(40):
        rng = random.Random(seed)  # noqa: S311 - test data, not crypto
        ex_idx = rng.randrange(16, 30)
        ratio = rng.choice([0.15, 0.25, 0.5])
        prices = _bonus_prices(ex_idx, 1 + ratio, 40)
        act = _bonus_action(days, ex_idx, ratio)
        late_at = rng.choice([None, ex_idx - 1, ex_idx + rng.randrange(1, 8)])
        plan: Plan = {}
        for i in range(12, 36):
            roll = rng.random()
            if roll < 0.25:
                plan[i] = [("AAA", "buy", float(rng.randrange(1, 30) * 10))]
            elif roll < 0.6:
                plan[i] = [("AAA", "sell", float(rng.randrange(1, 20) * 10))]
        sim = Simulator(
            prices,
            act if late_at is None else None,
            CAL,
            executable(engine_cfg),
            risk=RiskLayer(engine_cfg.risk),
            cooldown_sessions=2,
        )
        for i, d in enumerate(sim.sessions):
            if i == late_at:
                sim.add_actions(act)
            sim.open_session(d)
            sim.mark(d)
            held = sim.ledger.shares("AAA")
            total = sum(x.qty for x in sim._lots.get("AAA", []))
            assert total == pytest.approx(held, abs=1e-6), (seed, i)
            for ticker, side, qty in plan.get(i, []):
                sim.queue(ticker, side, qty, d)  # type: ignore[arg-type]
            sim.record(d)


@pytest.mark.parametrize("late_at", [None, 23])
def test_lot_bought_at_the_ex_date_open_has_a_post_event_atr(
    engine_cfg: AppConfig, late_at: int | None
) -> None:
    days = make_days(30)
    prices = _bonus_prices(20, 1.5)
    act = _bonus_action(days, 20, 0.5)
    plan: Plan = {19: [("AAA", "buy", 300)]}  # fills at the idx 20 open, the ex-date
    sim, _ = _drive(
        engine_cfg, prices, act if late_at is None else None,
        None if late_at is None else (late_at, act), plan,
    )  # fmt: skip
    # Fill at 50,000 / 1.5 = 33,333.33 x 1.001 = 33,366.67 (post-event). ATR19 = 1,500 in the
    # pre-event basis, so the lot's ATR is 1,500 / 1.5 = 1,000 and the stop
    # 33,366.67 - 2 x 1,000 = 31,366.67 (not 33,366.67 - 3,000 = 30,366.67).
    lot = sim._lots["AAA"][0]
    assert lot.price == pytest.approx(33_366.67, abs=0.01)
    assert lot.atr == pytest.approx(1_000)
    assert lot.price - 2 * lot.atr == pytest.approx(31_366.67, abs=0.01)


def test_residual_lot_keeps_the_session_its_atr_was_read_at(engine_cfg: AppConfig) -> None:
    days = make_days(40)
    over = _flat(18, 40, 40_000)
    prices = wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))
    a1 = _bonus_action(days, 18, 0.25)
    a2 = _bonus_action(days, 19, 0.10)
    plan: Plan = {14: [("AAA", "buy", 100)], 18: [("AAA", "sell", 100)]}
    sim = Simulator(
        prices, None, CAL, executable(engine_cfg), risk=RiskLayer(engine_cfg.risk),
        cooldown_sessions=2,
    )  # fmt: skip
    for i, d in enumerate(sim.sessions):
        if i == 21:
            sim.add_actions(a1)  # sold position: residual lot, ATR read at the idx 20 close
        if i == 25:
            sim.add_actions(a2)
        sim.open_session(d)
        sim.mark(d)
        if i == 21:
            first = sim._lots["AAA"][-1].atr  # ATR20 = 1,259.8 (hand numbers: see above)
            assert first == pytest.approx(1_259.8, abs=0.1)
        for ticker, side, qty in plan.get(i, []):
            sim.queue(ticker, side, qty, d)  # type: ignore[arg-type]
        sim.record(d)
    # The late a2 (ex idx 19) divides the series from row 19 on; the residual lot's ATR is the
    # recomputed value at the session it was read (idx 20), not one session back (idx 19).
    series = sim._atr_series["AAA"]
    residual = [x for x in sim._lots["AAA"] if x.day == days[20]]
    assert residual
    assert residual[0].atr == pytest.approx(series[days[20]])
    assert residual[0].atr != pytest.approx(series[days[19]])
    assert sum(x.qty for x in sim._lots["AAA"]) == pytest.approx(sim.ledger.shares("AAA"))


@pytest.mark.parametrize("ratio", [0.15, 0.1, 0.3, 0.07, 0.33, 0.2])
def test_lot_sync_tolerance_is_relative_with_fractional_shares(
    engine_cfg: AppConfig, ratio: float
) -> None:
    days = make_days(30)
    prices = _bonus_prices(20, 1 + ratio)
    act = _bonus_action(days, 20, ratio)
    params = make_params(engine_cfg, "executable", 1e12, lots=False)
    plan: Plan = {
        12: [("AAA", "buy", 3_333_333.3333333)],
        13: [("AAA", "buy", 7_177_777.777777)],
        14: [("AAA", "buy", 1_312_345.67891)],
        16: [("AAA", "sell", 987_654.321987)],
    }
    sim = Simulator(prices, act, CAL, params, risk=RiskLayer(engine_cfg.risk), cooldown_sessions=2)
    for i, d in enumerate(sim.sessions):
        sim.open_session(d)
        sim.mark(d)
        for ticker, side, qty in plan.get(i, []):
            sim.queue(ticker, side, qty, d)  # type: ignore[arg-type]
        sim.record(d)
    # Shares of about 1e7 carry float noise above an absolute 1e-9: no spurious residual lot
    # (three buys, three lots) and the lots still add up to the ledger.
    assert len(sim._lots["AAA"]) == 3
    assert sum(x.qty for x in sim._lots["AAA"]) == pytest.approx(sim.ledger.shares("AAA"))


# ---------------------------------------------------------------- breaker re-arm (X-breaker)


def _crash_prices(recover: bool) -> tuple[list[date], pd.DataFrame]:
    """AAA 50,000 until idx 16; close 42,000 at idx 17 (-16 %), 42,000 through idx 18; then
    43,000 (idx 19-21) and 44,200 from idx 22 (or 42,000 throughout when ``recover`` is off).
    Limits are widened so the stop exit fills."""
    days = make_days(30)
    over: dict[int, dict[str, float]] = {}
    for i in range(len(days)):
        px = 50_000.0 if i < 17 else 42_000.0
        if recover and i >= 19:
            px = 43_000.0 if i < 22 else 44_200.0
        over[i] = {"ceiling": 70_000, "floor": 20_000}
        if i == 17:
            over[i]["close"] = px
        elif i > 17:
            over[i].update(open=px, close=px)
    return days, wide(synthetic_prices(synthetic_bars("AAA", days, 50_000, over=over)))


def _crash_run(cfg: AppConfig, recover: bool) -> tuple[Simulator, dict[int, tuple[float, ...]]]:
    days, prices = _crash_prices(recover)
    layer = RiskLayer(cfg.risk.model_copy(update={"circuit_breaker_drawdown_pct": 0.01}))
    sim = Simulator(prices, None, CAL, executable(cfg), risk=layer, cooldown_sessions=2)
    targets = {14: weights(AAA=0.08), 21: weights(AAA=0.08), 23: weights(AAA=0.08)}
    seen: dict[int, tuple[float, ...]] = {}
    for i, day in enumerate(days):
        sim.open_session(day)
        sim.mark(day)
        shadow = sim.shadow_equity
        seen[i] = (sim.equity_now(), sim.peak_equity, -1.0 if shadow is None else shadow)
        if i in targets:
            sim.decide(day, targets[i])
        sim.record(day)
    return sim, seen


def test_breaker_rearms_on_shadow_equity_hand_computed(engine_cfg: AppConfig) -> None:
    """dd 1 %, peak = capital 100,000,000 -> threshold 99,000,000.

    Buy at idx 15 (AAA 0.08, 50,050 with slippage). Idx 17 close 42,000: the position loses
    about 1.3 M, equity E17 is about 98.7 M <= 99.0 M -> breaker on, shadow = E17. The ATR stop
    (50,050 - 2 x 1,500) also fires; the book is in cash from idx 18-19 and its equity is flat.
    Shadow holds the h shares of the book at the trigger until the idx-21 decision (price
    43,000), which moves it to 0.08 x shadow / 43,000 shares (fractional, no costs).
        shadow(19..21) = E17 + h x 1,000
        shadow(22)     = shadow(21) + 0.08 x shadow(21) / 43,000 x 1,200   (44,200 close)
    Idx 21 is just short of 99.0 M and idx 22 is above it: off at idx 22, peak := actual equity.
    """
    days, _ = _crash_prices(True)
    sim, seen = _crash_run(engine_cfg, True)
    ev = sim.result().risk_events
    assert ev is not None
    ev = ev[ev["event"].str.startswith("circuit")].reset_index(drop=True)
    assert [(r.session, r.event) for r in ev.itertuples()] == [
        (days[17], "circuit_breaker_on"),
        (days[22], "circuit_breaker_off"),
    ]
    e17, peak17, shadow17 = seen[17]
    assert peak17 == 100_000_000
    assert shadow17 == pytest.approx(e17)
    assert e17 <= 99_000_000 < seen[16][0]  # on at 17; the equity before it was above
    assert seen[16][2] == -1.0  # shadow only exists while on
    pos = sim.result().positions
    h = round(float(pos[pos["date"] == days[17]]["shares"].iloc[0]))
    s21 = e17 + h * 1_000
    assert seen[19][2] == pytest.approx(s21)
    assert seen[21][2] == pytest.approx(s21)
    assert s21 < 99_000_000  # still on at idx 21
    s22 = s21 + 0.08 * s21 / 43_000 * 1_200
    assert s22 >= 99_000_000  # off exactly at idx 22
    assert f"shadow {s22:.0f}" in ev["detail"].iloc[1]
    # Peak reset to the actual (flat, in cash) equity: no immediate re-trigger, buys resume.
    assert seen[22][1] == pytest.approx(seen[22][0])
    assert seen[22][1] < 99_000_000
    assert seen[22][2] == -1.0
    buys = sim.result().trades[sim.result().trades["side"] == "buy"]
    assert sorted(set(zip(buys["ticker"], buys["session"], strict=True))) == [
        ("AAA", days[15]),
        ("AAA", days[24]),
    ]  # none after the idx-21 decision (breaker on); the idx-23 decision buys at idx 24


def test_breaker_stays_on_when_prices_never_recover(engine_cfg: AppConfig) -> None:
    days, _ = _crash_prices(False)
    sim, seen = _crash_run(engine_cfg, False)
    ev = sim.result().risk_events
    assert ev is not None
    ev = ev[ev["event"].str.startswith("circuit")]
    assert [(r.session, r.event) for r in ev.itertuples()] == [(days[17], "circuit_breaker_on")]
    assert seen[29][2] == pytest.approx(seen[17][0])  # shadow flat at E17: 98.7 M < 99.0 M
    trades = sim.result().trades
    assert set(trades[trades["side"] == "buy"]["session"]) == {days[15]}
