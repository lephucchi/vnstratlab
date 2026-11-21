"""Build and read ``features_daily`` (infrastructure side; the pure core is ``core`` / ``groups``).

``build_features`` reads the rebuilt derived tables of one source, computes the features and
replaces ``features_daily`` in one transaction (idempotent: same input, same table).
``load_features`` is the only read path for strategies; it clamps to an ``asof`` date and refuses a
read that mixes feature versions.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from vnstratlab.data.adjust import adjusted_is_rebuilt
from vnstratlab.data.pipeline import load_execution_frame
from vnstratlab.data.protocol import SourceError
from vnstratlab.data.store import MarketStore
from vnstratlab.features.core import FeatureError, calendar_span_sessions, compute_features
from vnstratlab.features.groups import FEATURE_GROUPS, MA_SHORT, YEAR_WINDOW

log = logging.getLogger(__name__)

SURVIVORSHIP_WARNING = (
    "survivorship_warning: the universe is today's membership plus known exits, not the "
    "membership history (GAP-13, P1-T05)"
)


@dataclass(frozen=True)
class BuildReport:
    source: str
    feature_version: str
    rows: int
    rows_per_ticker: dict[str, int]
    nan_share: dict[str, float]  # per feature group, share of NaN cells
    span_20: float  # median weekdays covered by 20 stored sessions (sessions_in_window note)
    span_250: float
    seconds: float
    written: bool
    missing_tickers: tuple[str, ...] = ()
    stale: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)


def require_rebuilt(adjusted: pd.DataFrame) -> None:
    """Stop with a clear error when ``prices_adjusted`` is empty or not built by this code (A2)."""
    if not adjusted_is_rebuilt(adjusted):
        raise SourceError(
            "prices_adjusted is empty or was not rebuilt by the current adjustment method: "
            "run `vnstratlab data rebuild` first"
        )


def build_features(
    store: MarketStore, source: str, universe: Sequence[str], dry_run: bool = False
) -> BuildReport:
    """Compute the features of ``universe`` from the store's derived tables of ``source``."""
    started = time.perf_counter()
    if not store.has_table("prices_adjusted") or not store.has_table("prices_exec"):
        raise SourceError("no derived series in this store: run `vnstratlab data rebuild`")
    adjusted = store.read_adjusted(source)
    require_rebuilt(adjusted)
    tickers = sorted(set(universe))
    present = {str(t) for t in adjusted["ticker"]}
    missing = tuple(t for t in tickers if t not in present)
    start, end = min(adjusted["date"]), max(adjusted["date"])
    frame = load_execution_frame(store, tickers, start, end, source)
    warnings: list[str] = []
    log.warning(SURVIVORSHIP_WARNING)  # once per run (plan section 0)
    if frame.stale:
        warnings.append("execution series is older than the latest ingest run: run data rebuild")
    features = compute_features(
        adjusted, frame.prices, tickers, actions=frame.actions if not frame.actions.empty else None
    )
    if not dry_run:
        store.replace_features(features)
    version = str(features["feature_version"].iloc[0]) if len(features) else ""
    per_ticker = {str(t): int(n) for t, n in features.groupby("ticker").size().items()}
    shares = {
        group: float(features[list(cols)].isna().to_numpy().mean()) if len(features) else 1.0
        for group, cols in FEATURE_GROUPS.items()
    }
    good = adjusted[adjusted["ticker"].isin(tickers) & adjusted["signal_ok"].fillna(True)]
    span_20 = _median_span(good, MA_SHORT)
    span_250 = _median_span(good, YEAR_WINDOW)
    return BuildReport(
        source=source,
        feature_version=version,
        rows=len(features),
        rows_per_ticker=per_ticker,
        nan_share=shares,
        span_20=span_20,
        span_250=span_250,
        seconds=time.perf_counter() - started,
        written=not dry_run,
        missing_tickers=missing,
        stale=frame.stale,
        warnings=tuple(warnings),
    )


def _median_span(good: pd.DataFrame, n: int) -> float:
    """Median over tickers of the weekdays an ``n``-session window covers (A4 sanity note)."""
    spans = [calendar_span_sessions(g["date"], n) for _, g in good.groupby("ticker")]
    finite = [x for x in spans if x == x]
    return float(statistics.median(finite)) if finite else float("nan")


def asof_view(frame: pd.DataFrame, asof: date) -> pd.DataFrame:
    """Rows of ``frame`` dated on or before ``asof``: later rows cannot reach a strategy."""
    keep = pd.to_datetime(frame["date"]) <= pd.Timestamp(asof)
    return frame[keep.to_numpy()].reset_index(drop=True)


def load_features(
    store: MarketStore,
    start: date,
    end: date,
    columns: Sequence[str] | None = None,
    asof: date | None = None,
) -> pd.DataFrame:
    """Features in ``[start, end]``; with ``asof`` the window ends at ``min(end, asof)`` and
    ``asof_view`` is applied again, so no row dated after ``asof`` is returned.

    Raises ``FeatureError`` when the rows carry more than one ``feature_version``."""
    stop = end if asof is None else min(end, asof)
    frame = store.read_features(start, stop, columns)
    if asof is not None:
        frame = asof_view(frame, asof)
    versions = sorted({str(v) for v in frame["feature_version"]})
    if len(versions) > 1:
        raise FeatureError(f"mixed feature versions in one read: {versions}; run features build")
    return frame
