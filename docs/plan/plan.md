# vnstratlab — Implementation Plan

Version 1.1 · 2026-11-17 · Owner: Le Phuc Chi
Audience: the owner, contributors, and the AI coding agents (Opus manager and reviewers, Sonnet workers) that build the system.
Companion design doc: "Hệ thống AI phát hiện điểm giao dịch cho cổ phiếu ngân hàng VN30" (Claude Docs). Where the two disagree, **this plan wins**.

This document is research and engineering planning for an open-source project. It is not investment advice.

**Changes in v1.1** (see [ADR-001](../adr/ADR-001-python-core-recommend-only.md)):
- Project renamed `vnstratlab` → **vnstratlab**; public open-source tool installed with `pipx` / `uv tool`.
- **Recommend-only.** No live trading, broker API, order confirmation or automation levels. The former Phase 3 (go live) is replaced by **portfolio optimisation**.
- Workflow adds a QA Reviewer and a Reality Analyst, four gates (G0–G4) and a defined branching model ([workflow.md](../workflow.md), [qa-gates.md](../qa-gates.md), [git-branching.md](../git-branching.md)).
- Benchmarks made explicit ([benchmarks.md](../benchmarks.md)); new cards P1-T32 (demo), P1-T33 (stress), P1-T34 (cross-engine), P1-T35 (init wizard).
- Secrets only via environment (`VNSTRATLAB_*`); user data in a per-user app home, never in the repo.
- Scheduler runs inside `serve` (avoids DuckDB cross-process locking).

---

## 0. How to read this document (agents start here)

1. Read sections 1–5 fully before doing any task. They hold decisions that are **fixed** and must not be re-litigated inside a task.
2. Read section 6 (agent roles and rules). Every task must follow it.
3. Work only on the task card you were assigned (sections 8–10). Each card has an ID like `P1-T07`.
4. If a task needs something that contradicts sections 1–6, stop and report it to the manager instead of working around it.
5. Items marked **[VERIFY]** are market facts taken from secondary sources or general knowledge. They live in `config.yaml`, never hard-coded, and must be confirmed against official sources before a release relies on them (gate G3).

---

## 1. Goal and scope

**Goal.** One end-to-end tool that, every trading evening, pulls market data for the bank stocks in VN30, runs a lab of trading strategies through one simulator, picks and weights the strategies that survive statistical tests, and produces a recommended portfolio for three horizons. Over three phases it moves from simulation (POC), to evaluating a news signal, to portfolio optimisation. **The user always places orders themselves; the system never trades.**

**Phase summary**

| Phase | Name | What it delivers | Real money |
| --- | --- | --- | --- |
| 1 | POC | Nightly data pull, simulator, strategy lab, three paper books of 11,000,000 VND each, dashboard, Telegram report | No |
| 2 | News evaluation | News collection and LLM scoring, controlled test of whether a news parameter improves results, a written adopt/reject decision | No |
| 3 | Portfolio optimisation | Optimisers (shrinkage mean-variance, HRP, risk parity, Black-Litterman with lab views) under lot constraints; user-recorded fills; real vs. recommended tracking | No |

**Out of scope for all phases:** placing or routing orders with any broker, short selling, margin, derivatives, intraday trading, any hosted multi-user deployment. The default universe is section 3; users may configure others.

---

## 2. Fixed decisions

| # | Decision | Value |
| --- | --- | --- |
| D1 | Language and runtime | Python 3.11+, inside a venv |
| D2 | Storage | DuckDB files for market data and lab; SQLite for the journal (the only store the API writes to); raw downloads kept as Parquet |
| D3 | Backend | FastAPI, bound to 127.0.0.1 in Phases 1–2 |
| D4 | UI | Plain HTML, CSS, JavaScript. No framework, no build step, no chart library (charts are hand-written SVG) |
| D5 | Notifications | One Telegram bot |
| D6 | Data source (Phase 1) | ~~`vnstock` (free Community tier)~~ Superseded by [ADR-006](../adr/ADR-006-synthetic-first.md) and **[ADR-007](../adr/ADR-007-yahoo-interim-source.md)**: synthetic market for tests/CI/demo (P1-T36); **Yahoo Finance as interim user-side price source** (P1-T37); gaps tracked in `data/gaps.yaml` (P1-T38) |
| D7 | News | **Not used in any signal in Phase 1.** Raw news is collected passively from Phase 1 so that Phase 2 has forward data |
| D8 | Horizons | Short = 1 week (5 sessions), Medium = 3–6 months, Long = 1 year |
| D9 | Capital | Three independent paper books, one per horizon, 11,000,000 VND each (section 4) |
| D10 | Strategy selection | Lab with two statistical gates, Model Confidence Set, Hedge weights shrunk toward equal weight. Never "pick the single best backtest" |
| D11 | One engine | Backtest, lab and paper books use the same code path; only the `Executor` differs |
| D12 | Execution | **None.** Recommend-only; only `SimExecutor` and `PaperExecutor` exist (ADR-001) |
| D13 | Hardware | Runs on a normal laptop; GPU not required. Optional user VPS |
| D14 | Comments and docs | English. User-facing UI text and Telegram messages in Vietnamese |
| D15 | Distribution | Public repo, Apache-2.0, PyPI package `vnstratlab`; user data in a per-user app home (`VNSTRATLAB_HOME`) |
| D16 | Secrets | Environment variables / `.env` only, via `vnstratlab.settings` |
| D17 | GitHub Actions | CI, benchmarks, statistical tests, docs, releases on synthetic data only; no real data in the public repo |

---

## 3. Universe and market rules

### 3.1 Universe

13 bank tickers in VN30 for the review effective **2026-08-03**:
`ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, VCB, VIB, VPB`.

- Membership is stored as a table with `effective_from` / `effective_to`, never as a hard-coded list.
- TPB left VN30 on that review; it must be present in history before 2026-08-03 to avoid survivorship bias.
- Membership before the July 2026 review is not yet known. Task `P1-T05` builds the history; until then the engine runs with the current 13 plus TPB and logs a `survivorship_warning`.
- VN30 is reviewed in January and July.

### 3.2 Market rules (all in `config.yaml`)

