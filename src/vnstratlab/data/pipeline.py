"""Ingest orchestration: fetch -> raw snapshot -> normalise -> upsert -> run log.

``--dry-run`` normalises in memory and creates no file or directory.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from vnstratlab.data.protocol import (
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    DataSource,
    SourceError,
    TickTable,
    universe_tickers,
)
from vnstratlab.data.raw import write_raw
from vnstratlab.data.store import Kind, MarketStore, RunRecord, kind_of_basis, kind_of_source

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig
    from vnstratlab.paths import AppPaths

Clock = Callable[[], datetime]
PrevClose = Callable[[str, date], float | None]
_PRICE_FLOATS = ("open", "high", "low", "close")


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class IngestReport:
    run_id: str
    source: str
    start: date
    end: date
    dry_run: bool
    rows_in: int
    rows_written: int
    rows_changed: int
    rows_dropped: int
    db_path: Path | None
    raw_path: Path | None
    preview: dict[str, pd.DataFrame] = field(default_factory=dict)


def source_kind(source: DataSource) -> Kind:
    """Kind from ``SourceInfo``; the name and the price basis must agree (one rule).

    The source named ``synthetic`` is the only one with ``price_basis = synthetic``. A
    disagreement is a configuration error and is refused before anything is written.
    """
    info = source.info
    by_basis = kind_of_basis(info.price_basis)
    if kind_of_source(info.name) != by_basis:
        raise SourceError(
            f"source {info.name!r} with price_basis {info.price_basis!r} is inconsistent: only the "
            "source named 'synthetic' may use price_basis 'synthetic'"
        )
    return by_basis


def make_run_id(now: datetime, source: str, start: date, end: date) -> str:
    """UTC timestamp plus a short hash of (source, start, end)."""
    digest = hashlib.sha256(f"{source}|{start}|{end}".encode()).hexdigest()[:8]
    return f"{now.astimezone(UTC):%Y%m%dT%H%M%SZ}-{digest}"


def default_start(cfg: AppConfig, paths: AppPaths, source: DataSource) -> date:
    """Day after the latest stored date, or ``project.backfill_start`` on an empty store."""
    db_path = paths.market_db_for(source_kind(source))
    if db_path.is_file():
        with MarketStore(db_path, source_kind(source), read_only=True) as store:
            latest = store.latest_date()
        if latest is not None:
            return latest + timedelta(days=1)
    return cfg.project.backfill_start


def ingest(
    cfg: AppConfig,
    paths: AppPaths,
    source: DataSource,
    start: date,
    end: date,
    dry_run: bool = False,
    clock: Clock = utc_now,
) -> IngestReport:
    started = clock()
    kind = source_kind(source)
    tickers = universe_tickers(cfg)
    run_id = make_run_id(started, source.info.name, start, end)
    raw = source.fetch_daily(tickers, start, end)
    actions = source.fetch_corporate_actions(tickers, start, end)
    db_path = paths.market_db_for(kind)
    ticks = TickTable.from_config(cfg)

    if dry_run:
        return _dry_run(source, db_path, kind, raw, actions, (start, end), ticks, run_id)

    with MarketStore(db_path, kind) as store:  # validates the store kind before anything is written
        if store.has_run(run_id):
            raise SourceError(
                f"run id {run_id} already exists in {db_path.name}; "
                "refusing to overwrite its snapshot or audit row (retry in a later second)"
            )
        raw_path = write_raw(paths, source.info.name, run_id, raw)
        try:
            with store.transaction():
                frame, dropped = normalise(
                    raw,
                    source,
                    start,
                    end,
                    ticks,
                    lambda t, d: store.previous_close(t, d, source.info.name),
                )
                result = store.upsert_prices(frame, run_id, started)
                store.upsert_corporate_actions(
                    _action_frame(actions, source.info.name), run_id, kind
                )
                store.record_run(
                    RunRecord(
                        run_id=run_id,
                        source=source.info.name,
                        started_at=started,
                        finished_at=clock(),
                        start_date=start,
                        end_date=end,
                        tickers=",".join(tickers),
                        rows_in=len(raw),
                        rows_written=result.written,
                        rows_changed=result.changed,
                        rows_dropped=dropped,
                        status="ok",
                        raw_path=str(raw_path),
                    )
                )
        except BaseException as original:
            # BaseException on purpose: Ctrl-C mid-write also leaves an error audit row.
            # The transaction rolled back: no price, action or "ok" run row survives. Keep the
            # raw snapshot and leave one audit row with status="error".
            try:
                store.record_run(
                    RunRecord(
                        run_id=run_id,
                        source=source.info.name,
                        started_at=started,
                        finished_at=clock(),
                        start_date=start,
                        end_date=end,
                        tickers=",".join(tickers),
                        rows_in=len(raw),
                        rows_written=0,
                        rows_changed=0,
                        rows_dropped=0,
                        status="error",
                        raw_path=str(raw_path),
                    )
                )
            except Exception as secondary:
                original.add_note(f"also failed to record the error run row: {secondary!r}")
            raise
    return IngestReport(
        run_id=run_id,
        source=source.info.name,
        start=start,
        end=end,
        dry_run=False,
        rows_in=len(raw),
        rows_written=result.written,
        rows_changed=result.changed,
        rows_dropped=dropped,
        db_path=db_path,
        raw_path=raw_path,
    )


def _dry_run(
    source: DataSource,
    db_path: Path,
    kind: Kind,
    raw: pd.DataFrame,
    actions: pd.DataFrame,
    window: tuple[date, date],
    ticks: TickTable,
    run_id: str,
) -> IngestReport:
    name = source.info.name
    if db_path.is_file():
        with MarketStore(db_path, kind, read_only=True) as store:
            frame, dropped = normalise(
                raw, source, *window, ticks, lambda t, d: store.previous_close(t, d, name)
            )
    else:
        frame, dropped = normalise(raw, source, *window, ticks, lambda t, d: None)
    return IngestReport(
        run_id=run_id,
        source=name,
        start=window[0],
        end=window[1],
        dry_run=True,
        rows_in=len(raw),
        rows_written=0,
        rows_changed=0,
        rows_dropped=dropped,
        db_path=None,
        raw_path=None,
        preview={"prices": frame, "corporate_actions": _action_frame(actions, name)},
    )


def _action_frame(actions: pd.DataFrame, source_name: str) -> pd.DataFrame:
    frame = actions.copy()
    frame["source"] = source_name
    if frame.empty:
        return frame.reindex(columns=["ticker", "ex_date", "type", "ratio_or_amount", "source"])
    return frame


# ------------------------------------------------------------------ normalise


def normalise(
    raw: pd.DataFrame,
    source: DataSource,
    start: date,
    end: date,
    ticks: TickTable,
    prev_close: PrevClose,
) -> tuple[pd.DataFrame, int]:
    """Schema, dtypes, sort, validity filter and derived limits. Returns ``(frame, dropped)``."""
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SourceError(f"source frame is missing columns: {', '.join(missing)}")
    columns = [*REQUIRED_COLUMNS, *(c for c in OPTIONAL_COLUMNS if c in raw.columns)]
    if "value" in raw.columns:
        columns.append("value")
    frame = raw[columns].copy()
    frame["ticker"] = frame["ticker"].astype(str)
    frame["date"] = [pd.Timestamp(d).date() for d in frame["date"]]
    for col in (*_PRICE_FLOATS, *(c for c in (*OPTIONAL_COLUMNS, "value") if c in frame.columns)):
        frame[col] = pd.to_numeric(frame[col]).astype(np.float64)
    frame["volume"] = pd.to_numeric(frame["volume"])
    keep = _valid_mask(frame, start, end)
    frame = frame[keep].copy()
    frame["volume"] = frame["volume"].astype(np.int64)
    frame = frame.drop_duplicates(["ticker", "date"], keep="last")
    dropped = len(raw) - len(frame)
    frame = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    frame = _with_limits(frame, ticks, prev_close)
    if "value" not in frame.columns:
        frame["value"] = frame["close"] * frame["volume"]
    frame["source"] = source.info.name
    frame["price_basis"] = source.info.price_basis
    return frame, dropped


def _valid_mask(frame: pd.DataFrame, start: date, end: date) -> pd.Series:
    prices = frame[list(_PRICE_FLOATS)]
    ok = prices.notna().all(axis=1) & (prices > 0).all(axis=1)
    ok &= frame["volume"].notna() & (frame["volume"] >= 0)
    in_range = [start <= d <= end for d in frame["date"]]
    return ok & pd.Series(in_range, index=frame.index)


def _with_limits(frame: pd.DataFrame, ticks: TickTable, prev_close: PrevClose) -> pd.DataFrame:
    """Fill missing ref/ceiling/floor from the previous close (GAP-02) and flag them derived."""
    if frame.empty:
        frame["derived_limits"] = pd.Series([], dtype=bool)
        for col in OPTIONAL_COLUMNS:
            if col not in frame.columns:
                frame[col] = pd.Series([], dtype=np.float64)
        return frame
    derived = not all(c in frame.columns for c in OPTIONAL_COLUMNS)
    if "ref_price" not in frame.columns:
        previous = frame.groupby("ticker")["close"].shift(1)
        first = ~frame.duplicated("ticker")
        for index in frame.index[first]:
            previous.loc[index] = prev_close(
                str(frame.loc[index, "ticker"]), frame.loc[index, "date"]
            )
        frame["ref_price"] = previous.astype(np.float64)
    if "ceiling" not in frame.columns or "floor" not in frame.columns:
        ceiling, floor = ticks.limits(frame["ref_price"].to_numpy(dtype=np.float64))
        if "ceiling" not in frame.columns:
            frame["ceiling"] = ceiling
        if "floor" not in frame.columns:
            frame["floor"] = floor
    frame["derived_limits"] = derived
    return frame
