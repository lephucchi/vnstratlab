"""Ingest orchestration: fetch -> raw snapshot -> normalise -> upsert -> run log.

``--dry-run`` normalises in memory and creates no file or directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast

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

log = logging.getLogger(__name__)
# Vietnam has no daylight saving time; a fixed offset avoids a tz-database dependency.
VN_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")

Clock = Callable[[], datetime]
PrevClose = Callable[[str, date], float | None]
# Relative tolerance when comparing a re-fetched close with the stored one (rescale check).
RESCALE_RTOL = 1e-6
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
    status: str = "ok"
    failed: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    refetched: tuple[str, ...] = ()


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


def ticker_start(
    store: MarketStore, ticker: str, source_name: str, overlap: int, backfill: date
) -> date:
    """First date to request for one ticker on a refresh.

    No stored rows: ``backfill``. Otherwise the ``overlap``-th most recent stored session (the
    first stored one if there are fewer), so the fetch re-reads ``overlap`` stored sessions and
    can notice a rescaled history; with ``overlap = 0``, the day after the latest stored date.
    """
    rows = store.connection.execute(
        "SELECT date FROM prices_daily WHERE ticker = ? AND source = ? ORDER BY date DESC LIMIT ?",
        [ticker, source_name, max(overlap, 1)],
    ).fetchall()
    if not rows:
        return backfill
    if overlap <= 0:
        return cast(date, rows[0][0]) + timedelta(days=1)
    return cast(date, rows[-1][0])


def default_start(cfg: AppConfig, paths: AppPaths, source: DataSource) -> date:
    """Earliest per-ticker refresh start over the universe (see :func:`ticker_start`).

    A ticker with no stored rows (or one that failed in a partial run and so lags behind) pulls
    the start back, so it is fetched again on the next run. Empty store: ``backfill_start``.
    """
    kind = source_kind(source)
    db_path = paths.market_db_for(kind)
    backfill = cfg.project.backfill_start
    if not db_path.is_file():
        return backfill
    overlap = int(getattr(source, "overlap_sessions", 0))
    with MarketStore(db_path, kind, read_only=True) as store:
        starts = [
            ticker_start(store, t, source.info.name, overlap, backfill)
            for t in universe_tickers(cfg)
        ]
    return min(starts, default=backfill)


@dataclass
class _Acquired:
    raw: pd.DataFrame
    actions: pd.DataFrame
    failed: dict[str, str]
    warnings: tuple[str, ...]
    refetched: tuple[str, ...]


def _replace_ticker(frame: pd.DataFrame, ticker: str, new: pd.DataFrame) -> pd.DataFrame:
    kept = frame[frame["ticker"] != ticker] if not frame.empty else frame
    return (
        pd.concat([kept, new], ignore_index=True) if not new.empty else kept.reset_index(drop=True)
    )


def _rescaled_tickers(
    raw: pd.DataFrame, actions: pd.DataFrame, store: MarketStore, source_name: str
) -> list[str]:
    """Tickers whose stored history no longer matches the source (a rescale or a new split).

    A stored ticker is flagged when any fetched close on a stored date differs from the stored
    close by more than ``RESCALE_RTOL`` (relative), or the response holds a ``stock`` event the
    store does not have yet.
    """
    con = store.connection
    flagged: list[str] = []
    if raw.empty:
        return flagged
    for ticker, group in raw.groupby("ticker"):
        name = str(ticker)
        if not con.execute(
            "SELECT 1 FROM prices_daily WHERE ticker = ? AND source = ? LIMIT 1",
            [name, source_name],
        ).fetchall():
            continue  # nothing stored: nothing to be inconsistent with
        old = dict(
            con.execute(
                "SELECT date, close FROM prices_daily WHERE ticker = ? AND source = ? "
                "AND date BETWEEN ? AND ?",
                [name, source_name, min(group["date"]), max(group["date"])],
            ).fetchall()
        )
        mismatch = any(
            day in old and abs(float(close) - old[day]) > RESCALE_RTOL * abs(old[day])
            for day, close in zip(group["date"], group["close"], strict=True)
        )
        if mismatch or _new_stock_event(actions, name, store, source_name):
            flagged.append(name)
    return flagged


def _new_stock_event(actions: pd.DataFrame, ticker: str, store: MarketStore, source: str) -> bool:
    if actions.empty:
        return False
    events = actions[(actions["ticker"] == ticker) & (actions["type"] == "stock")]
    if events.empty:
        return False
    known = {
        row[0]
        for row in store.connection.execute(
            "SELECT ex_date FROM corporate_actions WHERE ticker = ? AND type = 'stock' "
            "AND source = ?",
            [ticker, source],
        ).fetchall()
    }
    return any(pd.Timestamp(d).date() not in known for d in events["ex_date"])


def _empty_failures(
    raw: pd.DataFrame,
    tickers: list[str],
    failed: dict[str, str],
    window: tuple[date, date],
    store: MarketStore | None,
    source_name: str,
) -> dict[str, str]:
    """Tickers with no rows at all although sessions were expected (``empty_is_failure``).

    Expected means: the ticker has no stored rows yet, or the window holds a weekday after its
    first stored date. A weekday that is a public holiday cannot be told apart here, so a
    holiday-only window is also reported (rare; the next run clears it).
    """
    have = set(raw["ticker"]) if not raw.empty else set()
    found: dict[str, str] = {}
    for ticker in tickers:
        if ticker in have or ticker in failed:
            continue
        first = None
        if store is not None:
            row = store.connection.execute(
                "SELECT min(date) FROM prices_daily WHERE ticker = ? AND source = ?",
                [ticker, source_name],
            ).fetchall()
            first = row[0][0] if row else None
        if first is None:
            found[ticker] = "empty response (no stored rows yet)"
            continue
        low = max(window[0], first + timedelta(days=1))
        days = [low + timedelta(days=i) for i in range(min((window[1] - low).days + 1, 7))]
        if any(d.weekday() < 5 for d in days):
            found[ticker] = f"empty response for {low}..{window[1]}"
    return found


def _acquire(
    cfg: AppConfig,
    source: DataSource,
    tickers: list[str],
    window: tuple[date, date],
    store: MarketStore | None,
) -> _Acquired:
    """Fetch, then apply the source's consistency rules against the stored history.

    ``rescale_refetch`` sources: a stored ticker whose overlapping closes changed or that has a
    new ``stock`` event is fetched again from ``project.backfill_start`` and replaced as a whole
    (earlier rows get revisions). A ticker whose refetch fails loses its rows for this run, so
    rows of two scales are never mixed. ``empty_is_failure`` sources: see ``_empty_failures``.
    """
    start, end = window
    name = source.info.name
    raw = source.fetch_daily(tickers, start, end)
    actions = source.fetch_corporate_actions(tickers, start, end)
    failed = dict(getattr(source, "failures", {}))
    warnings = list(getattr(source, "warnings", ()))
    refetched: list[str] = []
    backfill = cfg.project.backfill_start
    if store is not None and getattr(source, "rescale_refetch", False) and start > backfill:
        for ticker in _rescaled_tickers(raw, actions, store, name):
            log.warning("rescale detected, full refetch: %s from %s", ticker, backfill)
            full = source.fetch_daily([ticker], backfill, end)
            full_actions = source.fetch_corporate_actions([ticker], backfill, end)
            failed.update(getattr(source, "failures", {}))  # the refetch reset the source's own
            warnings = [w for w in warnings if not w.startswith(f"{ticker} ")]
            warnings.extend(getattr(source, "warnings", ()))
            raw = _replace_ticker(raw, ticker, full)
            actions = _replace_ticker(actions, ticker, full_actions)
            refetched.append(ticker)
    if getattr(source, "empty_is_failure", False):
        failed.update(_empty_failures(raw, tickers, failed, window, store, name))
    if failed and raw.empty:
        raise SourceError(f"every ticker failed: {', '.join(sorted(failed))}")
    return _Acquired(raw, actions, failed, tuple(warnings), tuple(refetched))


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
    cutoff = partial_bar_cutoff(source, end, started)
    db_path = paths.market_db_for(kind)
    ticks = TickTable.from_config(cfg)

    if dry_run:
        return _dry_run(cfg, source, db_path, kind, tickers, (start, end), ticks, run_id, cutoff)

    with ExitStack() as stack:
        # An existing file is opened (and its kind validated) before the fetch, so the consistency
        # checks can read it. A missing file is created only after a fetch that produced rows.
        store = stack.enter_context(MarketStore(db_path, kind)) if db_path.is_file() else None
        got = _acquire(cfg, source, tickers, (start, end), store)
        raw, actions, failed = got.raw, got.actions, got.failed
        status = "partial" if failed else "ok"
        if store is None:
            store = stack.enter_context(MarketStore(db_path, kind))
        if store.has_run(run_id):
            raise SourceError(
                f"run id {run_id} already exists in {db_path.name}; "
                "refusing to overwrite its snapshot or audit row (retry in a later second)"
            )
        raw_path = write_raw(paths, source.info.name, run_id, raw)
        rescaled = set(got.refetched)
        try:
            with store.transaction():
                frame, dropped = normalise(
                    raw,
                    source,
                    start,
                    end,
                    ticks,
                    _prev_close(store, source.info.name, rescaled),
                    exclude_from=cutoff,
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
                        status=status,
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
        status=status,
        failed=failed,
        warnings=got.warnings,
        refetched=got.refetched,
    )


def _prev_close(store: MarketStore | None, source_name: str, rescaled: set[str]) -> PrevClose:
    """Stored previous close; none for a refetched ticker (its history starts at the backfill
    start, so its first row has no earlier row at the refreshed scale)."""

    def lookup(ticker: str, day: date) -> float | None:
        if store is None or ticker in rescaled:
            return None
        return store.previous_close(ticker, day, source_name)

    return lookup


def _dry_run(
    cfg: AppConfig,
    source: DataSource,
    db_path: Path,
    kind: Kind,
    tickers: list[str],
    window: tuple[date, date],
    ticks: TickTable,
    run_id: str,
    cutoff: date | None,
) -> IngestReport:
    name = source.info.name
    with ExitStack() as stack:
        store = (
            stack.enter_context(MarketStore(db_path, kind, read_only=True))
            if db_path.is_file()
            else None
        )
        got = _acquire(cfg, source, tickers, window, store)
        frame, dropped = normalise(
            got.raw,
            source,
            *window,
            ticks,
            _prev_close(store, name, set(got.refetched)),
            exclude_from=cutoff,
        )
    return IngestReport(
        run_id=run_id,
        source=name,
        start=window[0],
        end=window[1],
        dry_run=True,
        rows_in=len(got.raw),
        rows_written=0,
        rows_changed=0,
        rows_dropped=dropped,
        db_path=None,
        raw_path=None,
        preview={"prices": frame, "corporate_actions": _action_frame(got.actions, name)},
        status="partial" if got.failed else "ok",
        failed=got.failed,
        warnings=got.warnings,
        refetched=got.refetched,
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
    exclude_from: date | None = None,
) -> tuple[pd.DataFrame, int]:
    """Schema, dtypes, sort, validity filter and derived limits. Returns ``(frame, dropped)``.

    ``exclude_from`` drops rows dated on or after it (the partial-bar rule). Sources with
    ``drop_filler_rows = True`` also lose holiday filler rows (GAP-05).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SourceError(f"source frame is missing columns: {', '.join(missing)}")
    columns = [*REQUIRED_COLUMNS, *(c for c in OPTIONAL_COLUMNS if c in raw.columns)]
    if "value" in raw.columns:
        columns.append("value")
    frame = raw[columns].reset_index(drop=True)
    frame["ticker"] = frame["ticker"].astype(str)
    frame["date"] = [pd.Timestamp(d).date() for d in frame["date"]]
    for col in (*_PRICE_FLOATS, *(c for c in (*OPTIONAL_COLUMNS, "value") if c in frame.columns)):
        frame[col] = pd.to_numeric(frame[col]).astype(np.float64)
    frame["volume"] = pd.to_numeric(frame["volume"])
    keep = _valid_mask(frame, start, end)
    if exclude_from is not None:
        keep &= pd.Series([d < exclude_from for d in frame["date"]], index=frame.index)
    if getattr(source, "drop_filler_rows", False):
        filler = _filler_mask(frame, prev_close)
        if filler.any():
            _log_filler(frame, filler)
        keep &= ~filler
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


