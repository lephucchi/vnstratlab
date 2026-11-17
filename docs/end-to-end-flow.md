# End-to-end flow

> **Status: design.** This page explains how the pieces specified in [engine.md](engine.md),
> [strategies.md](strategies.md) and the [plan](plan/plan.md) fit together, from new data to a
> recommendation. Numbers in the worked example are **illustrative** (tickers `AAA`, `BBB`,
> `CCC` are placeholders), not real prices or advice.

"Trading" in this page always means **simulated fills under real HOSE rules**. vnstratlab never
sends orders (ADR-001).

---

## 1. The big picture

```
 ┌───────────── every trading evening (inside `vnstratlab serve`) ─────────────┐
 │                                                                              │
 │  A. DATA PIPELINE                                                            │
 │     ingest new session ─► DQ checks ─► corporate actions + adjusted prices   │
 │     ─► fundamentals (by published_at) ─► features (point-in-time)            │
 │     (raw news collected on the side; never blocks)                           │
 │                                     │                                        │
 │  B. BACKTEST LAB ("time machine")   ▼                                        │
 │     for every registered trial: replay the newest period with data           │
 │     locked at that period's decision date ─► append OOS returns              │
 │                                     │                                        │
 │  C. SELECTION (decision days only)  ▼                                        │
 │     gate 1 (DSR, PBO, min periods) ─► gate 2 (SPA vs equal weight)           │
 │     ─► MCS ─► Hedge weights shrunk to equal ─► or hold_benchmark             │
 │                                     │                                        │
 │  D. RECOMMENDATION                  ▼                                        │
 │     combine strategy weights ─► risk layer ─► lot-aware quantities           │
 │     ─► append-only journal ─► paper books ─► dashboard + report              │
 └──────────────────────────────────────┬───────────────────────────────────────┘
                                        ▼
                     USER reads it next morning and decides; places orders manually
```

## 2. Stage by stage

| # | Stage | Input | Output | Command / card | On failure |
|---|---|---|---|---|---|
| A1 | Ingest prices | Data source API | `prices_daily` (raw), `data/raw/*.parquet` | `ingest` · P1-T03 | **Stop** loop, alert |
| A2 | Data-quality checks | `prices_daily` | `dq_results` | P1-T08 | **Stop** loop, alert |
| A3 | Corporate actions + adjustment | Source, `prices_daily` | `corporate_actions`, `prices_adjusted` | P1-T06 | **Stop** |
| A4 | Fundamentals | Source | `fundamentals_q` with `published_at` | P1-T07 | Warn; keep last known (flagged) |
| A5 | Universe membership | HOSE announcements | `universe_membership` | P1-T05 | Warn (`survivorship_warning`) |
| A6 | Features | A3–A5 | `features_daily` (+`feature_version`) | P1-T10 | **Stop** |
| A7 | Raw news | News sources | `news_raw` | P1-T09 | Warn only |
| B1 | Lab update (all trials) | features, raw prices, rules | `oos_returns` (ideal, executable) | P1-T20 | **Stop**; previous state kept |
| C1 | Selection (decision days) | `oos_returns`, benchmark | `selection_runs` | `lab` · P1-T22 | **Stop**; previous selection stays active |
| D1 | Combine + risk | selection, strategy targets | target weights, quantities | P1-T12, P1-T24 | **Stop** |
| D2 | Recommendation | D1 | `recommendations` (append-only) | P1-T25 | **Stop** |
| D3 | Paper books | D2, next open | `orders`, `fills`, `book_equity` | P1-T24 | **Stop** |
| D4 | Report | journal | dashboard, Telegram/console | P1-T28, P1-T29 | Warn only |

"Stop" means: the loop ends, nothing later runs, yesterday's recommendation stays the latest,
and an alert is sent. Optional parts (news, notifications) never stop the loop.

## 3. The "time machine": how a backtest locks data

To test a strategy on a past date `d`, the engine behaves as if today were `d`:

| What is locked | How |
|---|---|
| Prices and features | Strategy receives `features_daily` rows with `date <= d` only (truncated **before** the call) |
| Fundamentals | Only rows with `published_at <= d` (fallback: quarter end + 45 days, flagged) |
| Universe | Members on `d` from `universe_membership` (stocks that later left the index are included; later joiners are not) |
| News (Phase 2) | Only items with `effective_date <= d` (published after 14:45 → next session) |
| Execution | Orders decided at the close of `d` fill at the **next open**, never at `d`'s close |
| Parameters | Fixed when the trial was registered; the replay cannot tune them |

Enforcement: features are truncated by the engine, not by the strategy; P1-T10 recomputes
features on truncated data and checks they are identical; P1-T20 includes a deliberately
"peeking" strategy that must fail.

### How far back

| Horizon | Each step replays | Window used for ranking and weights | Gates use |
|---|---|---|---|
| Short | 1 week | last **52 weeks** of OOS returns | all OOS history (min 52 weeks) |
| Medium | 1 month | last **36 months** | all OOS history (min 24 months) |
| Long | 1 month (12 tranches) | **all** history | all OOS history (min 24 months, proposed in ADR-005) |

With data from 2015-01-01 and about 250 sessions of feature warm-up, the first OOS period is
around January 2016; the first short-horizon selection is possible around January 2017
(52 weeks later), medium and long around 2018 (24 months later).

### Why replay many windows, not one

