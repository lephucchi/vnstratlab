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
SYNTHETIC DATA — results say nothing about the real market.
trial                                   horizon   CAGR    vol  Sharpe   maxDD  turnover  trades
S01_weekly_reversal n=2                 short    -1.4%   5.4%   -0.23  -10.3%     0.574     364
S17_equal_weight (benchmark)            short     2.4%   6.0%    0.43   -8.9%     0.065     177
...
data window 2016-01-01 .. 2020-12-31 (synthetic data from 2015-01-01, features warm)
trials run 19, skipped 0
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
