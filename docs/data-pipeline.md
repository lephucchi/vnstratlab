# Data pipeline

The data pipeline is the only part of vnstratlab that talks to a data source. It turns a
source's responses into point-in-time tables in `market.duckdb`; everything downstream
(features, strategies, engine, lab, books) reads those tables and nothing else
([ADR-007](adr/ADR-007-yahoo-interim-source.md) §3).

## 1. Layers

```
 ┌───────────── vnstratlab.data (I/O allowed) ─────────────────────────────────────────┐
 │                                                                                     │
 │  DataSource adapters          raw snapshot            normalise         quality     │
 │  ┌───────────────┐          ┌──────────────┐       ┌────────────┐    ┌──────────┐   │
 │  │ SyntheticSource│ ──────► │ <home>/data/ │ ────► │ schema,    │ ─► │ DQ checks│   │
 │  │ YahooSource    │         │ raw/<source>/│       │ calendar,  │    │ (P1-T38) │   │
 │  │ (future: File, │         │ <run_id>.pq  │       │ price_basis│    └────┬─────┘   │
 │  │  broker API…)  │         └──────────────┘       └────────────┘         │         │
 │  └───────────────┘                                                         ▼         │
 │                                                       market.duckdb (upsert, revisions)
 └─────────────────────────────────────────────────────────────────────────┬───────────┘
                                                                           │ tables only
                     features · strategies · engine · lab · books ◄────────┘
```

| Step | Module (planned) | Card |
|---|---|---|
| `DataSource` protocol, `SourceInfo` | `vnstratlab/data/protocol.py` | P1-T36 |
| Market store: DuckDB schema, upsert, revisions | `vnstratlab/data/store.py` | P1-T36 |
| Raw snapshots (Parquet, one file per run and source) | `vnstratlab/data/raw.py` | P1-T36 |
| Synthetic market | `vnstratlab/data/sources/synthetic.py` | P1-T36 |
| Ingest orchestration (`vnstratlab ingest`) | `vnstratlab/data/pipeline.py` | P1-T36 |
| Yahoo adapter (optional extra) | `vnstratlab/data/sources/yahoo.py` | P1-T37 |
| Quality checks v0, `dq_results` | `vnstratlab/data/quality.py` | P1-T38 |
| Gap register, `vnstratlab data status` | `vnstratlab/data/gaps.py`, `gaps.yaml` | P1-T38 |

## 2. Boundary rule

- Only `vnstratlab.data` may import a source adapter or a source library (`yfinance`, ...).
- `engine`, `features`, `strategies`, `lab`, `risk`, `portfolio` never import
  `vnstratlab.data.sources`; they receive DataFrames read from the store. A test
  (`tests/test_data_boundary.py`, P1-T36) enforces this.
- A source library is imported lazily inside its adapter, so the core install works without it.

## 3. `DataSource` protocol (P1-T36)

```python
class DataSource(Protocol):
    info: SourceInfo            # name, price_basis, interim: bool, terms_url, requires_extra
    def symbols(self, universe: Sequence[str]) -> dict[str, str]: ...      # ticker -> source symbol
    def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame: ...
    def fetch_corporate_actions(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame: ...
```

`fetch_daily` returns the **source frame** (columns `ticker, date, open, high, low, close,
volume`, plus optional source columns). The pipeline, not the adapter, writes raw snapshots and
normalises. Adapters never write to the store.

## 4. Tables written

Plan §5.5 tables, with columns added by ADR-007:

| Table | Key | Columns added |
|---|---|---|
| `prices_daily` | (ticker, date, source) | `price_basis` (`raw` / `split_adjusted` / `synthetic`), `derived_limits` (bool), `run_id`, `revision` |
| `corporate_actions` | (ticker, ex_date, type, source) | `source`, `run_id` |
| `ingest_runs` | run_id | source, started_at, finished_at, tickers, rows_in, rows_written, rows_changed, rows_dropped, status (`ok`, `ok_with_warnings`, `partial`, `failed_dq`, `dq_crashed`, `error`), raw_path |
| `dq_results` | (run_id, check, ticker, date) | severity (`error` / `warning`), detail (P1-T38) |
| `prices_adjusted` | (ticker, date, source) | `adj_open` … `adj_close`, `adj_factor`, `adj_version`, `dq_error` (P1-T06), `signal_ok` (P1-T06c) |
| `prices_exec` | (ticker, date, source) | execution series: `price_basis` `exec_reconstructed` (from `split_adjusted` rows) or the stored basis, `stock_factor` (P1-T06) |
| `exec_exclusions` | (source, ticker, kind, date) | what was left out of `prices_exec`: `scale_discontinuity`, `precondition_unverifiable`, `dq_error`, `no_reference` (P1-T06), `scale_outlier_row`, `scale_step_before`, `non_hose_history` (P1-T06b); column `rows` = sessions covered by the row (P1-T06c) |

