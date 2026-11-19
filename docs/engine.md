# Engine specification

> **Status: design.** Nothing in this page runs yet. It specifies what cards P1-T10 (features),
> P1-T11 (simulator), P1-T12 (risk), P1-T13 (strategy registry), P1-T20–T23 (lab) must build.
> Engine refinements are in [ADR-003](adr/ADR-003-engine-architecture.md) (accepted in part).
> Strategy rules are in [strategies.md](strategies.md).
>
> **Config keys and table columns not yet in `defaults.yaml`, `hose.yaml` or plan §5.5** (e.g.
> `engine.*`, `cash_proceeds_offset`, `rights_policy`, `cash_dividend_pay_lag_days`,
> `risk.stop_cooldown_sessions`, `corporate_actions.pay_date` and `listing_date`) come from
> ADR-003, **accepted in part on 2026-11-18**. They become real when the owning card adds them
> (P1-T11 for the engine keys); proposals 2 (fast path) and 5 (effective trials) are deferred.

The engine turns **target weights** produced by strategies into **simulated orders, fills,
positions and returns** under HOSE rules. The same engine serves backtests, the lab, paper
books, meta-backtests and stress tests (plan D11). Only the `Executor` and a few mode flags
differ.

**Diagrams.** All figures for this page (layers, data to orders, two clocks, session loop,
order lifecycle, one portfolio, lab selection, modes, build order) are in one HTML page:
[engine-architecture.html](diagrams/engine-architecture.html).

<iframe src="../diagrams/engine-architecture.html" title="Engine architecture diagrams" loading="lazy" style="width:100%;height:880px;border:1px solid #d9d9d9;border-radius:12px;"></iframe>

---

## 1. Layers

```
┌────────────── interfaces ──────────────┐  cli.py · app/ (FastAPI) · web/
│                                         │
├────────────── application ─────────────┤  lab/ (walk-forward, gates, selection, meta-backtest,
│                                         │  stress) · daily orchestration · journal writers
├────────────── domain core (pure) ──────┤  engine/ (rules, costs, ledger, event loop)
│  no I/O, no network, no DuckDB          │  strategies/ · risk/ · features/ (computation only)
├────────────── infrastructure ──────────┤  data/ (sources, storage) · journal/ (SQLite)
│                                         │  notify/ · news/
└─────────────────────────────────────────┘
```

**Dependency rule:** the domain core imports nothing from infrastructure or interfaces. It
receives plain arrays / DataFrames and returns plain results. This keeps the engine fast,
deterministic and testable without databases. The data boundary is enforced today by
`tests/test_data_boundary.py` (P1-T36); a full import-linter contract in CI is proposed in
ADR-003 §1.

## 2. Inputs

| Input | Source table | Used for | Price basis |
|---|---|---|---|
| Raw OHLCV, `ref_price`, ceiling, floor | `prices_daily` | **Execution**: fills, limits, ticks, lots, valuation | Raw |
| Adjusted OHLCV | `prices_adjusted` | **Signals and features** only | Adjusted |
| Corporate actions | `corporate_actions` | Applied to **holdings** (shares, cash) | — |
| Features | `features_daily` (point-in-time) | Strategy input | Adjusted |
| Universe membership | `universe_membership` | Tradable set per date | — |
| Market rules, costs | `config/markets/*.yaml`, `defaults.yaml` | Rules | — |

**Why two price bases.** Ceiling/floor, tick size and lot value are defined on the raw traded
price. Simulating fills on adjusted prices breaks the limit check (an adjusted open can sit
below a raw ceiling that was actually hit), the tick grid and the cash needed per lot.
Signals use adjusted prices so that a dividend does not look like a crash.

Corporate actions are applied to the simulated portfolio on the ex-date:

