---
id: P1-T20b
title: Walk-forward runs every registered trial; summary per current versions; G2 minors
milestone: M1.5 Lab
release: v0.2.0
status: in-progress
branch: fix/P1-T20b-registry-trials
due: 2026-11-28
---

### P1-T20b — follow-up of P1-T20 G2 (round 1, request changes)

Must land before P1-T21. Full G2 delta not required unless a blocker remains (owner policy).

1. **[major] Trials come from the registry, not the config.** `backtest --all` /
   `--strategy ID` list the registry records for the current `feature_version` and
   `ENGINE_VERSION`, rebuild each strategy from `strategy_id` + `params_json` + `horizon`,
   and verify `strategy_code_hash` against the current module. A registered trial that cannot
   be rebuilt (unknown id, hash mismatch, invalid params) is **reported** in the output and in
   the run summary (`not_runnable: [{trial_id, reason}]`), never silently skipped. Trials in
   the config but not registered → error unless `--register`. Fix the CLI help text.
   Test: register S17 short+medium, drop medium from the config, `backtest --all` still
   produces medium rows.
2. **[minor]** `load_summary` and `GET /api/backtest/summary` show only rows whose trial ids
   belong to the current `feature_version` / `ENGINE_VERSION` (filter via the registry);
   older rows stay stored but are not summarised (optional `?all_versions=1`).
3. **[minor]** Card P1-T20 text: `period_end <= Vietnam date of registered_at`.
4. **[minor]** One test feeding a row dated after `asof` to a strategy → `LookaheadError`
   from `asof_guard`.
5. **[minor]** Document the CAGR period-count convention (a skipped decision day still counts
   one period) in the module docstring and engine.md §12.
6. Use the shared simulator bars from X-65 (`build_bars` / `bars=`) once per trial set to cut
   the `--all` runtime; report before/after.

Files: `src/vnstratlab/lab/walkforward.py`, `src/vnstratlab/lab/store.py`, `src/vnstratlab/cli.py`
(backtest only), `src/vnstratlab/app/server.py` (summary filter only),
`tests/test_walkforward.py`, `docs/engine.md` §12, `docs/cards/P1-T20-walk-forward.md`,
`CHANGELOG.md`, this card (`docs/cards/P1-T20b-registry-trials.md`).
