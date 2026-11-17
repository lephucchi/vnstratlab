# Architecture

## 1. Principles

1. **One engine.** Backtest, lab and paper books run the same code; only the `Executor`
   differs (`SimExecutor` for history, `PaperExecutor` for the nightly paper books).
2. **Recommend-only.** The last step of the pipeline is a recommendation written to an
   append-only journal and shown to the user. There is no broker executor.
3. **Point-in-time everything.** Every table that feeds a decision carries the time the value
   became knowable (`published_at`, `effective_date`, `ingested_at`).
4. **User data stays local.** Databases, raw downloads and config live in the app home, never in
   the repository or in CI.
5. **Swap-able edges.** Data sources, strategies and notifiers are plug-ins behind protocols.

## 2. Pipeline

```
 DataSource adapters ──► ingest ──► data-quality checks ──► market.duckdb
 (free API first)                     │ fail → stop + alert      │
                                      ▼                          ▼
                                                         features (point-in-time)
                                                                 │
                                    strategies S00…S18 + user strategies
                                                                 │ target weights
                                                                 ▼
                                    SimExecutor + HOSE rules + costs  ──► OOS returns (lab.duckdb)
                                                                 │
                         lab: gate 1 (DSR, PBO) → gate 2 (SPA) → MCS → shrunk Hedge weights
                                                                 │
                                         risk layer (sizing, ATR stops, limits)
                                                                 │
                       ┌──────────────── portfolio optimiser (Phase 3) ────────────┐
                       ▼                                                           ▼
          recommendations (journal.sqlite, append-only)              PaperExecutor → paper books
                       │
          dashboard (127.0.0.1) · Telegram/console report
                       │
                     USER decides and places orders in their own broker app
                       │
          (optional) user records actual fills → journal → real vs. recommended tracking
```

## 3. Packages

| Package | Responsibility | First card |
|---|---|---|
| `vnstratlab.cli` | Typer commands | P1-T01 |
| `vnstratlab.paths` | App home and file locations (`VNSTRATLAB_HOME`) | P1-T01 |
| `vnstratlab.settings` | Env-only secrets | P1-T01 |
| `vnstratlab.config` | Packaged YAML defaults, loader and validation | P1-T02 |
| `vnstratlab.data` | `DataSource` protocol, adapters, ingestion, DQ checks, corporate actions, fundamentals, universe membership | P1-T03 |
| `vnstratlab.features` | `features_daily` | P1-T10 |
| `vnstratlab.engine` | Simulator, cost model, settlement/limit/lot/tick rules | P1-T11 |
| `vnstratlab.risk` | Sizing, stops, circuit breaker | P1-T12 |
| `vnstratlab.strategies` | Protocol, registry, trial log, built-ins | P1-T13 |
| `vnstratlab.lab` | Walk-forward, metrics, gates, MCS, weights, meta-backtest, stress | P1-T20 |
| `vnstratlab.execution` | `SimExecutor`, `PaperExecutor` | P1-T11, P1-T24 |
| `vnstratlab.journal` | Recommendations, paper orders/fills, equity, user fills | P1-T25 |
| `vnstratlab.notify` | Console, file, Telegram | P1-T29 |
| `vnstratlab.app` | FastAPI (read-only) + in-process scheduler | P1-T27 |
| `vnstratlab.web` | Static dashboard (no framework, hand-written SVG charts) | P1-T28 |
| `vnstratlab.news` | Raw collection (P1), scoring and features (P2) | P1-T09 |
| `vnstratlab.portfolio` | Optimisers with lot constraints | P3 |

## 4. Core interfaces

```python
Horizon = Literal["short", "medium", "long"]

class Strategy(Protocol):
    id: str                       # "S02_breakout20"
    horizons: tuple[Horizon, ...]
    params: dict                  # frozen; new params = new trial
    def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        """Long-only weights summing to <= 1, using rows with date <= asof only."""

class Executor(Protocol):         # SimExecutor, PaperExecutor — nothing else
    def submit(self, orders: pd.DataFrame) -> pd.DataFrame: ...
    def fills(self, trade_date: str) -> pd.DataFrame: ...

class DataSource(Protocol):       # P1-T03
    name: str
    def daily_prices(self, tickers: list[str], start: date, end: date) -> pd.DataFrame: ...
```

## 5. Storage

| File (in app home) | Engine | Contents |
|---|---|---|
| `data/market.duckdb` | DuckDB | Membership, prices (raw and adjusted), corporate actions, fundamentals, features, raw news |
| `data/lab.duckdb` | DuckDB | Trial registry, OOS returns, selection runs |
| `data/journal.sqlite` | SQLite | Recommendations (append-only, enforced by triggers), paper orders/fills, book equity, user-recorded fills |
| `data/raw/` | Parquet | Raw API responses, for audit and re-processing |

**DuckDB locking.** A DuckDB file accepts either one read-write process or several read-only
processes, not both. Therefore the nightly loop runs **inside** the `serve` process (built-in
scheduler), and API handlers use short-lived connections from that same process. Running
`vnstratlab daily` from a terminal while `serve` is running is refused with a clear message.

## 6. Daily loop (Vietnam time)

| Time | Step |
|---|---|
| 15:30 | Ingest, data-quality checks (stop on failure) |
| 16:00 | Features |
| 16:15 | Lab: update OOS returns; re-select on a horizon's decision day |
| 16:30 | Risk layer, stops, recommendations, journal |
| 17:00 | Dashboard refresh, report |
| 17:15 | Raw news collection (never blocks the loop) |

A missed run (computer off) is detected on the next start and backfilled.

## 7. Where things run

| Place | Runs | Data |
|---|---|---|
| User's computer (or their VPS) | `serve`, nightly loop, dashboard | Real, local |
| GitHub Actions (this public repo) | CI, benchmarks, statistical tests, docs, releases | Synthetic only |
| Optional private ops repo of a user | Their own nightly run | Real, private (check the source allows datacenter IPs) |