Rules: raw values are never overwritten silently; an upsert that changes a stored value
increments `revision` and is counted in `ingest_runs`. Synthetic rows are labelled
`source = synthetic`, `price_basis = synthetic` and are never mixed with a real source in one
database file (the store refuses it).

Run integrity: the run id (UTC second plus a hash of source and window) is unique. The store
is opened and validated first; an id already present in `ingest_runs`, or an existing raw
snapshot file, makes `ingest` raise `SourceError` and nothing is overwritten (retry in a later
second). Prices, corporate actions and the `ingest_runs` row are written in ONE transaction. If
it fails, the transaction rolls back (no partial rows) and a single `ingest_runs` row with
`status = "error"` is recorded; the raw snapshot is kept as evidence of what was fetched.
The store also refuses rows whose `source` name or `price_basis` disagrees with its kind.

One kind rule: a source's kind comes from its `SourceInfo`, and `kind_of_source(name)` and
`kind_of_basis(price_basis)` must agree. The synthetic source is named `synthetic` and is the
only source with `price_basis = synthetic`; any other combination is a configuration error and
`ingest` raises `SourceError` before anything is written (no raw snapshot, no run row). Every
corporate-action row's `source` is checked the same way, even when a kind is passed explicitly.

Stock events use one convention for every source: `ratio_or_amount` of a `stock` event is the
bonus fraction (0.10 = 10 new shares per 100). The Yahoo adapter converts Yahoo's split factor
(1.1) with `factor - 1`; factors of 1 or less (reverse splits) are not stored and are reported
as run warnings. Cash events hold VND per share.

## 5. Commands

```bash
vnstratlab ingest --source synthetic --from 2020-01-01 --dry-run   # print, write nothing
vnstratlab ingest --source yahoo --from 2015-01-01                  # backfill (needs [yahoo])
vnstratlab ingest                                                   # refresh to the last session
vnstratlab data rebuild [--source yahoo]                            # adjusted + execution series (offline)
vnstratlab data status                                              # stores, runs, DQ, gaps
vnstratlab data gaps                                                # gap register only
```

### Adjusted and execution series (P1-T06)

`vnstratlab data rebuild` reads `prices_daily` and `corporate_actions` of one source and
replaces that source's rows in `prices_adjusted`, `prices_exec` and `exec_exclusions` in one
transaction. It is offline, deterministic and idempotent (two runs give identical tables) and
never writes `prices_daily` or `corporate_actions`. Run it after every `ingest`; the pure
computation is `vnstratlab.data.adjust.build_series`, the engine input is
`vnstratlab.data.pipeline.load_execution_frame(store, tickers, start, end)`.

- **Adjusted (signals)**: backward ratio method. Stock events scale earlier `raw` / `synthetic`
  rows by `1 / (1 + ratio)`; `split_adjusted` rows are never scaled by a split again; a cash
  dividend `D` scales every earlier row by `1 - D / P` (`P` = close of the session before the
  ex-date, in its raw share basis). `adj_version` hashes the method and the ticker's events.
  `dq_error` marks rows with an error-level finding (kept, flagged). `signal_ok` is false for rows
  counted under `dq_error`, `scale_outlier_row`, `scale_step_before` or `non_hose_history`; features
  (P1-T10) treat a false row as missing. Existing stores get both new columns on the next open /
  rebuild.
- **Execution**: engine.md section 2 formulas. `raw` / `synthetic` rows are copied unchanged.
- **Left out, counted once, never repaired**: sessions with an error-level per-row finding
  (`dq_error`; the engine reads a missing row as a suspension), rows without a reference price
  (`no_reference`) and tickers failing the stock ex-date check (`scale_discontinuity`, or
  `precondition_unverifiable` when only bad sessions follow the event; every `split_adjusted` row of
  the ticker that is not already a `dq_error`). The command prints the counts; `exec_exclusions`
  lists them and `load_execution_frame` returns them.
