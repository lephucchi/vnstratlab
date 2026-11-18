"""Session loop (engine.md section 4): pure, deterministic, no I/O.

Orders are created at a close and filled at the next open. Within a session: corporate
actions and settlement first, then sells, then buys, then mark to market and decisions.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.engine.costs import CostModel, LotType, Piece, plan_buy, sell_pieces
from vnstratlab.engine.ledger import Ledger
from vnstratlab.engine.orders import EventKind, EventLog, Order
from vnstratlab.engine.rules import (
    EPS,
    MarketRules,
    Side,
    after_sessions,
    buy_blocked_by_ceiling,
    sell_blocked_by_floor,
    target_quantity,
)

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

Mode = Literal["ideal", "executable"]
ALLOWED_BASES = ("raw", "synthetic", "exec_reconstructed")
PRICE_COLUMNS = (
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ref_price",
    "ceiling",
    "floor",
    "price_basis",
)
ACTION_COLUMNS = ("ticker", "ex_date", "type", "ratio_or_amount")
TRADE_COLUMNS = (
    "order_id",
    "ticker",
    "side",
    "session",
    "qty",
    "price",
    "open",
    "notional",
    "fee",
    "tax",
    "slippage",
    "lot_type",
)
EQUITY_COLUMNS = (
    "date",
    "cash_available",
    "cash_pending",
    "cash_reserved",
    "positions_value",
    "equity",
)
POSITION_COLUMNS = ("date", "ticker", "shares", "sellable", "close", "value")
_ACTION_KINDS: dict[str, Literal["cash", "stock"] | None] = {
    "cash": "cash",
    "stock": "stock",
    "bonus": "stock",
    "rights": None,  # rights_policy: ignore
}


@dataclass(frozen=True)
class SimParams:
    """Everything the loop needs besides data; build with :func:`make_params`."""

    rules: MarketRules
    costs: CostModel
    unfilled_buy: Literal["cancel", "carry"]
    unfilled_sell: Literal["carry", "cancel"]
    max_carry: int
    mode: Mode
    lots: bool
    odd_lots: bool
    capital: float
    proceeds_offset: int


def make_params(
    cfg: AppConfig,
    mode: Mode,
    capital_vnd: float | None = None,
    lots: bool = True,
    odd_lots: bool = True,
) -> SimParams:
    """Resolve config into loop parameters.

    ``ideal``: fractional shares, ``engine.ideal_capital_vnd``, no proceeds delay.
    ``executable``: ``capital_vnd`` (required), ``lots`` / ``odd_lots`` as given, and the
    configured ``cash_proceeds_offset``.
    """
    rules = MarketRules.from_config(cfg)
    costs = CostModel.from_config(cfg)
    eng = cfg.engine
    if mode == "ideal":
        return SimParams(
            rules, costs, eng.unfilled_buy, eng.unfilled_sell, eng.max_carry_sessions, mode,
            False, False, eng.ideal_capital_vnd, 0,
        )  # fmt: skip
    if capital_vnd is None or capital_vnd <= 0:
        raise ValueError("executable mode needs a positive capital_vnd")
    return SimParams(
        rules, costs, eng.unfilled_buy, eng.unfilled_sell, eng.max_carry_sessions, mode,
        lots, odd_lots, float(capital_vnd), rules.proceeds_offset,
    )  # fmt: skip


class _Bar(NamedTuple):
    open: float
    close: float
    ceiling: float
    floor: float


@dataclass(frozen=True)
class _Action:
    ex_date: date
    ticker: str
    kind: Literal["cash", "stock"]
    value: float
    pay_date: date | None
    listing_date: date | None


@dataclass(frozen=True)
class SimResult:
    returns: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    order_events: pd.DataFrame
    equity: pd.DataFrame

    def frames(self) -> dict[str, pd.DataFrame]:
        return {
            "returns": self.returns.rename("ret").reset_index(),
            "positions": self.positions,
            "trades": self.trades,
            "order_events": self.order_events,
            "equity": self.equity,
        }

    def digest(self) -> str:
        """SHA-256 over every output frame (values, columns, order)."""
        h = hashlib.sha256()
        for name, frame in self.frames().items():
            h.update(name.encode())
            h.update("|".join(map(str, frame.columns)).encode())
            h.update(frame.astype(str).to_csv(index=False).encode())
        return h.hexdigest()


def period_returns(returns: pd.Series, period_ends: Sequence[date]) -> pd.Series:
    """Compound per-session returns into periods ending on ``period_ends`` (inclusive).

    The first period starts at the first session; sessions after the last end are dropped.
    """
    out: dict[date, float] = {}
    start: date | None = None
    for end in sorted(period_ends):
        growth = 1.0
        for day, ret in zip(returns.index, returns.to_numpy(dtype=float), strict=True):
            if (start is None or day > start) and day <= end:
                growth *= 1.0 + float(ret)
        out[end] = growth - 1.0
        start = end
    return pd.Series(out, name="ret", dtype=float)


# ------------------------------------------------------------------ input validation


def _check_columns(frame: pd.DataFrame, columns: Sequence[str], name: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")


def _bars(prices: pd.DataFrame) -> dict[date, dict[str, _Bar]]:
    _check_columns(prices, PRICE_COLUMNS, "prices")
    bases = set(prices["price_basis"].unique())
    if "split_adjusted" in bases:
        raise ValueError(
            "prices contain split_adjusted rows: the engine needs raw, synthetic or "
            "exec_reconstructed prices. Reconstruct the execution series first (P1-T06, "
            "ADR-007, engine.md section 2)."
        )
    unknown = sorted(bases - set(ALLOWED_BASES))
    if unknown:
        raise ValueError(f"unknown price_basis {unknown}; allowed: {list(ALLOWED_BASES)}")
    out: dict[date, dict[str, _Bar]] = {}
    rows: list[dict[Any, Any]] = prices.sort_values(["date", "ticker"]).to_dict("records")
    for row in rows:
        day = pd.Timestamp(row["date"]).date()
        bar = _Bar(
            float(row["open"]), float(row["close"]), float(row["ceiling"]), float(row["floor"])
        )
        out.setdefault(day, {})[str(row["ticker"])] = bar
    return out


def _optional_date(value: Any) -> date | None:
    return None if pd.isna(value) else pd.Timestamp(value).date()


def _actions(actions: pd.DataFrame | None) -> list[_Action]:
    if actions is None or actions.empty:
        return []
    _check_columns(actions, ACTION_COLUMNS, "corporate_actions")
    found: list[_Action] = []
    for r in actions.to_dict("records"):
        if r["type"] not in _ACTION_KINDS:
            raise ValueError(f"unknown corporate action type {r['type']!r}")
        kind = _ACTION_KINDS[r["type"]]
        if kind is None:
            continue
        found.append(
            _Action(
                pd.Timestamp(r["ex_date"]).date(),
                str(r["ticker"]),
                kind,
                float(r["ratio_or_amount"]),
                _optional_date(r.get("pay_date")),
                _optional_date(r.get("listing_date")),
            )
        )
    return sorted(found, key=lambda a: (a.ex_date, a.ticker))


def _validate_weights(weights: pd.Series) -> None:
    if (weights < -EPS).any():
        raise ValueError("target weights must be long-only (no negatives)")
    if weights.sum() > 1 + 1e-9:
        raise ValueError(f"target weights sum to {weights.sum():.6f} > 1")


# ------------------------------------------------------------------ simulator


class Simulator:
    """Steppable event loop. Use :func:`run_simulation` for target-weight runs."""

    def __init__(
        self,
        prices: pd.DataFrame,
        corporate_actions: pd.DataFrame | None,
        calendar: TradingCalendar,
        params: SimParams,
    ) -> None:
        self.params = params
        self.calendar = calendar
        self._bars = _bars(prices)
        self.sessions = sorted(self._bars)
        bad = [d for d in self.sessions if not calendar.is_trading_day(d)]
        if bad:
            raise ValueError(f"price dates are not trading days: {bad[:3]}")
        self._actions = _actions(corporate_actions)
        self._next_action = 0
        self.ledger = Ledger(params.capital)
        self._last_close: dict[str, float] = {}
        self._pending: list[Order] = []
        self._next_id = 1
        self._events = EventLog()
        self._trades: list[tuple[Any, ...]] = []
        self._equity: list[tuple[Any, ...]] = []
        self._positions: list[tuple[Any, ...]] = []
        self._prev_equity = params.capital
        self._returns: dict[date, float] = {}

    # -- orders

    def queue(self, ticker: str, side: Side, qty: float, created: date) -> Order:
        order = Order(self._next_id, ticker, side, qty, created)
        self._next_id += 1
        self._pending.append(order)
        return order

    # -- session steps

    def open_session(self, today: date) -> list[tuple[Any, ...]]:
        """Pre-open then open: corporate actions, releases, fills. Returns today's new trades."""
        first = len(self._trades)
        self._apply_actions(today)
        self.ledger.release_cash(today)
        orders = sorted(self._pending, key=lambda o: (o.side == "buy", o.ticker, o.order_id))
        for order in orders:
            self._resolve(order, today)
        return self._trades[first:]

    def mark(self, today: date) -> None:
        for ticker, bar in self._bars[today].items():
            self._last_close[ticker] = bar.close

    def equity_now(self) -> float:
        return self.ledger.cash_available + self.ledger.cash_pending + self._positions_value()

    def record(self, today: date) -> None:
        ledger = self.ledger
        value = self._positions_value()
        equity = ledger.cash_available + ledger.cash_pending + value
        self._equity.append(
            (today, ledger.cash_available, ledger.cash_pending, self._reserved(), value, equity)
        )
        for ticker, shares in ledger.holdings().items():
            close = self._last_close[ticker]
            self._positions.append(
                (today, ticker, shares, ledger.sellable(ticker, today), close, shares * close)
            )
        self._returns[today] = equity / self._prev_equity - 1.0
        self._prev_equity = equity

    def decide(self, today: date, weights: pd.Series) -> None:
        """Turn target weights into orders for the next session (sizing on today's close)."""
        _validate_weights(weights)
        equity = self.equity_now()
        held = self.ledger.holdings()
        wanted: dict[tuple[str, Side], float] = {}
        p = self.params
        for ticker in sorted(set(weights.index.astype(str)) | set(held)):
            weight = float(weights.get(ticker, 0.0))
            price = self._last_close.get(ticker)
            if price is None:
                raise ValueError(f"no price for {ticker} at decision on {today}")
            target = target_quantity(weight * equity, price, p.rules, p.lots, p.odd_lots)
            delta = target - held.get(ticker, 0.0)
            if abs(delta) > EPS:
                wanted[(ticker, "buy" if delta > 0 else "sell")] = abs(delta)
        self._replace_pending(wanted, today)

    # -- internals

    def _positions_value(self) -> float:
        return sum(q * self._last_close[t] for t, q in self.ledger.holdings().items())

    def _reserved(self) -> float:
        c, total = self.params.costs, 0.0
        for o in self._pending:
            if o.side == "buy" and o.ticker in self._last_close:
                price = self._last_close[o.ticker] * (1 + c.slip_round)
                total += o.qty * price * (1 + c.fee_pct)
        return total

    def _replace_pending(self, wanted: dict[tuple[str, Side], float], today: date) -> None:
        """New decision supersedes pending orders; same ticker and side keep id and age."""
        old = {(o.ticker, o.side): o for o in self._pending}
        kept: list[Order] = []
        for key, qty in wanted.items():
            order = old.pop(key, None)
            if order is None:
                order = Order(self._next_id, key[0], key[1], qty, today)
                self._next_id += 1
            order.qty = qty
            kept.append(order)
        for order in old.values():
            self._events.add(order, today, "cancelled", "superseded by new decision")
        self._pending = kept

    def _apply_actions(self, today: date) -> None:
        while self._next_action < len(self._actions):
            action = self._actions[self._next_action]
            if action.ex_date > today:
                break
            self._next_action += 1
            if action.kind == "cash":
                self._cash_dividend(action)
            else:
                self._stock_dividend(action)

    def _cash_dividend(self, a: _Action) -> None:
        shares = self.ledger.shares(a.ticker)
        if shares <= EPS:
            return
        pay = a.pay_date or a.ex_date + timedelta(days=self.params.rules.dividend_lag_days)
        self.ledger.credit_pending(pay, shares * a.value)

    def _stock_dividend(self, a: _Action) -> None:
        shares = self.ledger.shares(a.ticker)
        if shares <= EPS:
            return
        new = shares * a.value
        new = float(math.floor(new + EPS)) if self.params.lots else new
        if new > EPS:
            listing = a.listing_date or after_sessions(
                self.calendar, a.ex_date, self.params.rules.listing_lag_sessions
            )
            self.ledger.add_shares(a.ticker, new, listing)
        for order in self._pending:  # pending orders were sized in pre-event shares
            if order.ticker == a.ticker:
                scaled = order.qty * (1 + a.value)
                order.qty = float(math.floor(scaled + EPS)) if self.params.lots else scaled

    def _log(self, order: Order, today: date, event: EventKind, reason: str) -> None:
        self._events.add(order, today, event, reason)

    def _drop(self, order: Order) -> None:
        self._pending = [o for o in self._pending if o is not order]

    def _unfilled(self, order: Order, today: date, reason: str) -> None:
        """Apply the lifecycle policy to the unfilled part of a blocked order."""
        p = self.params
        policy = p.unfilled_buy if order.side == "buy" else p.unfilled_sell
        if policy == "cancel":
            self._log(order, today, "cancelled", f"unfilled_{order.side}=cancel: {reason}")
            self._drop(order)
        elif order.carried >= p.max_carry:
            self._log(order, today, "stale_order", f"still blocked after {p.max_carry} sessions")
            self._drop(order)
        else:
            order.carried += 1
            self._log(order, today, "carried", f"{reason}; carry {order.carried}/{p.max_carry}")

    def _resolve(self, order: Order, today: date) -> None:
        bar = self._bars[today].get(order.ticker)
        if bar is None:
            self._unfilled(order, today, "no price for ticker (not tradable)")
        elif order.side == "sell":
            self._resolve_sell(order, today, bar)
        else:
            self._resolve_buy(order, today, bar)

    def _resolve_sell(self, order: Order, today: date, bar: _Bar) -> None:
        ledger, p = self.ledger, self.params
        qty = min(order.qty, ledger.shares(order.ticker))
        if qty <= EPS:
            self._log(order, today, "cancelled", "nothing left to sell")
            self._drop(order)
            return
        sellable = min(qty, ledger.sellable(order.ticker, today))
        if sellable <= EPS:
            when = ledger.next_sellable_date(order.ticker)
            self._log(order, today, "queued_until_sellable", f"shares sellable from {when}")
            return
        if sell_blocked_by_floor(bar.open, bar.floor):
            self._log(order, today, "blocked_floor", f"open {bar.open} <= floor {bar.floor}")
            self._unfilled(order, today, "open at floor")
            return
        pieces = sell_pieces(sellable, p.rules.round_lot, p.odd_lots, p.lots)
        if not pieces:
            self._log(order, today, "cancelled", "odd lots disabled")
            self._drop(order)
            return
        for piece in pieces:
            self._fill_sell(order, today, bar, piece)
        order.qty = qty - sum(x.qty for x in pieces)
        if order.qty <= EPS:
            self._drop(order)
        else:
            self._log(order, today, "queued_until_sellable", "remainder not yet sellable")

    def _resolve_buy(self, order: Order, today: date, bar: _Bar) -> None:
        p = self.params
        if buy_blocked_by_ceiling(bar.open, bar.ceiling):
            self._log(order, today, "blocked_ceiling", f"open {bar.open} >= ceiling {bar.ceiling}")
            self._unfilled(order, today, "open at ceiling")
            return
        pieces = plan_buy(
            self.ledger.cash_available, order.qty, bar.open, p.costs,
            p.rules.round_lot, p.rules.odd_lot_max, p.lots, p.odd_lots,
        )  # fmt: skip
        filled = sum(x.qty for x in pieces)
        for piece in pieces:
            self._fill_buy(order, today, bar, piece)
        remaining = order.qty - filled
        if remaining <= EPS:
            self._drop(order)
            return
        reason = "insufficient cash" if not p.lots or p.odd_lots else "odd lots disabled"
        wanted = order.qty
        order.qty = remaining
        self._log(order, today, "blocked_cash", f"{reason}: filled {filled} of {wanted}")
        self._unfilled(order, today, reason)

    def _fill_buy(self, order: Order, today: date, bar: _Bar, piece: Piece) -> None:
        price = self.params.costs.fill_price(bar.open, "buy", piece.lot)
        notional = piece.qty * price
        fee = self.params.costs.fee(notional)
        self.ledger.cash_available -= notional + fee
        sellable = after_sessions(self.calendar, today, self.params.rules.settle_offset)
        self.ledger.add_shares(order.ticker, piece.qty, sellable)
        self._trade(order, today, bar, piece.qty, price, fee, 0.0, piece.lot)

    def _fill_sell(self, order: Order, today: date, bar: _Bar, piece: Piece) -> None:
        costs = self.params.costs
        price = costs.fill_price(bar.open, "sell", piece.lot)
        notional = piece.qty * price
        fee, tax = costs.fee(notional), costs.tax(notional, "sell")
        self.ledger.remove_shares(order.ticker, piece.qty, today)
        net = notional - fee - tax
        release = after_sessions(self.calendar, today, self.params.proceeds_offset)
        if release <= today:
            self.ledger.cash_available += net
        else:
            self.ledger.credit_pending(release, net)
        self._trade(order, today, bar, piece.qty, price, fee, tax, piece.lot)

    def _trade(
        self, order: Order, today: date, bar: _Bar, qty: float, price: float, fee: float,
        tax: float, lot: LotType,
    ) -> None:  # fmt: skip
        slip = qty * abs(price - bar.open)
        row = (
            order.order_id, order.ticker, order.side, today, qty, price, bar.open,
            qty * price, fee, tax, slip, lot,
        )  # fmt: skip
        self._trades.append(row)

    # -- results

    def result(self) -> SimResult:
        returns = pd.Series(self._returns, name="ret", dtype=float)
        returns.index.name = "date"
        return SimResult(
            returns=returns,
            positions=pd.DataFrame(self._positions, columns=list(POSITION_COLUMNS)),
            trades=pd.DataFrame(self._trades, columns=list(TRADE_COLUMNS)),
            order_events=self._events.frame(),
            equity=pd.DataFrame(self._equity, columns=list(EQUITY_COLUMNS)),
        )


def run_simulation(
    prices: pd.DataFrame,
    corporate_actions: pd.DataFrame | None,
    targets: Mapping[date, pd.Series],
    calendar: TradingCalendar,
    params: SimParams,
) -> SimResult:
    """Run every session in ``prices``; ``targets[d]`` is decided at the close of ``d``."""
    sim = Simulator(prices, corporate_actions, calendar, params)
    unknown = sorted(set(targets) - set(sim.sessions))
    if unknown:
        raise ValueError(f"target dates are not sessions in prices: {unknown[:3]}")
    for today in sim.sessions:
        sim.open_session(today)
        sim.mark(today)
        if today in targets:
            sim.decide(today, targets[today])
        sim.record(today)
    return sim.result()
