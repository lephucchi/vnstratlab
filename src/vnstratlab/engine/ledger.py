"""Positions with sellable dates and cash buckets (engine.md section 8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from vnstratlab.engine.rules import EPS


@dataclass
class _Tranche:
    qty: float
    sellable_from: date


class Ledger:
    """Shares in tranches (each with the first session it may be sold) and cash buckets.

    ``cash_available`` funds buys now; ``cash_pending`` holds ``(release_date, amount)`` entries
    (sale proceeds, dividends) that move to available on their release date.
    """

    def __init__(self, cash: float) -> None:
        self.cash_available = cash
        self._pending: list[tuple[date, float]] = []
        self._tranches: dict[str, list[_Tranche]] = {}

    @property
    def cash_pending(self) -> float:
        return sum(amount for _, amount in self._pending)

    def credit_pending(self, release: date, amount: float) -> None:
        self._pending.append((release, amount))

    def release_cash(self, today: date) -> None:
        """Move entries whose release date is on or before ``today`` to available cash."""
        due = [amount for release, amount in self._pending if release <= today]
        self._pending = [(r, a) for r, a in self._pending if r > today]
        self.cash_available += sum(due)

    def add_shares(self, ticker: str, qty: float, sellable_from: date) -> None:
        self._tranches.setdefault(ticker, []).append(_Tranche(qty, sellable_from))

    def shares(self, ticker: str) -> float:
        return sum(t.qty for t in self._tranches.get(ticker, []))

    def sellable(self, ticker: str, today: date) -> float:
        return sum(t.qty for t in self._tranches.get(ticker, []) if t.sellable_from <= today)

    def next_sellable_date(self, ticker: str) -> date | None:
        dates = [t.sellable_from for t in self._tranches.get(ticker, [])]
        return min(dates) if dates else None

    def remove_shares(self, ticker: str, qty: float, today: date) -> None:
        """Sell ``qty`` from sellable tranches, earliest first. Raises if not enough."""
        if qty > self.sellable(ticker, today) + EPS:
            raise ValueError(f"cannot sell {qty} {ticker}: only sellable shares may be sold")
        left = qty
        for tranche in sorted(self._tranches.get(ticker, []), key=lambda t: t.sellable_from):
            if tranche.sellable_from > today or left <= EPS:
                continue
            take = min(tranche.qty, left)
            tranche.qty -= take
            left -= take
        self._tranches[ticker] = [t for t in self._tranches.get(ticker, []) if t.qty > EPS]

    def holdings(self) -> dict[str, float]:
        """Total shares per held ticker, sorted by ticker."""
        held = {k: self.shares(k) for k in sorted(self._tranches)}
        return {k: v for k, v in held.items() if v > EPS}
