"""``oos_returns`` on ``lab.duckdb``: out-of-sample returns per trial and decision period (P1-T20).

``LabStore`` is a ``TrialRegistry`` (same file, same connection) with one more table. The registry
part stays append-only; ``oos_returns`` is derived data and is replaced per (trial, mode, source)
when a trial is re-run, so a re-run is idempotent.

Each row is the return of one decision period: from the close of the previous decision day to the
close of ``period_end`` (the next decision day), for a portfolio decided at the close of the
previous decision day. ``in_sample_by_design`` is ``period_end <= registered date`` (Vietnam date
of ``trial_registry.registered_at``; engine.md section 12), fixed when the row is written.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from vnstratlab.lab.trials import TrialError, TrialRegistry

OOS_TABLE = "oos_returns"
OOS_COLUMNS = (
    "trial_id",
    "horizon",
    "mode",
    "period_end",
    "ret",
    "turnover",
    "source",
    "feature_version",
    "engine_version",
    "run_id",
    "computed_at",
    "in_sample_by_design",
)
MODES = ("ideal", "executable")


class LabStore(TrialRegistry):
    """Trial registry plus ``oos_returns``. ``read_only=True`` never creates or changes anything."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        super().__init__(path, read_only=read_only)
        if not read_only:
            self._con.execute(
                f"""CREATE TABLE IF NOT EXISTS {OOS_TABLE} (
                    trial_id VARCHAR NOT NULL,
                    horizon VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL,
                    period_end DATE NOT NULL,
                    ret DOUBLE NOT NULL,
                    turnover DOUBLE NOT NULL,
                    source VARCHAR NOT NULL,
                    feature_version VARCHAR NOT NULL,
                    engine_version VARCHAR NOT NULL,
                    run_id VARCHAR,
                    computed_at TIMESTAMPTZ NOT NULL,
                    in_sample_by_design BOOLEAN NOT NULL,
                    PRIMARY KEY (trial_id, mode, period_end, source)
                )"""
            )

    def __enter__(self) -> LabStore:
        return self

    def _has_oos(self) -> bool:
        row = self._con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [OOS_TABLE]
        ).fetchone()
        return row is not None

    def replace_oos(
        self,
        trial_id: str,
        mode: str,
        source: str,
        rows: pd.DataFrame,
        *,
        horizon: str,
        feature_version: str,
        engine_version: str,
        registered_date: date,
        run_id: str | None = None,
        now: datetime | None = None,
    ) -> int:
        """Replace this trial's rows for ``mode`` and ``source`` with ``rows`` (columns
        ``period_end``, ``ret``, ``turnover``); returns the number of rows written."""
        if self.read_only:
            raise TrialError("lab store opened read-only: cannot write oos_returns")
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
        stamp = now if now is not None else datetime.now(UTC)
        if stamp.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        ends = [pd.Timestamp(v).date() for v in rows["period_end"].tolist()]
        rets = rows["ret"].to_numpy(dtype=float)
        turns = rows["turnover"].to_numpy(dtype=float)
        records: list[list[Any]] = [
            [
                trial_id,
                horizon,
                mode,
                end,
                float(ret),
                float(turn),
                source,
                feature_version,
                engine_version,
                run_id,
                stamp,
                end <= registered_date,
            ]
            for end, ret, turn in zip(ends, rets, turns, strict=True)
        ]
        self._con.execute("BEGIN TRANSACTION")
        try:
            self._con.execute(
                f"DELETE FROM {OOS_TABLE} WHERE trial_id = ? AND mode = ? AND source = ?",  # noqa: S608
                [trial_id, mode, source],
            )
            if records:
                self._con.executemany(
                    f"INSERT INTO {OOS_TABLE} ({', '.join(OOS_COLUMNS)}) "  # noqa: S608
                    f"VALUES ({', '.join('?' * len(OOS_COLUMNS))})",
                    records,
                )
            self._con.execute("COMMIT")
        except BaseException:
            self._con.execute("ROLLBACK")
            raise
        return len(records)

    def oos_returns(
        self,
        trial_id: str | None = None,
        *,
        source: str | None = None,
        mode: str | None = None,
    ) -> pd.DataFrame:
        """Stored rows (``OOS_COLUMNS``), ordered by trial, mode, period_end."""
        if not self._has_oos():
            return pd.DataFrame(columns=list(OOS_COLUMNS))
        where: list[str] = []
        args: list[str] = []
        for column, value in (("trial_id", trial_id), ("source", source), ("mode", mode)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        return self._con.execute(
            f"SELECT {', '.join(OOS_COLUMNS)} FROM {OOS_TABLE} {clause} "  # noqa: S608
            "ORDER BY trial_id, mode, period_end",
            args,
        ).df()
