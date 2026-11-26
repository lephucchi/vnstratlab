# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0, minor versions may break APIs.

## [Unreleased]

### Fixed
- **Circuit breaker re-arms on shadow equity (X-breaker, G3 finding R1, owner decision
  2026-11-26):** the stateless breaker could never turn off once the book was in cash. While on,
  a frictionless fractional shadow book follows the pre-breaker targets; the breaker turns off
  when the shadow has fully recovered to `trigger_peak` and at least one decision period (the
  stop cooldown, in sessions) has passed since the trigger (hysteresis, owner decision
  2026-11-26); the peak then resets to the actual equity (engine.md section 7). `ENGINE_VERSION` is now `engine-v2`, so trial ids change.
- **Demo benchmark is a true equal-weight book (G3 finding R2):** the row
  `S17_equal_weight (benchmark) no risk layer` runs S17 with `risk=None` (executable, no ATR
  sizing, position cap, vol scaling, stops or breaker). It is not a trial: not registered and not
  counted. The packaged S17 trials run with the risk layer and lose the benchmark label.

### Added
- **Console stock insight UI (X-stock-ui):** recommendations on Kết quả and a Tổng quan mini card,
  new Cổ phiếu page (picker, live analysis run, numbers, signals, backtest, risk, compare), palette
  and tour entries, contract-shaped `?mock=1` data (`docs/cards/stock-insight-api.md`).
- **Recommendations preview and per-stock analysis (X-stock-api):** `vnstratlab recommend` and
  `vnstratlab stock TICKER`; `vnstratlab.insight` (equal weight over the registered trials of a
  horizon, then the risk layer once; lot, entry zone, ATR stop and cost from the engine rules;
  per-stock numbers, features with universe rank, each strategy's signal and decision history,
  a per-ticker attribution and a recommendation); the `stock_analysis` pipeline, the first one
  that takes validated parameters (`RunManager.start(pipeline, params)`, `ParamError`); endpoints
  `GET /api/recommendations[/all]`, `GET /api/stocks`, `POST /api/stocks/{ticker}/analyze`,
  `GET /api/stocks/{ticker}/analysis`, `GET /api/stocks/compare`. Contract:
  `docs/cards/stock-insight-api.md`.
- **Lab statistics (P1-T21):** `vnstratlab.lab.stats` with per-period Sharpe, the Deflated
  Sharpe Ratio (plan Appendix C, non-excess kurtosis, N = every registered trial of the horizon)
  and PBO by CSCV; table `trial_stats` in `lab.duckdb`; `vnstratlab lab stats` with gate-1
  pass/fail columns; `GET /api/lab/stats`; a `lab_stats` task in the `backtest_all` pipeline.

### Changed
- **Backtest trials from the registry (P1-T20b):** `backtest --all` / `--strategy` run the
  registered trials of the current feature and engine version, rebuilt from id, params and
  horizon with the code hash checked, not the config; trials that cannot be rebuilt are listed
  as not runnable (CLI and `BacktestResult.not_runnable`); unregistered config trials are an
  error unless `--register`. The summary and `GET /api/backtest/summary` show only the current
  versions (`?all_versions=1` for all). The shared simulator bars are built once per run. The
  CAGR period-count convention is documented.
- **Demo follow-ups (X-65):** the risk layer logs a blocked decision at DEBUG (the engine already
  warns once when the circuit breaker turns on or off, so a demo run has a handful of warnings
  instead of over a thousand); the demo warning line is pure ASCII (Windows consoles); the demo
  builds the per-session price bars once and shares them across trials (`bars=` on `Simulator`
  and `run_simulation`), so it is faster. No simulation result changes (digests are equal; the
  engine version is not bumped).
- **Leaner process and tests (X-trim, owner decision 2026-11-26):** the full G2 review tier is
  limited to engine, finance, cost and statistics math; reviews are one round (a delta round only
  for an unfixed blocker); new cards follow a lean test policy. On pull requests CI runs the test
  job on ubuntu and windows with Python 3.12 only (the full 3 OS x 3 Python matrix runs on push
  to `develop`/`main`, nightly and on demand; the `demo` smoke runs on one job). The test suite
  dropped duplicated cases and shares one synthetic ingest per module; no behaviour change.

