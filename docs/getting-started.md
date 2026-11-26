# Getting started

> vnstratlab is pre-alpha. Today you can install it, run `doctor`, and follow development.
> Commands marked "planned" print the task card that will implement them.

## 1. Install

Requirements: Python 3.11+, Git.

```bash
git clone https://github.com/lephucchi/vnstratlab.git
cd vnstratlab
python -m venv .venv
```

Activate the environment:

| Shell | Command |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Git Bash | `source .venv/Scripts/activate` |
| macOS / Linux | `source .venv/bin/activate` |

```bash
pip install -e ".[dev]"
vnstratlab doctor
```

`doctor` prints the version, the app home and which secrets are set.

## 2. Configure secrets (optional)

```bash
cp .env.example .env      # then edit .env
```

Nothing is required yet. See [configuration.md](configuration.md).

## 3. Try the lab (planned for v0.1)

```bash
vnstratlab demo                              # synthetic data, offline
vnstratlab init                              # create your config
vnstratlab ingest --source synthetic --from 2015-01-01   # offline synthetic data
vnstratlab backtest --strategy S02_breakout20
```

### Create your config: `vnstratlab init`

```bash
vnstratlab init                  # asks capital per book, data source, brokerage fee
vnstratlab init --yes --capital-short 20000000 --source synthetic   # no prompts
vnstratlab init --force          # replace an existing config.yaml (a .bak-* copy is kept)
```

It creates the home folders and writes only the values that differ from the defaults. Choosing
`yahoo` prints the data terms notice (accepted for real by `ingest`). It never asks for secrets:
the optional Telegram report is set up through `.env` ([configuration.md](configuration.md)).

### The demo (offline, synthetic)

```bash
vnstratlab demo                  # about 45 s; no network, no setup
vnstratlab demo --out demo-out   # also write summary.csv and equity/<trial_id>.csv
vnstratlab demo --quiet          # warning and footer only (used by CI)
```

It goes through the whole Phase 1 pipeline on the synthetic market: ingest, rebuild, features,
every enabled packaged trial, the simulator in executable mode (lots, odd lots, the risk layer)
and a summary table. The window is fixed (2016-01-01 .. 2020-12-31) whatever today's date is.

- **It is isolated.** It works in a temporary directory that is deleted at the end. Your app home
  (market data, trial registry, config, accepted terms) is neither read nor written, and **no
  trials are registered**: synthetic runs are not lab evidence.
- **`--out DIR`** needs `DIR` to be empty or missing; otherwise the demo refuses and writes
  nothing. Only `summary.csv` and `equity/*.csv` are written.
- **Every result is fake.** The first line of the output says so, and so should anything you
  copy from it.

Output shape (numbers are illustrative):

```text
SYNTHETIC DATA - results say nothing about the real market.
trial                                         horizon    CAGR    vol  Sharpe   maxDD  turnover  trades
S01_weekly_reversal n=2                       short     -4.8%   6.5%   -0.72  -25.2%     0.596     494
S17_equal_weight                              short      2.4%   6.0%    0.43   -8.9%     0.065     177
S17_equal_weight (benchmark) no risk layer    short     10.1%  20.8%    0.57  -26.3%     0.026    1958
...
data window 2016-01-01 .. 2020-12-31 (synthetic data from 2015-01-01, features warm)
trials run 19, skipped 0
benchmark rows (3): S17 equal weight without the risk layer; not trials, not registered, not counted
run time 45.0 s
no trials were registered (synthetic runs are not lab evidence)
```

Blocked strategies (`enabled: false` in the config) are listed as `skipped: <id>: <reason>`.

### Real prices from Yahoo Finance (interim source)

Yahoo Finance is the interim price source ([ADR-007](adr/ADR-007-yahoo-interim-source.md)). It
is an optional extra and needs no account or key:

```bash
pip install -e ".[dev,yahoo]"
vnstratlab ingest --from 2015-01-01          # first backfill
vnstratlab ingest                            # refresh (see below)
```

A refresh resumes per ticker: it starts `data.yahoo.overlap_sessions` (default 5) stored sessions
before each ticker's latest date, so a ticker that failed last time is fetched again. If Yahoo has
rescaled history (after a split) or reports a new stock event, that ticker is re-downloaded from
`project.backfill_start` and its earlier rows are revised (the run says so). Exit code 3 means some
tickers failed: just run `vnstratlab ingest` again.

The first run shows a notice (Vietnamese and English): Yahoo's terms restrict automated access,
the data is for your own research and you are responsible for following those terms. Confirm
once; the answer is stored in `<app home>/state/accepted_sources.json`. For an OS scheduler
(Task Scheduler / cron) accept up front with `vnstratlab ingest --accept-source-terms`.
Prices are split-adjusted and Yahoo history starts at different dates per ticker; see
[data-gaps.md](data-gaps.md). Data is written to `market.duckdb` in your data directory and is
never part of the repository.

### Walk-forward backtest: `vnstratlab backtest`

After `ingest`, `data rebuild` and `features build` (it never ingests or builds), `backtest` walks
every **registered** trial forward and stores its out-of-sample return per decision period, ideal
and executable, in `lab.duckdb` (table `oos_returns`):

```bash
vnstratlab lab register                       # or add --register below (it says so)
vnstratlab backtest --strategy S08_momentum   # all its registered parameter sets x horizons
vnstratlab backtest --all                     # every enabled strategy
vnstratlab backtest --all --source synthetic  # offline: needs `ingest --source synthetic` first
vnstratlab backtest --all --mode ideal        # ideal | executable | both (default)
```

