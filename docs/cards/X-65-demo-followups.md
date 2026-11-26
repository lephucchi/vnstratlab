---
id: X-65
title: P1-T32 follow-ups — quiet circuit-breaker log, ASCII warning, faster demo, test gaps
milestone: M1.4
release: v0.1.0
status: in-progress
branch: fix/X-65-demo-followups
due: 2026-11-27
---

### X-65 — follow-ups from issue #65 (lean)

- Goal: remove what users see first as noise or breakage in `demo` / the Console, and make the
  demo faster, **without changing any simulation result**.

#### Changes

1. **Circuit-breaker log noise.** `vnstratlab.risk.layer` logs `circuit breaker active` at
   WARNING on every blocked decision (hundreds per demo). Log at WARNING only when the breaker
   turns **on** and when it turns **off** (the engine already records `circuit_breaker_on/off`
   risk events — reuse that state); the per-decision line becomes DEBUG. Same for any other
   per-decision repeated warning you find in a demo run log (list them in the handoff).
2. **ASCII warning line.** `WARNING_LINE` in `src/vnstratlab/demo.py` and its copies (CLI,
   docs/getting-started.md, Console static text if it shows the CLI line) use `-` instead of
   the em dash, so Windows cp1252 consoles print it correctly. Vietnamese UI text with proper
   diacritics is unaffected (that is UTF-8 in the browser).
3. **Faster demo.** `Simulator.__init__` → `_bars(prices)` is rebuilt for every trial from the
   same price frame (~0.6 s × 19). Build it once per price frame and share it (e.g. an optional
   precomputed `bars` argument or a small cache keyed by the frame object in the demo stage).
   **Every `SimResult.digest()` must be identical before and after** (one test over the
   packaged trials on a short synthetic window, comparing to digests computed with the old
   path in the same test).
4. **Test gaps from G2 (#65 items 2–3).** Isolation test plants a user `config.yaml` that would
   change the demo (e.g. `books.short.capital_vnd`) and asserts the report ignores it; a test
   that `run_demo` restores the `vnstratlab` logger level after an error; a hand-computed test
   for `lab.metrics.equity_curve`.

#### Files

`src/vnstratlab/risk/layer.py`, `src/vnstratlab/engine/loop.py` (shared bars only),
`src/vnstratlab/demo.py`, `src/vnstratlab/cli.py` (warning text only),
`src/vnstratlab/app/static/**` (only if it shows the CLI warning line), `docs/getting-started.md`,
`tests/test_demo.py`, `tests/test_metrics.py`, `tests/test_risk_layer.py` (log assertions only),
`CHANGELOG.md`, this card (`docs/cards/X-65-demo-followups.md`).

#### Acceptance criteria

1. A demo run log has the breaker warning only on on/off transitions (count drops from hundreds
   to a handful); a test asserts one WARNING per transition.
2. The warning line is pure ASCII.
3. Digests identical (test); full demo time reported before/after in the handoff.
4. The three test gaps are closed.
5. `ruff`, `mypy`, `pytest` green; guardrails unchanged; `ENGINE_VERSION` **not** bumped (no
   result changes).

#### Out of scope

Any change to fills, costs, risk decisions or strategy logic.