def _filler_mask(frame: pd.DataFrame, prev_close: PrevClose) -> pd.Series:
    """Rows with zero volume and open = high = low = close = the ticker's previous close."""
    ordered = frame.sort_values(["ticker", "date"], kind="stable")
    previous = ordered.groupby("ticker")["close"].shift(1)
    for index in ordered.index[~ordered.duplicated("ticker")]:
        previous.loc[index] = prev_close(
            str(ordered.loc[index, "ticker"]), ordered.loc[index, "date"]
        )
    reference = previous.astype(np.float64)
    flat = ordered["volume"] == 0
    for col in _PRICE_FLOATS:
        flat &= pd.Series(
            np.isclose(ordered[col], reference, rtol=1e-9, atol=0.0), index=ordered.index
        )
    return flat.reindex(frame.index).fillna(False).astype(bool)


def _log_filler(frame: pd.DataFrame, filler: pd.Series) -> None:
    for ticker, group in frame[filler].groupby("ticker"):
        days = ", ".join(str(d) for d in group["date"])
        log.info("dropped %d filler row(s) for %s: %s", len(group), ticker, days)


# ------------------------------------------------------------------ partial bar


def partial_bar_cutoff(source: DataSource, end: date, now: datetime) -> date | None:
    """Today's date when ``end`` reaches today and the session is not final yet, else ``None``.

    Reads the optional ``final_after`` (a ``datetime.time``, Vietnam time) from the source.
    """
    final_after: time | None = getattr(source, "final_after", None)
    if final_after is None:
        return None
    local = now.astimezone(VN_TZ)
    if end >= local.date() and local.time() < final_after:
        return local.date()
    return None


