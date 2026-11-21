---
id: P1-T06b
title: Yahoo event-scale repair, split-adjusted dividends, pre-HOSE history
milestone: M1.1 Data
release: v0.1.0
status: done
branch: feat/P1-T06b-yahoo-event-scale
due: 2026-11-21
---

### P1-T06b — Yahoo event-scale repair, split-adjusted dividends, pre-HOSE history

- Depends on: P1-T06 · issue #31
- Branch: `feat/P1-T06b-yahoo-event-scale`, from `develop` (the manager's docs commit with the
  verified Yahoo findings is already on it)
- Goal: stop losing whole tickers from the execution series because of a few out-of-scale Yahoo
  sessions, book dividends in the right share basis, and keep non-HOSE history out of execution.
  Never invent or interpolate a price; every omitted row and excluded window stays counted.

#### Evidence (owner's local store, 2026-11-19; shapes only — fixtures must be synthetic)
`data rebuild` excludes 5 of 14 tickers (`scale_discontinuity`). Three shapes:
1. **Isolated out-of-scale session** (ACB-like): the ex-date row sits at old-scale level
   (+15 % ≈ ratio), the next session returns to the prior level and stays there.
2. **Persistent step** (HDB/LPB/VIB-like): at the stored ex-date the level steps **up** by about
   the ratio and stays; there is no matching drop anywhere nearby. The stored event does not match
   a real price adjustment at that date (wrong date or not a share-count event), so applying it to
   holdings would create shares out of nothing.
3. **Pre-HOSE history** (SHB-like): many ±9–10 % opens around 2015 — impossible under the HOSE
   ±7 % band, i.e. another exchange's history under the same symbol (GAP-04).

#### Design
- `data/adjust.py` classifies each failing stock event before excluding anything:
  - **outlier row**: the ex-date session(s) deviate beyond tolerance but the first following good
    session is back within tolerance of the pre-event close in the same basis
    (`close[p] × F[j]`); at most `MAX_OUTLIER_SESSIONS = 2` consecutive sessions (module
    constant, documented). Those rows are omitted (`scale_outlier_row`), the ticker stays.
  - **persistent step**: the event is marked `suspect_event`; every execution row on or before the
    ex-date is excluded (`scale_step_before`, one exclusion row with the window and count), later
    rows stay if they pass every other check; `load_execution_frame` does not return suspect
    events as actions, so books never apply them. If the step falls inside the run window of a
    backtest, the engine simply cannot trade the ticker before it.
  - Anything else keeps today's behaviour (`scale_discontinuity`, whole ticker excluded).
- **Pre-HOSE history**: a ticker's execution series starts after its last session whose open or
  close is outside the HOSE band by more than the tick tolerance on a non-event day **and** that
  lies before a run of ≥ 60 sessions fully inside the band (constant, documented). Rows before
  that are excluded as `non_hose_history` (one exclusion row, counted). Record in GAP-04's
  workaround text (re-render with `tools/render_gaps.py`).
- **Dividends**: set `DIVIDENDS_SPLIT_ADJUSTED = True` (evidence in
  `docs/reports/data-source-yahoo.md` §5); applies to `split_adjusted` sources only.
- Nit from P1-T06: the `dq_error` exclusion detail says "finding in the latest run"; rebuild now
  recomputes over the full history — fix the wording.
- Report: `RebuildReport` and the CLI print counts per exclusion kind; still each omitted row is
  counted once.

#### Files to create / change
- `src/vnstratlab/data/adjust.py`, `src/vnstratlab/data/pipeline.py` (report, loader actions),
  `src/vnstratlab/cli.py` (report lines)
- `tests/test_adjust.py` (synthetic fixtures for each shape), `tests/test_cli.py`
- `src/vnstratlab/data/gaps.yaml` (GAP-04, GAP-06 workaround text) + re-render
  `docs/data-gaps.md`; `docs/data-pipeline.md`, `docs/engine.md` §2 (only where settled),
  `CHANGELOG.md`

#### Acceptance criteria (hand-computed; numbers in test comments)
1. Outlier row: a `split_adjusted` fixture whose ex-date row is at old scale (×1.15) and whose
   next session is back in scale → that one row omitted as `scale_outlier_row`, ticker kept, exec
   series continuous elsewhere (hand numbers).
2. Two-session outlier → both omitted; three sessions → falls back to `scale_discontinuity`.
3. Persistent step (+15 % at a stored 15 % event, no drop) → rows on/before the ex-date excluded
   as `scale_step_before` (count stated), later rows kept, the event is not returned by
   `load_execution_frame`, and `run_simulation` on the remaining window runs.
4. A genuine, correctly scaled event still passes untouched (regression).
5. Pre-HOSE: a fixture with ±9.5 % moves for 100 sessions then 80 sessions inside ±7 % → the
   first 100 sessions excluded as `non_hose_history`; a single in-band ±6.9 % day does not
   trigger it.
6. Dividends: a `split_adjusted` cash dividend of 500 followed by a 10 % stock event is booked as
   550 (500 × 1.1) in `prices_adjusted` factors and in loader actions; `raw` sources unchanged.
7. Rebuild report counts each kind once; idempotent; `prices_daily` / `corporate_actions`
   unchanged.
8. No real data, no network. `pytest && ruff check . && ruff format --check . && mypy` green;
   coverage ≥ 80 %; `python tools/render_gaps.py --check` clean.

#### Out of scope
A tick-grid ratio detector, a raw-price FileSource, P1-T05 membership, engine changes (risk
follow-ups are P1-T12b).