| Rule | Default | Status |
| --- | --- | --- |
| Settlement: earliest sell date after a buy | buy on T, sell from T+3 (example: buy Monday, sell Thursday) | [VERIFY] |
| Daily price limit (HOSE) | ±7% of reference price | [VERIFY] |
| Round lot | 100 shares | [VERIFY] |
| Odd lot | 1–99 shares, limit orders only, separate board | [VERIFY] |
| Tick size | < 10,000: 10 · 10,000–49,950: 50 · ≥ 50,000: 100 (VND) | [VERIFY] |
| Sessions | ATO 09:00–09:15 · continuous 09:15–11:30, 13:00–14:30 · ATC 14:30–14:45 | [VERIFY] |
| Sales tax | 0.1% of sell value, charged even on a loss | Confirmed by a broker page |
| Brokerage fee | 0.15% per side (conservative default; some brokers advertise zero fees, conditions vary) | [VERIFY] |
| Slippage assumption | 0.10% per side (round lot), 0.30% per side (odd lot) | Assumption; users may recalibrate from their recorded fills (P3-T05) |
| Short selling, intraday (T+0) | Not available to retail | Plan assumes long-only |

---

## 4. Capital model (11,000,000 VND)

- Phases 1–2 run **three paper books**, one per horizon, each starting with 11,000,000 VND. This makes horizons comparable. They are not one shared account.
- Capital per book is configurable (`books.*.capital_vnd`); 11,000,000 VND is the default. Phase 3 turns the books' targets into a lot-aware recommended portfolio for the user's own capital.
- With 11,000,000 VND, round lots are a binding constraint (e.g. 100 VCB shares cost about 5.3 million VND). Therefore every strategy produces two return series:
  - **Ideal returns**: fractional shares, no lot rule. The lab uses these for statistics (they measure signal quality).
  - **Executable returns**: lot-rounded with the real 11,000,000 VND, odd lots allowed with the odd-lot slippage. Paper books and recommendations use these.
- The equal-weight benchmark (1/N over the 13 stocks) also has both versions. The executable version uses odd lots.
- Risk rules for executable books (from the design doc): max 1% of book equity at risk per position (entry to ATR stop), max 4 positions, no margin, circuit breaker at −10% from equity peak. With 11,000,000 VND, expect 2–3 positions in practice.

---

## 5. Architecture

### 5.1 Daily loop (Vietnam time, suggested)

| Time | Step | Phase |
| --- | --- | --- |
| 15:30 | Ingest data, run data-quality checks. On failure: stop the loop, send an error alert | 1 |
| 16:00 | Compute features | 1 |
| 16:15 | Lab: update out-of-sample returns for all strategies; re-select weights only on a horizon's decision day | 1 |
| 16:30 | Risk layer, stop checks on open positions, build recommendations, write journal (immutable) | 1 |
| 17:00 | Dashboard refresh, Telegram report | 1 |
| 17:15 | Collect raw news (no scoring in Phase 1); score news in Phase 2 | 1 (collect) / 2 (score) |
| Next morning | **User** reads the recommendation and, if they agree, places orders in their own broker app; optionally records fills | user |

The loop runs inside `vnstratlab serve` (built-in scheduler). Paper books simulate fills at the next open.

Decision days: Short = last trading day of the week; Medium = last trading day of the month (book split into 3–6 tranches, one tranche rebalanced per month); Long = last trading day of the month, one of 12 tranches (ADR-005; previously after report seasons).

### 5.2 Repository layout

Current layout and package responsibilities: [architecture.md](../architecture.md). Original sketch (package now under `src/vnstratlab/`; `execution/` holds Sim and Paper executors only; `portfolio/` added for Phase 3):

```
vnstratlab/
├── pyproject.toml
├── config.yaml                 # all parameters; see Appendix A
├── .env.example                # secrets template (never commit .env)
├── vnstratlab/
│   ├── cli.py                  # vnstratlab <command>
│   ├── config.py               # load + validate config (pydantic)
│   ├── calendar.py             # trading days, decision days
│   ├── data/                   # source adapters, ingestion, data-quality checks
│   ├── features/               # feature computation
│   ├── strategies/             # one module per strategy + registry
│   ├── engine/                 # simulator, cost model, lot/limit/settlement rules
│   ├── lab/                    # walk-forward, metrics, gates, MCS, weights, meta-backtest
│   ├── risk/                   # position sizing, stops, circuit breaker
│   ├── execution/              # Executor protocol; Sim and Paper executors only
│   ├── journal/                # recommendations, orders, fills (SQLite)
│   ├── news/                   # Phase 1: raw collector only; Phase 2: scoring + features
│   ├── notify/                 # Telegram bot
│   └── app/                    # FastAPI app + routers
├── web/                        # index.html, stock.html, lab.html, book.html, health.html, css/, js/
├── notebooks/                  # explore_*.ipynb for the owner to inspect data and results
├── tests/                      # pytest; unit tests never hit the network
├── data/                       # market.duckdb, lab.duckdb, journal.sqlite, raw/ (gitignored)
└── docs/
    ├── adr/                    # decision records (e.g. ADR-002 news adopt/reject)
    └── reports/                # task handoff reports, lab reports
```

### 5.3 CLI commands

| Command | Does |
| --- | --- |
| `vnstratlab daily [--dry-run]` | Full daily loop. `--dry-run` prints DataFrames and writes nothing |
| `vnstratlab ingest --from YYYY-MM-DD` | Backfill or refresh data |
| `vnstratlab backtest --strategy ID` | One strategy, walk-forward |
| `vnstratlab lab --horizon short|medium|long [--asof DATE]` | One lab selection cycle |
| `vnstratlab meta-backtest --horizon H` | Backtest the lab itself vs. equal weight and vs. "pick last winner" |
| `vnstratlab serve` | FastAPI + UI on 127.0.0.1:8000 + built-in scheduler |
| `vnstratlab doctor` | Version, paths, which secrets are set |
| `vnstratlab demo` | Whole pipeline on bundled synthetic data (P1-T32) |
| `vnstratlab init` | Interactive user config (P1-T35) |
| `vnstratlab stress --horizon H` | Realism stress tests (P1-T33) |

### 5.4 Core interfaces

```python
# vnstratlab/strategies/base.py
from typing import Protocol, Literal
import pandas as pd

Horizon = Literal["short", "medium", "long"]

class Strategy(Protocol):
    id: str                 # e.g. "S02_breakout20"
    horizons: tuple[Horizon, ...]
    params: dict            # fixed; changing params = a new trial in the registry

    def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        """Return long-only target weights per ticker summing to <= 1.
        Must use only rows with date <= asof (point-in-time)."""
```

