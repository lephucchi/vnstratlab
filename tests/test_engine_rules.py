"""Hand-computed HOSE rule cases (engine.md sections 5 and 14). Arithmetic is in comments."""

from __future__ import annotations

from datetime import date

import pytest

from vnstratlab.calendar import TradingCalendar
from vnstratlab.config.models import AppConfig
from vnstratlab.engine import CostModel, MarketRules, plan_buy, round_limit_price, tick_size
from vnstratlab.engine.costs import Piece, sell_pieces
from vnstratlab.engine.rules import (
    after_sessions,
    buy_blocked_by_ceiling,
    sell_blocked_by_floor,
    split_lots,
    target_quantity,
)

BANDS = ((0, 10), (10_000, 50), (50_000, 100))


def test_config_adds_engine_section_and_hose_rules(engine_cfg: AppConfig) -> None:
    e = engine_cfg.engine
    assert (e.unfilled_buy, e.unfilled_sell, e.unsettled_sell) == (
        "cancel",
        "carry",
        "queue_until_sellable",
    )
    assert (e.max_carry_sessions, e.rights_policy, e.ideal_capital_vnd) == (5, "ignore", 1.0e12)
    r = engine_cfg.market.rules
    assert (r.cash_proceeds_offset.value, r.cash_proceeds_offset.status) == (2, "VERIFY")
    assert r.cash_dividend_pay_lag_days.value == 30
    assert r.stock_dividend_listing_lag_sessions.value == 20
    rules = MarketRules.from_config(engine_cfg)
    assert (rules.settle_offset, rules.round_lot, rules.odd_lot_max) == (3, 100, 99)


@pytest.mark.parametrize(
    ("price", "tick"),
    [(1, 10), (9_990, 10), (9_999, 10), (10_000, 50), (49_999, 50), (50_000, 100), (120_000, 100)],
)
def test_tick_size_band_boundaries(price: float, tick: int) -> None:
    assert tick_size(price, BANDS) == tick


@pytest.mark.parametrize(
    ("price", "side", "expected"),
    [
        # 49,973 / 50 = 999.46 -> floor 999 -> 999 x 50 = 49,950
        (49_973, "buy", 49_950),
        # 52,730 / 100 = 527.3 -> ceil 528 -> 52,800
        (52_730, "sell", 52_800),
        # 9,995 / 10 = 999.5 -> buy floor 999 -> 9,990 ; sell ceil 1000 -> 10,000 (band edge)
        (9_995, "buy", 9_990),
        (9_995, "sell", 10_000),
        # 10,020 in the 50 band: 200.4 -> buy 200 x 50 = 10,000 ; sell 201 x 50 = 10,050
        (10_020, "buy", 10_000),
        (10_020, "sell", 10_050),
        # 49,990: 999.8 -> buy 999 x 50 = 49,950 ; sell 1000 x 50 = 50,000 (band edge)
        (49_990, "buy", 49_950),
        (49_990, "sell", 50_000),
        # 50,040 in the 100 band: 500.4 -> buy 500 x 100 = 50,000 ; sell 501 x 100 = 50,100
        (50_040, "buy", 50_000),
        (50_040, "sell", 50_100),
        # on-grid prices never move, at every band edge
        (10_000, "buy", 10_000),
        (10_000, "sell", 10_000),
        (50_000, "buy", 50_000),
        (50_000, "sell", 50_000),
        (9_990, "sell", 9_990),
    ],
)
def test_limit_price_rounding(price: float, side: str, expected: float) -> None:
    assert round_limit_price(price, side, BANDS) == expected  # type: ignore[arg-type]


def test_limit_checks() -> None:
    # ref 50,000: ceiling 53,500, floor 46,500 (7 %).
    assert buy_blocked_by_ceiling(53_500, 53_500)
    assert not buy_blocked_by_ceiling(53_400, 53_500)
    assert sell_blocked_by_floor(46_500, 46_500)
    assert not sell_blocked_by_floor(46_600, 46_500)


def test_split_lots_and_target_quantity(engine_cfg: AppConfig) -> None:
    assert split_lots(150, 100, True) == (100, 50)  # 150 = 100 round + 50 odd
    assert split_lots(150, 100, False) == (100, 0)  # odd lots off
    assert split_lots(99.9999999999, 100, True) == (100, 0)  # float noise
    rules = MarketRules.from_config(engine_cfg)
    # 11,000,000 / 52,700 = 208.7 -> 208 shares = 200 round + 8 odd
    assert target_quantity(11_000_000, 52_700, rules, True, True) == 208
    assert target_quantity(11_000_000, 52_700, rules, True, False) == 200
    assert target_quantity(11_000_000, 52_700, rules, False, False) == pytest.approx(
        11_000_000 / 52_700
    )