### Added
- **Console v2 UI (X-console-ui):** the Console now looks like the intro site and the PO dashboard
  (monochrome tokens, dot grid, bundled Geist fonts with the OFL licence, buffalo mascot, light and
  dark). New pages Tổng quan, Chiến lược and Cấu hình; command palette (Ctrl/⌘+K), keyboard
  shortcuts, toasts, an active-run tracker, Cancel and Rerun, log search with highlight, chart
  hovers, a Tour, a built-in terminal for `vnstratlab` commands and the equivalent CLI line on every
  action. `?mock=1` serves contract-shaped synthetic fixtures (`docs/cards/console-v2-api.md`) so every
  page works without the new API. Static files only, no external URLs.
- **Console v2 API (X-console-api):** `GET /api/overview`; run `cancel` (cooperative between tasks) and
  `rerun`; config editing (`GET/PUT /api/config`, `validate`, `reset`) restricted to whitelisted
  fields, validated with the real loader and written atomically with a `.bak-<stamp>` copy that keeps
  your other keys; strategy parameter sets (`GET /api/strategies`, add, enable/disable, delete): a
  new set is stored in your `config.yaml` as `strategies.<id>.user_params` and its trials are
  registered first (append-only, so every trial is counted), packaged sets can only be switched
  off with `disabled_params`; chart data from the local store (`/api/data/prices/<ticker>`,
  `/api/data/quality`); a built-in terminal (`GET /api/cli/commands`, `POST /api/cli`) that runs only
  `vnstratlab` subcommands as a run of pipeline `cli` (no shell, no `serve`, `init` needs `--yes`,
  the source-terms gate applies, 30 minute limit, cancel kills the command); pipelines and started
  runs show their equivalent `cli` command. Parameter schemas live in `strategies/schemas.py`, so
  built-in trial ids are unchanged. Packaged defaults are untouched.
- **Walk-forward runner and `vnstratlab backtest` (P1-T20):** for every registered trial, ideal and
  executable out-of-sample returns per decision period (strategies see rows up to the decision day
  only; close of one decision day to the close of the next) stored in `lab.duckdb` table
  `oos_returns` (idempotent re-run; rows tagged `in_sample_by_design` against `registered_at`).
  `backtest --strategy ID | --all [--source] [--mode ideal|executable|both] [--register]` prints
  CAGR, vol, Sharpe, max drawdown and turnover split historical / forward with a data label
  (SYNTHETIC or interim Yahoo / GAP-13); an unregistered trial is refused. New pipeline
  `backtest_all` (features check, backtest, report) and `GET /api/backtest/summary?source=`.
  `demo._targets` is now the public `demo.decision_targets` (no behaviour change).
- **PO dashboard product demo (X-po-demo):** the Pages build runs the offline `demo` pipeline into a temp `APP_HOME` and adds a `demo` object (run DAG with durations, last 40 log lines per task, summary table, downsampled equity for S17 and the top 3 trials) to the encrypted PO data only; `tools/build_status.py` takes `--demo-home`, and `status.json` never carries demo fields. The build also publishes the Console's `guide-data.js` under `/po/guide/` and four Playwright screenshots of the synthetic Console under `/po/shots/` (not the Data page). A demo or screenshot failure never fails the build (`demo: unavailable`).
- **Console UI (P1-T28a):** `vnstratlab serve` now opens a Vietnamese, offline Console (static
  files, no build step, no external assets): an animated step-by-step guide to the pipeline with
  commands and watch-outs, a Runs page (start pipelines, grid of recent runs, live task DAG and
  logs over Server-Sent Events with a polling fallback), a Data page (stores, tickers, checks, open
  gaps) and a Results page for the demo (synthetic banner, sortable table, equity chart).
- **Run registry and `vnstratlab serve` (P1-T27a):** new package `vnstratlab.runs`: pipelines
  (`demo`, `refresh`, `ingest`, `rebuild`, `features`) are DAGs of tasks run in a background thread
  (one run at a time), each task with a status, a summary and a log, stored under
  `<home>/logs/runs/<run_id>/` (last 50 kept; an interrupted run loads as failed). `demo`,
  `ingest`, `data rebuild` and `features build` now go through it with unchanged output, and
  `vnstratlab runs list` / `runs show` show the history. `vnstratlab serve` (replacing the stub)
  starts a FastAPI app on loopback only (`--host` other than loopback is refused, `--port`,
  `--no-open`) with the JSON API under `/api`: pipelines, runs, task logs, Server-Sent Events,
  data status and gaps, demo results; POSTs need the header `X-Vnstratlab: 1`, and a Yahoo run from
  the web needs an explicit terms confirmation. New runtime dependencies `fastapi` and `uvicorn`
  (dev: `httpx` for the test client). The Console UI is P1-T28a.
