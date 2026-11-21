"""Feature store benchmark (card P1-T10): 15 tickers x 3,000 sessions, synthetic data only."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from vnstratlab.features import FEATURE_COLUMNS, compute_features

TICKERS = [f"T{i:02d}" for i in range(15)]
SESSIONS = 3_000


def synthetic_market() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(7)
    days = [d.date() for d in pd.bdate_range("2010-01-04", periods=SESSIONS)]
    adjusted, executed = [], []
    for ticker in TICKERS:
        close = 50_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, SESSIONS)))
        volume = rng.integers(10_000, 1_000_000, SESSIONS).astype(float)
        adjusted.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": days,
                    "adj_high": close * 1.01,
                    "adj_close": close,
                    "adj_version": "ratio-v2:bench",
                    "signal_ok": True,
                }
            )
        )
        executed.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": days,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": volume,
                }
            )
        )
    return pd.concat(adjusted, ignore_index=True), pd.concat(executed, ignore_index=True)


def test_bench_compute_features_15_tickers_3000_sessions(benchmark: Any) -> None:
    adjusted, executed = synthetic_market()
    out = benchmark.pedantic(
        compute_features, args=(adjusted, executed, TICKERS), rounds=3, iterations=1
    )
    assert len(out) == len(TICKERS) * SESSIONS
    assert out[list(FEATURE_COLUMNS)].iloc[-1].notna().all()