```python
# vnstratlab/execution/base.py
class Executor(Protocol):
    """Same interface for backtest, paper and live; only the fill source differs."""
    def submit(self, orders: pd.DataFrame) -> pd.DataFrame: ...   # returns order ids
    def fills(self, trade_date: str) -> pd.DataFrame: ...          # matched qty and price
# SimExecutor (backtest/lab) · PaperExecutor (paper books). No broker executor (D12).
```

### 5.5 Key tables

| Store | Table | Key columns |
| --- | --- | --- |
| market.duckdb | `universe_membership` | ticker, index_code, effective_from, effective_to, source_url |
| market.duckdb | `prices_daily` | ticker, date, open, high, low, close, volume, value, ref_price, ceiling, floor, source, ingested_at |
| market.duckdb | `corporate_actions` | ticker, ex_date, type (cash/stock/bonus/rights), ratio_or_amount, source; optional `pay_date`, `listing_date` (ADR-003 §6, added by P1-T06) |
| market.duckdb | `prices_adjusted` | ticker, date, adj_open … adj_close, adj_factor |
| market.duckdb | `fundamentals_q` | ticker, fiscal_period, metric, value, **published_at**, ingested_at |
| market.duckdb | `features_daily` | ticker, date, feature columns…, feature_version |
| market.duckdb | `news_raw` | news_id, ticker, published_at, title, body_or_url, source, collected_at |
| lab.duckdb | `trial_registry` | trial_id, strategy_id, params_json, horizon, registered_at, rationale |
| lab.duckdb | `oos_returns` | trial_id, period_end, ret_ideal, ret_exec, turnover |
| lab.duckdb | `selection_runs` | run_id, horizon, asof, gate1_passed, spa_pvalue, mcs_members, weights_json, status |
| journal.sqlite | `recommendations` | rec_id, horizon, asof, created_at, status (propose/hold_benchmark), targets_json, evidence_json |
| journal.sqlite | `orders` / `fills` | order_id, book, ticker, side, qty, price, order_type, created_at · fill_id, order_id, qty, price, filled_at |
| journal.sqlite | `book_equity` | book, date, cash, positions_value, equity |

`recommendations` rows are **append-only**: written before the next market open, never updated.

---

## 6. Agent roles and rules

### 6.1 Roles

| Role | Model | Responsibilities | Must not |
| --- | --- | --- | --- |
| Manager | Opus | Reads this plan; breaks a milestone into task cards; assigns; runs integration tests; merges into `develop`; updates the progress log; escalates decisions to the owner | Write large features itself when a worker can; review its own assignments; merge work whose tests it has not run |
| Worker | Sonnet | Implements one task card on `feat/<card>-<slug>`; writes tests first; opens a PR with a handoff report | Change anything outside the card's listed files; change config thresholds or strategy params; touch secrets; write order-placement code |
| QA Reviewer | Opus (fresh context) | Gate G2: independent code review of each PR against the card and checklist | Edit code; approve with failing CI |
| Reality Analyst | Opus | Gate G3: benchmarks, cross-engine check, stress tests, product comparison; writes the release readiness report | Tune parameters or code to improve results |
| Owner | Human | Approves releases (G4), ADRs, config parameter changes | — |

Full process: [workflow.md](../workflow.md). Agent definitions: `.claude/agents/`.

### 6.2 Task card format (manager writes these)

```markdown
### <ID> — <title>
- Depends on: <IDs>
- Goal: <one sentence>
- Files to create/change: <paths>
- Inputs: <tables, config keys, fixtures>
- Outputs: <tables, files, endpoints>
- Acceptance criteria:
  1. <testable statement>
  2. ...
- Out of scope: <explicit exclusions>
- Notes: <domain hints, links to plan sections>
```

### 6.3 Handoff report format (worker returns this)

```markdown
## Handoff <ID>
- Status: done | blocked | partial
- Files changed: ...
- Tests added / run: <command> → <result summary>
- Acceptance criteria: 1 ✅ 2 ✅ 3 ❌ (reason)
- Assumptions made: ...
- Open questions for manager: ...
```

### 6.4 Global rules (every task)

1. **No lookahead.** A value used at date `t` must have been knowable at the close of `t`. Fundamentals use `published_at`; if missing, assume availability 45 days after quarter end and flag it. News published after 14:45 counts for the next trading day.
2. **No invented data.** Never type prices, fundamentals or news into code or fixtures except clearly synthetic test fixtures named `synthetic_*`.
3. **Parameters are frozen.** Strategy params, gate thresholds, λ, η and risk limits come from `config.yaml`. A worker never edits them to make a result look better. A new parameter set is a new row in `trial_registry`, registered **before** it is backtested. Trial identity includes the strategy code hash, feature version and engine version (ADR-003 §3), so a code change is a new trial.
4. **Count every trial.** Anything backtested is registered. Deflated Sharpe uses the total trial count.
5. **Deterministic.** Fixed random seeds; bootstrap seeds in config; same inputs give the same outputs.
6. **Tests.** pytest; unit tests use fixtures and never hit the network; engine rules (T+2/T+3, limits, lots, fees) each have hand-computed test cases.
7. **Dry-run first.** Every command that writes supports `--dry-run`, which prints the DataFrames it would write and writes nothing.
8. **Secrets.** Only from environment variables or the OS keyring. Never logged, printed or committed. Never sent to the browser.
9. **Recommend-only.** No code places, routes or confirms orders, connects to a broker or stores trading credentials. Enforced by `tests/test_guardrails.py`; violations are blocked at G2.
10. **Style.** Type hints, English comments, ruff-clean, small functions. UI and Telegram text in Vietnamese.
11. **Scope.** If a task seems to need a change to the fixed decisions (section 2), stop and report.

### 6.5 Definition of done (every card)

- Acceptance criteria all met and demonstrated in the handoff report.
- `pytest` passes; `ruff check` clean.
- `--dry-run` path works for anything that writes.
- No new network calls in unit tests; no secrets in the diff.
- CI (G1) green and QA review (G2) approved.
- Manager has re-run the tests, squash-merged into `develop` and appended a line to `docs/reports/progress.md`.

---

## 7. Strategy library v1 (Phase 1)

News-based and ML strategies are excluded from the Phase 1 core. Each strategy has at most 3 pre-declared parameter sets.