Rewinding once and taking the best performer gives **one** sample; the winner of one window is
often just lucky. The lab therefore replays **every period since 2016** for every trial and
judges strategies on the whole out-of-sample series. "Pick the last window's #1" is itself
tested as a selector (`last_winner`) in the meta-backtest (P1-T23), against the gated
selection and against equal weight, so the data decides which selection method is better.
The dashboard leaderboard shows the ranking either way. Decision and pre-registered switching
rule: [ADR-004](adr/ADR-004-selection-method.md) (default: the gated, weighted set).

## 4. First run vs. nightly run

| | First run (`vnstratlab ingest --from 2015-01-01`, then `lab`) | Nightly run |
|---|---|---|
| Data | Full backfill | Newest session only |
| Features | All history | Newest session (+ recompute if data was corrected) |
| Lab | Replays **2015 → today** for every trial once; stores OOS returns in `lab.duckdb` | Appends the **newest period** for every trial (only when a period closes) |
| Selection | Runs for the latest decision day | Runs only on decision days |
| Time | Minutes (depends on trial count) | Seconds to a minute |

**Cache invalidation.** Stored OOS returns of a trial are recomputed in full when:
a new trial is registered (its own history only); `feature_version` changes; `engine_version`
changes; corrected raw data or corporate actions change history (affected trials only).

## 5. Worked example (illustrative)

Short horizon, decision day **Friday 2026-11-20**. Book capital 11,000,000 VND.

### 5a. One historical replay step inside the lab

Trial `S02_breakout20 {lookback: 20, vol_mult: 1.5, max_n: 3}`, period ending Friday 2024-03-22.

| When | What happens |
|---|---|
| Fri 2024-03-15, close | Data locked at this close. S02 sees `AAA` and `BBB` closing above their 20-day highs on volume > 1.5× average; target weights `AAA 1/3, BBB 1/3`, cash 1/3 |
| Mon 2024-03-18, open | Orders fill. `BBB` opens at its ceiling (ref 30,000 → ceiling 32,100): **buy blocked**, cancelled (`unfilled_buy: cancel`), logged in `order_events` |
| | `AAA` opens at 25,300. Budget 3,666,666. Round lot: 100 × 25,300 × 1.001 slippage = 2,532,530 + 0.15% fee → 2,536,329. Odd lot with the rest: price 25,300 × 1.003 = 25,375.9 → **44 shares** (1,118,214 incl. fee). Position: 144 shares |
| Tue–Wed | Shares not yet sellable; a stop hit now would queue until Thursday |
| Thu 2024-03-21, open | Earliest sell session (`earliest_sell_session_offset: 3`, [VERIFY]) |
| Fri 2024-03-22, close | Next decision. If S02 no longer holds `AAA`, a sell fills Mon 2024-03-25 open with fee + 0.1% tax |
| Recorded | Weekly return of the trial for the period ending 2024-03-22, both **ideal** (fractional, no lots) and **executable** (lots, odd lots, blocked orders) |

The lab does this for every trial and every week from 2016 to today on the first run, then one
new week each Friday.

### 5b. Selection on Friday 2026-11-20

| Step | Input | Illustrative result |
|---|---|---|
| Trials | All short-horizon trials registered | 14 trials |
| Gate 1 | Each trial's full OOS series: DSR ≥ 0.95 (with N = total trials), PBO ≤ 0.5, ≥ 52 weeks | 4 pass |
| Gate 2 | Last 52 weeks of excess return vs. equal weight; SPA p-value | p = 0.06 < 0.10 → pass |
| MCS | Same window, α = 0.10 | {S02, S03, S05} |
| Weights | λ = 0.5 toward equal, η = 2.0 on Sharpe, cap 0.4 | S02 0.40 · S03 0.33 · S05 0.27 |
| Fallback | If gate 1 empty, gate 2 fails or MCS empty | `hold_benchmark` (equal weight of the universe) |

Combination: `W(ticker) = 0.40·w_S02 + 0.33·w_S03 + 0.27·w_S05`, then the risk layer (1% equity
at risk to the ATR stop, max 4 positions, max 35% per ticker, circuit breaker), then
lot-aware quantities at Friday's raw close.

### 5c. Recommendation card (what the user sees Friday evening)

```
Khung ngắn hạn · 2026-11-20 · trạng thái: ĐỀ XUẤT
Mã   Tỷ trọng  Số lượng          Vùng mua            Dừng lỗ   Đồng thuận
AAA  34%       100 + 44 lô lẻ    25,250 – 25,500     24,600    2/3 chiến lược
CCC  30%       100               33,000 – 33,300     32,000    3/3
Tiền 36%
Bằng chứng: SPA p = 0.06 · DSR: S02 0.97, S03 0.96, S05 0.95 · 14 trial · MCS {S02,S03,S05}
So với chia đều 52 tuần: +X% (khoảng tin cậy ...)
Đây không phải lời khuyên đầu tư. Bạn tự quyết định và tự đặt lệnh.
```

Stops respect the 1% risk rule: 1% of 11,000,000 = 110,000 VND per position, so
`AAA` 144 shares × (≈25,375 − 24,600) ≈ 112,000 and `CCC` 100 × (≈33,100 − 32,000) = 110,000
(stop prices on the tick grid).

The same targets drive the **paper book**, which fills at Monday's open under the same rules,
so paper results can later be compared with what the backtest predicted (gate G3).

## 6. What runs where

| Step | Every session | Decision days only |
|---|---|---|
| A1–A7 data pipeline | ✅ | |
| B1 lab update | ✅ (when a period closes) | |
| C1 selection | | ✅ |
| D1–D2 new recommendation | | ✅ |
| Stops, settlement, paper fills, equity | ✅ | |
| D4 report | ✅ (status, stops, equity) | ✅ (new recommendation) |
