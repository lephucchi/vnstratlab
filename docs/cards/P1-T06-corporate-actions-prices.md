---
id: P1-T06
title: Corporate actions, adjusted prices for signals, reconstructed prices for execution
milestone: M1.1 Data
release: v0.1.0
status: done
branch: feat/P1-T06-corporate-actions-prices
due: 2026-11-26
---

### P1-T06 — Corporate actions and adjusted prices (respects `price_basis`)

- Depends on: P1-T36, P1-T37, P1-T38, P1-T11 (consumer of `exec_reconstructed`)
- Branch: `feat/P1-T06-corporate-actions-prices`, from `develop`
- Spec: plan §M1.1 P1-T06 and §3 (tables); [engine.md §2 "Phase 1 data constraints"](../engine.md)
  (authoritative formulas); ADR-007 §5; [data-pipeline.md](../data-pipeline.md); gaps GAP-01,
  GAP-02, GAP-06, GAP-08 in `src/vnstratlab/data/gaps.yaml` (do not change gap content except
  the workaround text if this card changes it, then re-render).
- Goal: from `prices_daily` + `corporate_actions` build (a) `prices_adjusted` for signals and
  (b) an execution series with `price_basis = exec_reconstructed` that `run_simulation` accepts,
  so the engine can run on the stored Yahoo history.

#### Design
- **Adjusted series (signals)** — `prices_adjusted`: for `raw` / `synthetic` rows apply stock
  and cash adjustments (backward, multiplicative, standard ratio method); for `split_adjusted`
  rows **never re-apply split factors**, apply only cash-dividend adjustment. Raw rows are never
  overwritten. Store `adj_version` (or `feature_version`-style) so recompute is reproducible.
- **Execution series** (engine.md §2 formulas, verbatim):
  `F(t) = Π(1 + ratio_e)` over stored stock events with `ex_date > t`;
  `exec(t) = adjusted(t) × F(t)` for O/H/L/C, rounded to the **nearest** tick and clipped to
  [floor, ceiling]; volume ÷ `F(t)` (state the assumption; Yahoo volume scaling is an open
  question in `docs/reports/data-source-yahoo.md`); `ref(t) = round_down_to_tick(adj_close(t−1)
  × F(t))`, ceiling/floor from the HOSE rules in `config/markets/hose.yaml`. On cash ex-dates
  `ref` stays at the previous close (residual under GAP-02, documented). For `raw`/`synthetic`
  rows the execution series is the stored row unchanged.
- **Storage**: new tables in `market.duckdb`, not `prices_daily` under the same key — suggested
  `prices_adjusted` and `prices_exec` (your call; document in plan §3 table list and
  data-pipeline.md). Built by a pure function in `data/` (or `features/`-free helper) and a
  `vnstratlab data rebuild` (or as a step after `ingest`) command; rebuild is idempotent and
  deterministic.
- **Precondition check** (engine.md §2): on each stock ex-date the reconstructed open must be
  near `prev_close / (1 + ratio)`; tolerance stated and justified in the docstring (beyond normal
  daily moves). Failing tickers are flagged and **excluded from execution** until fixed; every
  exclusion is counted and reported (survivorship).
- **Bad source rows**: sessions with an error-severity DQ finding in the latest run (e.g.
  `ohlc_inconsistent`; the real Yahoo store currently has 15, e.g. high < open) are **not**
  repaired or invented: they are omitted from the execution series (engine treats them as a
  missing row = suspension semantics) and counted in the rebuild report. Never interpolate.
- **Corporate actions**: add optional `pay_date`, `listing_date` columns (plan §3; nullable,
  migration on open for existing stores). `bonus` = `stock`; `rights` stored but ignored by the
  engine. **[VERIFY]** whether Yahoo dividend amounts are split-adjusted: if the evidence
  (fixtures only) says yes, multiply by `F(ex_date)`; otherwise leave as is. Write the finding
  in `docs/reports/data-source-yahoo.md`. Do not fetch from the network in tests.
- A loader `load_execution_frame(store, tickers, start, end)` returns the frame + actions in the
  shape `run_simulation` expects (data → engine boundary stays one-way).

#### Files to create / change
- `src/vnstratlab/data/adjust.py` (new, pure), `src/vnstratlab/data/store.py` (tables,
  migration), `src/vnstratlab/data/pipeline.py` / `cli.py` (rebuild step/command),
  `src/vnstratlab/engine/loop.py` only if accepting `exec_reconstructed` needs a tweak
- Tests: `tests/test_adjust.py` (new), `tests/test_store.py`, `tests/test_cli.py`, an
  end-to-end synthetic test: synthetic `split_adjusted`-style fixture → rebuild → `run_simulation`
- `docs/engine.md` (§2 only where settled), `docs/data-pipeline.md`, `docs/plan/plan.md` §3
  table list, `src/vnstratlab/data/gaps.yaml` + `python tools/render_gaps.py` if a workaround
  text changes, `CHANGELOG.md`

#### Acceptance criteria (hand-computed; numbers in test comments)
1. Plan AC: on a synthetic fixture with a 10 % stock dividend the adjusted series has no
   artificial −9 % gap; raw rows are unchanged after rebuild (hash).
2. Cash dividend: adjusted close before the ex-date is scaled by `(P − D) / P` (hand numbers).
3. `split_adjusted` fixture with one 10 % event: `exec(t)` before the ex-date = adjusted × 1.1,
   rounded to the nearest tick; after = adjusted; `ref` on the ex-date = theoretical ex-price
   rounded down to the tick; ceiling/floor match HOSE rules (hand numbers).
4. Scale check (amended by the manager after G2 round 1): a fixture whose stored history is not
   in one scale at a stock ex-date (unrescaled history, jump above the tolerance) fails the
   `scale_discontinuity` check, the ticker is excluded, and the count appears in the rebuild
   report. A wrong but consistently applied ratio cannot be detected this way (the ratio cancels);
   this is recorded under GAP-06.
5. Bad row: a fixture row with high < open is omitted from the execution series and counted;
   no value is invented.
6. Engine accepts the execution frame: `run_simulation` on a rebuilt synthetic fixture runs and
   is deterministic (digest); `split_adjusted` input is still refused.
7. Rebuild is idempotent (running twice gives identical tables) and does not change
   `prices_daily` or `corporate_actions` content.
8. No real data in tests/fixtures; no network. `pytest && ruff check . && ruff format --check .
   && mypy` green; coverage ≥ 80 %; `python tools/render_gaps.py --check` clean.

#### Out of scope
Features (P1-T10), DQ alerting/Telegram and the adjusted-change check (P1-T08), raw-price
FileSource (gap-closing card), risk layer (P1-T12).
