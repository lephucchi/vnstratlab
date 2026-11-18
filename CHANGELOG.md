# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0, minor versions may break APIs.

## [Unreleased]

### Changed
- **Data source (ADR-007):** Yahoo Finance becomes the interim Phase 1 price source through an
  optional adapter (P1-T37); the data pipeline is a separate layer (`vnstratlab.data`); known
  shortfalls are tracked in a gap register (`src/vnstratlab/data/gaps.yaml`, `docs/data-gaps.md`).
  New cards P1-T36 (scope extended), P1-T37, P1-T38; P1-T03 is replaced. Review:
  `docs/reports/data-source-yahoo.md`.
- **Data source (ADR-006):** plan decision D6 (`vnstock`) is superseded. Phase 1 runs on a
  synthetic market (new card P1-T36); real-data cards wait for the owner's source decision.
  Review: `docs/reports/data-source-vnstock.md`.
- **Breaking:** environment variables have no project prefix: `APP_HOME` (was
  `VNSTRATLAB_HOME`), `LOG_LEVEL`, `VNSTOCK_API_KEY` (was `VNSTRATLAB_DATA_API_KEY`),
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. The unused LLM key is removed until the Phase 2
  card that needs it. Rename the keys in your `.env`.
- Pages: PO dashboard data is published only encrypted (`po/data.enc.json`); the plaintext
  `po/data.json` is no longer written.

### Added
- Data-quality checks use a per-year calendar (warnings in years with incomplete holiday
  lists), summarise findings on rescaled split-adjusted history, report per-ticker holes and mark
  a crashed check run `dq_crashed` (P1-T38 review fixes).
- Data quality (P1-T38): nine checks after every ingest stored in `dq_results`
  (`vnstratlab.data.quality`), run statuses `ok_with_warnings` and `failed_dq` (exit 1),
  `vnstratlab data status [--json]` and `vnstratlab data gaps`, a typed gap register loader
  (`vnstratlab.data.gaps`) and a `gaps: N open (...)` line in `doctor`.
- Yahoo adapter (P1-T37): `YahooSource` (optional extra `pip install "vnstratlab[yahoo]"`,
  `data.source` default is now `yahoo`, new `data.yahoo` config), rate limit with retries and
  backoff, holiday filler-row and partial-bar rules, a one-time terms notice stored in
  `<home>/state/accepted_sources.json` (`ingest --accept-source-terms` for schedulers), and a
  `partial` run status when a ticker fails. Refreshes resume per ticker with an overlap
  (`data.yahoo.overlap_sessions`, default 5, ADR-007) and re-download a ticker in full when Yahoo
  rescales its history or reports a new split; terms acceptance is keyed by source and terms URL;
  `--to` defaults to today in Vietnam time. `VNSTOCK_API_KEY` is removed.
- Data pipeline (P1-T36): `DataSource` protocol and registry, DuckDB market store with raw
  Parquet snapshots, revisions and a `store_meta.kind` guard (synthetic data goes to
  `market-synthetic.duckdb`, real data to `market.duckdb`), deterministic synthetic market
  (HOSE tick grid, daily limits, dividends, suspensions), derived price limits, and a working
  `vnstratlab ingest [--source] [--from] [--to] [--dry-run]`. New `data:` config section;
  runtime deps `duckdb`, `pandas`, `pyarrow`.
- PO dashboard login: `PO_USERNAME` / `PO_PASSWORD` (GitHub secrets for the Pages build),
  `tools/encrypt_po.py` (AES-256-GCM, PBKDF2-SHA256 600k, NFC-normalised credentials).
- Config loader and trading calendar (P1-T02): typed frozen config (`load_config`, `ConfigError`
  with `dotted.path: reason` messages), deep-merge of user `config.yaml`, `TradingCalendar`
  (config holidays or observed sessions), `decision_days` for short/medium/long horizons,
  `holiday_coverage`; `doctor` reports config status and holiday coverage; HOSE holidays for
  2026 (complete) and 2027 (partial); long book uses monthly decision days.
- Pages: single deployment (`pages.yml`) combining intro site (`site` branch), docs (from `main`) and PO dashboard (`po` branch); `tools/build_status.py` generates public status data; `docs.yml` is build-only.
- Project scaffold (P1-T01): `src/` layout package, Typer CLI with `doctor` and stubs for all
  planned commands, per-user app home via `platformdirs` (`VNSTRATLAB_HOME` override),
  env-only secrets via `pydantic-settings`, packaged default config (HOSE rules, VN30 banks).
- Guardrail tests: recommend-only (no order-placement code), config validity.
- CI (lint, types, tests on Windows/macOS/Linux × Python 3.11–3.13, secret scan),
  benchmark, weekly statistical tests, docs and release workflows.
- Documentation: workflow, git branching, QA gates, benchmarks, architecture, configuration,
  data sources, writing strategies, roadmap; ADR-001.
- ADR-005: long horizon decides monthly (accepted); threshold conversions and 12 tranches proposed.
- ADR-004 (accepted): gated, weighted selection by default; pre-registered rule for `last_winner`.
- End-to-end flow with a worked example (`docs/end-to-end-flow.md`).
- Engine specification (`docs/engine.md`), strategy catalogue (`docs/strategies.md`),
  ADR-003 (proposed engine and architecture refinements).
- Implementation plan v1.1 (recommend-only, portfolio optimisation as Phase 3).