- **Event-scale repair (P1-T06b)**: a failing stock ex-date is classified before a ticker is lost.
  *Outlier row*: at most `MAX_OUTLIER_SESSIONS = 2` sessions from the ex-date are out of scale and
  the next good session is back within tolerance of the previous good close: those rows are omitted
  (`scale_outlier_row`), the next session's reference is the last non-omitted close (never an
  invented price). *Persistent step*: the open steps by the stored ratio and stays: the event is
  *suspect*; every row of the ticker through the first good session on or after the ex-date is
  excluded (`scale_step_before`, one row per event with the count, dated the ex-date), later rows
  stay, and `load_execution_frame` does not return the event as an action. Otherwise the whole
  ticker is excluded as before. *Pre-HOSE history* (`non_hose_history`, GAP-04): on a
  `split_adjusted` ticker rows up to and including the last session outside the HOSE band that is
  followed by `MIN_HOSE_RUN = 60` in-band sessions are excluded, but only if that session belongs
  to a cluster: the trailing window of `NON_HOSE_WINDOW = 250` good sessions ending at it holds at
  least `NON_HOSE_MIN_OUT_OF_BAND = 10` out-of-band sessions (P1-T06d; both constants owner-approved
  2026-11-21); an up-and-back spike (the next session is out of band too and lands back within
  tolerance of the close before it) counts as ONE event; an isolated out-of-band session is never
  a cut point and no cluster means no cut; a clustered out-of-band session that is not a cut point
  resets the run of in-band sessions (one row with the count; a cash ex-date session is exempt
  from the band test). The persistent-step test also accepts an ex-date open between the old
  level and the stepped level (old level times the stored ratio), up to the tolerance past the
  stepped level (P1-T06e, e.g. a 9 % open for a 0.19 ratio); an open away from or far past it
  still excludes the ticker. *Duplicated sessions* (`duplicate_session`, GAP-07): a row whose
  open, high, low, close and volume (> 0) equal the previous stored session's is omitted from
  `prices_exec` and gets `signal_ok = false`; it is neutral for the band and scale checks. Each
  row is counted under the first of `dq_error`, `duplicate_session`, `non_hose_history`,
  `scale_outlier_row`, `scale_step_before`; the command prints one count per kind (the
  `duplicate_session` count is in `RebuildReport.duplicate_rows_omitted` and the exclusion list).
- **Consumers must read a rebuilt store (P1-T10)**: opening a store created before P1-T06c adds
  `prices_adjusted.signal_ok` with `DEFAULT TRUE`, so a migrated store that was not rebuilt looks
  clean while no row is flagged. Call `vnstratlab.data.adjust.adjusted_is_rebuilt(
  store.read_adjusted(source))` before computing features: it is `True` only when every row
  carries the current method label in `adj_version` (`ratio-v2` since P1-T06e); otherwise run
  `vnstratlab data rebuild` first. An empty table is not rebuilt.
- **Bad rows are recomputed, not read from a run**: rebuild runs the error-level per-row checks
  (`quality.check_row_rules`) over the whole stored history of the source. A later clean run,
  another source's run or a crashed run never re-admits an old bad row; a corrected row (new
  revision) is no longer omitted.
- **Scale-discontinuity check**: at each stock ex-date the first good session on or after it is
  compared with the previous good session; the stored ratios cancel, so the test is
  `|open / previous close - 1| <= 8 %` (HOSE limit + 1 %). It detects a store that is not in one
  scale (GAP-08) or a jump beyond the daily limit; it does NOT detect a wrong ratio that Yahoo
  applied consistently, reverse splits or ratios below the tolerance (GAP-06).
- **Freshness**: rebuild records the source's latest ingest run in `store_meta`
  (`rebuilt_through_run:<source>`). `load_execution_frame` logs a warning and sets
  `ExecutionFrame.stale` when a newer run of that source exists. `vnstratlab data rebuild
  --dry-run` computes and prints the report and writes nothing; a source with no stored rows is an
  error and nothing is deleted.
- **Which series feeds what (lookahead guidance)**: `prices_adjusted` is for scale-invariant
  signals only (returns, ratios, normalised indicators): a backward adjustment changes every
  earlier level whenever a new event arrives. Level and liquidity features (price level, value
  traded, lot cost) must use `prices_exec` (point-in-time, raw-like). Features are recomputed when
  `adj_version` changes and never mixed across versions.