| Action | Effect on holdings | Status |
|---|---|---|
| Cash dividend | Cash receivable booked at ex-date; becomes available on the payment date (`corporate_actions.pay_date`, fallback config `cash_dividend_pay_lag_days`) | [VERIFY] lag |
| Stock dividend / bonus shares | `shares += floor(shares × ratio)`; new shares sellable from the listing date (fallback config lag) | [VERIFY] lag |
| Rights issue | Not exercised by default (`rights_policy: ignore`); the position's value drop is real and recorded | Policy |

### Phase 1 data constraints (ADR-007)

The interim Yahoo source has **no raw series** (GAP-01) and **no exchange limits** (GAP-02).
Until a raw source closes those gaps, the engine runs on Yahoo rows as follows:

Let `F(t) = Π (1 + ratio_e)` over the stored stock events `e` of the ticker with `ex_date > t`
(ratio = bonus fraction, P1-T37 convention). P1-T06 builds the execution series from it; P1-T11
only consumes it (`price_basis = exec_reconstructed`) and refuses `split_adjusted` input.

| Topic | Yahoo rows (`price_basis = split_adjusted`) | Phase 1 handling |
|---|---|---|
| Execution prices | Split-adjusted; prices before a stock dividend / bonus issue are divided by `1 + ratio` | **P1-T06 reconstructs** `exec(t) = adjusted(t) × F(t)` for open/high/low/close, rounded to the **nearest** tick and clipped to [floor, ceiling] (as the synthetic generator does); volume is divided by `F(t)` (if Yahoo scales volume, open question in the Yahoo review). Lot cost and cash per lot are then close to raw |
| `ref_price`, `ceiling`, `floor` | Derived at ingest from the previous split-adjusted close (`derived_limits = true`) | P1-T06 recomputes them in day t's share basis: `ref(t) = round_down_to_tick(adj_close(t−1) × F(t))`, which equals the previous raw close on normal days and the theoretical ex-price `prev / (1 + ratio)` on a stock ex-date (same convention as the synthetic `ex_price`). On a **cash** ex-date Yahoo's close is not cash-adjusted, so `ref` stays at the previous close instead of `prev − dividend`; this residual stays under GAP-02. Ceiling/floor follow from the HOSE rules. Logging `derived_limits` in `order_events` is a follow-up proposal, not part of P1-T11 |
| Stock dividend / bonus shares | Yahoo rescales all earlier history; P1-T37 refetches the ticker's full history when it sees a new event (GAP-08), so the store stays in one scale | Applied to **holdings as for raw rows** (`shares += floor(shares × ratio)`). The loop applies every not-yet-applied action with `ex_date ≤ t` (idempotent, tracked per book), so an event that Yahoo publishes a few days after its ex-date is still applied once to a paper book |
| Cash dividend | Not in `Close` (P1-T37 reads Yahoo with `auto_adjust=False`) | Booked to cash as for raw rows. **[VERIFY]** whether Yahoo's dividend amounts are split-adjusted too; if so, P1-T06 multiplies them by `F(ex_date)` like prices |
| `prices_adjusted` (P1-T06, built) | — | For signals: split factors are **never re-applied** to `split_adjusted` rows (already split-continuous); cash-dividend adjustment still applies (ADR-007 §5) |
| Preconditions | Reconstruction is only as good as the stored stock events (GAP-06); P1-T37 drops reverse splits (factor ≤ 1) | P1-T06 adds a check: on each stock ex-date the reconstructed open should be near `prev_close / (1 + ratio)` (tolerance stated by P1-T06, beyond normal daily moves). A ticker that fails is flagged and excluded from execution until fixed, and every exclusion is counted in run outputs (survivorship). Reverse splits that P1-T37 drops cannot be detected this way (GAP-06). P1-T06 stores them in `prices_exec` (key ticker, date, source), exclusions in `exec_exclusions`. The check is a single-scale / discontinuity check (`scale_discontinuity`): the stored ratios cancel, so it reduces to `|open / previous close − 1| ≤ price limit + 1 %` (8 %) at the first good session after each stock ex-date; it detects a store not in one scale, not a wrong ratio the source applied consistently. **Use of the two series:** `prices_adjusted` is for scale-invariant signals only (returns, ratios, normalised indicators); level and liquidity features use `prices_exec` (point-in-time, raw-like); features are recomputed when `adj_version` changes and never mixed across versions |
| Synthetic rows (`price_basis = synthetic`) | Raw-like, on the tick grid, with exact limits | Engine rule tests (§14) run on synthetic data, where every rule is exact |

