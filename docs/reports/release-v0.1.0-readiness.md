# Release v0.1.0 readiness

- Date / analyst / commit: 2026-11-26 / Reality Analyst (G3, AI agent) / `release/v0.1.0` at
  `0898969` (CI run 45809703810 green on that commit)
- Scope: lean G3 (owner decision 2026-11-26). G3.1 to G3.3 are N/A because their tools ship in
  v0.2. A reduced engine sanity check, a real-data sanity run and release hygiene replace them.
- Verdict: **Not ready.** Three things block it, and all three are small fixes on the release
  branch (C1 to C3 below). When they are done, the release is **Ready with conditions**, and the
  conditions are the disclosures listed under "Recommendation to owner".
- Summary:
  1. The engine is correct and deterministic on the case we checked by hand. Two demo runs gave
     byte-identical `summary.csv` and 19 equity files. A full replay of S17 matched every fill,
     fee, tax, T+3 settlement and cash bucket to 0 VND.
  2. Hygiene fails. The version is still `0.0.1`, no rc exists on TestPyPI, and the README still
     describes the scaffold. The built wheel installs and runs cleanly, and the Console works
     end to end.
  3. On real data, the risk layer's circuit breaker never turns off once it has moved the book to
     cash. On interim Yahoo data, S17 with the risk layer has held only cash since 2018-12-28.
     This does not change any v0.1.0 result. It must be decided before the v0.2 backtests.

## G3.1 Benchmarks

