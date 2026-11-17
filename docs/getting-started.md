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
vnstratlab ingest --from 2015-01-01          # download data to your machine
vnstratlab backtest --strategy S02_breakout20
```

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
