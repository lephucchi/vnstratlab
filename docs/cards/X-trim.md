---
id: X-trim
title: Lean tests, smaller PR CI, one-round reviews (owner decision 2026-11-26)
milestone: M1.4
release: v0.1.0
status: in-progress
branch: chore/X-trim-lean-tests
due: 2026-11-27
---

### X-trim — lean tests, smaller PR CI, one-round reviews

- Goal: make every card faster to build, check and merge, now that the framework is in place.
  Owner decision 2026-11-26: "cut redundant tests, no over-thorough checks, speed up".
- No change to any behaviour in `src/`.

#### 1. Process docs (record the owner decision, dated 2026-11-26)

- `docs/qa-gates.md`: review tiers → **full** only for engine, finance, cost or statistics
  math (simulator, risk, adjustment, metrics, lab statistics); everything else **light**
  (manager). **One round**; minor findings → follow-up issue; a second round only for an
  unfixed blocker. Real-data dry run only when data-cleaning logic changes.
- `docs/workflow.md` and `.claude/agents/worker.md`: test policy for new cards — one happy path
  per feature, the edge cases that matter, and the guard tests (no lookahead, guardrails,
  hand-computed market rules). No exhaustive parameter matrices, no duplicated cases.
- `.claude/agents/qa-reviewer.md`: one round by default, matching qa-gates.md.
- `CLAUDE.md`: manager loop step 3 → "max 1 round" (keep everything else).

#### 2. CI

- `.github/workflows/ci.yml`: on `pull_request` the test job runs **ubuntu-latest and
  windows-latest, Python 3.12** only. The full 3 OS × 3 Python matrix runs on push to
  `develop`/`main`, on a nightly `schedule`, and on `workflow_dispatch`. Implement with a
  matrix computed from the event (e.g. a small `setup` job that outputs the matrix JSON, or
  `include` lists chosen by `github.event_name`). Keep job names stable enough that
  `gh pr checks` stays readable.
- The smoke step with `vnstratlab demo --quiet` runs on one job only (ubuntu, 3.12).
- Do not touch lint, guardrails, secrets, pr-title, build or the release workflow.

#### 3. Test suite trim

- Keep untouched: `tests/test_guardrails.py`, every no-lookahead test, hand-computed market-rule
  tests (settlement, lots, ceiling/floor, fees/tax, corporate-action entitlement), determinism
  / digest tests, `tests/test_data_boundary.py`.
- Reduce: merge duplicated or near-duplicated cases, shrink parametrize lists that test the
  same branch many times, drop tests that only re-assert what another test already covers.
  Move heavy property / statistical tests (anything > ~2 s) to `@pytest.mark.slow` (they keep
  running in `stats-tests.yml`).
- Targets: local `pytest` wall time **−40 % or better**, coverage stays **≥ 80 %**.
- Report in the handoff: tests before/after, wall time before/after (same machine), coverage
  before/after, and a short list of what was removed per file.

#### Files

`docs/qa-gates.md`, `docs/workflow.md`, `CLAUDE.md`, `.claude/agents/{worker,qa-reviewer}.md`,
`.github/workflows/ci.yml`, `tests/**` (trim only), `CHANGELOG.md`, this card
(`docs/cards/X-trim.md`).

#### Acceptance criteria

1. Docs state the new tiers, one round and the test policy, dated 2026-11-26.
2. A PR run shows only the 2 test jobs (ubuntu + windows, 3.12); the workflow file shows the
   full matrix for push/schedule/dispatch.
3. `pytest` wall time −40 % or better, coverage ≥ 80 %, `ruff`, `mypy` green.
4. The kept tests listed above are unchanged (diff shows no edits to them).

#### Out of scope

Any `src/` change, new features, the Pages workflow.

#### Notes

Another worker builds P1-T27a (`vnstratlab.runs`, `serve`) in parallel; it adds new test files
— do not touch `tests/test_runs*.py` or `tests/test_serve*.py` if they appear.