**N/A for v0.1.0.** Lab benchmarks per horizon need the walk-forward runner and the lab report,
P1-T20 (`backtest`, issue #78) and P1-T22/P1-T23 (lab, meta-backtest), all planned for v0.2.0.
No lab result exists yet. Instead there is a real-data sanity run (interim Yahoo data). It is not
a benchmark result.

### Real-data sanity run: interim Yahoo data, survivorship-biased (GAP-13), not evidence

Setup:
- Source: the owner's local store, opened read-only. Only aggregate numbers are shown here.
- Packaged config with no user overrides.
- Simulation: executable mode, round lots and odd lots, 11,000,000 VND per book, costs from
  config.
- Calendar: built from observed sessions, because there are no holiday lists before 2026 (GAP-05).
- Rows marked "+risk" use the risk layer exactly as `demo` does. Rows marked "no-risk" are plain
  target weights.
- Buy-and-hold: 1/N of the tickers with features on the first decision day, bought once at the
  next open, never rebalanced, with costs. Dividends stay in cash.
- No confidence intervals were computed. Do not read any difference below as significant.

**Window B: 2023-09-05 to 2026-11-25.** 772 sessions (about 3.1 years). All 14 tickers have
features from 2023-08-23, so buy-and-hold covers the same universe as S17.

| Trial | Horizon | Decisions | Total | CAGR | Vol | Sharpe | Max DD | Trades |
|---|---|---|---|---|---|---|---|---|
| Buy-and-hold 1/N (14 tickers), executable | – | 1 | +43.7% | 12.6% | 19.5% | 0.70 | -18.9% | 14 |
| S17 equal weight, no-risk | short | 165 | +37.6% | 11.0% | 19.9% | 0.62 | -20.3% | 1,210 |
| S17 equal weight, no-risk | medium | 37 | +57.6% | 16.0% | 19.3% | 0.87 | -20.3% | 366 |
| S17 equal weight, +risk | short | 165 | +14.5% | 4.5% | 6.1% | 0.76 | -6.0% | 65 |
| S17 equal weight, +risk | medium | 37 | +16.7% | 5.2% | 6.1% | 0.85 | -6.1% | 29 |
| S08 momentum L=6m, no-risk | medium | 37 | +23.1% | 7.0% | 19.0% | 0.45 | -28.0% | 201 |
| S08 momentum L=12m, no-risk | medium | 37 | +14.8% | 4.6% | 18.8% | 0.33 | -22.3% | 178 |
| S08 momentum L=6m, +risk | medium | 37 | +7.0% | 2.2% | 9.1% | 0.29 | -12.5% | 100 |
| S08 momentum L=12m, +risk | medium | 37 | -8.1% | -2.7% | 9.8% | -0.23 | -17.4% | 90 |

**Window A: 2017-01-03 to 2026-11-25.** 2,390 sessions (about 9.6 years). The universe grows over
this window: it has 5 tickers with features on 2017-01-13 and 14 by 2023-08. Buy-and-hold holds
the first 5 only, so this window is **not** a like-for-like comparison.

| Trial | Horizon | Decisions | Total | CAGR | Vol | Sharpe | Max DD |
|---|---|---|---|---|---|---|---|
| Buy-and-hold 1/N (5 tickers from 2017-01-13) | – | 1 | +390% | 18.3% | 26.4% | 0.77 | -42.8% |
| S17 equal weight, no-risk | short | 511 | +320% | 16.3% | 25.0% | 0.73 | -50.1% |
| S17 equal weight, no-risk | medium | 117 | +307% | 16.0% | 24.3% | 0.73 | -48.5% |
| S17 equal weight, +risk | short | 511 | +38.6% | 3.5% | 6.6% | 0.56 | -16.6% |
| S08 momentum L=6m, +risk / no-risk | medium | 117 | +54% / +256% | 4.7% / 14.3% | – | 0.72 / 0.69 | -14.1% / -41.0% |
| S08 momentum L=12m, +risk / no-risk | medium | 117 | +36% / +124% | 3.3% / 8.9% | – | 0.55 / 0.47 | -12.3% / -45.3% |

What these runs show (descriptive only):

- **Friction.** Execution friction costs S17 short between 1.4 and 1.9 pp of CAGR at
  11,000,000 VND. Ideal mode gave 12.4% (window B) and 18.2% (window A), against 11.0% and 16.3%
  executable.
- **Equal weight vs. buy-and-hold.** In window B neither S08 trial beats buy-and-hold of the
  universe, with or without the risk layer. Only S17 medium without the risk layer is above it.
  That rests on 37 monthly decisions with no confidence interval, so it is not evidence.
- **The risk layer.** It changes everything here, because the circuit breaker cannot turn off
  once the book is in cash (see Risks, R1). In window A, S17 short +risk triggered the breaker on
  2018-05-08 and sold its last position on 2018-12-28. It then held only cash for about 8 years.
  The 4.5% / 3.5% CAGR of the "+risk" rows is mostly idle cash.
- **Medium and long are identical.** Both decide on the same month-end sessions, and the tranches
  in ADR-005 are not built yet. The demo therefore prints duplicate S17 medium/long rows too.
- **Number of independent decisions.**
  - Window B: short 165 (weekly), medium 37 (monthly), long 37 monthly decisions but only about
    3 non-overlapping 1-year outcomes.
  - Window A: 511 / 117 / about 9.

### Real data status (owner's store, read-only)

**Store:** `market.duckdb` (real), interim Yahoo source.
- 14 tickers (VN30 banks) and 31,375 price rows from 2015-01-01 to 2026-11-25.
- Derived tables:
  - `prices_exec`: 27,583 rows (2015-01-05 to 2026-11-25).
  - `features_daily`: 27,593 rows, one version (`features-v5:62d0433f62e8`).
- 142 corporate actions (61 cash, 81 stock).
- Rebuilt through the last run.

**Ingest runs:**

| Run | Range | Written / changed / dropped | Status |
|---|---|---|---|
| 2026-11-19 full backfill | 2015-01-01 to 2026-11-19 | 31,333 / 0 / 2,453 | `failed_dq` |
| 2026-11-26 refresh | 2026-11-13 to 2026-11-26 | 56 / 14 / 28 | `ok_with_warnings` |

**DQ, last run:** 0 errors and 14 warnings. All 14 are `missing_ticker` for **2026-11-24**, a
Tuesday. Every ticker lacks that session (`prices_daily` has 0 rows that day), so the whole
market day is missing. This probably comes from the Yahoo Tuesday-duplicate pattern (GAP-07);
that cause is not verified. Simulations treat 2026-11-24 as a non-session.

**DQ, full backfill:**
- 15 `ohlc_inconsistent` errors across 12 tickers. These rows are excluded as `dq_error`.
- Warnings:

  | Check | Warnings |
  |---|---|
  | `repeated_bar` | 444 |
  | `close_outside_limits` | 26 |
  | `off_tick` | 21 |
  | `missing_ticker` | 14 |
  | `large_move` | 9 |
  | `zero_volume` | 8 |

**Execution exclusions** (rows):

| Kind | Rows | Detail |
|---|---|---|
| `duplicate_session` | 442 | |
| `scale_step_before` | 1,973 | HDB 1,290, LPB 662, SHB 13, VIB 8 |
| `non_hose_history` | 1,349 | SHB |
| `dq_error` | 15 | |
| `no_reference` | 10 | |
| `scale_outlier_row` | 3 | |

No ticker is excluded entirely. The HDB and LPB cuts are why the full 14-ticker cross-section
only starts in 2023-08.

**Open gaps:** 13 (3 high, 8 medium, 2 low).
- High: GAP-01 (no raw prices), GAP-11 (no bank fundamentals), GAP-14 (no exact price-board match
  on adjusted history).
- Medium: GAP-02, GAP-03, GAP-04, GAP-05, GAP-06, GAP-07, GAP-09, GAP-13.
- Low: GAP-10, GAP-12.

## G3.2 Cross-engine check

**N/A for v0.1.0.** The vectorbt/backtrader harness is P1-T34 (v0.2.0). A reduced engine sanity
check replaces it.

### Determinism

`vnstratlab demo --out` was run twice, in separate temp homes.

| Check | Result |
|---|---|
| Both runs exited 0 | 19 trials, 0 skipped; 32.7 s and 38.4 s |
| `summary.csv` | Identical. SHA-256 `385f273c…fd660b` both times |
| `equity/*.csv` | `diff -r` reports no differences (19 files) |

### Hand check: S17 equal weight, short horizon (SYNTHETIC)

Setup:
- Synthetic market, window 2016-01-01 to 2016-03-31: 65 sessions, 13 weekly decisions, 14
  tickers.
- Executable mode, lots and odd lots, 11,000,000 VND.
- Costs: fee 0.15% on both sides, sales tax 0.1% on sells, slippage 0.1% on round lots and 0.3%
  on odd lots.
- Selling allowed from T+3, and sale proceeds usable from T+3.

An independent replay recomputed every quantity from the simulator inputs.

| Check | Without risk layer (123 trades) | With risk layer, as in `demo` (28 trades) |
|---|---|---|
| Fill price = open × (1 ± slippage by lot type); notional, fee, tax (sells only), slippage | Max error 0 VND | Max error 0 VND |
| Lot types: round = multiple of 100; odd = 1–99 | All correct | All correct |
| No sell from shares bought fewer than 3 sessions earlier | 0 violations (smallest gap 5) | 0 violations (smallest gap 4) |
| `cash_available`, `cash_pending` (sale proceeds released at T+3; cash dividends at pay date) | Max error 0 VND; dividends 37,500 VND | Max error 0 VND |
| `positions_value` = Σ shares × close; equity = available + pending + positions | Max error 0 VND | Max error 0 VND |
| Cash never negative | Minimum 1,890 VND | Yes |
| Buy quantity ≤ floor(weight × equity / close at decision) | 0 violations | n/a (the risk layer resizes) |

Worked example: decision on 2016-01-01, 14 tickers at 1/14 each, fills at the 2016-01-04 open.

| Line | Close at decision | Target quantity | Open → fill price | Notional | Fee | Tax |
|---|---|---|---|---|---|---|
| ACB buy, 24 shares (odd lot) | 32,500 | floor(11,000,000/14/32,500) = 24 | 32,600 → 32,697.80 (+0.3%) | 784,747.20 | 1,177.12 | 0 |
| CTG sell, 1 share, on 2016-01-11 | – | – | – | 10,119.55 | 15.18 | 10.12 |

The CTG sale nets 10,094.25 VND, which is pending until 2016-01-14 (T+3). The simulator matched
all of these exactly.

The calendar used for the synthetic run treats 2016-01-01 as a session, because there are no
holiday lists before 2026 (GAP-05). This does not matter for synthetic data.

### Per-trial demo table (SYNTHETIC)

**SYNTHETIC DATA: these results say nothing about the real market.**

Window 2016-01-01 to 2020-12-31. Executable mode with the risk layer. Decisions: 261 short,
60 medium, 60 long.

| Trial | Horizon | CAGR | Vol | Sharpe | Max DD | Turnover | Trades |
|---|---|---|---|---|---|---|---|
| S00 composite, top_n=3, weights=equal | short | -2.3% | 2.1% | -1.09 | -11.4% | 0.511 | 74 |
| S00 composite, top_n=3, weights=trend_heavy | short | -2.2% | 2.1% | -1.09 | -11.4% | 0.510 | 74 |
| S01 weekly reversal, n=2 | short | -1.4% | 5.4% | -0.23 | -10.3% | 0.574 | 364 |
| S01 weekly reversal, n=3 | short | 0.2% | 6.4% | 0.07 | -10.9% | 0.678 | 425 |
| S02 breakout volume, lookback=20, max_n=3, vol_mult=1.5 | short | -1.4% | 2.8% | -0.50 | -8.9% | 0.341 | 102 |
| S03 oversold uptrend, rsi_len=14, rsi_max=30 | short | 0.0% | 0.0% | n/a | 0.0% | 0.000 | 0 |
| S03 oversold uptrend, rsi_len=2, rsi_max=10 | short | -0.8% | 3.3% | -0.24 | -11.1% | 0.427 | 150 |
| S04 bank pairs, entry_z=2.0, form=250, k=5, max_hold=10 | short | -1.5% | 4.0% | -0.36 | -11.0% | 0.209 | 160 |
| S05 residual reversion, entry_z=1.5, n=2, window=60 | short | -0.6% | 4.2% | -0.12 | -10.5% | 0.392 | 201 |
| S17 equal weight (benchmark) | short | 2.4% | 6.0% | 0.43 | -8.9% | 0.065 | 177 |
| S08 momentum, L_months=12, n=4 | medium | 5.1% | 11.4% | 0.49 | -14.9% | 0.289 | 139 |
| S08 momentum, L_months=6, n=4 | medium | 2.0% | 9.1% | 0.27 | -13.6% | 0.355 | 156 |
| S09 reversal, L_months=6, n=4 | medium | 3.1% | 8.3% | 0.42 | -10.3% | 0.369 | 145 |
| S14 low volatility, n=4, window=60 | medium | 4.1% | 7.8% | 0.56 | -11.0% | 0.340 | 126 |
| S15 sector trend, lookback_months=12 | medium | 2.2% | 5.1% | 0.45 | -10.7% | 0.090 | 108 |
| S15 sector trend, lookback_months=6 | medium | 0.8% | 4.8% | 0.19 | -8.3% | 0.098 | 125 |
| S17 equal weight (benchmark) | medium | 3.0% | 5.6% | 0.55 | -7.8% | 0.077 | 124 |
| S17 equal weight (benchmark) | long | 3.0% | 5.6% | 0.55 | -7.8% | 0.077 | 124 |
| S18 HRP, window=250 | long | 3.0% | 6.9% | 0.47 | -9.3% | 0.167 | 246 |

Notes:
- S03 with rsi_len=14 never trades on the synthetic market.
- S17 medium and long are identical by construction (G3.1 above).
- "S17 (benchmark)" runs through the risk layer. That layer caps it at 4 positions and applies
  ATR sizing, so it is **not** 1/N of the universe (R2).

## G3.3 Stress tests

**N/A for v0.1.0.** `vnstratlab stress` is P1-T33 (v0.2.0). Today the command prints "Not
implemented yet. Planned in task card P1-T33" and exits 1. The `stress:` config section exists,
with `regimes: []`.

| Test | Result | Pass/fail | Note |
|---|---|---|---|
| Higher costs ×2 / ×3 | not run | N/A | P1-T33 |
| Delayed fills (t+2) | not run | N/A | P1-T33 |
| Small capital, executable vs. ideal | partial | info | Real data, S17 short: 1.4 to 1.9 pp CAGR gap at 11 M VND (G3.1) |
| Liquidity (≤ 1% of ADV20) | not run | N/A | P1-T33 |
| Parameter noise ±20% | not run | N/A | P1-T33 |
| Regimes | not run | N/A | No regimes configured |
| Paper vs. backtest | not run | N/A | Paper books are v0.3 |

## G3.4 Product comparison

These are general features from each project's public documentation. They were **not**
re-verified against current versions for this lean release. The first full comparison comes
with v0.2, when vnstratlab has a backtest command.

| Tool | Type | HOSE rule realism | Overfitting controls | Transparency of evidence | Install / offline / cost |
|---|---|---|---|---|---|
| vnstratlab v0.1.0 | Open-source, recommend-only lab (Apache-2.0) | T+3 sellable, lots and odd lots, ticks, ±7% limits, fees, sales tax, proceeds delay (all [VERIFY]). Hand-checked (G3.2) | Trial registry and frozen params exist; DSR/PBO/SPA/MCS **not yet** (v0.2) | Synthetic demo only; no lab evidence yet; real data interim and survivorship-biased | `pip install`, offline, free |
| [vectorbt](https://github.com/polakowo/vectorbt) | Vectorised backtester (Apache-2.0 with Commons Clause) | None built in for HOSE; would need custom code | User's responsibility | User's responsibility | pip, offline, free (PRO is paid) |
| [backtrader](https://github.com/mementum/backtrader) | Event-driven backtester (GPL-3.0) | Generic broker model; HOSE rules custom | User's responsibility | User's responsibility | pip, offline, free; little maintenance |
| [QuantConnect Lean](https://github.com/QuantConnect/Lean) | Engine and cloud (Apache-2.0) | No Vietnamese market support known to us | Some research tooling | Cloud backtest reports | Heavier install; cloud data paid |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | RL for trading (MIT) | None for HOSE | Few by default | Paper-style examples | pip; GPU helps |
| Vietnamese broker screeners and signal tools | Commercial | Native market, but rules are opaque | Rarely disclosed | Usually none | Account required |

**Honest gap.** vnstratlab's distinctive parts are the statistical gate and the evidence. Neither
exists in v0.1.0. Today it is a HOSE-aware simulator with a strategy library and an offline demo.

## G3.5 Hygiene

### Release-specific checks

| Check | Result |
|---|---|
| Version | **Fail (C1).** `pyproject.toml` says `version = "0.0.1"`, and `__version__` comes from package metadata, so it is 0.0.1 too. `release.yml` stops any tag that differs from the pyproject version. Step 2 of git-branching §6 (`chore(release): v0.1.0`) has not been done. The analyst did not bump it. |
| CHANGELOG | Partial. An `[Unreleased]` section is ready to be renamed `[0.1.0] - <date>`. It repeats the `### Added` and `### Fixed` headings, which should be merged when it is renamed. It has no "Known limitations" entry for R1/R2. |
| TestPyPI rc in a clean venv | **Not done (C1).** No `v0.1.0rc1` tag exists, because the version is not bumped. |
| Substitute: locally built wheel | Pass. `python -m build` gave `vnstratlab-0.0.1-py3-none-any.whl`, which includes the Console static files. |
| Clean venv, Windows, Python 3.11.7 | Pass. `pip install` of the wheel worked, and so did `--help`, `doctor` (exit 0; config OK; 2027 holidays partial; 13 gaps) and `demo --quiet` (exit 0, 46.8 s, 19 trials). |
| `serve --no-open` from the same venv | Pass. `/api/pipelines` answered 200 (`demo, refresh, ingest, rebuild, features`) and `/` served the Console. The server was stopped and the port closed. macOS/Linux install was not run locally; CI covers Linux and macOS on push. |
| Console against a temp `APP_HOME` | Pass. A POST without `X-Vnstratlab` gets 403, and a second start while busy gets 409. `POST /api/runs {demo}` returned 202 and the run succeeded in 26 to 32 s (6 tasks). `GET /api/runs` listed the run. All 6 task logs returned 200 and were not empty. `/api/results` returned 19 rows and 19 equity series, with `synthetic: true`. The SSE stream ends with `end`. `/api/data/status` and `/api/data/gaps` returned 200. |
| Guardrails | Pass. `pytest tests/test_guardrails.py` gave 4 passed. |
| CI (G1) on release head | Pass. The CI push run on `release/v0.1.0` at `0898969` is green (full matrix). |
| Docs build | Pass. `mkdocs build --strict` succeeded with INFO notices only. One broken anchor: `workflow.md` and `CLAUDE.md` link to `qa-gates.md#review-tiers-owner-decision-2026-11-21`, but the heading now ends "narrowed 2026-11-26". |
| No open G2 "request changes" on the release branch | Pass. No open PRs. |

### README vs. behaviour

**Fail (C2).** The README does not match v0.1.0:

| README says | Behaviour |
|---|---|
| "The repository currently contains the scaffold (task card P1-T01)" | v0.1.0 ships the data pipeline, simulator, 19 trials, `demo`, `init` and the Console |
| `demo` and `init` listed without ✅ | Both are done |
| `ingest` card is P1-T03 | P1-T03 is superseded by P1-T36/T37 |
| `backtest --strategy S02_breakout20` | The strategy id is `S02_breakout_volume`, and `backtest` exits 1 (P1-T20) |
| `init` "chooses universe, data dir, notifications" | It sets capital per book, source and fee |
| `serve` is a "dashboard + nightly scheduler" | It is the Console (runs, logs, data, results); there is no scheduler until v0.3 |
| "Every command that writes supports `--dry-run`" | `init` has no `--dry-run` |

The stub commands (`backtest`, `stress`, `daily`, `meta-backtest`, `lab --horizon`) are honest:
they print "Not implemented yet. Planned in task card …" and exit 1.

### Licences of runtime dependencies

Resolved in a clean venv. All are permissive and compatible with Apache-2.0.

| Licence | Packages |
|---|---|
| MIT | fastapi 0.165.0, typer, pydantic, pydantic-settings, pydantic_core, duckdb 2.0.1, PyYAML, platformdirs, anyio, h11, rich, markdown-it-py, mdurl, annotated-types, annotated-doc, typing-inspection |
| BSD | uvicorn 0.54.0 (BSD-3), starlette 1.10.0 (BSD-3), click, idna, pandas 3.1.1, python-dateutil, python-dotenv, scipy 1.17.1, colorama, Pygments (BSD-2) |
| Apache-2.0 | pyarrow, opentelemetry-api, tzdata |
| Other permissive | numpy (BSD-3 and 0BSD/MIT/Zlib/CC0 parts), shellingham (ISC), typing_extensions (PSF-2.0) |

The optional `[yahoo]` extra adds:
- yfinance 1.8.0 and requests (Apache-2.0)
- curl_cffi and beautifulsoup4 (MIT)
- protobuf and websockets (BSD-3)
- peewee: its package metadata is empty, but the upstream licence is MIT.

Yahoo data itself is under Yahoo's terms (GAP-09). The user accepts them; the project does not
redistribute the data.

### `[VERIFY]` values still in use

None of these is newly relied upon in v0.1.0. All of them feed the simulator.

**`hose.yaml`:**

| Key | Value | Status |
|---|---|---|
| `earliest_sell_session_offset` | 3 | VERIFY |
| `price_limit_pct` | 0.07 | VERIFY |
| `round_lot` | 100 | VERIFY |
| `odd_lot` | 1–99, limit orders only | VERIFY |
| `tick_sizes` | 10 / 50 / 100 VND at 0 / 10,000 / 50,000 | VERIFY |
| `sessions` | ATO / continuous / ATC times | VERIFY |
| `cash_proceeds_offset` | 3 | VERIFY |
| `cash_dividend_pay_lag_days` | 30 | VERIFY |
| `stock_dividend_listing_lag_sessions` | 20 | VERIFY |
| `sales_tax_pct` | 0.001 | confirmed |
| `short_selling` | false | confirmed |
| `intraday_t0` | false | confirmed |

**Holidays:** all 13 days of 2026 are VERIFY, from press reports. The 5 days of 2027 are
provisional (partial year). Before 2026 there are no holiday lists (GAP-05).

**`defaults.yaml`:**
- `costs` (brokerage fee 0.15%, slippage 0.1% / 0.3%) is VERIFY: check it with your broker.
- `benchmarks.risk_free.annual_rate` is `null` and VERIFY; the user sets it.

**Data:** `DIVIDENDS_SPLIT_ADJUSTED = True` (Yahoo dividend scaling) and the Yahoo volume scaling
are still [VERIFY], from P1-T06.

### Known open issues

| Issue | Content | Effect on v0.1.0 |
|---|---|---|
| #41 | P1-T06f: minor adjust/step-detection edge cases | Low; on the current store it costs at most a few rows (SHB 1,351 → 1,349) |
| #44 | Membership by date in the features cross-section (TPB after 2026-07-31) | Low; waits for P1-T05 |
| #46 | Strategy `params` should be read-only; a test regex nit | Cosmetic |
| #65 | Demo follow-ups (see below) | Cosmetic, but visible to every Windows user |
| #78 | P1-T20 walk-forward `backtest` | Planned for v0.2 |

Issue #65 covers:
- The em dash in the demo warning prints as "�" on Windows cp1252. Reproduced in this check. The
  Vietnamese gap titles in `data status` are garbled the same way.
- A missing isolation test.
- Logging "circuit breaker active" hundreds of times per run.

## Risks and known limitations

- **R1: the circuit breaker never turns off once the book is in cash (major; spec-level, not a
  code bug).**
  - Rule (engine.md §7): equity ≤ peak × 0.90 blocks buys, and the breaker re-arms only when
    equity is above that threshold again.
  - Once stops and exits have moved the book to cash, equity stays flat, so the breaker cannot
    re-arm. Only dividends can move it.
  - On real data, S17 short +risk:
    - turned the breaker on on 2018-04-23, off on 2018-05-07, and on again on 2018-05-08;
    - sold its last share on 2018-12-28;
    - held only cash for the remaining ~8 years.
  - Both S08 runs in window B were in cash at the end after a breaker trip on 2025-04-03.
  - The code follows the accepted spec (P1-T12), so the fix is an owner decision. Options include
    resetting the peak when flat, or a time or decision-count re-arm.
  - It does not affect v0.1.0, which issues no recommendations. It would dominate every risk-on
    backtest in v0.2 (P1-T20) and every paper book in v0.3.
- **R2: "S17 (benchmark)" in `demo` is not equal weight.** The demo runs S17 through the risk
  layer (max 4 positions, 1% ATR risk sizing, max weight 35%). On real data, on days it held anything, it held 2.95 tickers
  on average, not 14. Any later "beats equal weight" comparison must use S17 without the risk
  layer, or label it plainly.
- **R3: interim data.**
  - Yahoo prices are split-adjusted reconstructions (GAP-01/14).
  - There are no index series (GAP-03) and no price limits from the source (GAP-02).
  - Universe membership is today's list (GAP-13: survivorship bias, `survivorship_warning`
    printed).
  - No holidays before 2026 (GAP-05).
  - Session 2026-11-24 is missing for all tickers.
  - Real-data results are not evidence.
- **R4: no statistical evidence yet.** The lab gates, the benchmarks and the stress tests all
  arrive in v0.2. Nothing in v0.1.0 supports choosing a strategy.
- **R5: market and cost rules are [VERIFY].** The settlement offset, lots, ticks, limits, fees
  and slippage are not confirmed against official sources.

## Recommendation to owner

**Verdict: Not ready.** The release is close. Do C1 to C3 on `release/v0.1.0` (light-tier
docs/chore PRs), then re-check G3.5 with the rc. After that the verdict becomes **Ready with
conditions**.

| # | Condition (blocking) | How |
|---|---|---|
| C1 | Bump to 0.1.0 and publish an rc | Do `chore(release): v0.1.0`: set the pyproject version, rename `[Unreleased]` to `[0.1.0] - <date>`, and merge the duplicate Added/Fixed headings. Tag `v0.1.0rc1`, then install from TestPyPI on Windows and Linux/macOS and run `vnstratlab demo --quiet`. |
| C2 | Make the README match v0.1.0 | Update the Status paragraph, the ✅ marks, the card numbers, the S02 id, the `init` and `serve` text, and the `--dry-run` claim. Fix the broken qa-gates anchor. |
| C3 | Disclose R1 and R2, and record the owner decision | Add a "Known limitations" section to the CHANGELOG/release notes and a note in docs/engine.md §7. Open an issue to decide the breaker re-arm rule before P1-T20 (it is a frozen risk rule, so the owner decides). Label S17 in the demo as "S17 + risk layer" or run the benchmark without it (a follow-up card is fine). |

Conditions to accept at G4 (non-blocking):
- G3.1, G3.2 and G3.3 are N/A until v0.2 (P1-T20/T22/T23, P1-T34, P1-T33).
- Data is interim and survivorship-biased (GAP-13), with 13 open gaps.
- [VERIFY] market and cost values.
- Open issues #41, #44, #46 and #65, including the cp1252 em dash on Windows consoles.
