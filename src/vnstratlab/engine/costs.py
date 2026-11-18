"""Fee, sales tax and slippage; cash-limited buy planning (engine.md section 5)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from vnstratlab.engine.rules import EPS, Side, split_lots

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

LotType = Literal["round", "odd", "fractional"]


@dataclass(frozen=True)
class CostModel:
    fee_pct: float
    tax_pct: float
    slip_round: float
    slip_odd: float

    @classmethod
    def from_config(cls, cfg: AppConfig) -> CostModel:
        c = cfg.costs
        return cls(
            c.brokerage_fee_pct, c.sales_tax_pct, c.slippage_pct.round_lot, c.slippage_pct.odd_lot
        )

    def slippage(self, lot: LotType) -> float:
        return self.slip_odd if lot == "odd" else self.slip_round

    def fill_price(self, open_price: float, side: Side, lot: LotType) -> float:
        """Buy = open x (1 + slippage); sell = open x (1 - slippage)."""
        slip = self.slippage(lot)
        return open_price * (1 + slip) if side == "buy" else open_price * (1 - slip)

    def fee(self, notional: float) -> float:
        return notional * self.fee_pct

    def tax(self, notional: float, side: Side) -> float:
        """Sales tax on sells only, whatever the profit."""
        return notional * self.tax_pct if side == "sell" else 0.0


@dataclass(frozen=True)
class Piece:
    """One fill piece: a quantity of one lot type."""

    qty: float
    lot: LotType


def _max_affordable(cash: float, unit_cost: float) -> int:
    return max(math.floor(cash / unit_cost + EPS), 0)


def sell_pieces(qty: float, round_lot: int, odd_lots: bool, lots: bool) -> list[Piece]:
    """Split a sell quantity into round and odd pieces (one fractional piece when lots off)."""
    if not lots:
        return [Piece(qty, "fractional")] if qty > EPS else []
    round_part, odd_part = split_lots(qty, round_lot, odd_lots)
    return _pieces(round_part, odd_part)


def _pieces(round_part: float, odd_part: float) -> list[Piece]:
    out: list[Piece] = []
    if round_part > 0:
        out.append(Piece(round_part, "round"))
    if odd_part > 0:
        out.append(Piece(odd_part, "odd"))
    return out


def plan_buy(
    cash: float,
    desired: float,
    open_price: float,
    costs: CostModel,
    round_lot: int,
    odd_max: int,
    lots: bool,
    odd_lots: bool,
) -> list[Piece]:
    """Largest buy not above ``desired`` that ``cash`` covers after fee and slippage.

    Round lots are filled first; leftover cash buys an odd-lot remainder (odd slippage).
    """
    fee_mult = 1 + costs.fee_pct
    if not lots:
        unit = open_price * (1 + costs.slip_round) * fee_mult
        qty = min(desired, cash / unit)
        return [Piece(qty, "fractional")] if qty > EPS else []
    want_round, _ = split_lots(desired, round_lot, True)
    lot_cost = round_lot * open_price * (1 + costs.slip_round) * fee_mult
    round_qty = min(want_round // round_lot, _max_affordable(cash, lot_cost)) * round_lot
    left = cash - round_qty * open_price * (1 + costs.slip_round) * fee_mult
    odd_qty = 0
    if odd_lots:
        unit_odd = open_price * (1 + costs.slip_odd) * fee_mult
        odd_qty = min(math.floor(desired + EPS) - round_qty, _max_affordable(left, unit_odd))
        odd_qty = max(min(odd_qty, odd_max), 0)
    return _pieces(round_qty, odd_qty)
