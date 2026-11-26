---
id: P1-T20
title: Walk-forward runner and `vnstratlab backtest`
milestone: M1.5 Lab
release: v0.2.0
status: in-progress
branch: feat/P1-T20-walk-forward
due: 2026-12-01
---

### P1-T20 — walk-forward runner, OOS returns, `vnstratlab backtest`

- Depends on: P1-T11/T12 (simulator, risk), P1-T13 (trial registry), P1-T32 (demo stages,
  `lab/metrics.py`), P1-T27a (runs).
- Spec: plan P1-T20; engine.md §12 (walk-forward, trial identity, in-sample by design).
- Goal: for every **registered** trial, produce out-of-sample return series per decision
  period, ideal and executable, stored in `lab.duckdb`, and a `backtest` command / Console
  pipeline that runs and reports them. P1-T21 (DSR, PBO) and P1-T22 (gates, MCS) consume
  these series.
- Owner policy 2026-11-26: lean tests; full G2 (this is engine/lab logic), one round.

#### Rules

1. **Registered first.** A trial is run only if it is in `trial_registry`
   (`ensure_trial` → `UnregisteredTrialError` otherwise). `backtest --register` may register
   the packaged trials first (same as `vnstratlab lab register`), and says so in the output.
2. **No lookahead.** At each decision day `d` of the trial's horizon (`decision_days`), the
   strategy gets only feature rows with `date <= d` (last `lookback_sessions` sessions, same
   slicing as `demo`, which matches the `BaseStrategy` contract); orders are created at the
   close of `d` and fill at the next open (engine rule). The period return of `d` is measured
   from the close of `d` to the close of the next decision day. There are no fitted components
   among the current strategies; leave a documented hook (`purge`/`embargo` = label length)
   for S07/S16 (P1-T31) but do not implement fitting.
3. **Modes.** Run each trial in `ideal` and `executable` mode (executable: the horizon book's
   capital, lots on, odd lots on, `RiskLayer`, cooldown = one decision period in sessions, as
   in `demo`). Per-period returns via `engine.loop.period_returns`, turnover via
   `period_turnover`.
4. **Storage** (`lab.duckdb`, through the existing lab store pattern of `lab/trials.py`):
   table `oos_returns(trial_id, horizon, mode, period_end, ret, turnover, source,
   feature_version, engine_version, run_id, computed_at)`, primary key
   `(trial_id, mode, period_end, source)`. Re-running replaces that trial's rows for that
   source (idempotent). Tag each row `in_sample_by_design = period_end <
   registered_at` (engine.md §12 table).
5. **Source.** Default = the configured data source and its store (real data on the owner's
   machine); `--source synthetic` uses the synthetic store. Synthetic results are labelled
   synthetic everywhere.
6. **Summary.** Per trial and mode: periods, CAGR, vol, Sharpe, max DD, avg turnover (reuse
   `lab/metrics.py`; convert period returns with the right periods-per-year: short 52, medium
   and long 12), split **historical (in-sample by design)** vs **forward (true OOS)**.

#### CLI and Console

- `vnstratlab backtest --strategy ID` (all registered param sets × horizons of that strategy),
  `vnstratlab backtest --all`, `--source`, `--mode ideal|executable|both` (default both),
  `--register`. Prints the summary table (Vietnamese not needed in CLI) with a data label
  (SYNTHETIC / "interim Yahoo, survivorship-biased (GAP-13)").
- New run pipeline `backtest_all` in `vnstratlab.runs.pipelines`: tasks
  `features → backtest → report` (features = rebuild check only if already built; do not
  re-ingest). It appears in the Console automatically via `/api/pipelines`; add
  `GET /api/backtest/summary?source=` returning the summary rows so a later UI card can show
  them (no UI work in this card).

#### Files

`src/vnstratlab/lab/walkforward.py` (new), `src/vnstratlab/lab/trials.py` or a new
`lab/store.py` (oos_returns table), `src/vnstratlab/demo.py` (only to share the decision-slice
helper, no behaviour change), `src/vnstratlab/runs/pipelines.py`, `src/vnstratlab/app/server.py`
(one endpoint), `src/vnstratlab/cli.py` (`backtest`), `tests/test_walkforward.py`,
`tests/test_cli.py` (backtest stub test → real), `docs/engine.md` §12 (as implemented notes),
`docs/getting-started.md` (backtest section), `CHANGELOG.md`, this card
(`docs/cards/P1-T20-walk-forward.md`).

#### Acceptance criteria (lean)

1. **Cheat test:** a test strategy that tries to read rows after `asof` either never receives
   them (assert max date ≤ asof on every call) or is rejected by `asof_guard`; and a strategy
   whose signal is tomorrow's return computed from the full frame cannot be built through the
   runner's inputs (document how).
2. Unregistered trial → error; `--register` registers then runs.
3. S17 on a synthetic window: ideal per-period returns equal the hand-computed equal-weight
   returns of the universe within 1e-9 (no costs in ideal mode); executable is lower by costs.
4. Re-run is idempotent (same rows, same values); rows carry the in-sample tag correctly
   around a given `registered_at`.
5. `backtest --all --source synthetic` runs all packaged trials and prints the table; the
   `backtest_all` pipeline runs through the runner and the endpoint returns rows.
6. `ruff`, `mypy`, `pytest` green; guardrails unchanged.

#### Out of scope

DSR/PBO (P1-T21), gates/MCS/weights (P1-T22), meta-backtest (P1-T23), stress (P1-T33),
Console UI for backtest results (later card), fitted strategies.

#### Notes

Another worker runs X-65 in parallel (risk log level, shared simulator bars, demo warning
text). Expect small merges in `cli.py`, `demo.py`, `CHANGELOG.md`.
