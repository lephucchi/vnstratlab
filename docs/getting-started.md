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

### Real prices from Yahoo Finance (interim source)

Yahoo Finance is the interim price source ([ADR-007](adr/ADR-007-yahoo-interim-source.md)). It
is an optional extra and needs no account or key:

```bash
pip install -e ".[dev,yahoo]"
vnstratlab ingest --from 2015-01-01          # first backfill; later runs resume after the last date
```

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
