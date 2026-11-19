# Next session — handoff (written 2026-11-19)

State of `develop` after this session: P1-T11b, P1-T06, P1-T12, P1-T12b, P1-T06b merged
(583 tests, coverage ≈ 97 %). See [progress.md](progress.md) for the per-card log.

## Do first (in this order)

1. **Issue #34 — P1-T06c**: open G2 findings of P1-T06b (merged by owner override). Two are
   major: a persistent step can be read as a 1-row outlier (suspect event applied to holdings),
   and the pre-HOSE cut uses the first 60-session run instead of the last out-of-band session.
   Also: exempt cash ex-dates, AC6 loader test, nits, and a `signal_ok` flag in
   `prices_adjusted`. A partial, **unverified** implementation is uncommitted in the local
   worktree `.claude/worktrees/agent-a2900456b70a36779` — review it before reusing; otherwise
   discard it. Workflow: worker → qa-reviewer (fresh) → manager re-runs checks → squash-merge.
2. **Re-run real data locally** after #34: `vnstratlab ingest --accept-source-terms` then
   `vnstratlab data rebuild` (check `--dry-run` first). On 2026-11-19 the rebuild excluded ACB,
   HDB, LPB, SHB, VIB (`scale_discontinuity`); P1-T06b/T06c should bring most of them back.
   Record the per-kind exclusion counts in the PR or progress log (counts only, no prices).
3. **P1-T10 — feature store v1**: card ready at
   [docs/cards/P1-T10-feature-store.md](../cards/P1-T10-feature-store.md). Create
   `feat/P1-T10-feature-store` from `develop`, open the task-card issue, delegate. Add to the card:
   features must treat `prices_adjusted.signal_ok = false` as missing (from #34).
4. Then P1-T13 (strategy base, registry, trial log) → P1-T14…T19 (strategies) → P1-T32 (`demo`),
   P1-T35 (`init`) → `release/v0.1.0` with gate G3 (target 2026-12-28).

## Decisions taken 2026-11-19 (owner: "follow best practice")

- `risk.stop_cooldown_sessions = null` (one decision period); the cooldown starts when the stop
  exit completes. Documented in engine.md §7 and `defaults.yaml`.
- Yahoo dividends and volume are split-adjusted (verified on the local store by the
  round-in-raw-basis test; method and counts in
  [data-source-yahoo.md §5](data-source-yahoo.md)). `DIVIDENDS_SPLIT_ADJUSTED = True`.
- P1-T06 AC4 is a scale-discontinuity check; a wrong but consistent ratio is undetected (GAP-06).

## Waiting on the owner

- **P1-T05**: HOSE VN30 review announcements before 2026-08 (membership history, GAP-13).
- **P1-T07 / GAP-11**: no bank-fundamentals source. Write an ADR choosing one before S10–S13.

## Housekeeping

- Local worktrees under `.claude/worktrees/` and `../vsl-t06b` can be removed
  (`git worktree list`, then `git worktree remove <path>`); each holds its own `.venv`.
- Force-push is blocked in this environment: to update a branch after `develop` moved, merge
  `origin/develop` into it instead of rebasing.
- The shared `.venv` in the main checkout is an editable install of the main checkout; when
  running tests inside another worktree use `PYTHONPATH=src`.
- Commits and PRs carry no AI attribution lines (CLAUDE.md owner rule).
