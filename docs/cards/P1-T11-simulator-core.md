---
id: P1-T11
title: Simulator core (SimExecutor) with HOSE rules
milestone: M1.3 Engine
release: v0.1.0
status: todo
branch: feat/P1-T11-simulator-core
due: 2026-12-04
---

### P1-T11 — Simulator core (SimExecutor) with HOSE rules

- Depends on: P1-T02 (merged), P1-T36 (merged), ADR-003 (accepted in part, 2026-11-18), ADR-007
- Branch: `feat/P1-T11-simulator-core` from `develop`
- Goal: a pure, deterministic event loop that turns target weights on decision days into
  orders, fills, positions, cash and returns under HOSE rules, in ideal and executable modes,
  as specified in [engine.md](../engine.md) §2–§11 and drawn in
  [engine-architecture.html](../diagrams/engine-architecture.html) figures 2, 4, 5 and 8.

#### Files to create / change
- `src/vnstratlab/engine/` (new modules; names are suggestions, keep functions small):
  `rules.py` (ticks, limits, lots, settlement), `costs.py` (fee, tax, slippage),
  `ledger.py` (positions with sellable dates, cash buckets), `orders.py` (order model, lifecycle,
  `order_events`), `loop.py` (session loop, modes), `__init__.py` (public API).
- `src/vnstratlab/execution/base.py` (`Executor` protocol, plan §5.4) and
  `src/vnstratlab/execution/sim.py` (`SimExecutor` wrapping the core).
- `src/vnstratlab/config/defaults.yaml`: new `engine:` section (below).
- `src/vnstratlab/config/markets/hose.yaml`: new rules (below), each with a `status`.
- `src/vnstratlab/config/models.py`: models for the new keys.
- Tests (new): `tests/test_engine_rules.py`, `tests/test_engine_ledger.py`,
  `tests/test_engine_loop.py`, `tests/test_engine_properties.py`; extend
  `tests/test_data_boundary.py` so `engine/` imports no `duckdb`, `pyarrow`, `vnstratlab.data`,
  `httpx`, `socket` or file I/O helpers.
- `docs/engine.md` (only where the implementation settles an open detail), `CHANGELOG.md`.

#### New config (ADR-003 proposals 6, 7, 9, 12; owner freezes these values at merge)
```yaml
# defaults.yaml
engine:
  unfilled_buy: cancel                 # ADR-003 §7
  unfilled_sell: carry
  unsettled_sell: queue_until_sellable
  max_carry_sessions: 5
  rights_policy: ignore                # ADR-003 §6
  ideal_capital_vnd: 1.0e12            # "very large" capital for ideal mode
```
```yaml
# markets/hose.yaml, under rules:
cash_proceeds_offset: {value: 2, status: VERIFY, note: "sessions after a sell fill until proceeds can fund buys; conservative"}
cash_dividend_pay_lag_days: {value: 30, status: VERIFY, note: "fallback when corporate_actions.pay_date is missing"}
stock_dividend_listing_lag_sessions: {value: 20, status: VERIFY, note: "fallback when corporate_actions.listing_date is missing"}
```

#### Inputs (plain DataFrames; the core does no I/O)
- `prices`: `ticker, date, open, high, low, close, volume, ref_price, ceiling, floor,
  price_basis` for the sessions to simulate. Allowed `price_basis`: `raw`, `synthetic`, or
  `exec_reconstructed` (produced later by P1-T06 from `split_adjusted` rows). A frame with
  `split_adjusted` rows raises a clear error (reconstruction is P1-T06's job, ADR-007 / engine.md
  §2).
- `corporate_actions`: `ticker, ex_date, type (cash|stock), ratio_or_amount` (+ optional
  `pay_date`, `listing_date`).
- `targets`: mapping decision date → target weights (Series by ticker, long-only, sum ≤ 1).
- `calendar`: `TradingCalendar` (P1-T02); `rules`: resolved config; `mode`: `ideal` |
  `executable`; `capital_vnd`.

#### Outputs (engine.md §11)
`returns` (per session; per period helper), `positions` (session × ticker), `trades` (qty, price,
fee, tax, slippage, lot type), `order_events` (order id, ticker, side, session, event
`blocked_ceiling|blocked_floor|blocked_cash|carried|queued_until_sellable|stale_order|cancelled`,
reason), `equity` (cash_available, cash_pending, cash_reserved, positions_value, equity).

#### Acceptance criteria (hand-computed; numbers in test comments)
Costs from defaults: fee 0.15 % per side, sales tax 0.1 % on sells, slippage 0.10 % (round lot)
/ 0.30 % (odd lot); HOSE ±7 %, ticks 10 / 50 / 100 VND at < 10,000 / < 50,000 / ≥ 50,000;
settlement offset 3.
1. Settlement: buy fills Monday open; sell signal Tuesday close → the sell fills no earlier than
   Thursday open; the order is `queued_until_sellable` in between.
2. Ceiling open blocks a buy (ref 50,000; ceiling 53,500; open 53,500) → `blocked_ceiling`,
   then `cancelled` (`unfilled_buy: cancel`).
3. Floor open blocks a sell → `carried`; still blocked after 5 sessions → `stale_order`.
4. Lots: 11,000,000 VND and price 52,700 → at most 2 round lots (not 3); with odd lots on, the
   remainder is bought as an odd lot with odd-lot slippage, within available cash after costs.
5. Odd lot: target 150 shares → 100 round lot + 50 odd lot, each with its slippage.
6. Fees on both sides; sales tax on a sell at a loss (exact VND amounts).
7. Fill prices: buy = open × 1.001, sell = open × 0.999 (round lot).
8. `cash_proceeds_offset`: proceeds of a Monday sell are not usable for a buy before the offset;
   sells fill before buys within a session.
9. Cash dividend: receivable booked on the ex-date, available on `pay_date` (or ex-date +
   `cash_dividend_pay_lag_days`).
10. Stock dividend 10 % on 1,000 shares: `shares += 100` on the ex-date; the 100 new shares are
    sellable only from `listing_date` (or the lag); equity is continuous across the ex-date on a
    synthetic series (1,000 × 50,000 before ≈ 1,100 × 45,450 after, within one tick of value).
11. Limit-price helper: buy rounds down, sell rounds up: 49,973 → 49,950; 52,730 → 52,800; every
    tick band boundary tested.
12. Ideal mode: fractional shares, `ideal_capital_vnd`; property test on ≥ 20 random synthetic
    seeds: executable with lots off and capital → ideal_capital equals ideal returns to 1e-10.
13. Determinism: same inputs → identical outputs (hash of every output frame).
14. `split_adjusted` input refused with a clear message; `order_events` has a row for every
    blocked, carried, queued, stale or cancelled order.
15. Boundary: `engine/` stays pure (extended `tests/test_data_boundary.py`).
16. `pytest && ruff check . && ruff format --check . && mypy` green; coverage ≥ 80 %; no network.

#### Out of scope
Risk layer and stops (P1-T12; a stop is just a sell order here), strategies and registry
(P1-T13+), run manifest (P1-T20), prices reconstruction from `split_adjusted` (P1-T06), the
vectorised fast path (ADR-003 §2, deferred), PaperExecutor (P1-T24).

#### Notes
- Tests use the synthetic market (P1-T36) or hand-built `synthetic_*` frames only.
- Do not change existing config values; only add the keys above. Report any rule you believe is
  wrong instead of changing it ([VERIFY] items stay [VERIFY]).
