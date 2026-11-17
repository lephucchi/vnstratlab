# Writing a strategy

> The strategy protocol and registry land in P1-T13. This page describes the target contract.

## Contract

A strategy is a class with three attributes and one method:

```python
class MyStrategy:
    id = "U01_low_rsi_uptrend"          # unique; user strategies start with "U"
    horizons = ("short",)                # any of "short", "medium", "long"
    params = {"rsi_max": 30, "top_n": 2}  # frozen; a new set = a new trial

    def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        """Long-only target weights per ticker, summing to <= 1.
        Use only rows with date <= asof."""
```

Full example: [`examples/my_strategy.py`](../examples/my_strategy.py).

## Rules the lab enforces

| Rule | How |
|---|---|
| Long-only, weights ≤ 1 | Validated after each call |
| Point-in-time | Features are truncated at `asof` before the call; a test re-runs on truncated data |
| Registered before backtest | Running an unregistered (strategy, params) raises |
| Every trial counts | The Deflated Sharpe Ratio uses the total number of trials |
| Same engine | Your weights go through the same HOSE rules, costs and risk layer as built-ins |

## Where to put it

- **Your own use:** drop the file into `<home>/strategies/`.
- **Contributing a built-in:** add `src/vnstratlab/strategies/builtin/<id>.py`, a docstring with
  the rule and its academic or economic basis, tests (long-only, no lookahead, deterministic,
  smoke backtest on synthetic data), and an entry in `defaults.yaml` with at most 3 parameter sets.

## Built-in library (Phase 1)

Full rules, proposed parameters and status: [strategies.md](strategies.md).

| ID | Strategy | Horizons |
|---|---|---|
| S00 | Composite score | short |
| S01 | Weekly reversal within group | short |
| S02 | 20-day breakout with volume | short |
| S03 | Oversold in uptrend | short |
| S04 | Long-only pairs | short |
| S05 | Residual mean reversion | short |
| S06 | Foreign flow (if data exists) | short |
| S08 | Cross-sectional momentum 6–12m | medium |
| S09 | Medium-term reversal | medium |
| S10 | P/B vs. ROE-justified P/B | medium, long |
| S11 | E/P | medium, long |
| S12 | Asset quality and profitability | medium, long |
| S13 | Value + momentum | medium |
| S14 | Low volatility | medium |
| S15 | Sector trend filter | medium |
| S17 | Equal weight (benchmark) | all |
| S18 | Hierarchical Risk Parity | long |

Sources for each rule are in the [plan](plan/plan.md), section 7.
