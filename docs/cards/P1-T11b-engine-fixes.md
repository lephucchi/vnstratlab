---
id: P1-T11b
title: Close P1-T11 review findings, synthetic trailing-suspension DQ error, CLI import time
milestone: M1.3 Engine
release: v0.1.0
status: in progress
branch: feat/P1-T11b-engine-fixes
due: 2026-11-20
---

### P1-T11b — Close P1-T11 review findings, synthetic DQ error, CLI import time

- Depends on: P1-T11 (merged with open G2 findings), P1-T38
- Branch: `feat/P1-T11b-engine-fixes`, from `develop`
- Goal: make the simulator match its own card (P1-T11 "Settled details" and "Outputs") on the
  three points the G2 review left open, stop the synthetic market from producing error-severity
  DQ findings, and bring `vnstratlab --help` back to its pre-P1-T11 speed.
- Spec source: [P1-T11 card](P1-T11-simulator-core.md) is authoritative; this card does not change
  any rule, frozen parameter or config default.

#### Findings to fix

1. **Late-action entitlement** (`engine/loop.py` `_apply_actions`, `_cash_dividend`,
   `_stock_dividend`). The card says: entitlement for an action applied late (published after its
   ex-date) uses the shares held at pre-open of the **ex-date**; shares bought after the ex-date
   get nothing; shares sold after the ex-date keep their entitlement. The code uses the shares
   held when the action is applied. Fix: record holdings at each session's pre-open (before
   actions and fills; only what is needed, e.g. per ticker, to stay cheap) and use the ex-date
   holdings. If the ex-date precedes the first simulated session, entitlement is the holdings at
   the first session's pre-open (i.e. zero at start) — state this in the docstring. For a late
   stock event, new shares are added even if the position was since sold; sellable from
   `listing_date` (or the lag), never earlier than the session the action is applied.
2. **Turnover denominator** (`Simulator.record`). Card: per session Σ|traded value| / equity at
   the **previous close** (first session: initial capital). Code divides by the same session's
   closing equity. Fix the code, the `SimResult` docstring and the hand-computed test in
   `tests/test_engine_loop.py` (around the `period_turnover` test).
3. **Pending rescale on stock events** (`_stock_dividend`). Card: only pending orders created
   **before** the ex-date scale by `1 + ratio`. The code scales every pending order of the ticker,
   which is wrong when the action is applied late (orders decided on or after the ex-date were
   sized on post-event prices). Fix: scale only orders with `created < ex_date`. Note: the
   "also when no shares are held yet" rule means the rescale must run even when `shares == 0`
   (check the early `return` in `_stock_dividend` — today it skips the rescale when nothing is
   held, which also contradicts the card).

#### Other fixes

4. **Synthetic trailing-suspension DQ error** (progress log, P1-T38 note). Ingesting the synthetic
   market can end a run range on a session where a ticker is suspended, which the
   `missing_ticker` check reports as a trailing gap with severity **error** (raw/synthetic
   basis). Real HOSE suspensions exist, so a raw source must stay strict when it gives no
   reason. Preferred fix: the synthetic source declares the sessions it suspended (it knows
   them; e.g. an optional field on the fetch result or a store table, your call — keep the
   `DataSource` protocol backward compatible) and the DQ check downgrades a trailing gap to a
   **warning** with reason "declared suspension" only for sessions the source declared. Do not
   change the severity table for undeclared gaps. Update `docs/data-pipeline.md` if the table
   needs a footnote.
5. **CLI import time** (benchmark alert on PR #23: `test_bench_cli_help` 170 → 81 iter/s).
   `vnstratlab.cli` imports pandas/duckdb/numpy at module load via `data.pipeline`,
   `data.store`, `data.quality`, etc. Move heavy imports inside the commands that need them
   (keep type hints under `TYPE_CHECKING`), so `vnstratlab --help` and `vnstratlab --version` do
   not import pandas, numpy or duckdb. Add a test (subprocess `python -X importtime` or
   `sys.modules` check in a fresh interpreter) asserting pandas and duckdb are not imported by
   `vnstratlab --help`.

#### Files to create / change
- `src/vnstratlab/engine/loop.py`, `src/vnstratlab/engine/ledger.py` (if needed)
- `src/vnstratlab/data/sources/synthetic.py`, `src/vnstratlab/data/quality.py`,
  `src/vnstratlab/data/protocol.py` / `pipeline.py` / `store.py` (only as needed for item 4)
- `src/vnstratlab/cli.py`
- Tests: `tests/test_engine_loop.py`, `tests/test_quality.py`, `tests/test_synthetic*.py`,
  a CLI import test (new or in an existing CLI test file)
- `docs/cards/P1-T11-simulator-core.md` only to tick off the follow-ups; `docs/data-pipeline.md`
  if needed; `CHANGELOG.md`

#### Acceptance criteria (hand-computed; numbers in test comments)
1. Late cash dividend: 1,000 shares held at ex-date pre-open, sold two sessions later, action
   published after the sale → receivable = 1,000 × amount. Shares bought on the session after the
   ex-date and then a late action → no receivable (existing AC10 test still passes).
2. Late stock dividend 10 %: 1,000 shares held at ex-date, action applied 2 sessions late → +100
   shares, sellable from listing date (or lag, but not before the apply session); a buy order
   created on the session after the ex-date and still pending is **not** rescaled; a buy order
   created before the ex-date and still pending **is** rescaled, also when no shares are held.
3. Turnover: hand-computed case where buys on session 1 and a sell on session 3 are divided by the
   previous close's equity (first session uses capital); the old denominator gives a different
   number in the comment.
4. Synthetic ingest over a range whose last session has a declared suspension → the
   `missing_ticker` finding is a warning ("declared suspension"), run status not failed; a raw
   frame with the same undeclared trailing gap is still an error. Property test: for ≥ 20 seeds
   and random range ends, synthetic ingest produces no error-severity DQ finding.
5. `vnstratlab --help` in a fresh interpreter imports neither `pandas` nor `duckdb` (test);
   `pytest benchmarks --benchmark-only --no-cov` runs.
6. Determinism and existing ACs of P1-T11 / P1-T38 still pass (update tests only where this card
   changes the expected number, and say which in the handoff).
7. `pytest && ruff check . && ruff format --check . && mypy` green; coverage ≥ 80 %; no network;
   `python tools/render_gaps.py --check` clean.

#### Out of scope
Risk layer (P1-T12), price reconstruction (P1-T06), `derived_limits` in `order_events`, any
change to config defaults or frozen parameters (stop and report instead).