- **`vnstratlab init` (P1-T35):** interactive (or `--yes` with flags) wizard that creates the home
  folders and a minimal `config.yaml` (capital per book, data source, brokerage fee), validated with
  the config loader, written atomically; `--force` keeps a `.bak-*` copy and your other keys. It
  never handles secrets.

- **`vnstratlab demo` (P1-T32):** one offline command that runs ingest, rebuild, features, every
  enabled packaged trial (19 today) and the simulator with the risk layer on the synthetic
  market (fixed window 2016-2020, about 45 s) and prints a summary table headed by a synthetic
  data warning. It works in a temporary directory, never touches the app home or the trial
  registry and registers no trials; `--out DIR` writes `summary.csv` and `equity/<trial_id>.csv`
  into an empty directory, `--quiet` prints the warning and footer only. New pure module
  `vnstratlab.lab.metrics` (total return, CAGR, volatility, Sharpe, max drawdown, average
  turnover) for P1-T20 to reuse.
- **Strategies S14, S15 and S18 (P1-T19):** S14 low volatility (buy the 4 lowest `std_60d`), S15
  sector trend filter (1/N of the cross-section when the group return over 12 or 6 months is > 0,
  else cash) and S18 Hierarchical Risk Parity (250-session `ret_1d`, single linkage, recursive
  bisection), medium, medium and long horizon with frozen params in the packaged config (`lab
  register` now lists 19 trials, 12 strategy ids). New feature column `group_ret_6m`; the feature
  code version is now `features-v5`, so every `feature_version` changes: rebuild
  `features_daily`. New runtime dependency `scipy>=1.11` (S18 only, imported locally). S06 stays
  blocked on P1-T04.
- **Strategies S08 and S09 (P1-T17):** S08 cross-sectional momentum (buy the top 4 by the 6- or
  12-month return skipping the last month; `L_months` 6 and 12) and S09 medium-term reversal
  (the bottom 4 by the 6-month signal), both medium horizon with frozen params in the packaged
  config (`lab register` now lists 15 trials). New feature column `ret_6m_skip1m`; the feature
  code version is now `features-v4`, so every `feature_version` changes: rebuild
  `features_daily`. S13 stays blocked on P1-T07.
- **Strategies S04 and S05 (P1-T16):** S04 long-only bank pairs (formation 250 sessions, top 5
  correlated pairs, buy the laggard when |z| > 2, hold at most 10 sessions or until z crosses 0)
  and S05 residual mean reversion (60-session regression on the group return, buy the 2 most
  negative cumulative-residual z below -1.5), both short horizon with frozen params in the
  packaged config (`lab register` now lists 12 trials). New feature column `ret_1d` (group
  `returns`); the feature code version is now `features-v3`, so every `feature_version` changes:
  rebuild `features_daily`. New `BaseStrategy.lookback_sessions` (default 1) declares how many
  sessions of history a strategy reads; S04 and S05 return all cash with less history.
- **Strategies S01, S02, S03 (P1-T15):** S01 weekly reversal (`ret_5d_vs_group_median`, buy the
  `n` most negative, `n` 2 and 3), S02 close-based 20-day breakout with volume (`lookback` 20,
  `vol_mult` 1.5, `max_n` 3) and S03 oversold in an uptrend (RSI 2 < 10 and RSI 14 < 30, close
  above MA50, `max_n` 3), all short horizon with frozen param sets in the packaged `strategies:`
  config (`lab register` now lists 10 trials). New feature column `close_20d_break` (adjusted
  close above the highest adjusted close of the previous 20 good sessions); the feature code
  version is now `features-v2`, so every `feature_version` changes: rebuild `features_daily`.
- **Strategies S00 and S17 (P1-T14):** S00 composite score v1 with 4 blocks (trend, relative
  strength, mean reversion, volume; the valuation block is omitted until fundamentals exist,
  GAP-11) and two frozen weight sets (`equal`, `trend_heavy`, `top_n` 3), and S17 equal weight
  (1/N, no params, short/medium/long). Both are in the packaged `strategies:` config, so
  `vnstratlab lab register` now lists 5 trials. A user `config.yaml` merges with these entries;
  set `enabled: false` to drop one.

### Fixed
- **Risk follow-ups (P1-T12b):** `Simulator.add_actions` now updates the ex-date ATR factors and
  recomputes the affected tickers' ATR series, so a late stock action gives the same ATR state
  from its apply session on as one known up front (past reads are not rewritten). Lots shrink to
  the ledger's remaining shares (no drift after floored bonuses or late credits); shares added
  with no lot (a late bonus on a sold position) get a lot at the last close before the apply
  session with the current ATR. No change without a risk layer.

