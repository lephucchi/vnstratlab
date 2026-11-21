# Strategy catalogue

> **Status: design.** Implemented so far: S00 and S17 (card P1-T14), S01–S03 (card P1-T15) and S04–S05 (card P1-T16); the
> rest follow in cards P1-T17 … P1-T19. Parameter sets
> below are **proposals**; the owner freezes them in `defaults.yaml` when each card starts.
> After that, a changed parameter set is a new trial (plan §6.4.3). Each strategy has at most
> 3 parameter sets.

How strategies are run, combined and selected: [engine.md](engine.md). How to write your own:
[writing-strategies.md](writing-strategies.md).

## Common contract

- Input: `features_daily` truncated at `asof` (adjusted-price features, point-in-time fundamentals).
- Output: long-only target weights per ticker, sum ≤ 1. Cash is the remainder.
- Called on the horizon's decision days only. Stops, settlement and lots are handled by the
  engine and risk layer, not by the strategy.
- Every strategy is a candidate in the lab. None is used directly unless it passes the gates
  (or the lab falls back to S17 equal weight).

## Overview

| ID | Name | Horizons | Data needed | Card | Status |
|---|---|---|---|---|---|
| S00 | Composite score | short | prices, volume (4 blocks; valuation omitted, GAP-11) | P1-T14 | **Implemented** (v1, 4 blocks) |
| S01 | Weekly reversal within group | short | prices | P1-T15 | **Implemented** |
| S02 | 20-day breakout with volume | short | prices, volume | P1-T15 | **Implemented** |
| S03 | Oversold in uptrend | short | prices | P1-T15 | **Implemented** |
| S04 | Long-only bank pairs | short | prices (return history) | P1-T16 | **Implemented** |
| S05 | Residual mean reversion | short | prices (return history) | P1-T16 | **Implemented** |
| S06 | Foreign flow | short | foreign net buy/sell | P1-T19 | **Blocked** on P1-T04 (free data source) |
| S07 | LightGBM meta-label filter | short | features | P1-T31 | **Stretch** |
| S08 | Cross-sectional momentum 6–12m | medium | prices | P1-T17 | Planned |
| S09 | Medium-term reversal | medium | prices | P1-T17 | Planned |
| S10 | P/B vs. ROE-justified P/B | medium, long | equity, net income, prices | P1-T18 | Planned; depends on P1-T07 data quality |
| S11 | Earnings yield (E/P) | medium, long | net income, prices | P1-T18 | Planned; depends on P1-T07 |
| S12 | Asset quality and profitability | medium, long | ROE, NPL, NPL coverage | P1-T18 | Planned; **NPL availability from free sources unverified** |
| S13 | Value + momentum | medium | S08 and S10 ranks | P1-T17 | Planned |
| S14 | Low volatility | medium | prices | P1-T19 | Planned |
| S15 | Sector trend filter | medium | prices | P1-T19 | Planned |
| S16 | LightGBM ranking (60-day) | medium | features | P1-T31 | **Stretch** |
| S17 | Equal weight | all | membership | P1-T14 | **Implemented**; **benchmark and selectable strategy** |
| S18 | Hierarchical Risk Parity | long | returns | P1-T19 | Planned |

Candidates per horizon, excluding stretch S07/S16: **short 8** (S00–S06, S17; 7 while S06 is
blocked), **medium 9** (S08–S15, S17), **long 5** (S10, S11, S12, S17, S18).

---

## Short horizon (1 week, weekly decisions)

### S00 — Composite score (design doc "Layer 1")
- **Status.** Implemented (P1-T14), `src/vnstratlab/strategies/builtin/s00_composite.py`, v1 with
  **4 blocks**. The fifth block of the design, valuation (P/B gap), is omitted because
  fundamentals are unavailable (GAP-11, P1-T07). A future 5-block version is a code change and
  therefore a new trial (new `trial_id`), not an edit of v1. Owner decision 2026-11-21.
- **Rule.** Each block is the mean of the cross-sectional percentile ranks of its components
  (1.0 = best): trend (`close_vs_ma20`, `close_vs_ma50`, `ret_60d`), relative strength
  (`rs_20d_vs_group_median`), mean reversion (negated cross-sectional z-score of `rsi_14`,
  then ranked), volume (`vol_vs_avg20`). Weighted sum of the four block ranks → score. A NaN
  component is skipped within its block; a ticker whose whole block is NaN is not eligible. Buy
  the top `top_n` eligible tickers that also show a trigger: breakout (`high_20d_break`) **or**
  oversold-in-uptrend (RSI14 < 35 and close > MA50; 35 is a frozen code constant). Weight
  1/`top_n` each; fewer qualifiers leave the rest in cash. Ties are broken by ticker symbol.
- **Params (frozen).** `{weights: equal, top_n: 3}` (0.25 per block) and
  `{weights: trend_heavy, top_n: 3}` (trend 0.4; relative strength, mean reversion and volume
  0.2 each). The weight numbers are constants in the module, so changing them changes the code
  hash and creates new trials.
