---
id: P1-T27a
title: Run registry (DAG runner, per-task logs) and `vnstratlab serve` API
milestone: M1.4
release: v0.1.0
status: in-progress
branch: feat/P1-T27a-runs-serve
due: 2026-11-28
---

### P1-T27a — run registry (Airflow-like) and the `serve` API

- Depends on: P1-T32 (demo), P1-T36…T38 (ingest, rebuild, data status), P1-T10 (features).
- Goal: every pipeline the user starts — from the CLI or from the local web Console (P1-T28a)
  — is a **run** made of **tasks** in a small DAG, with a status per task and a log per task,
  stored in the app home, and served by a local FastAPI app that P1-T28a's UI calls.
- Owner decisions 2026-11-26: Console ships in v0.1.0; lean tests (one happy path + the edge
  cases that matter + guard tests); the Yahoo ingest may be started from the web only after an
  explicit terms confirmation.

#### 1. `vnstratlab.runs` (new package)

- `Task(id, label_vi, fn, upstream: tuple[str, ...])`, `Pipeline(id, label_vi, tasks)`.
  Pipelines (ids fixed, used by the UI):
  - `demo`: `ingest → rebuild → features → strategies → simulate → report` on the synthetic
    market, same logic as `vnstratlab demo` (split `demo.run_demo` into stage functions; the
    `vnstratlab demo` output and `summary.csv` stay byte-identical — one test).
  - `refresh`: `ingest → rebuild → features` on the configured source (real data).
  - `ingest`, `rebuild`, `features`: one task each.
- Runner: executes tasks in topological order in a **background thread**; one run at a time
  (a second start returns "busy"); statuses `queued | running | success | failed | skipped`
  (skipped = an upstream failed). Each task records start, end, duration, and a short
  `summary` dict (e.g. rows written, trials run).
- Logs: while a task runs, records from the `vnstratlab` logger **of that thread** go to
  `<task>.log` (format `HH:MM:SS LEVEL logger: message`). Restore logger state afterwards.
- Storage: `<home>/logs/runs/<run_id>/run.json` (+ `<task>.log`). `run_id` =
  `YYYYmmddTHHMMSS-<pipeline>-<4 hex>`. Keep the last 50 runs (delete older run folders). The
  demo pipeline writes its outputs (`summary.csv`, `equity/*.csv`) into
  `<run_dir>/demo/`; its market store stays in a temp dir as today (never the user's
  `market.duckdb`, never the trial registry).
- A run interrupted by a process exit shows as `failed` with reason "interrupted" on next load.
- CLI: `vnstratlab demo`, `ingest`, `data rebuild`, `features build` run through the runner
  in the foreground (same output as today) so they appear in the run history. Add
  `vnstratlab runs list` and `vnstratlab runs show <run_id>` (tasks, status, durations).

#### 2. `vnstratlab serve` (replace the stub)

- FastAPI + uvicorn, added to core dependencies. Imports stay lazy inside the command.
- Binds `127.0.0.1` by default; any non-loopback `--host` is refused with exit 1. `--port`
  (default 8000), `--no-open` (else open the browser at start).
- Static UI from `src/vnstratlab/app/static/` (P1-T28a builds it; this card ships a minimal
  `index.html` placeholder in Vietnamese that lists the API links).
- API (JSON):
  - `GET /api/pipelines` — ids, Vietnamese labels, tasks and edges (for drawing the DAG).
  - `GET /api/runs?limit=` — newest first; `GET /api/runs/{run_id}` — tasks with status,
    times, summary.
  - `GET /api/runs/{run_id}/tasks/{task}/log?offset=N` — text from byte offset N + new offset.
  - `GET /api/runs/{run_id}/events` — Server-Sent Events: task status changes and new log
    lines until the run ends.
  - `POST /api/runs` `{pipeline, accept_terms?: bool}` — start a run; `409` if busy; for a
    pipeline whose source needs terms (Yahoo) and that are not yet accepted: `409` with the
    `terms_notice` text unless `accept_terms` is true, then record acceptance with the
    existing `record_terms_acceptance` and start.
  - `GET /api/data/status` — the same facts as `vnstratlab data status` (stores, tickers,
    ranges, last runs, last checks), `GET /api/data/gaps` — the gap register.
  - `GET /api/results/{run_id}` — the demo `summary.csv` rows and equity series.
- POST protection: require header `X-Vnstratlab: 1` and an `Origin`/`Host` on loopback;
  otherwise `403`.
- No endpoint places, routes or confirms orders, and nothing returns secrets.
  `tests/test_guardrails.py` must pass unchanged.

#### Files

`src/vnstratlab/runs/` (new), `src/vnstratlab/demo.py` (split into stages only),
`src/vnstratlab/app/` (FastAPI app, `static/index.html` placeholder), `src/vnstratlab/cli.py`
(`serve`, `runs`, and wrapping the four commands), `pyproject.toml` (fastapi, uvicorn; mypy
overrides only if needed), `tests/test_runs.py`, `tests/test_serve.py`, `docs/getting-started.md`
(short `serve` section), `CHANGELOG.md`, this card (`docs/cards/P1-T27a-runs-serve.md`).

#### Acceptance criteria (lean)

1. A `demo` run through the runner ends with 6 tasks `success`, a log file per task, and
   `summary.csv` identical to `vnstratlab demo --out`.
2. A failing task marks its downstream tasks `skipped` and the run `failed`; the error and
   traceback are in that task's log.
3. Starting a second run while one is running returns busy (`409` on the API).
4. API happy path with `TestClient`: start `demo` (use a short window via a test hook), poll
   `GET /api/runs/{id}` to success, read a task log with offset, read results.
5. `POST /api/runs` without the header → 403; `serve --host 0.0.0.0` → exit 1.
6. Yahoo terms: `refresh` with source yahoo and no acceptance → 409 with the notice text; with
   `accept_terms: true` → acceptance recorded (network mocked; no real call in tests).
7. Retention keeps 50 runs; an interrupted run loads as failed.
8. `ruff`, `mypy`, `pytest` (coverage ≥ 80 %) green; guardrails unchanged.

#### Out of scope

The Console UI pages and animations (P1-T28a), the scheduler (P1-T30), backtest/lab
pipelines, authentication beyond loopback.

#### Notes

Another worker runs X-trim in parallel (CI and test trimming). Touch only your new test files
and the CLI tests for commands you change; expect a small CHANGELOG merge.