- **Dividend amounts**: Yahoo's cash amounts are split-adjusted (verified 2026-11-19, see
  [data-source-yahoo.md §5](reports/data-source-yahoo.md)); P1-T06b multiplies them by
  `F(ex_date)` (`adjust.DIVIDENDS_SPLIT_ADJUSTED = True`).

Refresh and resume (Yahoo): `vnstratlab ingest` without `--from` starts at the earliest per-ticker
start over the universe. A ticker's start is its `data.yahoo.overlap_sessions`-th most recent
stored session (default 5; `0` = the day after its latest date) or `project.backfill_start` when
it has no rows, so a ticker that failed in a `partial` run is fetched again next time. `--to`
defaults to today in Asia/Ho_Chi_Minh.

Rescale rule: for sources with `rescale_refetch` (Yahoo), a ticker is re-fetched from
`project.backfill_start` in the same run, and its rows replaced as a whole (earlier rows get
`revision + 1`, `rescale detected, full refetch` is logged and shown in the report), when any
fetched close on a stored date differs from the stored close by more than a relative 1e-6, or the
response holds a `stock` event not yet stored. If that refetch fails the ticker is written
nowhere (no mixed scales) and counts as failed. The refetch covers `project.backfill_start` up to the later of
`--to` and the ticker's latest stored date, so rows after an explicit past `--to` are revised too.
The store is opened read-write during the (rate-limited) download, so other processes cannot open
it meanwhile. Split-adjusted OHLC is rounded to 4 decimals.

Empty answers: for sources with `empty_is_failure` (Yahoo) a ticker with no rows at all counts as
failed (`partial`) when it has no stored rows yet or the window holds a weekday after its first
stored date. Retries: every exception from the fetch function is retried with exponential
backoff, not only network errors.

Exit codes of `vnstratlab ingest`: `0` ok or ok_with_warnings, `1` error (including a missing
extra, refused terms, every ticker failing) or failed_dq, `2` usage error (bad date, unknown
source), `3` partial (some tickers failed; the others were written, failed tickers are printed with a re-run hint;
no data-quality error). Before the terms prompt
the command checks that the adapter's library is importable and, if not, exits `1` with the
install hint without asking for or storing acceptance.

## 5b. Features (P1-T10)

`vnstratlab features build [--source S] [--dry-run]` computes `features_daily` (offline) from the
rebuilt `prices_adjusted` and `prices_exec` of one source and replaces the table in one
transaction (idempotent). It stops with an error naming `vnstratlab data rebuild` when
`prices_adjusted` is empty or any row lacks the current `ADJ_METHOD` in `adj_version`
(`adjust.adjusted_is_rebuilt`); `--dry-run` reports the same error and otherwise prints the row
count, rows per ticker, the NaN share per feature group, the `sessions_in_window` note and the
runtime, writing nothing.

- **Pure core** `vnstratlab.features.compute_features(adjusted, exec_, universe, asof_dates=None,
  actions=None)`: every feature at `t` uses rows `<= t` only (trailing windows; tested by
  truncating the history, with stock events after the cut, over 24 seeds). Column groups and
  window constants live in `features/groups.py`; the module docstring of `features/core.py` has the
  exact definitions.
- **Series**: returns, ratios and normalised indicators read `prices_adjusted`; the 52-week
  distances, value traded, volume ratio and ATR-14 read `prices_exec`. Distances and the volume
  ratio are restated into the share basis of day `t` with the stock ex-date factors (`actions`), so
  a stock dividend leaves no step. ATR uses `risk.atr.atr` with the engine's ex-date factors.
- **Missing sessions**: a `prices_adjusted` row with `signal_ok = false` is missing for every
  feature (dropped before any window, no output row, no interpolation). Windows count stored good
  sessions, so window lengths are in AVAILABLE sessions, not calendar days. Real history misses
  about one session in five (GAP-07), so a 250-session window spans roughly 300 trading days; the
  dry run prints the median calendar span of 20- and 250-session windows (`sessions_in_window`).
- **Version**: `feature_version = features-v1:<hash>` of the code version, the windows and the
  sorted `(ticker, adj_version)` pairs of the input: one value for the whole build. Reading rows
  with more than one version raises (`load_features`). `load_features(store, start, end, columns,
  asof)` clamps the window to `asof` so a strategy can never receive a later row.