Hand-computed engine tests therefore always use the synthetic market; real-data runs are for
research and are never evidence for the rule tests.


## 3. Two clocks

The engine runs on **every trading session** (daily clock). Strategies are called only on
**decision days** of their horizon (decision clock).

| Clock | Runs | Does |
|---|---|---|
| Daily | Every session | Corporate actions, settlement, pending orders, fills, stops, mark-to-market, circuit breaker, equity |
| Decision | Short: last session of the week · Medium: last session of the month (one of 3 tranches) · Long: last session of the month (one of 12 tranches, proposed in ADR-005) | Strategy weights → selection → risk layer → new target → orders |

## 4. Session loop

For each session `t` (all orders are generated at a close and filled at the **next open**):

```
1. PRE-OPEN (t)
   a. apply every not-yet-applied corporate action with ex_date <= t (idempotent per book)
   b. release settled shares  (bought at t - offset → sellable at t)
   c. release cash            (dividends paid, sale proceeds after cash_proceeds_offset)

2. OPEN (t) — fill orders created at close of t-1
   for each pending order, sells first, then buys:
     - universe check   (ticker tradable on t)
     - limit check      buy blocked if open >= ceiling; sell blocked if open <= floor
     - settlement check sell only shares sellable at t
     - cash check       buy only up to available cash after costs
     - quantity         round lots; remainder as odd lot if allowed (odd-lot slippage)
     - price            fill = open × (1 ± slippage)
     - costs            fee on both sides; sales tax on sells (even at a loss)
     - unfilled part    → order lifecycle policy (§6)

3. CLOSE (t)
   a. mark to market on raw close
   b. daily risk: ATR stop hit on close → sell order for t+1 (§7)
   c. circuit breaker: equity <= peak × (1 - dd) → block new buys, alert
   d. record equity, positions, cash, costs

4. DECISION (only if t is a decision day of the book's horizon)
   a. features with date <= t
   b. per strategy: target_weights(features, t)
   c. combine strategies with the lab's current weights (§9)
   d. risk layer: sizing, max positions, max weight, vol scaling, cooldowns
   e. target quantities from target weights × equity (raw close, lot-aware)
   f. orders = target - current, skipping changes below rebalance_threshold_pct
   g. orders become pending for t+1
```

Sells are filled before buys within a session; whether a buy may use **same-session** sale
proceeds is the config key `cash_proceeds_offset` (§8).

## 5. Fill rules (hand-computed tests required)

| Rule | Config key | Example test |
|---|---|---|
| Earliest sell after buy | `earliest_sell_session_offset` (default 3, [VERIFY]) | Buy fills Monday open; sell signal Tuesday close → sell fills Thursday open at the earliest |
| Ceiling open blocks buy | `price_limit_pct` | `ref=50,000`, open at ceiling `53,500` → no buy fill |
| Floor open blocks sell | `price_limit_pct` | open at floor → no sell fill; stop stays pending |
| Round lot | `round_lot` | 11,000,000 VND, price 52,700 → max 2 round lots (10,540,000 + costs), not 3 |
| Odd lot | `odd_lot` | Target 150 shares → 100 round + 50 odd lot with odd-lot slippage |
| Tick grid | `tick_sizes` | Limit price 49,973 → 49,950 (buy, round down); 52,730 → 52,800 (sell, round up) |
| Fees | `brokerage_fee_pct` | Both sides |
| Sales tax | `sales_tax_pct` | Sell at a loss still pays 0.1% |
| Slippage | `slippage_pct.round_lot / odd_lot` | Buy fill = open × 1.001 |

