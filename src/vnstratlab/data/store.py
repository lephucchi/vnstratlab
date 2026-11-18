"""DuckDB market store: schema, upserts with revisions, run log and read helpers.

Synthetic and real data never share a file; ``store_meta.kind`` records which one a file is and
a mismatching open or write raises ``SourceError``.
"""

# S608 is silenced per statement: the f-string SQL below is assembled only from module-level
# column/key constants; every value (run id, timestamps, tickers, dates) is a bound parameter
# or a registered frame.

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

import duckdb
import pandas as pd

from vnstratlab.data.protocol import SourceError

Kind = Literal["synthetic", "real"]
SCHEMA_VERSION = "1"

PRICE_COLUMNS = (
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value",
    "ref_price",
    "ceiling",
    "floor",
    "source",
    "price_basis",
    "derived_limits",
)
_VALUE_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value",
    "ref_price",
    "ceiling",
    "floor",
    "price_basis",
    "derived_limits",
)
ACTION_COLUMNS = ("ticker", "ex_date", "type", "ratio_or_amount", "source")

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS store_meta (key VARCHAR PRIMARY KEY, value VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS prices_daily (
        ticker VARCHAR NOT NULL, date DATE NOT NULL,
        open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, value DOUBLE,
        ref_price DOUBLE, ceiling DOUBLE, floor DOUBLE,
        source VARCHAR NOT NULL, price_basis VARCHAR NOT NULL, derived_limits BOOLEAN NOT NULL,
        run_id VARCHAR NOT NULL, revision INTEGER NOT NULL, ingested_at TIMESTAMP NOT NULL,
        PRIMARY KEY (ticker, date, source))""",
    """CREATE TABLE IF NOT EXISTS corporate_actions (
        ticker VARCHAR NOT NULL, ex_date DATE NOT NULL, type VARCHAR NOT NULL,
        ratio_or_amount DOUBLE, source VARCHAR NOT NULL, run_id VARCHAR NOT NULL,
        PRIMARY KEY (ticker, ex_date, type, source))""",
    """CREATE TABLE IF NOT EXISTS ingest_runs (
        run_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL,
        started_at TIMESTAMP, finished_at TIMESTAMP, start_date DATE, end_date DATE,
        tickers VARCHAR, rows_in BIGINT, rows_written BIGINT, rows_changed BIGINT,
        rows_dropped BIGINT, status VARCHAR, raw_path VARCHAR)""",
    # "check" is a reserved word in SQL; it is always quoted. ticker is '' for dataset-wide checks.
    """CREATE TABLE IF NOT EXISTS dq_results (
        run_id VARCHAR NOT NULL, "check" VARCHAR NOT NULL, ticker VARCHAR NOT NULL,
        date DATE NOT NULL, severity VARCHAR NOT NULL, detail VARCHAR NOT NULL,
        PRIMARY KEY (run_id, "check", ticker, date))""",
)


@dataclass(frozen=True)
class UpsertResult:
    inserted: int
    changed: int

    @property
    def written(self) -> int:
        return self.inserted + self.changed


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    source: str
    started_at: datetime
    finished_at: datetime
    start_date: date
    end_date: date
    tickers: str
    rows_in: int
    rows_written: int
    rows_changed: int
    rows_dropped: int
    status: str
    raw_path: str | None


@dataclass(frozen=True)
class DQRecord:
    """One data-quality finding as stored in ``dq_results``."""

    run_id: str
    check: str
    ticker: str
    date: date
    severity: str
    detail: str


def _naive_utc(moment: datetime) -> datetime:
    """DuckDB TIMESTAMP columns hold naive UTC."""
    return moment if moment.tzinfo is None else moment.astimezone(UTC).replace(tzinfo=None)


def kind_of_basis(price_basis: str) -> Kind:
    return "synthetic" if price_basis == "synthetic" else "real"


def kind_of_source(source: str) -> Kind:
    return "synthetic" if source == "synthetic" else "real"


class MarketStore:
    """A DuckDB file holding one kind (synthetic or real) of market data."""

    def __init__(self, path: Path, kind: Kind, *, read_only: bool = False) -> None:
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._in_tx = False
        self._con = duckdb.connect(str(path), read_only=read_only)
        try:
            if not read_only:
                for statement in _SCHEMA:
                    _run(self._con, statement)
            self.kind = self._claim_kind(kind, read_only)
        except Exception:
            self._con.close()
            raise

    def _claim_kind(self, kind: Kind, read_only: bool) -> Kind:
        row = _first(_run(self._con, "SELECT value FROM store_meta WHERE key = 'kind'"))
        if row is None:
            if read_only:
                raise SourceError(f"{self.path}: store has no kind recorded")
            _run(self._con, "INSERT INTO store_meta VALUES ('kind', ?)", [kind])
            _run(self._con, "INSERT INTO store_meta VALUES ('schema_version', ?)", [SCHEMA_VERSION])
            return kind
        if row[0] != kind:
            raise SourceError(
                f"{self.path} holds {row[0]} data (store_meta.kind) but {kind} was requested; "
                "synthetic and real data never share a file"
            )
        return kind

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        return self._con

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> MarketStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ writes

    def _require_kind(self, kind: Kind, what: str) -> None:
        if kind != self.kind:
            raise SourceError(
                f"refusing to write a {kind} {what} into the {self.kind} store {self.path.name}"
            )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One atomic unit; nested use joins the outer transaction. Rolls back on any error."""
        if self._in_tx:
            yield
            return
        _run(self._con, "BEGIN")
        self._in_tx = True
        try:
            yield
            _run(self._con, "COMMIT")
        except BaseException:
            # also reached when COMMIT itself raises: never leave a transaction open
            with suppress(duckdb.Error):  # no transaction left to roll back
                _run(self._con, "ROLLBACK")
            raise
        finally:
            self._in_tx = False

    def has_run(self, run_id: str) -> bool:
        row = _first(_run(self._con, "SELECT 1 FROM ingest_runs WHERE run_id = ?", [run_id]))
        return row is not None

    def upsert_prices(self, frame: pd.DataFrame, run_id: str, now: datetime) -> UpsertResult:
        """Insert new keys (revision 0); update changed rows (revision + 1); skip identical."""
        missing = [c for c in PRICE_COLUMNS if c not in frame.columns]
        if missing:
            raise SourceError(f"price frame is missing columns: {', '.join(missing)}")
        for basis in frame["price_basis"].unique():
            self._require_kind(kind_of_basis(str(basis)), "price frame")
        for name in frame["source"].unique():
            self._require_kind(kind_of_source(str(name)), "price frame (source name)")
        if frame.empty:
            return UpsertResult(0, 0)
        if frame.duplicated(["ticker", "date", "source"]).any():
            raise SourceError("price frame has duplicate (ticker, date, source) keys")
        incoming = frame[list(PRICE_COLUMNS)]
        stamp = _naive_utc(now)
        con = self._con
        con.register("incoming_prices", incoming)
        try:
            with self.transaction():
                changed = _count(
                    _run(
                        con,
                        "SELECT count(*) FROM incoming_prices i "  # noqa: S608
                        f"JOIN prices_daily p {_PRICE_JOIN} WHERE {_PRICE_DIFF}",
                    )
                )
                inserted = _count(
                    _run(
                        con,
                        "SELECT count(*) FROM incoming_prices i WHERE NOT EXISTS "  # noqa: S608
                        f"(SELECT 1 FROM prices_daily p WHERE {_PRICE_KEY})",
                    )
                )
                assignments = ", ".join(f"{c} = i.{c}" for c in _VALUE_COLUMNS)
                _run(
                    con,
                    f"UPDATE prices_daily AS p SET {assignments}, "  # noqa: S608
                    "run_id = ?, ingested_at = ?, "
                    "revision = revision + 1 FROM incoming_prices i "
                    f"WHERE {_PRICE_KEY} AND {_PRICE_DIFF}",
                    [run_id, stamp],
                )
                columns = ", ".join(PRICE_COLUMNS)
                selects = ", ".join(
                    "CAST(i.date AS DATE)" if c == "date" else f"i.{c}" for c in PRICE_COLUMNS
                )
                _run(
                    con,
                    f"INSERT INTO prices_daily ({columns}, run_id, revision, ingested_at) "  # noqa: S608
                    f"SELECT {selects}, ?, 0, ? FROM incoming_prices i WHERE NOT EXISTS "
                    f"(SELECT 1 FROM prices_daily p WHERE {_PRICE_KEY})",
                    [run_id, stamp],
                )
        finally:
            con.unregister("incoming_prices")
        return UpsertResult(inserted, changed)

    def upsert_corporate_actions(
        self, frame: pd.DataFrame, run_id: str, kind: Kind | None = None
    ) -> UpsertResult:
        """Upsert actions. Every row's source name must match the store kind; ``kind`` is an
        additional constraint, never a replacement for that check."""
        missing = [c for c in ACTION_COLUMNS if c not in frame.columns]
        if missing:
            raise SourceError(f"corporate-action frame is missing columns: {', '.join(missing)}")
        kinds = {kind_of_source(str(s)) for s in frame["source"].unique()}
        if kind is not None:
            kinds.add(kind)
        for found in kinds:
            self._require_kind(found, "corporate-action frame")
        if frame.empty:
            return UpsertResult(0, 0)
        incoming = frame[list(ACTION_COLUMNS)].drop_duplicates(
            ["ticker", "ex_date", "type", "source"]
        )
        con = self._con
        con.register("incoming_actions", incoming)
        key = (
            "a.ticker = i.ticker AND a.ex_date = CAST(i.ex_date AS DATE) "
            "AND a.type = i.type AND a.source = i.source"
        )
        diff = "a.ratio_or_amount IS DISTINCT FROM i.ratio_or_amount"
        try:
            with self.transaction():
                changed = _count(
                    _run(
                        con,
                        "SELECT count(*) FROM incoming_actions i "  # noqa: S608
                        f"JOIN corporate_actions a ON {key} WHERE {diff}",
                    )
                )
                inserted = _count(
                    _run(
                        con,
                        "SELECT count(*) FROM incoming_actions i WHERE NOT EXISTS "  # noqa: S608
                        f"(SELECT 1 FROM corporate_actions a WHERE {key})",
                    )
                )
                _run(
                    con,
                    "UPDATE corporate_actions AS a SET "  # noqa: S608
                    "ratio_or_amount = i.ratio_or_amount, run_id = ? "
                    f"FROM incoming_actions i WHERE {key} AND {diff}",
                    [run_id],
                )
                _run(
                    con,
                    "INSERT INTO corporate_actions "  # noqa: S608
                    "(ticker, ex_date, type, ratio_or_amount, source, run_id) "
                    "SELECT i.ticker, CAST(i.ex_date AS DATE), i.type, i.ratio_or_amount, "
                    "i.source, ? FROM incoming_actions i WHERE NOT EXISTS "
                    f"(SELECT 1 FROM corporate_actions a WHERE {key})",
                    [run_id],
                )
        finally:
            con.unregister("incoming_actions")
        return UpsertResult(inserted, changed)

    def record_run(self, record: RunRecord) -> None:
        _run(
            self._con,
            "INSERT INTO ingest_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.run_id,
                record.source,
                _naive_utc(record.started_at),
                _naive_utc(record.finished_at),
                record.start_date,
                record.end_date,
                record.tickers,
                record.rows_in,
                record.rows_written,
                record.rows_changed,
                record.rows_dropped,
                record.status,
                record.raw_path,
            ],
        )

    def set_run_status(self, run_id: str, status: str) -> None:
        _run(self._con, "UPDATE ingest_runs SET status = ? WHERE run_id = ?", [status, run_id])

    def record_dq_results(self, records: list[DQRecord]) -> None:
        """Insert findings atomically (a run id's findings are written once)."""
        if not records:
            return
        with self.transaction():
            for r in records:
                _run(
                    self._con,
                    "INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?)",
                    [r.run_id, r.check, r.ticker, r.date, r.severity, r.detail],
                )

    # ------------------------------------------------------------------ reads

    def has_table(self, name: str) -> bool:
        rows = _run(
            self._con, "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [name]
        )
        return bool(rows)

    def get_run(self, run_id: str) -> RunRecord | None:
        rows = _run(self._con, f"SELECT {_RUN_COLUMNS} FROM ingest_runs WHERE run_id = ?", [run_id])  # noqa: S608
        return _to_run(rows[0]) if rows else None

    def recent_runs(self, limit: int = 5) -> list[RunRecord]:
        """Newest first (by ``started_at``)."""
        rows = _run(
            self._con,
            f"SELECT {_RUN_COLUMNS} FROM ingest_runs "  # noqa: S608
            "ORDER BY started_at DESC, run_id DESC LIMIT ?",
            [limit],
        )
        return [_to_run(r) for r in rows]

    def read_dq_results(self, run_id: str) -> list[DQRecord]:
        """Findings of one run, errors first; empty if the store predates ``dq_results``."""
        if not self.has_table("dq_results"):
            return []
        rows = _run(
            self._con,
            'SELECT run_id, "check", ticker, date, severity, detail FROM dq_results '
            "WHERE run_id = ? ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, "
            '"check", ticker, date',
            [run_id],
        )
        return [DQRecord(*r) for r in rows]

    def summary(self) -> list[tuple[str, date, date, int]]:
        """``(ticker, first date, last date, rows)`` per ticker, over all sources."""
        rows = _run(
            self._con,
            "SELECT ticker, min(date), max(date), count(*) FROM prices_daily "
            "GROUP BY ticker ORDER BY ticker",
        )
        return [(str(t), a, b, int(n)) for t, a, b, n in rows]

    def read_source_prices(self, source: str) -> pd.DataFrame:
        """All stored rows of one source, ordered by ticker and date (dates as ``date``)."""
        frame = self._con.execute(
            "SELECT * FROM prices_daily WHERE source = ? ORDER BY ticker, date", [source]
        ).df()
        frame["date"] = [d.date() if isinstance(d, pd.Timestamp) else d for d in frame["date"]]
        return frame

    def stored_sessions(self, source: str) -> list[date]:
        rows = _run(
            self._con,
            "SELECT DISTINCT date FROM prices_daily WHERE source = ? ORDER BY date",
            [source],
        )
        return [r[0] for r in rows]

    def row_count(self) -> int:
        return _count(_run(self._con, "SELECT count(*) FROM prices_daily"))

    def read_prices(self, tickers: list[str], start: date, end: date) -> pd.DataFrame:
        """Stored rows for ``tickers`` in ``[start, end]``, ordered by ticker and date."""
        frame = self._con.execute(
            "SELECT * FROM prices_daily WHERE list_contains(?, ticker) AND date BETWEEN ? AND ? "
            "ORDER BY ticker, date",
            [tickers, start, end],
        ).df()
        frame["date"] = [d.date() if isinstance(d, pd.Timestamp) else d for d in frame["date"]]
        return frame

    def read_corporate_actions(self, tickers: list[str]) -> pd.DataFrame:
        frame = self._con.execute(
            "SELECT * FROM corporate_actions WHERE list_contains(?, ticker) "
            "ORDER BY ticker, ex_date, type",
            [tickers],
        ).df()
        frame["ex_date"] = [
            d.date() if isinstance(d, pd.Timestamp) else d for d in frame["ex_date"]
        ]
        return frame

    def latest_date(self, ticker: str | None = None) -> date | None:
        if ticker is None:
            row = _first(_run(self._con, "SELECT max(date) FROM prices_daily"))
        else:
            row = _first(
                _run(self._con, "SELECT max(date) FROM prices_daily WHERE ticker = ?", [ticker])
            )
        value = row[0] if row else None
        return value if isinstance(value, date) else None

    def previous_close(self, ticker: str, before: date, source: str) -> float | None:
        row = _first(
            _run(
                self._con,
                "SELECT close FROM prices_daily WHERE ticker = ? AND source = ? AND date < ? "
                "ORDER BY date DESC LIMIT 1",
                [ticker, source, before],
            )
        )
        return None if row is None or row[0] is None else float(row[0])


_RUN_COLUMNS = (
    "run_id, source, started_at, finished_at, start_date, end_date, tickers, rows_in, "
    "rows_written, rows_changed, rows_dropped, status, raw_path"
)


def _to_run(row: tuple[Any, ...]) -> RunRecord:
    return RunRecord(*row)


_PRICE_KEY = "p.ticker = i.ticker AND p.date = CAST(i.date AS DATE) AND p.source = i.source"
_PRICE_JOIN = f"ON {_PRICE_KEY}"
_PRICE_DIFF = "(" + " OR ".join(f"p.{c} IS DISTINCT FROM i.{c}" for c in _VALUE_COLUMNS) + ")"


def _run(
    con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None
) -> list[tuple[Any, ...]]:
    """Execute and drain the result so the connection is free for the next statement."""
    return con.execute(sql, params).fetchall()


def _first(rows: list[tuple[Any, ...]]) -> tuple[Any, ...] | None:
    return rows[0] if rows else None


def _count(rows: list[tuple[Any, ...]]) -> int:
    return int(rows[0][0]) if rows else 0
