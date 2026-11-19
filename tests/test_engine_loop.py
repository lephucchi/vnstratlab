"""Session loop: settlement, limits, lots, costs, cash, corporate actions, ideal mode.

Every expectation is hand-computed in the comments (open 50,000 unless stated; fee 0.15 %,
sales tax 0.1 %, slippage 0.1 % round lot / 0.3 % odd lot; settlement offset 3; HOSE +/-7 %).
"""

from __future__ import annotations

import dataclasses
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
    Simulator,
    make_params,
    period_returns,
    period_turnover,
    run_simulation,
)
from vnstratlab.execution.base import Executor
from vnstratlab.execution.sim import SimExecutor

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