The simulator fills at the open (ATO-like). Tick rounding applies to **recommended limit
prices** shown to the user (entry zone, stop), not to simulated open fills.

## 6. Order lifecycle

When an order cannot be (fully) filled at `t`:

| Situation | Config key | Default | Rationale |
|---|---|---|---|
| Buy blocked (ceiling, cash) | `engine.unfilled_buy` | `cancel` | A missed entry is not chased; the next decision re-evaluates |
| Sell blocked (floor) | `engine.unfilled_sell` | `carry` | Exits must eventually happen |
| Sell before shares are sellable | `engine.unsettled_sell` | `queue_until_sellable` | Settlement is a hard rule |
| Carry limit | `engine.max_carry_sessions` | 5 | Then cancel and log `stale_order` |

Every blocked or carried order is written to an `order_events` log with its reason; lab
reports show how often each rule bound.

## 7. Stops and the decision clock

- ATR stop: `stop = entry_price - atr_stop_multiple × ATR14(at entry)`, checked on each close.
- **Stop before shares are sellable:** the sell order is queued until the first sellable
  session (§6), logged as `stop_pending_settlement`. The loss is real; the test asserts it.
- **Stop and rebalance on the same day:** the stop wins. The stopped ticker enters a cooldown
  (`risk.stop_cooldown_sessions`, default = one decision period) during which the risk layer
  will not re-buy it.
- Time exits (short horizon): positions are re-decided every decision day; no extra rule.

## 8. Cash ledger

| Bucket | Meaning |
|---|---|
| `cash_available` | Can be used for buys now |
| `cash_pending` | Sale proceeds or dividends not yet usable |
| `cash_reserved` | Earmarked by pending buy orders (incl. costs) |
| Buying power | `cash_available - cash_reserved` |

`cash_proceeds_offset` (sessions after the sell fill until proceeds are usable) is a
**[VERIFY]** key (proposed for `hose.yaml`, ADR-003 §9). Ideal mode uses 0 (no friction);
executable mode uses the conservative value the owner sets in `hose.yaml`. Brokers may offer advances on
sale proceeds; the engine never assumes them.

## 9. From strategies to one portfolio

```
strategies S_i  ──target weights w_i(ticker)──►  combine: W(ticker) = Σ_i  α_i · w_i(ticker)
                                                  α_i = lab selection weights (MCS + shrunk Hedge)
                                                  W empty or lab says hold_benchmark → 1/N
                                                        │
                                                        ▼
                                                  risk layer → quantities → orders
```

- Combination happens on **weights**, then once through the risk layer, so the book trades
  one netted portfolio (no strategy buys what another sells).
- `consensus(ticker)` = number of selected strategies holding it; shown on the recommendation.

## 10. Modes: ideal and executable

One engine, three switches:

| Switch | Ideal | Executable |
|---|---|---|
| `lots` | off (fractional shares) | on |
| `capital_vnd` | very large | book capital (default 11,000,000) |
| `costs` | on | on |
| `limits_and_settlement` | on | on |
| proceeds offset | 0 | `cash_proceeds_offset` (3, [VERIFY]) |

Property test (must hold for random synthetic data): with `lots=off`, capital = `ideal_capital_vnd`
and weights low enough that cash never binds, executable returns equal ideal returns to 1e-10
(the proceeds offset differs, so equality is undefined when cash binds).

**Speed.** The lab's heavy loop (all trials × all periods × bootstrap) needs ideal returns
only. Paper books, meta-backtests and stress tests run executable mode. A vectorised fast path
for ideal mode is **deferred** (ADR-003 §2): it may be added only after benchmarks show a need
and the owner accepts it, behind a CI property test proving it equals the event loop.

## 11. Outputs per run

