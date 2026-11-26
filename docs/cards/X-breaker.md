---
id: X-breaker
title: Circuit breaker re-arms on shadow equity (R1); demo benchmark S17 without risk layer (R2)
milestone: M1.4
release: v0.1.0
status: in-progress
branch: fix/X-breaker-shadow-equity
due: 2026-11-27
---

### X-breaker — owner decisions 2026-11-26 on G3 findings R1 and R2

Source: `docs/reports/release-v0.1.0-readiness.md` on `release/v0.1.0` (C3, R1, R2).
Both are **owner decisions** (G4 question answered 2026-11-26): R1 → "shadow equity", R2 →
"benchmark without risk layer". Full G2 (engine/risk math), one round. This change goes to
`develop` and is then cherry-picked to `release/v0.1.0` before the rc tag.

#### R1 — circuit breaker re-arms on shadow equity

Problem: the breaker is stateless on actual equity (`equity <= peak × (1 − dd)`, peak never
reset). Once the book is in cash, equity is flat, so the breaker never turns off (real data: S17
short in cash ~8 years from 2018).

New rule (update docs/engine.md §7 "Circuit breaker" with this text, marked "owner decision
2026-11-26, replaces the stateless rule"):
1. **Trigger (unchanged):** at a close, if not active and `equity <= peak × (1 − dd)` with
   `peak` = running max of closing equity (starting at initial capital) → breaker **on**.
   Record `trigger_peak = peak`.
2. **Shadow equity while on:** from the trigger close, track `shadow` = a frictionless,
   fractional paper book that follows the strategy's **pre-breaker target weights** (the weights
   the risk layer would have produced with the breaker ignored) on each decision day, marked at
   each close with the same price series the engine uses for marking (execution basis, close to
   close; corporate actions applied as in marking). `shadow` starts at the actual equity at the
   trigger close. No costs, no lots, no settlement — it measures whether the **strategy**
   recovered, not the book.
3. **Re-arm (off):** at a close, if active and `shadow >= trigger_peak × (1 − dd)` → breaker
   **off**, and **reset `peak` to the current actual equity** (otherwise it would re-trigger
   immediately because the cash book is still below the old threshold). Log the transition as
   today (`circuit_breaker_off`, with shadow and peak values).
4. While on, behaviour is unchanged (no weight above held weight; pending buys cancelled).
5. `ENGINE_VERSION` **bumped** (results change → new trial ids; this is expected).

#### R2 — demo benchmark is a true equal-weight book

In `demo` (and the Console results), the row labelled benchmark must be **S17 equal weight run
without the risk layer** (executable: capital, lots, odd lots, costs, T+ — but no ATR sizing,
max positions, vol scaling, stops or breaker). The packaged S17 trials keep running with the
risk layer like every other trial and lose the "(benchmark)" label. Implementation: one extra
demo row `S17_equal_weight (benchmark, no risk layer)` per horizon present, computed with
`risk=None`; it is **not** a trial (not registered, not counted), and the output footer says so.
Console results already tag benchmark rows by label — keep the label text stable:
`benchmark` in the trial label.

#### Files

`src/vnstratlab/engine/loop.py` (breaker state, shadow book), `src/vnstratlab/risk/layer.py`
(only if the breaker check lives there), `src/vnstratlab/engine/__init__.py`
(`ENGINE_VERSION`), `src/vnstratlab/demo.py` (benchmark row), `docs/engine.md` §7,
`docs/reports/release-v0.1.0-readiness.md` is NOT edited (it is on the release branch),
`tests/test_engine_loop.py` / `tests/test_risk_layer.py` (breaker tests), `tests/test_demo.py`
(benchmark row), `CHANGELOG.md`, this card (`docs/cards/X-breaker.md`).

#### Acceptance criteria (lean, hand-computed where it matters)

1. Hand-computed scenario (3–4 tickers, ~15 sessions): price drop triggers the breaker → book
   goes to cash → prices recover → shadow crosses `trigger_peak × (1 − dd)` → breaker off at
   that exact close, `peak` reset to actual equity, buys resume at the next decision; assert
   the on/off sessions and the shadow values.
2. If prices never recover, the breaker stays on (no spurious re-arm).
3. The S17 real-data symptom cannot recur on synthetic data: a synthetic crash-and-recover
   path re-arms within the expected session.
4. Demo: benchmark row computed without risk layer holds all tickers (positions ≈ universe size,
   assert > max_positions), is not registered, footer says it is not a trial; packaged S17
   rows no longer say benchmark.
5. Determinism and the no-lookahead tests still pass; `ruff`, `mypy`, `pytest` green.
