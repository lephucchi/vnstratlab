"""Pure simulation engine (engine.md): HOSE rules, costs, ledger, order lifecycle, session loop.

No file, database or network I/O lives here (enforced by tests/test_data_boundary.py).
"""

from vnstratlab.engine.costs import CostModel, Piece, plan_buy
from vnstratlab.engine.ledger import Ledger
from vnstratlab.engine.loop import (
    SimParams,
    SimResult,
    Simulator,
    make_params,
    period_returns,
    period_turnover,
    run_simulation,
)
from vnstratlab.engine.orders import EventLog, Order
from vnstratlab.engine.rules import MarketRules, round_limit_price, tick_size

ENGINE_VERSION = "engine-v2"
"""engine-v2 (X-breaker): circuit breaker re-arms on shadow equity.

Part of every trial id (engine.md section 12). Bump it on any change that alters fills,
costs or ledger results, so earlier trials are not silently reused for a different engine."""

__all__ = [
    "ENGINE_VERSION",
    "CostModel",
    "EventLog",
    "Ledger",
    "MarketRules",
    "Order",
    "Piece",
    "SimParams",
    "SimResult",
    "Simulator",
    "make_params",
    "period_returns",
    "period_turnover",
    "plan_buy",
    "round_limit_price",
    "run_simulation",
    "tick_size",
]
