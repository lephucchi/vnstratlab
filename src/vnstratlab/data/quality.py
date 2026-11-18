"""Data-quality checks v0 (P1-T38), run after every non-dry ingest.

Checks read the rows of the run's source inside the run's date range and return findings; the
pipeline stores them in ``dq_results`` keyed by run id. Severity follows the data's provenance:
split-adjusted prices or derived limits (ADR-007, GAP-01/GAP-02) cannot be judged against the
HOSE limit/tick rules exactly, so those checks only warn on such rows.

Adjusted-price checks and alerts belong to P1-T06 / P1-T08 and are out of scope here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from vnstratlab.calendar import TradingCalendar, holiday_coverage
from vnstratlab.data.protocol import SourceError, TickTable
from vnstratlab.data.store import DQRecord, MarketStore

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

LARGE_MOVE = 0.15
_LIMIT_TOLERANCE = 1e-6
_PRICE_COLUMNS = ("open", "high", "low", "close")
_SEVERITY_ORDER = {"error": 0, "warning": 1}

CHECK_NAMES = (
    "duplicate_rows",
    "missing_ticker",
    "stale_data",
    "close_outside_limits",
    "off_tick",
    "ohlc_inconsistent",
    "zero_volume",
    "repeated_bar",
    "large_move",
)


@dataclass(frozen=True)
class DQResult:
    """One finding. ``ticker`` is empty for dataset-wide checks."""

    run_id: str
    check: str
    ticker: str
    date: date
    severity: str
    detail: str

    def to_record(self) -> DQRecord:
        return DQRecord(self.run_id, self.check, self.ticker, self.date, self.severity, self.detail)


def build_calendar(
    cfg: AppConfig, store: MarketStore, source: str, start: date, end: date
) -> TradingCalendar:
    """Configured holidays when every year of the range is complete, else stored sessions.

    Years without complete holiday data (GAP-05) fall back to the dates present in the store.
    """
    years = range(start.year, end.year + 1)
    if all(holiday_coverage(cfg, y) == "complete" for y in years):
        return TradingCalendar.from_config(cfg)
    stored = store.stored_sessions(source)
    return TradingCalendar.from_sessions(stored) if stored else TradingCalendar()


def run_checks(
    store: MarketStore,
    run_id: str,
    calendar: TradingCalendar,
    *,
    ticks: TickTable,
    through: date | None = None,
) -> list[DQResult]:
    """Run every check for one ingest run.

    ``through`` is the last session whose bar is final (the run end, or the day before a
    partial-bar cutoff); sessions after it are not expected. Findings are sorted errors first.
    """
    run = store.get_run(run_id)
    if run is None:
        raise SourceError(f"run {run_id} is not in {store.path.name}")
    frame = store.read_source_prices(run.source)
    last = min(run.end_date, through) if through is not None else run.end_date
    sessions = calendar.trading_days(run.start_date, last)
    results = [
        *check_duplicate_rows(frame, run_id, run.start_date, run.end_date),
        *check_missing_ticker(frame, run_id, run.start_date, sessions),
        *check_stale_data(frame, run_id, sessions),
        *check_row_rules(frame, run_id, run.start_date, run.end_date, ticks),
    ]
    results.sort(key=lambda r: (_SEVERITY_ORDER[r.severity], r.check, r.ticker, r.date))
    return results


def count_by_severity(results: list[DQResult]) -> tuple[int, int]:
    """``(errors, warnings)``."""
    errors = sum(1 for r in results if r.severity == "error")
    return errors, len(results) - errors


def final_status(base: str, results: list[DQResult]) -> str:
    """Combine the ingest status (``ok`` / ``partial``) with the checks (docs/data-pipeline.md).

    Errors win (``failed_dq``); otherwise ``partial`` stays ``partial`` (its exit code 3 is more
    specific) and findings are still stored; otherwise warnings give ``ok_with_warnings``.
    """
    errors, warnings = count_by_severity(results)
    if errors:
        return "failed_dq"
    if base != "ok":
        return base
    return "ok_with_warnings" if warnings else "ok"


# ------------------------------------------------------------------ helpers


def _soft(frame: pd.DataFrame) -> pd.Series:
    """Rows whose limit/tick rules cannot be trusted: split-adjusted or derived limits."""
    return (frame["price_basis"] == "split_adjusted") | frame["derived_limits"].astype(bool)


def _severity(soft: pd.Series) -> pd.Series:
    return pd.Series(np.where(soft, "warning", "error"), index=soft.index)


def _in_range(frame: pd.DataFrame, start: date, end: date) -> pd.Series:
    return pd.Series([start <= d <= end for d in frame["date"]], index=frame.index, dtype=bool)


def _emit(
    run_id: str,
    check: str,
    frame: pd.DataFrame,
    mask: pd.Series,
    severity: pd.Series,
    detail: pd.Series,
) -> list[DQResult]:
    out: list[DQResult] = []
    for idx in frame.index[mask]:
        out.append(
            DQResult(
                run_id,
                check,
                str(frame.at[idx, "ticker"]),
                _as_date(frame.at[idx, "date"]),
                str(severity.at[idx]),
                str(detail.at[idx]),
            )
        )
    return out


def _as_date(value: object) -> date:
    if not isinstance(value, date):
        raise TypeError(f"expected a date, got {type(value).__name__}")
    return value


def _fmt(series: pd.Series) -> pd.Series:
    return series.map(lambda v: "n/a" if pd.isna(v) else f"{v:g}")


# ------------------------------------------------------------------ dataset checks


def check_duplicate_rows(
    frame: pd.DataFrame, run_id: str, start: date, end: date
) -> list[DQResult]:
    """Same (ticker, date, source) more than once. Always an error."""
    if frame.empty:
        return []
    scoped = frame[_in_range(frame, start, end)]
    counts = Counter(
        zip(
            scoped["ticker"].astype(str).tolist(),
            [_as_date(d) for d in scoped["date"]],
            scoped["source"].astype(str).tolist(),
            strict=True,
        )
    )
    out = [
        DQResult(run_id, "duplicate_rows", t, d, "error", f"{n} rows for source {src}")
        for (t, d, src), n in counts.items()
        if n > 1
    ]
    return out


def check_missing_ticker(
    frame: pd.DataFrame, run_id: str, start: date, sessions: list[date]
) -> list[DQResult]:
    """A ticker with an earlier row but none on any session of the run range."""
    if frame.empty or not sessions:
        return []
    session_set = set(sessions)
    present = {t for t, d in zip(frame["ticker"], frame["date"], strict=True) if d in session_set}
    first = frame.groupby("ticker")["date"].min()
    latest = frame.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
    out: list[DQResult] = []
    for ticker, first_date in first.items():
        if first_date >= start or ticker in present:
            continue
        soft = bool(_soft(latest.loc[[ticker]]).iloc[0])
        out.append(
            DQResult(
                run_id,
                "missing_ticker",
                str(ticker),
                sessions[-1],
                "warning" if soft else "error",
                f"no row on any of {len(sessions)} session(s) {sessions[0]}..{sessions[-1]} "
                f"(last stored {_as_date(latest.at[ticker, 'date'])})",
            )
        )
    return out


def check_stale_data(frame: pd.DataFrame, run_id: str, sessions: list[date]) -> list[DQResult]:
    """The newest stored date is older than the last completed session. Always an error."""
    if not sessions:
        return []
    target = sessions[-1]
    newest = max(frame["date"]) if not frame.empty else None
    if newest is not None and newest >= target:
        return []
    detail = f"latest stored {newest}, last completed session {target}"
    return [DQResult(run_id, "stale_data", "", newest or target, "error", detail)]


# ------------------------------------------------------------------ row checks


def check_row_rules(
    frame: pd.DataFrame, run_id: str, start: date, end: date, ticks: TickTable
) -> list[DQResult]:
    """Per-row checks over rows in ``[start, end]``; prior rows only supply the previous bar."""
    if frame.empty:
        return []
    frame = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    grouped = frame.groupby("ticker")
    prev_close = grouped["close"].shift(1)
    prev_volume = grouped["volume"].shift(1)
    scope = _in_range(frame, start, end)
    soft = _soft(frame)
    hard = pd.Series("error", index=frame.index)
    warn = pd.Series("warning", index=frame.index)
    close, ceiling, floor = frame["close"], frame["ceiling"], frame["floor"]
    out: list[DQResult] = []

    outside = ((close > ceiling + _LIMIT_TOLERANCE) | (close < floor - _LIMIT_TOLERANCE)) & scope
    detail = "close " + _fmt(close) + " outside [" + _fmt(floor) + ", " + _fmt(ceiling) + "]"
    out += _emit(run_id, "close_outside_limits", frame, outside, _severity(soft), detail)

    off = pd.Series(False, index=frame.index)
    names = pd.Series("", index=frame.index)
    for col in _PRICE_COLUMNS:
        values = frame[col].to_numpy(dtype=np.float64)
        bad = pd.Series(~ticks.is_on_grid(values) & ~np.isnan(values), index=frame.index)
        off |= bad
        names = names.where(~bad, names + col + " ")
    out += _emit(
        run_id, "off_tick", frame, off & scope, _severity(soft), "not on tick grid: " + names
    )

    high, low, open_ = frame["high"], frame["low"], frame["open"]
    inconsistent = ((high < np.maximum(open_, close)) | (low > np.minimum(open_, close))) & scope
    detail = (
        "open "
        + _fmt(open_)
        + " high "
        + _fmt(high)
        + " low "
        + _fmt(low)
        + " close "
        + _fmt(close)
    )
    out += _emit(run_id, "ohlc_inconsistent", frame, inconsistent, hard, detail)

    zero = (frame["volume"] == 0) & scope
    out += _emit(
        run_id, "zero_volume", frame, zero, warn, pd.Series("volume is 0", index=frame.index)
    )

    repeated = (close == prev_close) & (frame["volume"] == prev_volume) & scope
    detail = "same close " + _fmt(close) + " and volume as the previous session"
    out += _emit(run_id, "repeated_bar", frame, repeated, warn, detail)

    change = (close / prev_close - 1.0).abs()
    large = (change > LARGE_MOVE) & scope
    detail = (
        "close "
        + _fmt(prev_close)
        + " -> "
        + _fmt(close)
        + " ("
        + (change * 100).map(lambda v: f"{v:.1f}")
        + " %)"
    )
    out += _emit(run_id, "large_move", frame, large, warn, detail)
    return out