- **Deferred (GAP-11)**: valuation and asset-quality groups wait for P1-T07; no empty columns.
- **Universe**: today's config universe (membership plus known exits); each build logs the
  `survivorship_warning` (plan section 0) until P1-T05.

## 5a. Data-quality checks (P1-T38)

After the write transaction commits, every non-dry ingest runs the checks on the run's source
and date range and stores the findings in `dq_results` (`run_id, check, ticker, date, severity,
detail`; `ticker` is empty for dataset-wide findings). The data stays even when a check fails,
so it can be inspected. Severity follows the row's provenance: for `price_basis =
split_adjusted` or `derived_limits` rows the limit and tick checks (and `missing_ticker`, since a
suspension is possible) only warn (GAP-01, GAP-02).

| Check | raw / synthetic | split_adjusted or derived limits |
|---|---|---|
| `duplicate_rows` | error | error |
| `missing_ticker`, trailing gap | error | warning |
| `missing_ticker`, interior hole | warning (suspension) | warning (suspension) |
| `stale_data` | error | error |
| `close_outside_limits` | error | warning |
| `off_tick` | error | warning |
| `ohlc_inconsistent` | error | error |
| `zero_volume`, `repeated_bar`, `large_move` (> 15 %) | warning | warning |

Sessions are the weekdays minus every holiday listed in the config; stored sessions are never
the reference (a missing day would otherwise count as a holiday). In a year whose holiday list is
`partial` or `missing` (GAP-05) an absence may be an unlisted holiday, so `stale_data` and
`missing_ticker` only warn for sessions of such years (an error stays an error for sessions of
complete years). `stale_data` compares the newest stored date with the last completed session
(the day before a partial-bar cutoff). `missing_ticker` reports a ticker with no row on any
session of the range, and, once per ticker, an interior hole (sessions after its first stored date
without a row, before a later row of that ticker in the range). An interior hole is always a
warning (a suspension is the usual cause); only a trailing gap follows the severity table.
A source may declare the sessions it suspended on purpose (optional method
`declared_suspensions(tickers, start, end)`; only the synthetic market has one). A trailing gap
made only of declared sessions is a warning with detail "declared suspension"; a gap with any
undeclared session, and every gap of a source without the method (raw HOSE data), keeps the
table's severity.

`duplicate_rows` is defensive: the primary key (ticker, date, source) already prevents duplicates
in the store, so it only fires on a damaged file. `ohlc_inconsistent` and `close_outside_limits`
share one absolute tolerance of 1e-6.

Rescaled history: for split-adjusted or derived-limit rows dated before the ticker's last `stock`
event, `close_outside_limits` and `off_tick` give ONE summary warning per ticker and check per
run (count and date range) instead of one finding per row; rows on or after the ex-date are
reported individually, so a genuine breach after a split still shows. Findings are inserted in
one batch.

Run status after the checks (`ingest_runs.status`): any error gives `failed_dq` (exit 1, even
if tickers also failed); otherwise a `partial` run stays `partial` (exit 3, warnings are still
stored); otherwise warnings give `ok_with_warnings` (exit 0) and none gives `ok`. If the checks
themselves crash, the run is marked `dq_crashed` (the data is committed, the checks are
incomplete; exit code 1), not `error`, which means the write was rolled back. Findings and the
final status are written in one transaction. `vnstratlab data status [--json]` prints stores,
the last 5 runs, the last run's checks and the open gaps; `vnstratlab data gaps [--status ...]
[--json]` prints the register.

## 6. Running ingest on a schedule (interim)

The nightly scheduler belongs in `vnstratlab serve` (P1-T30). Until then, schedule the refresh
with the operating system, after the market data is final (suggested 18:00 Vietnam time):

```powershell
# Windows Task Scheduler, every weekday at 18:00
schtasks /Create /TN vnstratlab-ingest /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:00 `
  /TR "vnstratlab ingest --accept-source-terms"
```

```bash
# cron (Linux/macOS), Asia/Ho_Chi_Minh
0 18 * * 1-5  vnstratlab ingest --accept-source-terms >> ~/vnstratlab-ingest.log 2>&1
```

Do not run `ingest` while `serve` is running (DuckDB allows one writer).

## 7. Known gaps

The interim Yahoo source has documented gaps (raw prices, indices, HNX, holidays, ...). They
are listed in [data-gaps.md](data-gaps.md) and printed by `vnstratlab data status`.