| Output | Grain | Used by |
|---|---|---|
| `returns` (ideal, executable) | per session and per period | Lab, reports |
| `positions` | per session × ticker | Dashboard, journal |
| `trades` | per fill: qty, price, fee, tax, slippage, lot type | Cost analysis |
| `order_events` | per blocked/carried/cancelled order + reason | Realism analysis |
| `equity` | per session: cash buckets, positions value | Books, circuit breaker |
| `run_manifest` | per run | Reproducibility (§13) |

## 12. Walk-forward and the lab

| Horizon | Period | Typical rebalance | Min OOS periods (gate 1) |
|---|---|---|---|
| Short | 1 week | Weekly | 52 |
| Medium | 1 month (3 tranches) | Monthly, one tranche | 24 |
| Long | 1 month (12 tranches, ADR-005) | Monthly, one tranche | 24 (proposed, ADR-005) |

1. **Register** every (strategy, params) as a trial before running (`trial_registry`).
2. **Walk forward:** at each period end `p`, strategies see data `< p` only; fitted components
   (S07/S16 only) use purge and embargo equal to the label length.
3. **OOS returns** per trial per period → `oos_returns` (ideal and executable).
4. **Selection cycle** on a decision day (plan Appendix B): gate 1 (DSR ≥ 0.95, PBO ≤ 0.5,
   min periods) → gate 2 (SPA vs. equal weight, α = 0.10) → MCS (α = 0.10) → Hedge weights
   shrunk toward equal weight, capped. Nothing passes → `hold_benchmark`.
5. **Meta-backtest** runs steps 1–4 historically as if live, against equal weight of
   strategies, last winner and S17.

### Trial identity

`trial_id = hash(strategy_id, params, strategy_code_hash, feature_version, engine_version)`.
A code change with unchanged params is a **new trial** (ADR-003 §3); otherwise edits would
silently reuse an old trial and escape the DSR count.

### In-sample by design

Parameters registered in 2026 were chosen with 2015–2026 history in view, so that history is
not truly out-of-sample for them. Lab reports always split performance at
`trial_registry.registered_at`:

| Window | Label | Weight in decisions |
|---|---|---|
| Before `registered_at` | *historical walk-forward (in-sample by design)* | Gates and selection |
| After `registered_at` | *forward (true OOS)* | Reported separately; G3 compares the two |

## 13. Reproducibility

Every run writes a `run_manifest`: run id, command, package version, git commit,
`engine_version`, resolved config hash (and the resolved config itself), data snapshot
(`max(ingested_at)` per table), seeds, trial ids. Same manifest inputs → same outputs; a test
replays a fixture run and compares hashes.

## 14. Test plan (minimum)

| Area | Cases |
|---|---|
| Settlement | buy Mon → earliest sell Thu; stop before sellable queued; sell proceeds offset |
| Limits | ceiling-open buy blocked; floor-open sell carried; carry expiry |
| Lots | 52,700 VND × 3 lots unaffordable; odd-lot remainder; odd lots off |
| Ticks | each tick band boundary, both rounding directions |
| Costs | fee both sides; tax on loss; odd-lot slippage |
| Corporate actions | 10% stock dividend (shares, no artificial gap in signals); cash dividend receivable → available; (P1-T06 test, not engine) on `split_adjusted` rows the reconstructed execution price equals the raw price (synthetic round trip: raw → Yahoo-style scaling → reconstruction); (engine) a book holding across a 10% stock dividend keeps its equity within one tick (1,000 sh × 50,000 = 50,000,000 before; 1,100 sh × 45,450 = 49,995,000 after, the ex-price rounded down to the tick) with no −ratio step in signals; an action published after its ex-date is applied once |
| Modes | executable == ideal with lots off and infinite capital (property test) |
| Lookahead | strategy that peeks at `t+1` is impossible (features truncated) and detected |
| Determinism | same manifest → identical outputs |
| Combination | two strategies with opposite targets net out; consensus counts |