# ------------------------------------------------------------------ source terms


def accepted_sources_path(paths: AppPaths) -> Path:
    return paths.home / "state" / "accepted_sources.json"


def _accepted(paths: AppPaths) -> dict[str, object]:
    path = accepted_sources_path(paths)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def terms_accepted(paths: AppPaths, source: DataSource) -> bool:
    """True if the source needs no acceptance or the user accepted its current terms.

    The acceptance is keyed by (source name, terms URL): a changed URL asks again.
    """
    if not source.info.interim:
        return True
    entry = _accepted(paths).get(source.info.name)
    return isinstance(entry, dict) and entry.get("terms_url") == source.info.terms_url


def record_terms_acceptance(paths: AppPaths, source: DataSource, now: datetime) -> None:
    accepted = _accepted(paths)
    accepted[source.info.name] = {
        "accepted_at": now.astimezone(UTC).isoformat(timespec="seconds"),
        "terms_url": source.info.terms_url,
    }
    path = accepted_sources_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(accepted, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def terms_notice(source: DataSource) -> str:
    """One-time notice (Vietnamese and English) for an interim source."""
    name, url = source.info.name, source.info.terms_url
    return (
        f"Nguồn dữ liệu '{name}' là nguồn tạm thời (interim). Điều khoản: {url}\n"
        "Dữ liệu chỉ dùng cho nghiên cứu cá nhân của bạn; bạn tự chịu trách nhiệm tuân thủ "
        "điều khoản của nguồn. vnstratlab không phân phối lại dữ liệu.\n"
        f"Data source '{name}' is an interim source. Its terms: {url}\n"
        "Use the data only for your own research; you are responsible for following the "
        "source's terms. vnstratlab never redistributes downloaded data."
    )
