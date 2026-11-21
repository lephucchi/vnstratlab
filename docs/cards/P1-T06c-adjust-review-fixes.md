---
id: P1-T06c
title: Open G2 findings of P1-T06b (adjust review fixes)
milestone: M1.1 Data
release: v0.1.0
status: done
branch: feat/P1-T06c-adjust-review-fixes
due: 2026-11-24
---

### P1-T06c — open G2 findings of P1-T06b

- Depends on: P1-T06b (merged, PR #33) · issue #34. Must land before P1-T10 consumes
  `prices_adjusted` / `prices_exec`.
- Branch: `feat/P1-T06c-adjust-review-fixes`, from `develop`
- Goal: close the G2 findings of P1-T06b. Never invent or interpolate a price; every omitted row
  and excluded window stays counted.
- Files: `src/vnstratlab/data/adjust.py`, `src/vnstratlab/data/store.py` (schema),
  `src/vnstratlab/data/pipeline.py` (only if needed for `load_execution_frame` / rebuild),
  `tests/test_adjust.py` (+ a pipeline test file if needed), `docs/data-gaps.md` (GAP-04 wording),
  `docs/plan/plan.md` §3 table rows for `prices_adjusted` / `exec_exclusions` (column additions
  only), `docs/data-pipeline.md` if it documents these columns.

#### Acceptance criteria (each has a test using the exact probe numbers)
1. **[major]** `adjust.py` (~497-509): a persistent step is misclassified as a 1-row outlier (the
   outlier test runs first; with ratio r = 10 % a normal -2 % next day counts as "back in
   scale"), so the suspect event is applied (shares from nothing) and the next exec close is
   clipped. Fix: classify as "back in scale" only if (a) the following session's open is nearer
   the old (pre-event) level than the stepped level, (b) it breaks continuity with the last
   outlier close, and (c) the tolerance bands do not overlap (r > 2 x tol); otherwise it is a
   persistent step / `scale_discontinuity` as appropriate. **Probe A:** closes 50,000 x3, 55,000
   on the ex-date of a 10 % stock event, then 53,900 x6 must be classified persistent step
   (`scale_step_before`, not applied as an action), not an outlier row; no clipped exec close.
2. **[major]** `adjust.py` (~412-438): the pre-HOSE cut is placed at the LAST out-of-band session
   that is followed by >= 60 in-band sessions (card P1-T06b wording), not at the start of the
   first 60-session calm run. **Probe E:** 100 sessions of wild +-9.5 % moves, 60 calm, 50 wild,
   80 calm: exactly 210 rows excluded as non-HOSE history.
3. Cash-dividend ex-dates are exempt from the band test (the reference price drops by the
   dividend). **Probe F:** 30,000 x5 then 27,000 x115 with a 3,000 cash dividend on the step
   date: nothing excluded.
4. End-to-end test through `rebuild` + `load_execution_frame`: a 500 cash dividend before a
   non-suspect 10 % stock event comes out as 550 per post-event share basis (split-adjusted
   dividend).
5. Nits: drop "([VERIFY])" in the `execution_actions` docstring; docs GAP-04 wording "up to and
   including"; store `Exclusion.rows` (row count) in `exec_exclusions` (new column, schema
   migration safe for existing stores).
6. Add boolean column `signal_ok` to `prices_adjusted`: false for rows that are
   `scale_outlier_row`, `dq_error`, inside a `scale_step_before` window, or non-HOSE history; true
   otherwise. Document that features (P1-T10) treat false as missing. Existing stores get the
   column on rebuild.

#### Out of scope
Feature store, new data sources, changes to tolerance constants beyond what AC1 needs (a constant
change is an owner decision: stop and report).