| ID | Strategy | Horizons | Core rule | Basis |
| --- | --- | --- | --- | --- |
| S00 | Composite score (design doc "Layer 1") | short | Weighted rank of trend, relative strength, mean reversion, volume, valuation; buy top-ranked on breakout or oversold-in-uptrend trigger | Design doc |
| S01 | Weekly reversal within group | short | Buy 2–3 biggest losers of last week vs. group median | Jegadeesh (1990) |
| S02 | 20-day breakout with volume | short | Close > 20-day high, volume > 1.5× 20-day average | Brock et al. (1992) |
| S03 | Oversold in uptrend | short | Short-term RSI low while close > 50-day MA | Jegadeesh (1990); Moskowitz et al. (2012) |
| S04 | Bank pairs, long-only | short | Buy the laggard when a pair spread exceeds 2 std | Gatev et al. (2006) |
| S05 | Residual mean reversion | short | Buy abnormally negative residual vs. bank index | Avellaneda & Lee (2010) |
| S06 | Foreign flow | short | Highest 5-day foreign net buy / traded value | Only if a free data source is found (P1-T04); otherwise skipped |
| S08 | Cross-sectional momentum 6–12m | medium | Top 3–4, skip last month | Jegadeesh & Titman (1993) |
| S09 | Medium-term reversal | medium | Opposite of S08 | Vietnam studies show reversal |
| S10 | Value: P/B vs. ROE-justified P/B | medium, long | Lowest P/B relative to (ROE − g)/(r − g) | Gordon (1959) |
| S11 | Value: E/P | medium, long | Highest E/P | Huang et al. (2023) |
| S12 | Asset quality and profitability | medium, long | High ROE, low NPL, high NPL coverage | Fama & French (2015) |
| S13 | Value + momentum | medium | Average rank of S08 and S10 | Asness et al. (2013) |
| S14 | Low volatility | medium | Lowest 60-day volatility | Frazzini & Pedersen (2014) |
| S15 | Bank-group trend filter | medium | Hold the group when its 12-month return > 0, else cash | Moskowitz et al. (2012) |
| S17 | Equal weight 13 | all | Benchmark and selectable strategy | DeMiguel et al. (2009) |
| S18 | Hierarchical Risk Parity | long | Allocation by correlation tree | López de Prado (2016) |
| S07, S16 | LightGBM ranking (5-day / 60-day labels) | short / medium | **Stretch goal, Phase 1 milestone M1.9 only if time allows** | Gu, Kelly & Xiu (2020) |

---

## 8. Phase 1 — POC (simulation only)

**Goal.** Every trading evening the system pulls data, runs all strategies through the lab, updates three paper books of 11,000,000 VND, and reports via dashboard and Telegram. No real orders, no news in signals.

**Estimated duration.** About 8–10 weeks of evening work to build (M1.0–M1.8), then the nightly paper run continues for at least 3 months; that run is the evidence for Phase 3.

**Exit criteria (all required).**

1. 20 consecutive trading days of `daily` running without manual fixes.
2. Spot check: 20 random (ticker, date) closes match a public price board exactly.
3. Engine rule tests all pass (settlement, limits, lots, ticks, fees, tax).
4. Lab report produced per horizon: per-strategy OOS Sharpe, DSR, PBO; SPA p-value; MCS members; weights.
5. Meta-backtest of the lab vs. equal weight and vs. "pick last winner" is produced (passing it is **not** required to exit Phase 1; it is reported at every release, gate G3).
6. Dashboard 5 pages and Telegram report working.
7. Raw news collection has been running daily since M1.1 (needed by Phase 2).

### M1.0 — Scaffold

**P1-T01 — Repo scaffold and tooling**
- Depends on: —
- Goal: create the repository skeleton of section 5.2 with tooling.
- Files: `pyproject.toml`, package folders with `__init__.py`, `tests/`, `.gitignore`, `.env.example`, `README.md`.
- Acceptance: `pip install -e .[dev]` works in a fresh venv; `pytest` runs (0 tests OK); `ruff check` clean; `vnstratlab --help` lists commands of 5.3 (stubs allowed).
- Out of scope: any business logic.

**P1-T02 — Config and calendar**
- Depends on: P1-T01
- Goal: typed config loader and trading calendar.
- Files: `vnstratlab/config.py`, `vnstratlab/calendar.py`, `config.yaml` (Appendix A), tests.
- Acceptance: invalid config fails with a clear message; `is_trading_day`, `next_trading_day`, `decision_days(horizon, start, end)` correct on a fixture holiday list; holidays live in config, not code.
- Notes: Vietnamese market holidays vary by year; keep a `holidays:` list per year in config and a test that fails if the current year has no list.

### M1.1 — Data

**P1-T36 — DataSource protocol, market store and synthetic market** *(added by ADR-006)* · card: [P1-T36](../cards/P1-T36-datasource-synthetic.md)
- Depends on: P1-T02
- Goal: the `DataSource` protocol of P1-T03 plus `SyntheticSource`: a deterministic, seeded market for the default universe (daily OHLCV and volume, HOSE price limits and tick sizes, lots, suspensions, corporate-action events, regime changes), written to the same tables real data will use.
- Acceptance: same seed → byte-identical output; every generated price respects the reference ±limit and the tick grid; corporate-action events are listed with their dates; data is labelled synthetic in tables and reports; no network access.

**P1-T37 — YahooSource adapter** *(added by ADR-007)* · card: [P1-T37](../cards/P1-T37-yahoo-source.md)
- Depends on: P1-T36
- Goal: optional `[yahoo]` adapter for daily prices of the universe, labelled interim and `split_adjusted`; filler rows and partial bars dropped; terms notice; no Yahoo access from tests or CI.

**P1-T38 — Data-quality checks v0, gap register, `data status`** *(added by ADR-007)* · card: [P1-T38](../cards/P1-T38-quality-gaps.md)
- Depends on: P1-T37
- Goal: quality checks after each ingest (severity by `price_basis`), `dq_results`, gap register loader, `vnstratlab data status` / `data gaps`.

**P1-T03 — Source adapter and price ingestion** · **replaced by P1-T36 + P1-T37 (ADR-007)**
- Depends on: P1-T02
- Goal: `DataSource` protocol with a `VnstockSource` implementation; ingest daily OHLCV for the universe into `prices_daily`, raw responses saved to `data/raw/` as Parquet.
- Acceptance: backfill from a configurable start date (default 2015-01-01) is idempotent (re-run creates no duplicates); rate limit respected (configurable, default 50 calls/min); network failures retried with backoff and logged; unit tests use recorded fixtures.
- Notes: check the installed vnstock version's API before coding; do not assume function names from older docs.

