---
id: P1-T06e
title: Adjust follow-ups (issue #37 items 2, 3, 5-9)
milestone: M1.1 Data
release: v0.1.0
status: done
branch: fix/P1-T06e-adjust-followups
due: 2026-11-24
---

### P1-T06e — adjust follow-ups

- Depends on: PR #39 (merged as 7803c9a) · closes issue #37.
- Branch: `fix/P1-T06e-adjust-followups`, from `develop`
- Goal: finish the data-cleaning layer so P1-T10 can read `prices_adjusted` / `prices_exec`.
  Never invent or interpolate a price; every omitted row stays counted. Tolerance constants,
  `NON_HOSE_WINDOW = 250` and `NON_HOSE_MIN_OUT_OF_BAND = 10` do not change (owner-approved
  2026-11-21).
- Files: `src/vnstratlab/data/adjust.py`, `src/vnstratlab/data/gaps.yaml`, `docs/data-gaps.md`
  (rendered by `tools/render_gaps.py`), `docs/data-pipeline.md`, `docs/engine.md`,
  `tests/test_adjust.py`.

#### Acceptance criteria (each with a test using exact synthetic numbers)
1. (#37 item 6) An up-and-back spike counts as ONE out-of-band event in the non-HOSE cluster
   count. 5 spikes 50 sessions apart, then 80 calm: no cut. Probe E still excludes exactly 210.
2. (#37 item 7) In-band run resets only on clustered out-of-band sessions: 900 calm + 300
   sessions with an out-of-band move every 15 sessions must not cut the 900 clean sessions.
3. (#37 item 8) Regression: a cluster case where the qualifying out-of-band session is a cash
   ex-date; the exemption changes the result.
4. (#37 item 2) Near-tolerance stock-event shape (previous close 14,530.73, ex-date open 15,850,
   ratio 0.19) is handled at row/step level, not as a whole-ticker `scale_discontinuity`; Probe A
   still passes; no `r > 2 * tol` rule.
5. (#37 item 5) A row with open, high, low, close and volume identical to the previous session
   (volume > 0) is omitted from `prices_exec` (`duplicate_session`, counted) and has
   `signal_ok = false`.
6. (#37 item 9) "pending owner approval" replaced by "owner-approved 2026-11-21".
7. (#37 item 3) Document that consumers must read a rebuilt store; cheap check function for
   P1-T10; tested.
8. Dry-run rebuild on the owner's store reported (no data committed).
