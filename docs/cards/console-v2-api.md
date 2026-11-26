# Console v2 — API contract (shared by X-console-api and X-console-ui)

All JSON, loopback guard as today; every non-GET needs header `X-Vnstratlab: 1`.
Errors: `{error: <code>, message?, problems?: ["dotted.path: reason"]}`.
Existing endpoints (P1-T27a) stay unchanged.

## Overview
- `GET /api/overview` → `{version, home, source, store: {kind, tickers, first, last, rows,
  stale_days} | null, last_runs: [run summary ×5], active_run_id | null, gaps: {high, medium,
  low}, verify_count, strategies: {registered, enabled, trials}}`

## Runs (additions)
- `POST /api/runs/{run_id}/cancel` → 202 `{run_id}`; cooperative: the current task finishes,
  remaining tasks become `skipped`, run `failed` with reason `"cancelled"`. 409 if not active.
- `POST /api/runs/{run_id}/rerun` → 202 `{run_id: <new>, pipeline}` (same pipeline; terms rule
  as `POST /api/runs`).

## Config
- `GET /api/config` → `{effective: {...}, defaults: {...}, user: {...}, editable: [field],
  file: "<home>/config.yaml", exists: bool}` where `field = {path: "books.short.capital_vnd",
  label_vi, group: "books"|"costs"|"risk"|"data"|"engine", type: "int"|"float"|"pct"|"enum"|
  "bool"|"date", min?, max?, step?, options?: [..], unit?: "VND"|"%"|"sessions",
  verify: bool, frozen_note_vi?: string, help_vi}`. Only fields in `editable` can be written.
  Include at least: books.{short,medium,long}.capital_vnd, books.medium.tranches,
  costs.brokerage_fee_pct, costs.sales_tax_pct, costs.slippage_pct.{round_lot,odd_lot},
  risk.* (all keys), data.source, project.backfill_start.
- `POST /api/config/validate` body `{changes: {path: value}}` → `{ok, problems, diff: [{path,
  from, to}]}` (no write).
- `PUT /api/config` body `{changes: {path: value}}` → `{ok, backup: "<file>.bak-<stamp>" |
  null, diff}`; validates with the real loader first; atomic write; keeps unrelated user keys
  (reuse `vnstratlab.init_wizard`). 422 with problems on invalid.
- `POST /api/config/reset` body `{paths: [..]}` → removes those overrides (back to defaults),
  same validation and backup.

## Strategies
- `GET /api/strategies` → `{strategies: [{id, name_vi, description_vi, basis, horizons_allowed,
  blocked: bool, reason?, params_schema: [{name, type, allowed?: [..], min?, max?, help_vi}],
  param_sets: [{index, params, horizons, enabled, origin: "packaged"|"user", trial_ids:
  [{horizon, trial_id, registered: bool, registered_at?}]}]}], trials_total, plugins: [{file,
  ids, error?}]}`. `params_schema` comes from a class attribute `PARAMS_SCHEMA` added to each
  built-in strategy (derive allowed values from each strategy's `validate_params`; keep them in
  sync with a test that every packaged param set validates against its schema).
- `POST /api/strategies/{id}/param-sets` body `{params, horizons}` → validates with the
  strategy's `validate_params` and horizons_allowed, appends to the user config, registers the
  new trials (`TrialRegistry`), returns `{ok, trial_ids, warning_vi}` (warning: "mỗi bộ tham số
  mới là một trial mới và làm ngưỡng Deflated Sharpe cao hơn").
- `PATCH /api/strategies/{id}/param-sets/{index}` body `{enabled}` → enable/disable (user
  override); packaged sets can only be disabled/enabled, not edited.
- `DELETE /api/strategies/{id}/param-sets/{index}` → only `origin: "user"`; removes it from the
  config; registered trials stay in the registry (append-only) and the response says so.

## Data (for charts)
- `GET /api/data/prices/{ticker}?from=&to=&series=adjusted|exec` → `{ticker, kind, dates,
  close, volume}` (≤ 3000 points, read-only, from the local store; never leaves the machine).
- `GET /api/data/quality?limit=` → recent DQ findings `{rows: [{date, ticker, check, level,
  detail}]}`.

## Built-in terminal (owner request 2026-11-26, "like dbt": UI actions and typed commands)
- `GET /api/cli/commands` → `{commands: [{path: ["data","rebuild"], help, options: [{name:
  "--from", type: "str"|"int"|"bool"|"choice", help, required, choices?: [..]}], allowed: bool,
  reason_vi?}]}` built by introspecting the Typer/Click app (no hand-kept list).
- `POST /api/cli` body `{command: "vnstratlab data rebuild --dry-run", accept_terms?: bool}`:
  - Parse with `shlex.split` (posix); a leading `vnstratlab` token is optional. Reject newlines,
    empty input, unknown commands (422 `{error:"unknown_command", suggestions}`).
  - **Only `vnstratlab` subcommands** — never a shell, never another executable. Run as
    `[sys.executable, "-m", "vnstratlab", *args]` with `shell=False`, `cwd` = app home,
    env = the current env (secrets stay in env; output is never parsed for them, but the API
    never echoes env).
  - Not allowed (422 `{error:"not_allowed", reason_vi}`): `serve` (recursive); `init` without
    `--yes` (needs a TTY); anything prompting interactively — pass `stdin=DEVNULL`.
  - `ingest` / `data` commands using a source whose terms are not accepted → 409
    `terms_required` with the notice unless `accept_terms: true`, then append
    `--accept-source-terms`.
  - It becomes a **run** of pipeline `cli` with one task `cli` (label = the command line);
    stdout+stderr stream into `cli.log` (same log/SSE endpoints); the task `summary` has
    `{command, exit_code}`; exit ≠ 0 → task failed. Same one-run-at-a-time rule (409 busy).
    Cancel (`POST /api/runs/{id}/cancel`) terminates the subprocess. Timeout 30 min.
  - Response 202 `{run_id, argv}`.
- Every UI action that starts a run also returns/shows its **equivalent CLI command**
  (`POST /api/runs` response gains `cli: "vnstratlab ..."`; `/api/pipelines` items gain `cli`).

## Deviations in the implementation (API PR #86), handled by the UI
- `pct` config values are raw fractions; the UI shows them x100 with "%".
- Fields may carry `min_exclusive`, `max_exclusive` and `nullable` (null means off; empty input sends null).
- Overview `store.tickers` is a list of strings plus `ticker_count`.
- `POST /api/strategies/{id}/param-sets` may return 409 `features_required`; success returns `index` and `backup`.
- `DELETE` of a packaged set returns 409 `packaged_set`.
- Cancel and rerun of a run that is not live return 409 `not_active`; rerun of an unknown pipeline returns 422 `not_rerunnable`.
- The terminal 202 `argv` starts with "vnstratlab".
- `backtest_all` is a pipeline (`cli`: `vnstratlab backtest --all`).
