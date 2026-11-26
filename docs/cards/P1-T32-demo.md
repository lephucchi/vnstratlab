---
id: P1-T32
title: vnstratlab demo — offline end-to-end run on synthetic data
milestone: M1.4 Strategies
release: v0.1.0
status: in review
branch: feat/P1-T32-demo
due: 2026-12-22
---

### P1-T32 — `vnstratlab demo`: offline end-to-end run on synthetic data

- Depends on: P1-T36 (synthetic market), P1-T06 (rebuild), P1-T10 (features), P1-T11/P1-T12
  (simulator, risk layer), P1-T13…P1-T19 (registry and built-in strategies).
- Goal: one command that a new user runs right after `pip install`, with no network and no
  setup, and that goes through the whole Phase 1 pipeline on the synthetic market: ingest →
  rebuild → features → every enabled packaged trial → simulator with the risk layer → a summary
  table. It is the smoke test of the release (qa-gates.md, G3 "`vnstratlab demo` runs").
- Spec: plan §5.3; ADR-006 (synthetic first); engine.md §4, §7, §10, §11; calendar
  `decision_days`.

#### Isolation (non-negotiable)

- The demo never reads or writes the user's app home (`get_paths()` / `$APP_HOME`): no
  `market.duckdb`, no trial registry, no accepted-terms file. It works in a fresh temporary
  directory (`tempfile.TemporaryDirectory`) that is removed at the end, unless `--out DIR` is
  given (then DIR is used and must be empty or not exist).
- It builds its config from the **packaged defaults** with `data.source = synthetic` in memory.
  It does not read a user config file and does **not** change `defaults.yaml`.
- No network: no Yahoo import, no socket use. The source is `SyntheticSource` only.
- No trials are registered (synthetic runs are not lab evidence). The output says so.

#### Pipeline

1. Window: fixed and deterministic, independent of today's date: `DEMO_START = 2016-01-01`,
   `DEMO_END = 2020-12-31` (module constants in the demo module, not config). Ingest synthetic
   data from `data.synthetic.start` to `DEMO_END` so the 250-session features are warm by
   `DEMO_START`; simulate `DEMO_START … DEMO_END` only.
2. Ingest through the existing pipeline (`data.pipeline.ingest`), then `rebuild`, then
   `build_features` — same code paths as the real CLI, against the temp store. Universe = the
   packaged universe.
3. For every **enabled** packaged strategy entry × params × horizon (the same expansion as
   `load_strategies` / `lab trials --dry-run`; currently 19 trials): targets on
   `decision_days(calendar, horizon, DEMO_START, DEMO_END)` using only features with
   `date <= asof` (the strategies already go through `asof_guard`).
4. Simulate each trial with `run_simulation` in **executable** mode, capital =
   `books.<horizon>.capital_vnd`, lots on, odd lots on, with `RiskLayer(cfg.risk)`. Cooldown:
   pass `cooldown_sessions` = 5 for short and 21 for medium/long (one decision period; module
   constants, documented in the docstring). Prices / actions = the execution series the real
   pipeline produces (`load_execution_frame`).
5. Disabled entries (blocked strategies) are listed as "skipped: <reason>" and not run.

#### Metrics (new pure module)

Add `src/vnstratlab/lab/metrics.py` with pure functions over a daily return series (P1-T20
will reuse them): `total_return`, `cagr` (252 sessions per year), `ann_vol`, `sharpe`
(risk-free 0, annualised with sqrt(252); NaN when vol is 0), `max_drawdown` (negative number,
from the compounded equity curve), `avg_turnover` (mean of `SimResult.turnover` on sessions with
fills; 0 if none). Each has a hand-computed test. No other lab logic in this card.

#### Output

- First line, always: `SYNTHETIC DATA — results say nothing about the real market.`
- A table sorted by horizon then trial: `trial` (strategy id + short params), `horizon`,
  `CAGR`, `vol`, `Sharpe`, `maxDD`, `turnover`, `trades`. S17 equal-weight rows are marked
  `(benchmark)`.
