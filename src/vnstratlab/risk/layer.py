"""Risk layer between combined target weights and target quantities (engine.md section 4d).

Pure: no I/O. Every step only ever lowers a weight, so the output never exceeds what the
strategies requested (and is never negative).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from vnstratlab.config.models import Risk

log = logging.getLogger(__name__)

VOL_WINDOW = 20
TRADING_DAYS = 252
_TOL = 1e-12


@dataclass(frozen=True)
class RiskDecision:
    """Weights after the risk limits.

    ``reasons`` lists, per ticker, the steps that lowered its weight (in order). ``alert`` is
    true while the circuit breaker is active (Telegram wiring is P1-T29). ``vol_scale`` is the
    factor applied to total exposure (1.0 when vol targeting is off or not binding).
    """

    weights: pd.Series
    reasons: dict[str, list[str]] = field(default_factory=dict)
    alert: bool = False
    vol_scale: float = 1.0


class RiskLayer:
    """Sizing, caps, vol scaling and circuit breaker on target weights."""

    def __init__(self, config: Risk) -> None:
        self.config = config

    def breaker_active(self, equity: float, peak_equity: float) -> bool:
        """Circuit breaker state: ``equity <= peak * (1 - circuit_breaker_drawdown_pct)``.

        Stateless: the peak is the running maximum of equity (including the initial capital)
        kept by the caller and is never reset. The breaker re-arms (buys allowed again) as soon as
        equity is back above that threshold.
        """
        return equity <= peak_equity * (1.0 - self.config.circuit_breaker_drawdown_pct)

    def stop_price(self, entry_price: float, atr_at_entry: float) -> float:
        """ATR stop level: ``entry - atr_stop_multiple * ATR14(at entry)``."""
        return entry_price - self.config.atr_stop_multiple * atr_at_entry

    def apply(
        self,
        weights: pd.Series,
        *,
        equity: float,
        prices_close: Mapping[str, float],
        atr: Mapping[str, float],
        held: Mapping[str, float],
        peak_equity: float,
        cooldown: Collection[str] = (),
        returns_history: pd.Series | None = None,
    ) -> RiskDecision:
        """Apply the steps in order: cooldown, sizing, max weight, max positions, vol scaling,
        circuit breaker.

        ``held`` is shares per ticker; ``prices_close`` and ``atr`` (ATR14 as of the same close)
        are per ticker. A ticker without a usable ATR cannot be sized: a new entry is dropped and
        a held position is not increased. Max positions keeps the largest weights after sizing and
        the max-weight cap; ties go to the alphabetically first ticker.
        """
        if equity <= 0:
            raise ValueError("equity must be positive")
        if (weights < -_TOL).any():
            raise ValueError("target weights must be long-only (no negatives)")
        cfg = self.config
        requested = {str(t): float(w) for t, w in weights.items() if float(w) > 0.0}
        current = {
            t: q * prices_close[t] / equity for t, q in held.items() if q > 0 and t in prices_close
        }
        w = dict(requested)
        reasons: dict[str, list[str]] = {}

        def lower(ticker: str, value: float, why: str) -> None:
            if value < w[ticker] - _TOL:
                w[ticker] = max(value, 0.0)
                reasons.setdefault(ticker, []).append(why)

        for t in sorted(w):  # 1. cooldown: never increase
            if t in cooldown:
                lower(t, current.get(t, 0.0), "cooldown")
        for t in sorted(w):  # 2. sizing: risk_per_position_pct of equity at risk to the ATR stop
            if t not in prices_close:
                lower(t, 0.0, "no_price")
                continue
            a = atr.get(t, math.nan)
            if math.isnan(a):
                lower(t, current.get(t, 0.0), "no_atr")
            elif a > 0:
                cap = cfg.risk_per_position_pct * prices_close[t] / (cfg.atr_stop_multiple * a)
                lower(t, cap, "sizing")
        for t in sorted(w):  # 3. max weight per ticker
            lower(t, cfg.max_weight_per_ticker, "max_weight")
        ranked = sorted((t for t in w if w[t] > 0), key=lambda t: (-w[t], t))
        for t in ranked[cfg.max_positions :]:  # 4. max positions
            lower(t, 0.0, "max_positions")
        scale = self._vol_scale(returns_history)  # 5. vol scaling (<= 1)
        if scale < 1.0:
            for t in sorted(w):
                lower(t, w[t] * scale, "vol_scale")
        alert = self.breaker_active(equity, peak_equity)  # 6. circuit breaker
        if alert:
            log.warning("circuit breaker active: equity %.0f, peak %.0f", equity, peak_equity)
            for t in sorted(w):
                lower(t, current.get(t, 0.0), "circuit_breaker")
        out = pd.Series({t: w[t] for t in sorted(w)}, dtype=float)
        return RiskDecision(out, reasons, alert, scale)

    def _vol_scale(self, returns: pd.Series | None) -> float:
        """``min(1, target / realised)``; realised = sample std of the last 20 session returns
        x sqrt(252). 1.0 when off, with fewer than 20 returns, or when realised vol is zero."""
        target = self.config.vol_target_annual
        if target is None or returns is None or len(returns) < VOL_WINDOW:
            return 1.0
        realised = float(returns.iloc[-VOL_WINDOW:].std(ddof=1)) * math.sqrt(TRADING_DAYS)
        if not realised > 0:
            return 1.0
        return min(1.0, target / realised)
