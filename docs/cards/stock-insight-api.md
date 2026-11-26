# Stock insight — API contract (shared by X-stock-api and X-stock-ui)

Owner request 2026-11-26: the Console must show **which stocks are recommended now**, and allow
**per-stock analysis**: pick a ticker, run an analysis, see the numbers, the strategies' signals and
a recommendation. Recommend-only: nothing places, routes or confirms orders; every recommendation
carries the disclaimer and the data label.

Same rules as the Console v2 contract (loopback, `X-Vnstratlab: 1` on non-GET, `{error,...}`).

## Current recommendations (preview of P1-T25; no lab selection yet)

- `GET /api/recommendations?horizon=short|medium|long&source=` →
  ```
  {asof, source, synthetic, label, status: "preview", note_vi,
   horizon, book_capital_vnd,
   strategies: [{strategy_id, params, trial_id, registered, weights: {ticker: w}}],
   targets: [{ticker, weight, consensus, strategies: [strategy_id...],
              last_close, lot_size, lot_qty, odd_qty, notional_vnd,
              entry_zone: {low, high}, ceiling, floor,
              atr14, stop_price, stop_pct, est_cost_vnd}],
   cash_weight, evidence: {trials_counted, dsr_by_strategy?: {...}, gate1_pass: [...] }}
  ```
  - `asof` = the latest features date; decision as at that close.
  - Each **enabled, registered** trial of the horizon computes `target_weights` (same slicing as
    walk-forward/demo: rows ≤ asof, `lookback_sessions`).
  - Combination until P1-T22 exists: **equal weight across those strategies**
    (W = mean of w_i), then **once through the risk layer** (book capital, ATR sizing, max
    positions, max weight) like engine.md §9; `status: "preview"` and
    `note_vi` = "Chưa qua lab chọn lọc (P1-T22): trung bình đều các chiến lược đang bật."
  - `consensus` = number of strategies holding the ticker (weight > 0).
  - Lot math: HOSE lot size from the market config; `lot_qty` round lots, `odd_qty` remainder;
    `entry_zone` = [last_close, min(ceiling, last_close × (1 + slippage round lot))];
    `stop_price` = entry − `atr_stop_multiple` × ATR14 (engine.md §7), rounded to tick.
  - `est_cost_vnd` = fees + slippage for the buy (cost model).
  - `evidence` from `trial_stats` (P1-T21) if present.
- `GET /api/recommendations/all?source=` → `{horizons: {short: <above>, medium: ..., long: ...}}`.

## Per-stock analysis

- `GET /api/stocks?source=` → `{tickers: [{ticker, name?, group?, last, last_close, change_1d,
  in_universe: bool, signal_ok}]}`.
- `POST /api/stocks/{ticker}/analyze` body `{source?, horizons?: [..]}` → 202 `{run_id, cli}`;
  starts pipeline `stock_analysis` (params `{ticker, source, horizons}`) — tasks
  `load → features → signals → backtest → report`; same busy / terms rules as runs.
  `cli` = `vnstratlab stock <TICKER>`.
- `GET /api/stocks/{ticker}/analysis?source=` → the latest stored analysis for the ticker:
  ```
  {ticker, asof, source, synthetic, label, run_id, generated_at,
   price: {last_close, change: {"1W","1M","3M","6M","1Y","YTD"}, high_52w, low_52w,
           dist_high_52w, dist_low_52w, vol_20d_ann, vol_60d_ann, max_dd_1y, atr14,
           adv20_value_vnd, volume_vs_adv20, ceiling, floor, lot_size},
   features: [{name, label_vi, group, value, pct_rank_universe, help_vi}],
   strategies: [{strategy_id, params, horizon, trial_id, holds: bool, weight, rank, of,
                 signal: {name, value}, reason_vi, history: {selected_share, last_selected,
                 n_decisions}}],
   backtest: {buy_hold: {cagr, vol, sharpe, max_dd},
              by_strategy: [{strategy_id, horizon, periods_held, contribution_return,
                             hit_rate, avg_hold_periods}]},
   risk: {book: {short: {...}, medium: {...}, long: {...}} each {capital_vnd, weight,
          lot_qty, notional_vnd, stop_price, stop_pct, risk_vnd, est_cost_vnd}},
   quality: {gaps: [ids], exec_exclusions: n, dq_findings_1y: n, corporate_actions: [...]},
   recommendation: {by_horizon: {short: {action: "MUA"|"GIỮ"|"KHÔNG"|"BÁN",
                    consensus, of, weight, reason_vi}, ...}, summary_vi,
                    disclaimer_vi: "Chỉ là khuyến nghị tham khảo, không phải lời mời mua bán. Bạn tự quyết định và tự đặt lệnh."},
   chart: {dates, close, volume, markers: [{date, strategy_id, side: "in"|"out"}]}}
  ```
  404 `no_analysis` if never run. Signals use only data ≤ asof. `backtest.by_strategy` comes from
  the stored `oos_returns`/trades of the walk-forward where available, otherwise from a
  per-ticker attribution run inside the pipeline (the ticker's P&L share while held).
- `GET /api/stocks/compare?tickers=A,B&source=` → the `price` and `recommendation` blocks for up
  to 4 tickers side by side.

## CLI (terminal parity)

- `vnstratlab recommend [--horizon H] [--source S]` prints the preview table.
- `vnstratlab stock TICKER [--source S] [--horizon H]` runs the analysis and prints the summary.
- Both appear in `/api/cli/commands` automatically.