- **Basis.** Design doc. Risk: many moving parts → one trial per weight set, no tuning.

### S01 — Weekly reversal within group
- **Rule.** Feature `ret_5d_vs_group_median` (last week's return minus the group median); buy the
  `n` most negative, equal weight 1/`n`. NaN is not eligible; fewer than `n` eligible leaves
  cash; ties by ticker. The sign is not filtered.
- **Params (frozen).** `{n: 2}`, `{n: 3}`; short horizon.
- **Basis.** Jegadeesh (1990), short-term reversal. Sensitive to costs: watch the ×2 cost stress test.

### S02 — 20-day breakout with volume
- **Rule.** Close > highest close of the previous `lookback` sessions **and** volume >
  `vol_mult` × 20-day average volume. Equal weight across signals, max `max_n` (ranked by
  `vol_vs_avg20` descending, ties by ticker), 1/`max_n` each, the rest in cash.
- **Close-based feature.** The older `high_20d_break` compares the close with prior *highs*; S02
  uses the new `close_20d_break` (features-v2: adjusted close above the highest adjusted close of
  the previous 20 good sessions, NaN during warm-up). `lookback` must be 20 (the feature window);
  other values are rejected.
- **Params (frozen).** `{lookback: 20, vol_mult: 1.5, max_n: 3}` (the only set); short horizon.
- **Basis.** Brock, Lakonishok & LeBaron (1992). Breakouts often open near the ceiling, so
  ceiling-blocked buys matter; check `order_events`.

### S03 — Oversold in uptrend
- **Rule.** RSI(`rsi_len`) < `rsi_max` while close > MA(`ma_len`) (`close_vs_ma50` > 0). Buy up to
  `max_n` lowest RSI, 1/`max_n` each, the rest in cash; ties by ticker. `rsi_len` 2 / 14 read the
  features `rsi_2` / `rsi_14`; `ma_len` must be 50; other values are rejected.
- **Params (frozen).** `{rsi_len: 2, rsi_max: 10, ma_len: 50, max_n: 3}`,
  `{rsi_len: 14, rsi_max: 30, ma_len: 50, max_n: 3}`; short horizon.
- **Basis.** Jegadeesh (1990); Moskowitz, Ooi & Pedersen (2012) for the trend filter.

### S04 — Long-only bank pairs
- **History.** Needs `ret_1d` over `lookback_sessions = form` sessions (the feature frame holds all
  rows ≤ asof). Fewer than `form` sessions, or `asof` not being the last session, gives all cash.
- **Rule as implemented.** Formation window = the last `form` sessions ending at asof. Pairs are
  ranked by the Pearson correlation of daily returns over the days both are observed (a pair needs
  ≥ 80 % of the window for both; top `k`, ties by pair symbols). Spread = cumulative log return
  of A minus that of B (the log price ratio up to a constant), on the days where both returns are
  observed only (no fill), z-scored with the window mean and sample std (ddof 1). The window is
  fixed at asof for every session in it (stateless; not lookahead, but an earlier session's z uses
  statistics that include later sessions of the window).
- **Open at asof (onset-based clock).** The window is replayed from its start. An onset is a
  session with |z| > `entry_z` whose previous observed z (carried across sessions without a
  spread value) had |z| ≤ `entry_z`; only the window start counts as no z. A position opens at the onset (session 1; sessions 1..`max_hold` are held)
  and closes when z crosses 0 (sign change or exactly 0) or after `max_hold` sessions. After a
  time stop there is no re-entry until z returns to |z| ≤ `entry_z` and breaks out again. The
  side is fixed at the onset. Buy the laggard
  (z > 0: A ahead, buy B; z < 0: buy A), 1/`k` per open pair; two open pairs on one laggard add
  up; total ≤ 1, the rest in cash.
- **Params (frozen).** `{form: 250, k: 5, entry_z: 2.0, max_hold: 10}`; short horizon.
- **Basis.** Gatev, Goetzmann & Rouwenhorst (2006). Long-only halves the hedge; results are
  closer to a reversal strategy and must be read that way.

### S05 — Residual mean reversion
- **History.** Needs `ret_1d` over `lookback_sessions = window` sessions; fewer gives all cash.
- **Rule as implemented.** Group return per session = equal-weight mean of the available `ret_1d`
  of all tickers. Per ticker (≥ 80 % of the window observed and observed on asof): OLS of its
  returns on the group return with an intercept; residual = `y - alpha - beta * g` (it sums to
  zero, so the last cumulative residual is 0 and z = -mean(X) / std(X), the Avellaneda & Lee
  s-score without the drift term). z = (last cumulative residual - mean of the cumulative
  residual) / std (ddof 1). Buy the `n` most negative z below `-entry_z`, 1/`n`
  each, the rest in cash; ties by ticker.
- **Params (frozen).** `{window: 60, entry_z: 1.5, n: 2}`; short horizon.
- **Basis.** Avellaneda & Lee (2010).

### S06 — Foreign flow *(blocked)*
- **Rule.** Highest 5-day foreign net buy / traded value; buy top `n`.
- **Status.** Disabled in config until P1-T04 finds an acceptable free source.

### S07 — LightGBM meta-label filter *(stretch)*
- **Rule.** Model predicts whether an S01–S05 signal beats the group over 5 sessions; signals
  with low predicted probability are dropped. Purged CV, embargo 5 sessions.
- **Basis.** Gu, Kelly & Xiu (2020); López de Prado (2018) meta-labelling.

## Medium horizon (3–6 months, monthly decisions, 3 tranches)

### S08 — Cross-sectional momentum
- **Rule.** Return from `t-L` to `t-1 month` (skip the last month); buy the top `n`.
- **Proposed params.** `{L_months: 6, n: 4}`, `{L_months: 12, n: 4}`.
- **Basis.** Jegadeesh & Titman (1993). With 13 highly correlated banks, momentum spreads are
  small; S09 tests the opposite.

### S09 — Medium-term reversal
- **Rule.** Opposite ranking of S08: buy the bottom `n`.
- **Proposed params.** `{L_months: 6, n: 4}`.
- **Basis.** Several Vietnamese market studies report reversal rather than momentum; the lab
  decides which survives.

### S10 — P/B vs. ROE-justified P/B
- **Rule.** Justified P/B = (ROE − g) / (r − g). Buy the `n` with the largest gap
  (justified − actual) / actual, using fundamentals by `published_at`.
- **Proposed params.** `{r: 0.14, g: 0.06, n: 3}`. `r` and `g` are assumptions, stated in the report.
- **Basis.** Gordon (1959) growth model applied to banks.

### S11 — Earnings yield
- **Rule.** Trailing-4-quarter net income / market cap; buy the top `n`.
- **Proposed params.** `{n: 3}`, `{n: 4}`.
- **Basis.** Value effect; Huang et al. (2023) for Vietnam.

### S12 — Asset quality and profitability
- **Rule.** Average rank of high ROE, low NPL ratio, high NPL coverage; buy the top `n`.
- **Proposed params.** `{n: 3}`.
- **Basis.** Fama & French (2015) profitability. **Risk:** NPL data from free sources may be
  missing or late; the strategy is disabled if coverage < 90% of ticker-quarters.

### S13 — Value + momentum
- **Rule.** Average of S08 rank and S10 rank; buy the top `n`.
- **Proposed params.** `{n: 4}`.
- **Basis.** Asness, Moskowitz & Pedersen (2013).

### S14 — Low volatility
- **Rule.** Lowest `window`-session volatility; buy the bottom `n`, equal weight.
- **Proposed params.** `{window: 60, n: 4}`.
- **Basis.** Frazzini & Pedersen (2014).

### S15 — Sector trend filter
- **Rule.** If the equal-weight bank group's 12-month return > 0, hold all members equally;
  otherwise hold cash.
- **Proposed params.** `{lookback_months: 12}`, `{lookback_months: 6}`.
- **Basis.** Moskowitz, Ooi & Pedersen (2012), time-series momentum.

### S16 — LightGBM ranking *(stretch)*
- **Rule.** Rank stocks by predicted 60-session relative return; buy top `n`.

## Long horizon (1 year, monthly decisions, 12 tranches — ADR-005)

| ID | Notes |
|---|---|
| S10, S11, S12 | As above; one of 12 tranches rebalanced each month |
| S17 | Equal weight of current members (DeMiguel, Garlappi & Uppal, 2009) |
| S18 | Hierarchical Risk Parity on 1-year daily returns (López de Prado, 2016) |

The long horizon decides monthly (~96 decisions in 8 years, ADR-005), but with a 1-year
holding period the outcomes overlap: there are only **~8 non-overlapping 1-year outcomes** in
8 years (plan §12), and that is what statistical power depends on. Gates have little power here, so the long book defaults to equal weight across 2–4
economically grounded strategies and the lab is used mainly to **drop** broken ones
(plan §12).

## All horizons

### S17 — Equal weight
- **Status.** Implemented (P1-T14), `s17_equal_weight.py`; no params, horizons short, medium, long
  (3 trials).
- **Rule.** 1/N across the tickers in the features on `asof` (universe by date: P1-T05).
  Executable version uses odd lots.
- **Role.** The benchmark every strategy must beat (gate 2) **and** a selectable strategy. When
  nothing passes the gates, the recommendation is `hold_benchmark`, i.e. S17.

---

## Known structural risks for this universe

| Risk | Effect | Mitigation |
|---|---|---|
| 13 banks are highly correlated | Cross-sectional spreads are small; many strategies pick the same names | Report average pairwise correlation of strategy returns; report the effective trial count next to the raw count (ADR-003 §5) |
| Few independent long-horizon decisions | Gates have little power | Long book defaults to equal weight of grounded strategies |
| Fundamentals from free sources | Missing `published_at`, missing NPL | Fallback lag + flag; disable S12 below coverage threshold |
| Ceiling opens on breakouts | Executable returns below ideal | `order_events` analysis in G3 |
