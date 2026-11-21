---
id: P1-T06d
title: Density guard for the non-HOSE cut (hotfix of P1-T06c / PR #36)
milestone: M1.1 Data
release: v0.1.0
status: in progress
branch: fix/P1-T06d-non-hose-guard
due: 2026-11-22
---

### P1-T06d — density guard for the non-HOSE cut

- Depends on: PR #36 (merged as 0c18200) · issue #37 item 1.
- Branch: `fix/P1-T06d-non-hose-guard`, from `develop`
- Goal: after #36 a single isolated out-of-band session cut all earlier history of a ticker
  (owner store: 25,094 rows excluded, prices_exec 25,925 -> 6,223). Only an out-of-band session
  that belongs to a cluster may be a cut point.
- Files: `src/vnstratlab/data/adjust.py`, `tests/test_adjust.py`, `docs/data-pipeline.md`,
  `docs/engine.md` (section 2), `src/vnstratlab/data/gaps.yaml` (GAP-04), `docs/data-gaps.md`
  (rendered by `tools/render_gaps.py`).

#### Rule
Module constants `NON_HOSE_WINDOW = 250` and `NON_HOSE_MIN_OUT_OF_BAND = 10` (pending owner
approval). A candidate qualifies only if the trailing window of 250 good sessions ending at it
holds at least 10 out-of-band sessions. Cut = last qualifying out-of-band session followed by at
least 60 in-band sessions; none qualifies, no cut.

#### Acceptance criteria
1. Probe E still excludes exactly 210 rows.
2. 300 flat sessions at 50,000, row 200 = 60,000, no dq flag: no `non_hose_history` exclusion.
3. 5 isolated out-of-band sessions over 250 calm sessions, then 80 calm: no cut.
4. All existing tests pass.
5. Dry-run rebuild on the owner's store reported (no data committed).