**P1-T04 — Foreign and proprietary flow availability check**
- Depends on: P1-T03
- Goal: find whether daily foreign net buy/sell per ticker is available from vnstock or another free source with acceptable terms.
- Output: `docs/reports/P1-T04-flow-data.md` with source, history depth, terms; ingestion only if available.
- Acceptance: report exists; if no source, S06 is marked `disabled` in config with the reason.

**P1-T05 — Universe membership history**
- Depends on: P1-T02
- Goal: populate `universe_membership` for VN30 banks back to the backfill start, from HOSE review announcements.
- Acceptance: table has `source_url` per row; the engine reads membership by date; a test checks TPB is a member on 2026-07-31 and not on 2026-08-03. Where history cannot be found, rows are absent and the engine logs `survivorship_warning`.
- Notes: the owner may need to supply announcements; report gaps instead of guessing.

**P1-T06 — Corporate actions and adjusted prices**
- Depends on: P1-T03
- Goal: ingest cash dividends, stock dividends, bonus shares, rights; compute `prices_adjusted`.
- Acceptance: on a synthetic fixture with a 10% stock dividend the adjusted series has no artificial −9% gap; raw prices are never overwritten; test for a cash dividend.

**P1-T07 — Fundamentals with publish dates**
- Depends on: P1-T03
- Goal: quarterly bank metrics (equity, net income, ROE, NPL ratio, NPL coverage, loans, NIM if available) into `fundamentals_q`.
- Acceptance: every row has `published_at` or a flagged fallback (quarter end + 45 days); a test proves a feature at date t never reads a row with `published_at > t`.

**P1-T08 — Data-quality checks**
- Depends on: P1-T03, P1-T06
- Goal: checks run after ingestion; the daily loop stops on a failure.
- Checks: missing tickers for the day; close outside [floor, ceiling]; zero volume on a trading day; day-over-day adjusted change > 15%; duplicate rows; stale data (latest date < today on a trading day).
- Acceptance: each check has a failing fixture; failures are written to a `dq_results` table and trigger a Telegram error message (stubbed in tests).

**P1-T09 — Passive raw news collector**
- Depends on: P1-T03
- Goal: daily collection of company news for the universe into `news_raw`. **No scoring, no features, no signal use.**
- Acceptance: dedup by `news_id` or URL hash; `published_at` and `collected_at` both stored; collection failure never stops the daily loop (warning only).

### M1.2 — Features

**P1-T10 — Feature store v1**
- Depends on: P1-T06, P1-T07, P1-T08
- Goal: `features_daily` with the groups in the design doc: trend and momentum (vs. MA20/MA50; returns 5/20/60/120/250 days; distance to 52-week high/low), relative strength vs. group median and rank, mean reversion (RSI-14, z-score vs. MA20), volatility (ATR-14, 20-day std), volume (vs. 20-day avg), valuation (P/B, E/P, P/B gap vs. ROE-justified P/B), asset quality (NPL, coverage, ROE), market context (VN30 vs. MA50, bank-group breadth).
- Acceptance: `feature_version` stored; recomputing a past date gives identical values; a test truncates data at t and verifies features at t are unchanged (no lookahead).

### M1.3 — Engine

**P1-T11 — Simulator core (SimExecutor)**
- Depends on: P1-T02, P1-T36 (was P1-T06; ADR-006), ADR-003 (accepted in part) · card: [P1-T11](../cards/P1-T11-simulator-core.md)
- Goal: event loop that turns target weights into orders and fills.
- Rules: decision at close of t, fill at open of t+1; no buy fill if open at ceiling, no sell fill if open at floor; sell allowed only from the configured settlement offset; round to lots (odd lots per config with odd-lot slippage); tick rounding for limit prices; fees, sales tax, slippage per Appendix A.
- Outputs: per-period ideal and executable returns, positions, turnover.
- Acceptance: hand-computed test cases for each rule (at least 10 cases), including: buy Monday then sell signal Tuesday → sell executes no earlier than the settlement date; 11,000,000 VND cannot buy 3 round lots of a 52,700 VND stock; ceiling-open blocks a buy.

**P1-T12 — Risk layer**
- Depends on: P1-T11
- Goal: position sizing (1% equity at risk to ATR stop), max positions, max weight per ticker, volatility scaling of total equity exposure, circuit breaker (−10% from peak → no new buys and alert).
- Acceptance: unit tests for each limit; risk layer never increases a weight a strategy did not request.

### M1.4 — Strategies

**P1-T13 — Strategy base, registry and trial log**
- Depends on: P1-T10
- Goal: `Strategy` protocol (5.4), registry loading strategies and param sets from config, `trial_registry` writes.
- Acceptance: running a backtest for an unregistered (strategy, params) raises an error; trial count query works.

**P1-T14 … P1-T19 — Implement strategies** (one card per 2–3 strategies)
- T14: S00, S17 · T15: S01, S02, S03 · T16: S04, S05 · T17: S08, S09, S13 · T18: S10, S11, S12 · T19: S14, S15, S18 (S06 only if P1-T04 found data)
- Acceptance per strategy: long-only weights ≤ 1; uses only data ≤ asof (test); deterministic; a docstring citing the rule and basis from section 7; a smoke backtest runs on fixture data.

### M1.5 — Lab

**P1-T20 — Walk-forward runner**
- Depends on: P1-T11, P1-T13
- Goal: produce OOS return series per trial with expanding or rolling windows; for any fitted component, purge and embargo equal to label length.
- Acceptance: OOS returns at period p depend only on data before p (test with a strategy that cheats by peeking — it must be detected or impossible).

**P1-T21 — Metrics: Sharpe, Deflated Sharpe, PBO**
- Depends on: P1-T20
- Goal: implement DSR (Appendix C) and PBO via combinatorially symmetric cross-validation.
- Acceptance: on 50 synthetic zero-edge strategies, the best has DSR < 0.95 in ≥ 90% of 200 seeds; on a synthetic strategy with strong edge, DSR > 0.95; PBO on pure noise ≈ 0.5 (tolerance documented).

**P1-T22 — Gates, MCS and weights**
- Depends on: P1-T21
- Goal: the selection cycle in the design doc: gate 1 (DSR, PBO, min periods) → gate 2 (SPA vs. equal weight) → MCS → Hedge weights shrunk toward equal weight with cap → `selection_runs`. Empty selection = `hold_benchmark`.
- Acceptance: uses `arch.bootstrap.SPA` and `MCS` (check signatures against the installed version); unit test on synthetic data where one strategy dominates → it gets the largest weight but ≤ cap; when nothing beats equal weight → `hold_benchmark`.