- Footer: data window, number of trials run / skipped, run time, "no trials were registered",
  and where files were written (only with `--out`).
- With `--out DIR`: also `summary.csv` (one row per trial, same columns, full precision) and
  `equity/<trial_id>.csv` (date, equity). Nothing else.
- Exit code 0 on success; non-zero with a clear message if any stage fails (do not swallow).

#### CLI

`vnstratlab demo [--out DIR] [--quiet]`. Replace the `_not_implemented("P1-T32")` stub. Keep
imports lazy inside the command (CLI import time). Put the logic in
`src/vnstratlab/demo.py` (function `run_demo(out_dir: Path | None, start: date, end: date) ->
DemoReport`) so tests can call it with a short window.

#### CI

Add `vnstratlab demo --quiet` to the existing smoke step in `.github/workflows/ci.yml` (after
`vnstratlab doctor`) if it runs in under 60 s on the runner; otherwise report the time in the
handoff and leave it out.

#### Files

`src/vnstratlab/demo.py` (new), `src/vnstratlab/lab/metrics.py` (new), `src/vnstratlab/cli.py`
(demo command only), `.github/workflows/ci.yml` (smoke step only), `tests/test_demo.py` (new),
`tests/test_metrics.py` (new), `tests/test_cli.py` (demo stub test → real test),
`docs/getting-started.md` (demo section: what it does, sample output shape, the synthetic
warning), `README.md` / `README.vi.md` (only if the demo line changes), `CHANGELOG.md`, this
card.

#### Acceptance criteria

1. `run_demo` on a short window (e.g. 2017-01-01 … 2017-12-31) runs every enabled packaged
   trial and returns one result row per trial; the trial count equals the packaged dry-run count
   (19 today; the test derives it from config, not a literal).
2. **Isolation:** with `APP_HOME` pointed at a temp dir that contains a sentinel
   `market.duckdb`, the demo leaves that directory byte-for-byte unchanged (no new or modified
   files) and the trial registry there is untouched.
3. **No network:** the demo test passes with `socket.socket.connect` monkeypatched to raise,
   and `vnstratlab.data.sources.yahoo` is not imported by the run (`sys.modules` check).
4. **Deterministic:** two runs with the same window give identical `SimResult.digest()` for
   every trial and identical `summary.csv` bytes.
5. **No lookahead:** a test wraps one strategy and asserts every features frame it receives
   has `max(date) <= asof`.
6. Metrics: hand-computed tests for each function (incl. zero-vol Sharpe = NaN, max drawdown
   on a known path, CAGR on a known path).
7. `--out DIR` writes exactly `summary.csv` and `equity/*.csv` (one per trial); a non-empty
   existing DIR is refused with a non-zero exit and nothing is written.
8. Output starts with the synthetic warning line; disabled strategies appear as skipped with
   their reason.
9. CLI: `vnstratlab demo --quiet` exits 0 via `CliRunner`; the old not-implemented test is
   replaced.
10. Full `vnstratlab demo` runtime measured locally and reported in the handoff (target < 60 s).
11. `ruff check .`, `ruff format --check .`, `mypy`, `pytest` (coverage ≥ 80 %) all green;
    `tests/test_guardrails.py` unchanged and passing.

#### Out of scope

Walk-forward, DSR/PBO/SPA/MCS, lab weights and combining strategies into one book (P1-T20 …
P1-T22); the `backtest` command (P1-T20); stress tests (P1-T33); tranches of medium/long books
(paper books, P1-T24); dashboard or Telegram output; any change to `defaults.yaml`, strategy
params, simulator, risk layer or data pipeline behaviour (if a defect is found, report it in the
handoff — do not fix it here).

#### Notes

- Data window and cooldown constants are demo-only choices made by the manager; they are not
  config defaults and do not need owner approval.
- If a strategy cannot run on the synthetic universe (e.g. S04 bank pairs needs tickers that are
  missing), it must still be listed: either a result row or "skipped: <reason>" — never silently
  dropped. Report which in the handoff.
