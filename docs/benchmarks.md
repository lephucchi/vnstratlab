# Benchmarks

vnstratlab measures two different things and keeps them apart.

## 1. Investment benchmarks

Every lab report, recommendation and paper book is compared against reference portfolios.
A strategy that cannot beat them after costs is not recommended; when nothing beats them,
the lab's answer is **hold the equal-weight benchmark** (`hold_benchmark`).

| Benchmark | Config key | Notes |
|---|---|---|
| VN-Index buy-and-hold | `benchmarks.market_indices` | Broad market |
| VN30 buy-and-hold | `benchmarks.market_indices` | Large caps |
| Equal weight of the universe (1/N) | `benchmarks.equal_weight_universe` | The main bar to clear (DeMiguel et al., 2009). Ideal and executable (odd-lot) versions |
| Sector index | `benchmarks.sector_index` | Computed from the universe (e.g. banks) |
| Risk-free rate | `benchmarks.risk_free` | 12-month deposit rate, set by the user |
| Equal weight of all strategies | `benchmarks.naive_selectors` | Is the lab's selection better than not selecting? |
| Pick last period's winner | `benchmarks.naive_selectors` | The classic overfit selector |

**Metrics** (per horizon, executable returns after costs): annual return, volatility, Sharpe,
Deflated Sharpe, max drawdown, turnover, hit rate, number of independent decisions, and the
excess return vs. each benchmark with a bootstrap confidence interval.

The long horizon has few independent decisions (about 2 per year). Reports state that number
explicitly and avoid significance claims it cannot support.

## 2. Technical benchmarks

Speed and memory of the code, run in CI on **synthetic data only**.

| Benchmark | Lands in | Measures |
|---|---|---|
| `test_bench_cli_help` | P1-T01 | CLI start-up (import cost) |
| Simulator, 30 tickers × 10 years | P1-T11 | Engine throughput |
| Walk-forward, 20 strategies | P1-T20 | Lab cycle time |
| SPA + MCS, 2,000 bootstrap reps | P1-T22 | Statistical gate cost |
| PBO (CSCV, 16 splits) | P1-T21 | Overfitting test cost |
| `daily --dry-run`, demo data | P1-T26 | End-to-end evening loop |

Run locally:

```bash
pytest benchmarks --benchmark-only --no-cov
pytest benchmarks --benchmark-only --no-cov --benchmark-autosave   # save a baseline
pytest benchmarks --benchmark-only --no-cov --benchmark-compare    # compare with it
```

In CI ([`benchmark.yml`](../.github/workflows/benchmark.yml)) results on `develop` are stored in
the `bench-data` branch; a PR that is more than 20% slower gets a warning comment (blocking from
v0.2). Shared runners are noisy, so only large regressions are meaningful.

### Performance policy

Measure before optimising. Order of remedies: vectorise with numpy → cache incremental results
in DuckDB → `numba` for hot loops → a small optional compiled extension only if all else fails,
always with a pure-Python fallback (see [ADR-001](adr/ADR-001-python-core-recommend-only.md)).