**P1-T23 — Meta-backtest of the lab**
- Depends on: P1-T22
- Goal: run the lab historically as if live (walk-forward over decision days) and compare to (a) equal weight of all strategies, (b) pick last period's winner, (c) S17 equal-weight stocks. Executable returns, after costs.
- Output: `docs/reports/meta-backtest-<horizon>.md` with tables: annual return, max drawdown, Sharpe, turnover, number of decisions.
- Acceptance: report generated for all three horizons; long horizon report states the number of independent decisions explicitly.

### M1.6 — Paper books and daily loop

**P1-T24 — PaperExecutor and books**
- Depends on: P1-T12, P1-T22
- Goal: three books (short, medium, long), 11,000,000 VND each, driven by the latest selection; same rules as SimExecutor; equity written to `book_equity` daily.
- Acceptance: restart-safe (state comes from journal, not memory); a replay of 20 fixture days reproduces the same equity curve.

**P1-T25 — Recommendations journal**
- Depends on: P1-T24
- Goal: append-only `recommendations` with fields: horizon, asof, status, targets (ticker, weight, lot qty, entry zone, stop), contributing strategies and weights, consensus, evidence (SPA p, DSR per member, trial count).
- Acceptance: an update attempt raises; rows are written before the next session (timestamp check).

**P1-T26 — `daily` orchestration**
- Depends on: P1-T08 … P1-T25
- Goal: one command running the loop of 5.1 (Phase 1 steps), with step timing logs and stop-on-DQ-failure.
- Acceptance: `--dry-run` prints all outputs and writes nothing; a failed step sends an alert and leaves previous day's state intact.

### M1.7 — UI and notifications

**P1-T27 — FastAPI endpoints**
- Depends on: P1-T26
- Endpoints: `/api/overview`, `/api/ranking?date=`, `/api/stocks/{symbol}/prices`, `/api/stocks/{symbol}/features`, `/api/lab/leaderboard?horizon=`, `/api/lab/recommendation?horizon=`, `/api/lab/weights?horizon=`, `/api/lab/trials`, `/api/books/{horizon}`, `/api/system/health`.
- Acceptance: Pydantic response models; read-only connections to DuckDB; TestClient tests per endpoint on a fixture DB; bound to 127.0.0.1.

**P1-T28 — Web UI (5 pages)**
- Depends on: P1-T27
- Pages: Tổng quan hôm nay (`index.html`), Xếp hạng mã (`stock.html`), Phòng lab (`lab.html`), Danh mục giả lập (`book.html`), Sức khỏe hệ thống (`health.html`).
- Acceptance: no framework, no external scripts; charts in plain SVG (price with signal markers, equity curves, strategy weights over time); works offline on localhost; Vietnamese labels.

**P1-T29 — Telegram daily report**
- Depends on: P1-T26
- Goal: one message per evening: per horizon status (propose / hold benchmark), targets, book equity vs. benchmark, DQ status.
- Acceptance: message template tested with fixtures; token from env; send failure logged, does not fail the loop.

### M1.8 — Operations

**P1-T30 — Scheduling, backups, logs**
- Depends on: P1-T26
- Goal: run `daily` on trading days at 15:30 via cron (Linux/macOS) or Task Scheduler (Windows), whichever the laptop uses; nightly backup of `data/` (keep 14 days); rotating logs.
- Acceptance: documented setup steps in README; a missed run (laptop off) is detected next run and backfilled.

### M1.9 — Stretch (does not block Phase 1 exit)

**P1-T31 — LightGBM ranking strategies S07, S16**
- Depends on: P1-T20
- Goal: cross-sectional rank of 13 stocks by forward relative return (5 and 60 sessions), purged CV, used as meta-label filter for S01–S05 (S07) and standalone (S16).
- Acceptance: registered as trials like any other; included in gates; no special treatment.

---

## 9. Phase 2 — News parameter evaluation

**Goal.** Decide, with a pre-registered test, whether a news-based parameter improves results enough to keep. The output is a decision record, not necessarily a new feature in production.

**Entry criteria.** Phase 1 exit criteria met; `news_raw` has at least 60 trading days of forward collection.

**Key risks this phase must control.**
- **LLM lookahead:** a model trained on later data may "know" what happened. Only score news collected forward in real time (from P1-T09 onward); never ask the model about prices or outcomes; pin the model version.
- **Low statistical power:** 13 stocks and a few months of news give few events. The decision rule must allow "insufficient evidence → reject for now, keep collecting".
- **Trial inflation:** every news variant is a new trial and raises the DSR bar for all strategies.

**Exit criteria.** `docs/adr/ADR-002-news-parameter.md` written with the decision (adopt / reject / extend collection), the evidence, and the date of the next review if not adopted.

**P2-T01 — Pre-registration (owner + manager)**
- Goal: before any scoring results are seen, write `docs/adr/ADR-002-news-parameter.md` (status: proposed) with: the exact news features, the variants to test, the test statistic, thresholds, minimum sample, and the decision rule below. Commit it.
- Decision rule (default, owner may edit before results exist):
  - Adopt only if all hold: (1) at least 60 trading days of scored forward news and at least 30 news events on universe tickers; (2) the "+news" variant of the chosen strategies passes gate 1 and is in the MCS; (3) the paired difference in daily executable excess return (B − A) has one-sided block-bootstrap p < 0.10; (4) max drawdown of B is not worse than A by more than 1 percentage point; (5) LLM cost < 2 USD/month.
  - Otherwise reject for now and re-evaluate after 3 more months of data.

**P2-T02 — News normalization**
- Depends on: P1-T09
- Goal: dedupe across sources, map to tickers (handle bank names and abbreviations), assign `effective_date` (published after 14:45 → next trading day).
- Acceptance: test cases for ticker mapping and cutoff; unmapped items kept with `ticker = null`.

**P2-T03 — LLM scoring service**
- Depends on: P2-T02
- Goal: nightly batch scoring with a small model (default Claude Haiku); prompt stored in `news/prompts/score_v1.md`; output validated against a JSON schema: `event_type` (enum: earnings, capital_raise, dividend, management_change, regulatory_action, credit_quality, mna, other), `direction` (−1/0/+1), `magnitude` (0–3), `confidence` (0–1), `rationale` (≤ 200 chars).
- Acceptance: invalid outputs retried once then stored as `failed`; scores stored with `model_id`, `prompt_version`, `scored_at`; cost per run logged; cache prevents re-scoring; prompt never includes price data.