def test_costs_are_exact(engine_cfg: AppConfig) -> None:
    c = CostModel.from_config(engine_cfg)
    assert (c.fee_pct, c.tax_pct, c.slip_round, c.slip_odd) == (0.0015, 0.001, 0.001, 0.003)
    # buy: 50,000 x 1.001 = 50,050 ; sell: 50,000 x 0.999 = 49,950 (round lot)
    assert c.fill_price(50_000, "buy", "round") == pytest.approx(50_050)
    assert c.fill_price(50_000, "sell", "round") == pytest.approx(49_950)
    # odd lot: 50,000 x 1.003 = 50,150 ; x 0.997 = 49,850
    assert c.fill_price(50_000, "buy", "odd") == pytest.approx(50_150)
    assert c.fill_price(50_000, "sell", "odd") == pytest.approx(49_850)
    # fee 0.15 % of 5,005,000 = 7,507.5 ; tax 0.1 % of 4,995,000 = 4,995 (sell only)
    assert c.fee(5_005_000) == pytest.approx(7_507.5)
    assert c.tax(4_995_000, "sell") == pytest.approx(4_995)
    assert c.tax(4_995_000, "buy") == 0


def test_plan_buy_two_round_lots_not_three(engine_cfg: AppConfig) -> None:
    c = CostModel.from_config(engine_cfg)
    # Cash 11,000,000, open 52,700, want 300 shares (3 lots).
    # Round fill 52,700 x 1.001 = 52,752.7 ; one lot with fee = 100 x 52,752.7 x 1.0015
    #   = 5,283,182.9 ; two lots = 10,566,365.81 <= 11,000,000 ; three = 15.85M > cash.
    # Odd: cash left 433,634.19 ; odd unit 52,700 x 1.003 x 1.0015 = 52,937.39 -> 8 shares
    #   (8 x 52,937.39 = 423,499.1 <= 433,634.19 < 9 x 52,937.39 = 476,436.5).
    pieces = plan_buy(11_000_000, 300, 52_700, c, 100, 99, lots=True, odd_lots=True)
    assert pieces == [Piece(200, "round"), Piece(8, "odd")]
    assert plan_buy(11_000_000, 300, 52_700, c, 100, 99, lots=True, odd_lots=False) == [
        Piece(200, "round")
    ]


def test_plan_buy_target_150_and_small_cash(engine_cfg: AppConfig) -> None:
    c = CostModel.from_config(engine_cfg)
    assert plan_buy(1e9, 150, 50_000, c, 100, 99, True, True) == [
        Piece(100, "round"),
        Piece(50, "odd"),
    ]
    assert plan_buy(1_000, 150, 50_000, c, 100, 99, True, True) == []  # cannot afford a share
    # fractional: 1,001,500 / (50,000 x 1.001 x 1.0015 = 50,125.075) = 19.98 < desired 100
    pieces = plan_buy(1_001_500, 100, 50_000, c, 100, 99, lots=False, odd_lots=False)
    assert len(pieces) == 1
    assert pieces[0].lot == "fractional"
    assert pieces[0].qty == pytest.approx(1_001_500 / 50_125.075)


def test_sell_pieces() -> None:
    assert sell_pieces(250, 100, True, True) == [Piece(200, "round"), Piece(50, "odd")]
    assert sell_pieces(250, 100, False, True) == [Piece(200, "round")]
    assert sell_pieces(50, 100, False, True) == []
    assert sell_pieces(12.5, 100, False, False) == [Piece(12.5, "fractional")]
    assert sell_pieces(0, 100, False, False) == []


def test_after_sessions_uses_the_calendar() -> None:
    cal = TradingCalendar()
    assert after_sessions(cal, date(2026, 11, 2), 0) == date(2026, 11, 2)
    # Monday + 3 sessions = Tue, Wed, Thu
    assert after_sessions(cal, date(2026, 11, 2), 3) == date(2026, 11, 5)
    ends = TradingCalendar.from_sessions([date(2026, 11, 2), date(2026, 11, 3)])
    assert after_sessions(ends, date(2026, 11, 3), 3) == date.max  # beyond the data
