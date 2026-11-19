---
id: P1-T10
title: Feature store v1 (price, volume and market-context features; point-in-time)
milestone: M1.2 Features
release: v0.1.0
status: in progress
branch: feat/P1-T10-feature-store
due: 2026-11-27
---

### P1-T10 — Feature store v1

- Depends on: P1-T06, P1-T06b, P1-T12 (ATR helper). P1-T07 (fundamentals) and P1-T08 are **not**
  available (GAP-11): valuation and asset-quality groups are deferred, see below.
- Branch: `feat/P1-T10-feature-store`, from `develop`
- Spec: plan §M1.2 P1-T10 and §3 (`features_daily`); [data-pipeline.md](../data-pipeline.md)
  "Which series feeds what"; [engine.md](../engine.md) §1 (features computation is pure), §12–13
  (`feature_version` in the trial identity); strategies S00–S18 in plan §7.
- Goal: a deterministic, point-in-time `features_daily` table that the strategies (P1-T13+) read
  through one loader, with no lookahead by construction and by test.

#### Design
- **Pure core** `src/vnstratlab/features/` (no I/O, no DuckDB; add to the pure set in
  `tests/test_data_boundary.py`): `compute_features(adjusted, exec_, universe, asof_dates=None)
  -> DataFrame` with one row per (ticker, date). Every feature at date t uses rows ≤ t only
  (rolling windows, never centred; no `shift(-k)`).
- **Input series** (data-pipeline.md rule): returns, ratios and normalised indicators from
  `prices_adjusted`; level and liquidity features (value traded, lot cost, 52-week high/low
  distance in the execution basis, ATR for risk) from `prices_exec`. ATR reuses
  `risk.atr.atr(..., ex_factor=)` so features and the engine agree.
- **Groups v1** (names are the column names; windows are module constants, documented):
  - trend/momentum: `close_vs_ma20`, `close_vs_ma50`, `ret_5d`, `ret_20d`, `ret_60d`, `ret_120d`,
    `ret_250d`, `ret_12m_skip1m` (S08), `dist_52w_high`, `dist_52w_low`, `high_20d_break` (close >
    prior 20-day high, S02)
  - relative strength: `rs_20d_vs_group_median`, `rs_20d_rank` (cross-section of the tradable
    universe on that date)
  - mean reversion: `rsi_14` (Wilder), `rsi_2` (S03 short-term), `z_ma20`, `ret_5d_vs_group_median`
    (S01)
  - volatility: `atr_14`, `std_20d`, `std_60d` (S14)
  - volume/liquidity: `vol_vs_avg20`, `value_traded_20d` (VND, exec basis)
  - market context: `group_ew_vs_ma50`, `group_breadth_ma50` (share above MA50),
    `group_ret_12m` (S15). The equal-weight universe index replaces VN30 (GAP-03); name it as
    such, do not call it VN30.
  - **Deferred** (GAP-11, P1-T07): valuation (P/B, E/P, ROE-justified P/B gap) and asset quality
    (NPL, coverage, ROE). Not created as empty columns; documented in the module docstring and
    plan P1-T10 note; strategies S10–S13 stay blocked.
- **Warm-up**: a feature is NaN until its window is full; never back-filled.
- **Missing sessions** (suspensions, omitted rows, exclusions from `exec_exclusions`): rolling
  windows count stored sessions only; a ticker excluded for a window has NaN level/liquidity
  features there. No interpolation.
- **Universe** from config (`universes/vn30_banks.yaml`) until P1-T05; log
  `survivorship_warning` once per run (plan §0).
- **Versioning**: `feature_version = hash(module code version constant, windows, adj_version of
  the input)`; stored per row. Recompute when `adj_version` changes, never mix versions in one
  read (loader raises if mixed).
- **Store + CLI** (infrastructure side, `data/` or a thin `features` writer outside the pure
  core): table `features_daily(ticker, date, <features>, feature_version)`, replaced per version
  in one transaction; `vnstratlab features build [--dry-run]`; loader
  `load_features(store, start, end, columns=None) -> DataFrame` with an `asof` guard helper that
  strategies use (rows with date > asof are impossible to receive).

#### Files to create / change
- `src/vnstratlab/features/{__init__,core,groups,build}.py` (split as you see fit; pure parts
  pure), `src/vnstratlab/data/store.py` (table), `src/vnstratlab/cli.py` (`features build`)
- Tests: `tests/test_features.py` (new), `tests/test_data_boundary.py`, `tests/test_cli.py`,
  `tests/test_store.py`
- `docs/plan/plan.md` (P1-T10 note on deferred groups), `docs/data-pipeline.md` (features
  section), `docs/architecture.md` if needed, `CHANGELOG.md`

#### Acceptance criteria (hand-computed; numbers in test comments)
1. Hand-computed values on a 30-row synthetic fixture for: `close_vs_ma20`, `ret_20d`,
   `rsi_14` (Wilder), `z_ma20`, `std_20d`, `vol_vs_avg20`, `high_20d_break`, `rs_20d_rank`.
2. **No lookahead (plan AC)**: for random t, features computed on data truncated at t equal the
   full-history features at t (property test over ≥ 20 synthetic seeds and every feature column).
3. **Reproducibility (plan AC)**: recomputing a past date gives identical values; `feature_version`
   stored; changing `adj_version` changes `feature_version`; mixed versions in one read raise.
4. Warm-up NaN until the window is full; no back-fill; a suspended ticker's windows skip missing
   sessions (hand case).
5. Level/liquidity features read `prices_exec`; return features read `prices_adjusted` (test with
   a fixture where the two differ by a stock event: `ret_20d` has no artificial gap, lot-cost /
   value features use the exec basis).
6. `atr_14` equals `risk.atr.atr` with the same ex-date factors.
7. Market context uses the equal-weight universe index; column names do not say VN30.
8. `vnstratlab features build --dry-run` writes nothing; build is idempotent; `features/` core is
   pure (boundary test).
9. No real data, no network. `pytest && ruff check . && ruff format --check . && mypy` green;
   coverage ≥ 80 %. Benchmark: building 15 tickers × 3,000 sessions on synthetic data finishes in a
   reasonable time (add a `benchmarks/` case; no hard threshold).

#### Out of scope
Fundamentals (P1-T07), strategies and registry (P1-T13+), Telegram/DQ alerts (P1-T08), VN30 index
source (GAP-03), membership history (P1-T05).