**P2-T04 — News features**
- Depends on: P2-T03
- Features per ticker-day: net direction score (1/5/20 days), count of negative high-magnitude events (5 days), abnormal news count vs. 60-day average, days to next known scheduled event.
- Acceptance: point-in-time test (feature at t uses only `effective_date ≤ t`).

**P2-T05 — Information coefficient study**
- Depends on: P2-T04
- Goal: rank IC of each news feature vs. forward 1/5/20-day relative returns, monthly, with block-bootstrap confidence intervals.
- Output: `docs/reports/P2-T05-news-ic.md`.
- Acceptance: report states sample sizes and does not claim significance beyond what the intervals show.

**P2-T06 — Variants and shadow books**
- Depends on: P2-T04, P2-T01
- Goal: register "+news" variants exactly as pre-registered (default: a veto filter that blocks new buys when the 5-day negative high-magnitude count ≥ 1, applied to S00–S05 and S08). Run shadow paper books A (current) and B (+news) per horizon from the same start date.
- Acceptance: variants appear in `trial_registry` with `rationale = "ADR-002"`; A and B share everything except the news filter (test).

**P2-T07 — Evaluation and decision**
- Depends on: P2-T05, P2-T06, minimum sample reached
- Goal: compute the statistics in the decision rule; fill in ADR-002 (status: accepted/rejected).
- Acceptance: numbers in the ADR are reproducible by a script in `notebooks/`; the owner signs off.

**P2-T08 — UI and report**
- Depends on: P2-T03
- Goal: news panel on the stock page (headline, score, rationale); Telegram report adds a line for high-magnitude events. Display only; affects signals only if ADR-002 is accepted.

---

## 10. Phase 3 — Portfolio optimisation (recommend-only)

**Goal.** Turn the lab's selected strategies and signals into a recommended portfolio for the user's own capital, with lot-aware quantities, entry zones and stops, and let the user track what they actually did against what was recommended. The system never places orders.

**Entry criteria.**
1. At least 3 months of Phase 1 paper books after Phase 1 exit.
2. Meta-backtest (P1-T23) and stress tests (P1-T33) reported for every horizon.
3. ADR-002 decided.

**P3-T01 — Optimiser library**
- Goal: shrinkage mean-variance (Ledoit-Wolf covariance), Hierarchical Risk Parity, risk parity, and Black-Litterman using lab signals as views; long-only, max weight per ticker, turnover penalty.
- Acceptance: each optimiser tested on synthetic data with known solutions; deterministic; registered as trials and evaluated through the lab like any strategy.

**P3-T02 — Lot-aware allocation**
- Goal: convert target weights into share quantities for the user's capital with round lots, odd lots, tick-valid limit prices and costs; minimise tracking error to target weights.
- Acceptance: hand-computed cases (e.g. 11,000,000 VND cannot buy 3 round lots of a 52,700 VND stock); never exceeds available cash after costs.

**P3-T03 — Recommendation card v2**
- Goal: per horizon: tickers, quantities, entry zone, stop, expected holding period, contributing strategies, evidence (DSR, SPA p, MCS), benchmark comparison, and "hold benchmark" when nothing qualifies. Dashboard and Telegram.
- Acceptance: card text in Vietnamese; every number traceable to the journal; includes the not-investment-advice notice.

**P3-T04 — User-recorded fills**
- Goal: the user records the orders they actually placed (dashboard form or CSV import); stored in the journal, separate from paper fills.
- Acceptance: append-only; validated against lot and tick rules; no broker connection.

**P3-T05 — Real vs. recommended tracking**
- Goal: compare the user's real portfolio with the recommended and paper portfolios: return gap, slippage vs. recommended entry, missed and extra trades.
- Acceptance: monthly report in the app home; slippage feeds a **proposed** cost recalibration the user approves (never auto-applied).

**P3-T06 — Optimiser evaluation**
- Goal: meta-backtest each optimiser vs. lab weights and vs. equal weight, after costs, with stress tests.
- Acceptance: report states whether optimisation adds value over the simpler lab weights; if not, the simpler method stays the default.

---

## 11. Timeline (indicative)

| Period | Work |
| --- | --- |
| Weeks 1–2 | M1.0, M1.1 (data, DQ, passive news collection starts) |
| Weeks 3–4 | M1.2 features, M1.3 engine |
| Weeks 5–6 | M1.4 strategies, M1.5 lab |
| Weeks 7–8 | M1.6 paper books, M1.7 UI and Telegram, M1.8 ops |
| Weeks 9–10 | Buffer, Phase 1 exit check, M1.9 stretch |
| Months 3–5 | Nightly paper run (evidence for Phase 3); Phase 2 tasks P2-T01–T06 once 60 days of news exist |
| Month 6 | P2-T07 decision; Phase 3 entry review |
| Month 6+ | Phase 3: portfolio optimisation (v0.5) |

---

## 12. Risks and open questions

| Risk / question | Mitigation / owner action |
| --- | --- |
| vnstock source changes or breaks | **Happened 2026-11-10** (ADR-006): synthetic data first; adapter interface; raw data kept; DQ stops the loop |
| No free foreign-flow data | S06 disabled (P1-T04) |
| VN30 membership history incomplete | P1-T05 reports gaps; owner supplies announcements |
| Laptop off at run time | Missed-run detection and backfill (P1-T30); user VPS option |
| Lot size with 11,000,000 VND | Ideal vs. executable returns (section 4); odd lots allowed |
| Overfitting through repeated tweaks | Trial registry, DSR with total trial count, frozen params (rule 6.4.3) |
| Long horizon has ~8 independent decisions in 8 years | Long book defaults to equal weight across 2–4 economically grounded strategies; lab used to drop broken ones only |
| News evaluation has low power | Pre-registered rule with "extend collection" outcome (P2-T01) |
| Recommendations mistaken for advice | DISCLAIMER.md and a notice on every recommendation card; recommend-only by design (ADR-001) |
| Data source licence (e.g. vnstock terms) | Licence review before integration; no redistribution (docs/data-sources.md) |
| DuckDB single-writer locking | Loop runs inside `serve`; CLI `daily` refuses while `serve` runs |
| Amended Securities Law (passed Nov 2026) | Owner checks whether publishing recommendation software raises obligations |

