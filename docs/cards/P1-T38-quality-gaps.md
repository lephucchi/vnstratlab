---
id: P1-T38
title: Data-quality checks v0, gap register and `vnstratlab data status`
milestone: M1.1 Data
release: v0.1.0
status: in-review
branch: feat/P1-T38-quality-gaps
due: 2026-11-21
---

### P1-T38 — Data-quality checks v0, gap register and `vnstratlab data status`

- Depends on: P1-T36, P1-T37, ADR-007
- Branch: `feat/P1-T38-quality-gaps`, from `feat/P1-T37-yahoo-source` (stacked)
- Goal: every ingest ends with quality checks written to `dq_results`, and the user can see the
  state of the data (stores, last runs, checks, open gaps) with one command.
- Relation to P1-T08: this card delivers the checks that work on the interim source; P1-T08 keeps
  the Telegram alert and the adjusted-change check once P1-T06 exists.

#### Files to create / change
- `src/vnstratlab/data/quality.py` (new): checks and `run_checks(store, run_id, calendar) ->
  list[DQResult]`.
- `src/vnstratlab/data/gaps.py` (new): pydantic model and loader for
  `src/vnstratlab/data/gaps.yaml` (already written by the manager; do not change its content).
- `src/vnstratlab/data/store.py`: `dq_results` table.
- `src/vnstratlab/data/pipeline.py`: run checks after each non-dry ingest; exit code.
- `src/vnstratlab/cli.py`: `data` sub-app with `status` and `gaps`; `doctor` prints the number of
  open gaps by severity.
- Tests (new): `tests/test_quality.py`, `tests/test_gaps.py`.
- `docs/data-pipeline.md` (if needed), `CHANGELOG.md`.

#### Checks (severity depends on `price_basis` / `derived_limits`)

| Check | raw / synthetic | split_adjusted or derived limits |
|---|---|---|
| `duplicate_rows` (same ticker, date, source) | error | error |
| `missing_ticker`, trailing gap (ticker has an earlier row but is behind at the end of the run range, or has none on any session) | error | warning (suspension possible) |
| `missing_ticker`, interior hole (sessions without a row before a later row of the same ticker in the range) | warning (suspension) | warning (suspension) |
| `stale_data` (latest date < last completed session) | error | error |
| `close_outside_limits` | error | warning |
| `off_tick` (price not on the tick grid) | error | warning |
| `ohlc_inconsistent` (high < max(open, close) or low > min(open, close)) | error | error |
| `zero_volume` on a session | warning | warning |
| `repeated_bar` (same close and volume as previous session) | warning | warning (GAP-07) |
| `large_move` (|close change| > 15 %) | warning | warning |

`dq_results(run_id, check, ticker, date, severity, detail)`. Sessions come from
`TradingCalendar.from_config` for configured years and from the stored sessions otherwise
(GAP-05).

#### `vnstratlab data status`
Prints, without network access:
1. stores found (`market.duckdb`, `market-synthetic.duckdb`) with kind, rows, tickers, first and
   last date per ticker (ragged starts visible, GAP-04);
2. last 5 ingest runs (source, range, rows written/changed/dropped, status);
3. checks of the last run: counts by severity and the first 10 errors;
4. open gaps by severity with `id`, `title` and `title_vi`; `--json` prints all of it as JSON.

`vnstratlab data gaps [--status open|mitigated|closed] [--json]` prints the register.

#### Acceptance criteria
1. Each check has a `synthetic_` failing fixture and a passing one; severity follows the table
   (hand-checked for one adjusted and one raw case per check where they differ).
2. An ingest whose checks produce an error exits 1 and records `status = failed_dq` in
   `ingest_runs`; warnings only → exit 0, `status = ok_with_warnings`.
3. `gaps.yaml` loads into the model; ids unique, `GAP-NN` format, sequential; every field present;
   `severity`/`status` in their enums.
4. `python tools/render_gaps.py --check` passes (docs/data-gaps.md in sync); the test calls the
   renderer and compares.
5. `data status` on an empty home prints "no data yet" hints and exits 0; on a home with a
   synthetic ingest prints the sections above; `--json` output parses.
6. `doctor` prints `gaps: N open (high H, medium M, low L)`.
7. Green `pytest && ruff check . && ruff format --check . && mypy`; no network.

#### Out of scope
Telegram alerts (P1-T08/P1-T29), adjusted-price checks (P1-T06/P1-T08), web UI.

#### Notes
CLI output English (like `doctor`); gap titles also show `title_vi`.
