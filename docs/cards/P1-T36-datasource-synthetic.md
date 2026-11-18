---
id: P1-T36
title: DataSource protocol, market store and synthetic market
milestone: M1.1 Data
release: v0.1.0
status: in-review
branch: feat/P1-T36-datasource-synthetic
due: 2026-11-19
---

### P1-T36 — DataSource protocol, market store and synthetic market

- Depends on: P1-T02 (merged), ADR-006, ADR-007
- Branch: `feat/P1-T36-datasource-synthetic`, from `docs/adr-007-yahoo-interim` (stacked; that
  branch carries ADR-007, the gap register and this card)
- Goal: the separate data pipeline of [data-pipeline.md](../data-pipeline.md): the
  `DataSource` protocol, a DuckDB market store with raw snapshots and revisions, a deterministic
  synthetic market, and a working `vnstratlab ingest --source synthetic`.

#### Files to create / change
- `src/vnstratlab/data/protocol.py` (new): `SourceInfo` (frozen dataclass: `name`,
  `price_basis: Literal["raw","split_adjusted","synthetic"]`, `interim: bool`,
  `terms_url: str | None`, `requires_extra: str | None`), `DataSource` Protocol
  (`info`, `symbols`, `fetch_daily`, `fetch_corporate_actions`), `SourceError`, and a registry
  `get_source(name, cfg) -> DataSource` that imports adapters lazily.
- `src/vnstratlab/data/store.py` (new): `MarketStore` over DuckDB: schema creation (idempotent),
  `upsert_prices`, `upsert_corporate_actions`, `record_run`, read helpers
  (`read_prices(tickers, start, end)`, `latest_date(ticker)`), `store_meta` guard.
- `src/vnstratlab/data/raw.py` (new): write one Parquet snapshot per (source, run_id) under
  `<home>/data/raw/<source>/<run_id>.parquet`; read back.
- `src/vnstratlab/data/pipeline.py` (new): `ingest(cfg, paths, source, start, end, dry_run,
  clock) -> IngestReport`: fetch → raw snapshot → normalise (schema, dtypes, sort, derived
  limits when the source has none) → upsert → `ingest_runs` row.
- `src/vnstratlab/data/sources/__init__.py`, `src/vnstratlab/data/sources/synthetic.py` (new).
- `src/vnstratlab/config/defaults.yaml`: new `data:` section (below).
- `src/vnstratlab/config/models.py`: `DataConfig` models for that section.
- `src/vnstratlab/paths.py`: `market_db_for(kind)` (see store rule 4).
- `src/vnstratlab/cli.py`: implement `ingest` (`--source`, `--from`, `--to`, `--dry-run`).
- `pyproject.toml`: runtime deps `duckdb>=1.1`, `pandas>=2.2`, `pyarrow>=16`; dev
  `pandas-stubs`; mypy override `ignore_missing_imports` for `pyarrow.*` only if needed.
- Tests (new): `tests/test_data_protocol.py`, `tests/test_store.py`,
  `tests/test_synthetic.py`, `tests/test_pipeline.py`, `tests/test_data_boundary.py`.
- `docs/data-pipeline.md` (only if the implementation differs), `CHANGELOG.md` (Unreleased).

#### `data:` config section (new defaults, approved by ADR-007)
```yaml
data:
  source: synthetic            # P1-T37 changes this to yahoo
  synthetic:
    seed: 20261118
    start: 2015-01-01          # first synthetic session (also capped by --from)
    corporate_actions_per_ticker_per_year: 1.0
    suspension_probability: 0.002
```

#### Behaviour
1. **Protocol.** Adapters return a *source frame* with columns `ticker, date, open, high, low,
   close, volume` (+ optional `ref_price, ceiling, floor`), dates as `datetime.date`, prices as
   float VND, volume as int. Adapters never write files or the store.