A trial that is not in the registry is refused before anything runs. At each decision day a
strategy sees only feature rows dated up to that day; a period's return runs from the close of one
decision day to the close of the next (orders fill at the next open). The table prints, per trial
and mode, the number of periods, CAGR, volatility, Sharpe, max drawdown and turnover, split into
**historical** periods (before the trial was registered: in-sample by design) and **forward**
periods (after: true out-of-sample). Short results use 52 periods a year, medium and long 12.
Synthetic runs are labelled `SYNTHETIC DATA`; real-data runs carry the Yahoo / survivorship
(GAP-13) label. Re-running replaces a trial's rows for that source. The same work is the
`backtest_all` pipeline in the Console, and `GET /api/backtest/summary?source=` returns the
summary rows.

### Which stocks now, and one stock in detail: `recommend` and `stock`

Both are read-only on your stores, need the same prerequisites as `backtest` (a store with
features, and **registered** trials) and never place orders:

```bash
vnstratlab recommend                      # the three horizons; add --horizon short|medium|long
vnstratlab recommend --source synthetic   # offline
vnstratlab stock ACB                      # numbers, each strategy's signal, a recommendation
vnstratlab stock ACB --horizon medium --source synthetic
```

`recommend` is a **preview** until the lab selection (P1-T22) exists: the registered trials of a
horizon get equal weight, then the risk layer applies once (ATR sizing, max weight, max
positions). Each line shows the weight, how many strategies hold the stock (consensus), round
lots and odd lot, an entry zone, the ATR stop and the estimated buying cost. An enabled strategy
that is not registered is listed as skipped. `stock` is the `stock_analysis` pipeline (run
`load`, `features`, `signals`, `backtest`, `report`): it keeps the latest analysis per stock, which
the Console shows (`GET /api/recommendations`, `/api/stocks`, `/api/stocks/<TICKER>/analysis`).
Every output carries the data label (`SYNTHETIC DATA` or the Yahoo / survivorship label) and the
disclaimer: a reference only, you decide and you place any order yourself.

### Runs, and the local Console: `vnstratlab serve`

`demo`, `ingest`, `data rebuild` and `features build` are recorded as **runs**: a small chain of
tasks, each with a status and a log, stored in `<app home>/logs/runs/<run_id>/` (the last 50 are
kept). Look at them with:

```bash
vnstratlab runs list
vnstratlab runs show <run_id>
```

```bash
vnstratlab serve              # http://127.0.0.1:8000, opens your browser
vnstratlab serve --port 8100 --no-open
```

`serve` starts the local Console API and page. It listens on this machine only: any `--host` that
is not loopback is refused. One run at a time; starting the Yahoo `refresh` from the web asks you
to confirm the source terms first. The API is JSON under `/api` (`/api/pipelines`, `/api/runs`,
`/api/data/status`, `/api/results/<run_id>`); it has no endpoint that places orders.

#### The Console pages

The page opens in Vietnamese and works offline (no build step, nothing loaded from the internet;
Geist fonts are bundled under the SIL OFL). It uses the same monochrome look as the intro site and
the PO dashboard, in light and dark, with a permanent "Chỉ khuyến nghị — không đặt lệnh" tag.

Eight pages in the left nav (a drawer under 760 px): **Tổng quan** (data freshness, last runs,
quick actions, gaps by severity, strategy and trial counts), **Hướng dẫn** (the six-step guide, plus
a "Tour" that highlights real parts of the page), **Runs** (start a pipeline, filter the grid, hover
cards, compare two runs; the run page has Hủy / Chạy lại, a DAG and a log panel with search),
**Dữ liệu** (tickers with sparklines, price and volume chart, DQ findings, gaps), **Kết quả**
(trial table that drives the equity chart, drawdown, comparison with the S17 equal-weight benchmark, run without the risk layer),
**Chiến lược** (strategies, their param sets, add or delete your own sets) and **Cấu hình**
(editable config with live validation, a diff preview and a backup on save).

**Kết quả** now opens with "Khuyến nghị hiện tại": the recommended tickers per horizon (weight,
consensus n/N, buy zone, lots, stop, cost) from `GET /api/recommendations/all`, labelled "Bản xem
trước — chưa qua lab chọn lọc" with the data label and the disclaimer; the demo results sit below.
A new **Cổ phiếu** page (`#/co-phieu/<TICKER>`, `g p`) lets you pick a ticker, run the analysis
(`vnstratlab stock <TICKER>`, live progress) and read the numbers, strategy signals, features,
backtest contribution, risk sizing, data quality and a MUA / GIỮ / KHÔNG / BÁN recommendation per
horizon; "So sánh" shows up to four tickers side by side. Both work with `?mock=1`.

Every action shows its equivalent CLI line (copy it or open it in the terminal). A **terminal** is
docked at the bottom of every page (Ctrl+`): type `vnstratlab ...` commands (Tab completes, ↑/↓
history, Ctrl+C cancels); only `vnstratlab` subcommands run, never a shell. Press Ctrl/⌘+K or `/`
for the command palette and `?` for the shortcuts (`g o`, `g r`, `g d`, ...). Toasts and the
active-run tracker in the top bar follow your runs on every page.

To try the page without a backend, open it with `?mock=1` (for example
`http://127.0.0.1:8000/?mock=1`): all data is synthetic and answered in the browser.

## 4. Daily use (planned for v0.3)

```bash
vnstratlab serve
```

Open http://127.0.0.1:8000. The built-in scheduler runs the evening loop on trading days.
Read the recommendations; if you agree, place the orders yourself in your broker's app.
vnstratlab never places orders.

## 5. Run the checks (contributors)

```bash
pytest
ruff check . && ruff format --check .
mypy
pytest benchmarks --benchmark-only --no-cov
```
