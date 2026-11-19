---
id: P1-T12
title: Risk layer (sizing, limits, vol scaling, stops, circuit breaker, rebalance threshold)
milestone: M1.3 Engine
release: v0.1.0
status: done
branch: feat/P1-T12-risk-layer
due: 2026-11-24
---

### P1-T12 — Risk layer

- Depends on: P1-T11, P1-T11b
- Branch: `feat/P1-T12-risk-layer`, from `develop`
- Spec: plan §M1.3 P1-T12; [engine.md](../engine.md) §4 (steps 3b, 3c, 4d, 4f), §7 (stops), §9.
  Config: `risk:` in `defaults.yaml` (values are frozen; do not change them).
- Goal: a pure risk layer between combined target weights and target quantities, plus the daily
  risk steps in the simulator loop (ATR stop on close, circuit breaker) and the rebalance
  threshold that P1-T11 left out.

#### Design (domain core, pure: no I/O, no DuckDB; `tests/test_data_boundary.py` must still pass)
- `src/vnstratlab/risk/atr.py`: `atr(high, low, close, n=14)` Wilder ATR on a per-ticker frame,
  using only rows ≤ asof (P1-T10 will reuse it; no lookahead test).
- `src/vnstratlab/risk/layer.py`: `RiskLayer(config.risk)` with
  `apply(weights, *, equity, prices_close, atr, held, peak_equity, cooldown, returns_history) ->
  RiskDecision` (weights after limits + a list of reasons per ticker). Steps, in this order:
  1. Drop tickers in stop cooldown (no re-buy; holdings kept at their current weight, never
     increased).
  2. **Sizing**: per ticker, cap weight at `risk_per_position_pct × equity / (atr_stop_multiple ×
     ATR14) × price / equity` (1 % of equity at risk to the ATR stop).
  3. **Max weight per ticker** (`max_weight_per_ticker`).
  4. **Max positions** (`max_positions`): keep the largest requested weights; ties by ticker.
  5. **Vol scaling** of total exposure when `vol_target_annual` is not null (realised vol of the
     portfolio from `returns_history`, 20-session window, annualised with √252; scale ≤ 1 only).
  6. **Circuit breaker**: when equity ≤ peak × (1 − `circuit_breaker_drawdown_pct`), no weight may
     increase above the current held weight (no new buys); sells still allowed. Report an
     `alert` flag in the decision (Telegram wiring is P1-T29; here only the flag + log).
  Invariant (property test): the output weight of each ticker is ≤ the strategy's requested
  weight, and ≥ 0; the layer never increases a weight a strategy did not request.
- Simulator (`engine/loop.py`), keep the existing API backward compatible (risk off when not
  given):
  - Close step 3b: ATR stop `entry_price − atr_stop_multiple × ATR14(at entry)` checked on each
    close → sell order for t+1; if shares are not sellable yet, the order is queued and logged
    `stop_pending_settlement` (new event kind). Stop beats a same-day rebalance; the ticker
    enters cooldown for `risk.stop_cooldown_sessions` sessions.
  - Close step 3c: circuit breaker state from running peak equity; event in `order_events` or a
    new `risk_events` output frame (your call; document it in engine.md §11).
  - Decision step 4f: skip order changes below `rebalance_threshold_pct` of the target position
    value (full exits and new entries are never skipped).
- `risk.stop_cooldown_sessions`: engine.md §7 already fixes its default as "one decision period".
  Add the key to `defaults.yaml` / models as `null` meaning "one decision period of the book's
  horizon" (sessions resolved by the caller); do not invent a number. Flag it in the handoff for
  owner confirmation.

#### Files to create / change
- `src/vnstratlab/risk/{__init__,atr,layer}.py` (new), `src/vnstratlab/engine/loop.py`,
  `src/vnstratlab/engine/orders.py` (event kind), `src/vnstratlab/config/{defaults.yaml,models.py}`
  (only `stop_cooldown_sessions`)
- Tests: `tests/test_risk_layer.py`, `tests/test_risk_atr.py` (new), `tests/test_engine_loop.py`,
  `tests/test_data_boundary.py` (add `risk/` to the pure set)
- `docs/engine.md` (§7/§11 only where settled), `CHANGELOG.md`

#### Acceptance criteria (hand-computed; numbers in test comments)
1. ATR14 on a hand-built 20-row frame matches a hand computation; truncating data after t leaves
   ATR at t unchanged.
2. Sizing: equity 100,000,000, price 50,000, ATR 1,500, multiple 2 → risk budget 1,000,000 /
   3,000 per share = 333.3 shares → weight cap 0.1667.
3. Max weight 0.35 and max positions 4 each have a test; ties are deterministic.
4. Vol scaling off when `vol_target_annual` is null; on, a hand-computed case scales exposure
   down and never up.
5. Circuit breaker: peak 100M, equity 89.9M → no weight increases, sells pass, `alert` true;
   equity back above the threshold → buys allowed again (state the re-arm rule in the docstring).
6. Property test (≥ 200 random cases): output ≤ requested, ≥ 0, sum ≤ 1.
7. Loop: stop hit on close → sell fills at next open; stop before shares are sellable →
   `stop_pending_settlement` until the T+3 session; stop and rebalance on the same day → stop
   wins and the ticker is not re-bought during cooldown.
8. Rebalance threshold: a 5 % change on a held position is skipped at 10 %; a full exit is not.
9. Existing P1-T11 / P1-T11b tests pass unchanged when no risk layer is given.
10. `pytest && ruff check . && ruff format --check . && mypy` green; coverage ≥ 80 %; no network.

#### Out of scope
Strategy combination and lab weights (P1-T13 / P1-T22), features store (P1-T10), Telegram
(P1-T29), corporate-action price reconstruction (P1-T06).
