---
id: P1-T37
title: YahooSource adapter (interim Phase 1 price source)
milestone: M1.1 Data
release: v0.1.0
status: todo
branch: feat/P1-T37-yahoo-source
due: 2026-11-20
---

### P1-T37 — YahooSource adapter (interim Phase 1 price source)

- Depends on: P1-T36, ADR-007, review [data-source-yahoo.md](../reports/data-source-yahoo.md)
- Branch: `feat/P1-T37-yahoo-source`, from `feat/P1-T36-datasource-synthetic` (stacked)
- Goal: users can backfill and refresh real daily prices for the universe from Yahoo Finance
  through an optional adapter, with every ADR-007 safeguard, without CI or tests ever touching
  Yahoo.

#### Files to create / change
- `src/vnstratlab/data/sources/yahoo.py` (new): `YahooSource`.
- `src/vnstratlab/data/sources/__init__.py`, `src/vnstratlab/data/protocol.py`: register
  `yahoo` (lazy import).
- `src/vnstratlab/data/pipeline.py`: filler-row and partial-bar rules (source-agnostic hooks),
  terms notice.
- `src/vnstratlab/config/defaults.yaml`: `data.source: yahoo`; new `data.yahoo` section.
- `src/vnstratlab/config/models.py`: models for `data.yahoo`.
- `src/vnstratlab/settings.py`, `.env.example`, `src/vnstratlab/cli.py` (`doctor`,
  `ingest --accept-source-terms`): remove `VNSTOCK_API_KEY` (ADR-007 §7).
- `pyproject.toml`: extra `yahoo = ["yfinance>=1.8,<2"]`; mypy override
  `ignore_missing_imports` for `yfinance`.
- Tests (new): `tests/test_yahoo_source.py`, fixtures
  `tests/fixtures/synthetic_yahoo_*.csv` (made-up numbers in Yahoo's shape).
- Docs: `docs/getting-started.md` (install with `[yahoo]`, first backfill, notice),
  `docs/data-sources.md` (status row), `CHANGELOG.md`.
- Existing tests touching `vnstock_api_key` (`tests/test_paths_settings.py`, `tests/test_cli.py`).

#### `data.yahoo` config (new defaults, ADR-007)
```yaml
data:
  source: yahoo
  yahoo:
    symbol_suffix: ".VN"
    max_requests_per_minute: 30
    retries: 3
    backoff_seconds: 2.0
    final_after: "16:00"      # Asia/Ho_Chi_Minh; today's bar is dropped before this time
```

#### Behaviour
1. `info = SourceInfo(name="yahoo", price_basis="split_adjusted", interim=True,
   terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html", requires_extra="yahoo")`.
2. `yfinance` is imported only inside the adapter's fetch function. If it is missing,
   `ingest --source yahoo` exits 1 with: `Yahoo adapter needs: pip install "vnstratlab[yahoo]"`.
3. The fetch function is **injectable** (`YahooSource(fetch=...)`); the default calls
   `yfinance.Ticker(symbol).history(start, end + 1 day, auto_adjust=False, actions=True)`.
   Map `Open/High/Low/Close/Volume` → source frame; the index date (Asia/Ho_Chi_Minh) → `date`;
   `Dividends` → cash dividend events; `Stock Splits` → `stock` events with the ratio. Ignore
   `Adj Close`.
4. Rate limit with an injectable sleep; retries with exponential backoff on exceptions; a ticker
   that still fails is reported (`status = partial`), the others are written.
5. **Filler rows** (GAP-05): a row with `volume == 0` and `open == high == low == close ==`
   previous close of that ticker is dropped and counted in `rows_dropped` (logged with dates).
6. **Partial bar:** if `--to` is today and the injected clock is before `final_after`, today's
   rows are dropped.
7. **Terms notice** (ADR-007 §2): on the first real ingest from a source with `interim=True`,
   print a short notice in Vietnamese and English naming the terms URL and that data is for the
   user's own research, then ask for confirmation; the acceptance is stored in
   `<home>/state/accepted_sources.json`. `--accept-source-terms` accepts non-interactively (for
   OS schedulers). Without acceptance in a non-interactive run, exit 1 with a hint.
8. Rows are written with `source = yahoo`, `price_basis = split_adjusted`,
   `derived_limits = true` (P1-T36 behaviour 4), into `market.duckdb` (real store).

#### Acceptance criteria
1. With a fake fetch returning `synthetic_yahoo_basic.csv`, ingest writes the expected rows
   (hand-checked count, columns, `source`, `price_basis`), corporate actions from the fixture's
   dividend/split columns, and a raw snapshot.
2. Filler rows in `synthetic_yahoo_holiday.csv` are dropped and counted; a genuine zero-volume
   session whose prices differ from the previous close is kept.
3. Partial bar dropped before 16:00 and kept after (injected clock).
4. Re-scaled history after a split (`synthetic_yahoo_resplit.csv`) updates earlier rows with
   `revision = 1` and keeps the earlier raw snapshot.
5. Missing `yfinance` → exit 1 with the install hint (simulate by making the import fail).
6. Retry/backoff: a fetch failing twice then succeeding is retried with the configured backoff
   (sleep injected, no real waiting); a ticker failing every time → run `status = partial`.
7. Terms: non-interactive run without acceptance exits 1; `--accept-source-terms` writes the
   state file and proceeds; second run does not ask again.
8. `VNSTOCK_API_KEY` no longer appears in `src/`, `.env.example` or `doctor` output.
   Settings tests are hermetic: they `chdir` to `tmp_path` (or pass `_env_file=None`) so a
   developer's own `.env` in the repo folder cannot change results (seen on 2026-11-18).
9. Tests never import `yfinance` and never open a socket (fail the test session if
   `socket.socket.connect` is called — use a fixture). `pytest && ruff check . &&
   ruff format --check . && mypy` green; coverage ≥ 80 %.

#### Out of scope
Index/ETF proxy ingestion (GAP-03), quality checks (P1-T38), adjusted prices, any second source.

#### Notes
- Never commit real data. Fixtures use invented prices on the HOSE tick grid.
- `yfinance` 1.8.0 was probed by the manager on 2026-11-18; `history(..., auto_adjust=False)`
  returns `Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits`.
- The universe tickers come from config; symbol = ticker + `symbol_suffix`.