### Added
- **Strategy base, registry and trial log (P1-T13):** `Strategy` protocol and `BaseStrategy` with `validate_weights` and an `asof_guard` that refuses feature rows dated after `asof`; a registry that loads strategies and parameter sets from `strategies:` in the config (disabled entries skipped with their reason, unknown ids and bad params raise `StrategyConfigError`); deterministic `trial_id` over strategy id, canonical params, horizon, code hash, feature version and `ENGINE_VERSION`; append-only `trial_registry` in `lab.duckdb` with `ensure_trial` (`UnregisteredTrialError`) and a trial count for the DSR; `vnstratlab lab trials` and `lab register [--dry-run]` (the `lab --horizon` cycle command is unchanged). The packaged `strategies:` stays empty.
- **Feature store v1 (P1-T10):** pure `vnstratlab.features` (trend/momentum, relative strength,
  mean reversion, volatility, volume/liquidity and equal-weight-universe market context; windows in
  stored good sessions, `signal_ok = false` rows are missing, no lookahead by test), table
  `features_daily` with a single `feature_version` per build (includes every `adj_version`),
  `vnstratlab features build [--dry-run]` (refuses a store that `data rebuild` has not rebuilt) and
  the `load_features` loader with an `asof` guard. Valuation and asset-quality groups are deferred
  (GAP-11).
- **Corporate actions and execution prices (P1-T06):** `vnstratlab data rebuild` builds
  `prices_adjusted` (signals), `prices_exec` (`exec_reconstructed` rows the engine accepts) and
  `exec_exclusions` from the stored Yahoo rows and corporate actions; bad source rows, rows without
  a reference and tickers failing the stock ex-date scale-discontinuity check are omitted and counted.
  `corporate_actions` gains nullable `pay_date` and `listing_date` (migrated on open). New
  `load_execution_frame` for the engine input.
- **Simulator core (P1-T11, ADR-003):** pure `vnstratlab.engine` (HOSE ticks, limits, lots, 
  settlement, costs, cash buckets, order lifecycle with `order_events`, session loop in ideal and
  executable modes) and `SimExecutor` behind the `Executor` protocol. New config: `engine:` section
  in `defaults.yaml`; `cash_proceeds_offset`, `cash_dividend_pay_lag_days`,
  `stock_dividend_listing_lag_sessions` in `hose.yaml` (all `VERIFY`). Values are frozen by the owner
  at merge.

- **Risk layer (P1-T12):** pure `vnstratlab.risk` (Wilder `atr`, `RiskLayer`: stop cooldown,
  1 %-at-risk ATR sizing, max weight, max positions, optional vol scaling, circuit breaker) and,
  in the simulator, ATR stops on the close (`stop_pending_settlement` order event), the circuit
  breaker, the rebalance threshold and a `risk_events` output; all opt-in (`risk=` argument), so
  runs without it are unchanged. New config key `risk.stop_cooldown_sessions` (`null` = one decision
  period of the book's horizon, resolved by the caller); owner to confirm.

### Fixed
- **Data (P1-T06b):** `data rebuild` no longer loses a ticker to a few out-of-scale Yahoo
  sessions: up to 2 sessions that return to scale are omitted (`scale_outlier_row`), a persistent
  step at a stored event excludes the rows through the ex-date (`scale_step_before`) and the event
  is no longer returned as an action, and rows before the first 60 in-band sessions of a
  `split_adjusted` ticker are excluded (`non_hose_history`, GAP-04). Yahoo cash dividends are
  booked as `amount x F(ex_date)` (`DIVIDENDS_SPLIT_ADJUSTED = True`). The rebuild report prints a
  count per kind; the `dq_error` detail no longer says "latest run".
- **Engine (P1-T11b):** late corporate actions use the holdings at pre-open of the ex-date;
  stock events rescale only pending orders created before the ex-date (also with no shares held);
  turnover divides by the previous close's equity (first session: initial capital).
- **Data:** the synthetic market declares the sessions it suspended; a trailing gap made only of
  such sessions is a `missing_ticker` warning ("declared suspension"), so synthetic ingests no
  longer end in `failed_dq`. Undeclared gaps (raw sources) keep their severity.
- **CLI:** `vnstratlab --help` and `--version` no longer import pandas, numpy or duckdb.

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