2. **Synthetic market** (`SyntheticSource`, `info.price_basis = "synthetic"`):
   - tickers = universe membership tickers + `known_exits` (TPB), sessions from
     `TradingCalendar.from_config(cfg)` between `start` and `end` (Mon–Fri minus configured
     holidays);
   - one `numpy.random.Generator(PCG64(seed))`, regime-switching drift/volatility, a common
     bank factor plus idiosyncratic noise;
   - every price is on the HOSE tick grid (`markets/hose.yaml` `tick_sizes`) and inside
     [floor, ceiling] computed from `ref_price` with `price_limit_pct`; ceiling rounded **down**
     and floor rounded **up** to the tick; `high >= max(open, close)`, `low <= min(open, close)`;
   - `ref_price` = previous close, except on an ex-date where it is the theoretical ex-price;
   - corporate actions (cash dividend, stock dividend) generated as events with `ex_date`,
     `type`, `ratio_or_amount`; suspensions = sessions with no row for that ticker;
   - output also fills `ref_price, ceiling, floor` (so `derived_limits = false`).
3. **Store** (`market.duckdb` tables of plan §5.5 plus ADR-007 columns):
   `prices_daily(ticker, date, open, high, low, close, volume, value, ref_price, ceiling, floor,
   source, price_basis, derived_limits, run_id, revision, ingested_at)` primary key
   (ticker, date, source); `corporate_actions(ticker, ex_date, type, ratio_or_amount, source,
   run_id)`; `ingest_runs(run_id, source, started_at, finished_at, start_date, end_date,
   tickers, rows_in, rows_written, rows_changed, rows_dropped, status, raw_path)`;
   `store_meta(key, value)`.
   1. Upsert: a new key is inserted with `revision = 0`; an identical row is a no-op; a changed
      row is updated, `revision += 1`, counted in `rows_changed`.
   2. `value` = close × volume when the source has none.
   3. `run_id` = UTC timestamp + short hash of (source, start, end); deterministic given the
      injected clock.
   4. Synthetic and real data never share a file: synthetic goes to
      `<home>/data/market-synthetic.duckdb`, real sources to `<home>/data/market.duckdb`;
      `store_meta.kind` (`synthetic` | `real`) is written on creation and a mismatching write
      raises `SourceError`.
4. **Derived limits.** If a source frame has no `ref_price`, the pipeline sets ref = previous
   stored close of that ticker, ceiling/floor from the HOSE rules, `derived_limits = true`
   (GAP-02). The first session of a ticker has null limits.
5. **CLI.** `vnstratlab ingest [--source NAME] [--from DATE] [--to DATE] [--dry-run]`.
   Defaults: source from `data.source`; `--from` = day after the latest stored date, or
   `project.backfill_start` on an empty store; `--to` = today. Prints a short report (rows in,
   written, changed, dropped, path). `--dry-run` prints the head of each frame it would write
   and creates **no** file or directory. Unknown source → exit 2 with the list of sources.

#### Acceptance criteria
1. Same seed and dates → identical synthetic frames (`pd.util.hash_pandas_object` equal);
   a different seed → different frames.
2. On a 3-year synthetic run: every OHLC value is on the tick grid; every close is within
   [floor, ceiling]; high/low bound open and close; at least one cash and one stock dividend
   exist, each listed in `corporate_actions` with its date; on an ex-date `ref_price` equals the
   theoretical ex-price (hand-computed test for one cash and one stock dividend).
3. Ingest twice with the same inputs → no duplicate rows, `revision` stays 0, second run reports
   0 rows written/changed. Changing one close in the source frame (fake source) → that row has
   `revision = 1` and `rows_changed = 1`.
4. `--dry-run` writes nothing: the temp app home is still empty afterwards (test with
   `APP_HOME` in `tmp_path`).
5. Writing a real-source frame into the synthetic store (or the reverse) raises `SourceError`.
6. Derived limits: with a fake source without limits, ref/ceiling/floor are computed as in
   behaviour 4 (hand-computed case at a tick boundary, e.g. ref just under 10,000 VND).
7. `tests/test_data_boundary.py`: no module under `engine`, `features`, `strategies`, `lab`,
   `risk`, `portfolio`, `execution` imports `vnstratlab.data.sources` or any source library
   (`yfinance`); importing `vnstratlab.data` does not import `yfinance`.
8. Raw snapshot exists for each non-dry run and round-trips to the same frame.
9. `pytest && ruff check . && ruff format --check . && mypy` green; coverage ≥ 80 %.
   No network in tests.

#### Out of scope
Yahoo adapter (P1-T37); quality checks and `data status` (P1-T38); adjusted prices (P1-T06);
features; scheduler.

#### Notes
- No real prices anywhere. Fixtures for fake sources are `synthetic_*`.
- Do not change existing config values; only add the `data:` section.
- Keep functions small and typed; `mypy --strict`.
