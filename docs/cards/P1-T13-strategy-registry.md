---
id: P1-T13
title: Strategy base, registry and trial log
milestone: M1.4 Strategies
release: v0.1.0
status: in progress
branch: feat/P1-T13-strategy-registry
due: 2026-11-26
---

### P1-T13 — Strategy base, registry and trial log

- Depends on: P1-T10 (features, `feature_version`), P1-T11 (engine)
- Spec: plan §5.4 (Strategy protocol), §3 (`trial_registry` in lab.duckdb), §6.4 rules 3–4 (frozen params, count every trial), Appendix A (`strategies:` config shape); docs/engine.md §12 "Trial identity" and "In-sample by design"; ADR-003 §3.
- Goal: strategies are pure classes behind one protocol, discovered by a registry from config; every (strategy, params, code, feature version, engine version) is a trial that must be registered before it can be backtested, and the total trial count is queryable for DSR.

#### Design
- `src/vnstratlab/strategies/base.py`: `Horizon = Literal["short","medium","long"]`; `Strategy` Protocol exactly as plan §5.4 (`id`, `horizons`, `params`, `target_weights(features, asof) -> pd.Series`). A small helper `validate_weights(w)` (long-only, finite, sum ≤ 1 + 1e-9, index = tickers) and `asof_guard(features, asof)` reuse — strategies receive features already clamped by `load_features(..., asof=)` and the base must also refuse rows with date > asof (raise).
- `src/vnstratlab/strategies/registry.py`: maps strategy id → class (built-ins register via a decorator in `strategies/builtin/`); `load_strategies(cfg)` reads `cfg.strategies` (Appendix A shape: `{id: {horizons: [...], params: [ {...}, ... ], enabled?: bool, reason?: str}}`), returns one instance per param set; disabled entries are skipped with their reason logged; unknown ids / bad params raise a clear config error. Config default `strategies: {}` stays empty (filled by P1-T14+) — do NOT add strategies to the packaged config.
- `strategy_code_hash(cls)`: stable hash of the class's source module (normalised line endings) so a code edit changes it.
- `ENGINE_VERSION` constant in `src/vnstratlab/engine/__init__.py` (e.g. "engine-v1"), documented: bump on any change that alters fills/ledger results.
- `trial_id = hash(strategy_id, canonical params JSON (sorted keys), strategy_code_hash, feature_version, engine_version)` per engine.md §12.
- `src/vnstratlab/lab/trials.py` (infrastructure, DuckDB): `TrialRegistry(path)` on `lab.duckdb` (`Paths.lab_db`): table `trial_registry(trial_id PK, strategy_id, params_json, horizon, strategy_code_hash, feature_version, engine_version, registered_at TIMESTAMPTZ, rationale)` — plan §3 columns plus identity parts. `register(...)` is idempotent (same trial_id → no new row, returns existing registered_at), append-only (no update/delete API), `require_registered(trial_id)` raises `UnregisteredTrialError`, `count(horizon=None)` returns the total number of distinct trials (all ever registered, never decremented), `list()`. Registration supports `--dry-run` style (`dry_run=True` computes ids, writes nothing).
- A backtest entry point guard: `lab/trials.py` exposes `ensure_trial(...)` used by the future walk-forward runner (P1-T20); for now the guard is tested directly, and the `backtest` CLI stub stays `_not_implemented("P1-T20")`.
- CLI: `vnstratlab lab trials [--horizon H]` prints the trial list and the count (read-only); `vnstratlab lab register [--dry-run]` registers every enabled (strategy, param set, horizon) from config with rationale "config". Keep the existing `lab` command working — if adding sub-commands conflicts with the existing `lab --horizon` command signature, stop and propose names instead (e.g. `vnstratlab trials list|register`).
- One trivial built-in for tests only is NOT allowed in the packaged registry; use a test-local strategy class registered in the test.

#### Files
`src/vnstratlab/strategies/{base,registry}.py`, `src/vnstratlab/strategies/builtin/__init__.py`, `src/vnstratlab/lab/trials.py`, `src/vnstratlab/engine/__init__.py`, `src/vnstratlab/config/` (schema for `strategies:` only if the loader needs it; no default changes), `src/vnstratlab/cli.py`, tests `tests/test_strategies_base.py`, `tests/test_trials.py`, `tests/test_cli.py`, `tests/test_data_boundary.py` (strategies/base + registry pure: no DuckDB/IO), docs: `docs/engine.md` §12 (pointer to the implementation), `docs/plan/plan.md` §3 row for trial_registry (identity columns), `CHANGELOG.md`.

#### Acceptance criteria
1. Running/ensuring a trial for an unregistered (strategy, params) raises `UnregisteredTrialError` (plan AC); after `register` it passes.
2. Trial count query works: registering 3 param sets across 2 strategies gives count 3; re-registering the same is idempotent (still 3); changing one param → 4; changing the strategy source (simulate via a different code hash) → new trial_id; changing feature_version or ENGINE_VERSION → new trial_id. Count never decreases.
3. trial_id is deterministic across processes and param dict key order (canonical JSON); hand-check one id in the test against a precomputed literal.
4. `validate_weights` rejects negative, NaN, sum > 1; `asof_guard` raises when any row has date > asof; a test strategy that peeks (returns weights using a row > asof) is caught.
5. `load_strategies` honours `enabled: false` (skipped with reason), rejects unknown ids and malformed params with a clear config error; empty `strategies: {}` loads nothing without error.
6. `registered_at` is stored (UTC) and returned; the registry is append-only (no API to delete/update; test that a second register does not change registered_at).
7. `lab register --dry-run` writes nothing (lab.duckdb not created/changed); `lab trials` is read-only. Guardrails test still passes (no order code).
8. `pytest && ruff check . && ruff format --check . && mypy` green; coverage ≥ 80 %.

#### Out of scope
Concrete strategies (P1-T14+), walk-forward runner and OOS returns (P1-T20), DSR/PBO (P1-T21), selection (P1-T22).