---

## Appendix A — `config.yaml` skeleton

```yaml
project:
  timezone: Asia/Ho_Chi_Minh
  backfill_start: 2015-01-01

universe:
  index: VN30
  sector: banks
  membership_table: universe_membership   # never a hard-coded list

market_rules:                  # all [VERIFY]; now in src/vnstratlab/config/markets/hose.yaml
  settlement_sell_offset_days: 3
  price_limit_pct: 0.07
  round_lot: 100
  allow_odd_lot: true
  tick_sizes: [[0, 10], [10000, 50], [50000, 100]]
  sessions: {ato: "09:00-09:15", continuous: ["09:15-11:30", "13:00-14:30"], atc: "14:30-14:45"}
  holidays: {2026: [], 2027: []}         # fill per year

costs:
  brokerage_fee_pct: 0.0015
  sales_tax_pct: 0.001
  slippage_pct: {round_lot: 0.001, odd_lot: 0.003}

books:
  short:  {capital_vnd: 11000000, decision_day: last_trading_day_of_week}
  medium: {capital_vnd: 11000000, decision_day: last_trading_day_of_month, tranches: 3}
  long:   {capital_vnd: 11000000, decision_day: last_trading_day_of_month, tranches: 12}   # ADR-005

risk:
  risk_per_position_pct: 0.01
  atr_stop_multiple: 2.0
  max_positions: 4
  max_weight_per_ticker: 0.35
  circuit_breaker_drawdown_pct: 0.10
  rebalance_threshold_pct: 0.10
  vol_target_annual: null      # set after Phase 1 study; null = off

lab:
  seed: 20261117
  gate1: {dsr_min: 0.95, pbo_max: 0.5, min_periods: {short: 52, medium: 24, long: 4}}
  gate2: {spa_alpha: 0.10, bootstrap_reps: 2000, block_size: {short: 4, medium: 3, long: 1}}
  mcs_alpha: 0.10
  weights:
    short:  {window: 52, lambda: 0.5,  eta: 2.0, max_weight: 0.4}
    medium: {window: 36, lambda: 0.75, eta: 1.0, max_weight: 0.4}
    long:   {window: null, lambda: 1.0, eta: null, max_weight: 0.5}
  decay: {short_window: 26, medium_window: 12}
  challenger_min_periods: {short: 13, medium: 6}

strategies:                    # params frozen; new params = new trial
  S02_breakout20: {horizons: [short], params: [{lookback: 20, vol_mult: 1.5}]}
  # ... one entry per strategy in section 7
  S06_foreign_flow: {enabled: false, reason: "pending P1-T04"}

news:
  collect_raw: true            # Phase 1: collect only
  use_in_signals: false        # only ADR-002 may set true
  cutoff_time: "14:45"

notify:
  telegram_chat_id_env: TELEGRAM_CHAT_ID
  telegram_token_env: TELEGRAM_BOT_TOKEN
```

## Appendix B — Selection cycle (reference)

```python
# vnstratlab/lab/selector.py - one selection cycle for one horizon (reference sketch)
import numpy as np
import pandas as pd
from arch.bootstrap import SPA, MCS  # verify signatures against the installed arch version

def select(oos: pd.DataFrame, bench: pd.Series, n_trials: int, cfg) -> pd.Series:
    """oos: out-of-sample period returns net of costs, one column per strategy.
    Returns strategy weights; an empty Series means 'hold the equal-weight benchmark'."""
    keep = [s for s in oos.columns if deflated_sharpe(oos[s], n_trials) >= cfg.dsr_min]
    if not keep:
        return pd.Series(dtype=float)

    window = oos[keep].iloc[-cfg.window:]
    excess = window.sub(bench.reindex(window.index), axis=0)

    # Gate 2: does the best surviving strategy beat equal weight? (losses = -excess)
    spa = SPA(pd.Series(0.0, index=excess.index), -excess, reps=cfg.reps, block_size=cfg.block)
    spa.compute()
    if spa.pvalues["consistent"] > cfg.spa_alpha:
        return pd.Series(dtype=float)

    mcs = MCS(-excess, size=cfg.mcs_alpha, reps=cfg.reps, block_size=cfg.block)
    mcs.compute()
    members = list(mcs.included)

    sharpe = window[members].mean() / window[members].std()
    hedge = np.exp(cfg.eta * sharpe)
    hedge /= hedge.sum()
    weights = cfg.lam / len(members) + (1 - cfg.lam) * hedge
    return cap_and_renormalise(weights, cfg.max_weight)
```

Weight formula: `w_i = λ / |M| + (1 − λ) · exp(η·S_i) / Σ_j exp(η·S_j)` for `i` in the MCS set `M`, capped at `max_weight` and renormalised.

## Appendix C — Deflated Sharpe Ratio (implement, then verify against Bailey & López de Prado, 2014)

For an observed (non-annualised) Sharpe `SR` over `T` periods, with return skewness `γ3` and kurtosis `γ4`, and `N` trials whose Sharpe ratios have variance `V`:

```
SR0 = sqrt(V) * ((1 - γ) * Φ⁻¹(1 - 1/N) + γ * Φ⁻¹(1 - 1/(N·e)))      # γ ≈ 0.5772 (Euler–Mascheroni)
DSR = Φ( (SR - SR0) * sqrt(T - 1) / sqrt(1 - γ3·SR + (γ4 - 1)/4 · SR²) )
```

Acceptance tests for this function are in P1-T21. Cite the paper in the docstring and verify the formula against it before relying on results.

## Appendix D — Glossary (Vietnamese ↔ English)

| Vietnamese | English / code name |
| --- | --- |
| Mã, cổ phiếu | ticker |
| Phiên | trading session / trading day |
| Giá tham chiếu, trần, sàn | reference price, ceiling, floor |
| Lô chẵn, lô lẻ | round lot, odd lot |
| Khối ngoại, tự doanh | foreign investors, proprietary trading |
| Nợ xấu, bao phủ nợ xấu | NPL ratio, NPL coverage |
| Chốt quyền, cổ tức cổ phiếu, cổ phiếu thưởng | record date, stock dividend, bonus shares |
| Phòng lab chiến lược | strategy lab |
| Sổ lệnh giả lập, danh mục giả lập | paper book |
| Cổng kiểm định | gate |
| Giữ mốc chia đều | hold_benchmark |
| Ngắt mạch | circuit breaker |
| Đối chiếu | reconciliation |
| Trượt giá | slippage |
