"""Trial registry on ``lab.duckdb`` (plan section 3, rules 3-4; engine.md section 12).

Every (strategy, params, horizon, code, feature version, engine version) is a trial and must be
registered before it can be backtested (``ensure_trial``). The registry is append-only: there is no
API to update or delete a row, so ``count()`` (the DSR trial count) never decreases.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

import duckdb

from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.strategies.registry import TrialSpec, make_trial_spec

if TYPE_CHECKING:
    from vnstratlab.data.store import MarketStore
    from vnstratlab.strategies.base import Horizon, Strategy

TABLE = "trial_registry"
_COLUMNS = (
    "trial_id",
    "strategy_id",
    "params_json",
    "horizon",
    "strategy_code_hash",
    "feature_version",
    "engine_version",
    "registered_at",
    "rationale",
)


class TrialError(RuntimeError):
    """The trial registry cannot do what was asked (read-only, no feature version, ...)."""


class UnregisteredTrialError(LookupError):
    """A trial was about to run without being registered first (plan rule 3)."""


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    strategy_id: str
    params_json: str
    horizon: str
    strategy_code_hash: str
    feature_version: str
    engine_version: str
    registered_at: datetime  # timezone-aware, UTC
    rationale: str


@dataclass(frozen=True)
class RegisterResult:
    """``created`` is False when the trial already existed; ``registered_at`` is then the original
    time. In a dry run ``registered_at`` is None for a trial that would be created."""

    trial_id: str
    created: bool
    registered_at: datetime | None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("registered_at must be timezone-aware")
    return value.astimezone(UTC)


class TrialRegistry:
    """``trial_registry`` table in a DuckDB file. ``read_only=True`` never creates or changes it."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(path), read_only=read_only)
        self._con.execute("SET TimeZone = 'UTC'")
        if not read_only:
            self._con.execute(
                f"""CREATE TABLE IF NOT EXISTS {TABLE} (
                    trial_id VARCHAR PRIMARY KEY,
                    strategy_id VARCHAR NOT NULL,
                    params_json VARCHAR NOT NULL,
                    horizon VARCHAR NOT NULL,
                    strategy_code_hash VARCHAR NOT NULL,
                    feature_version VARCHAR NOT NULL,
                    engine_version VARCHAR NOT NULL,
                    registered_at TIMESTAMPTZ NOT NULL,
                    rationale VARCHAR NOT NULL
                )"""
            )

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> TrialRegistry:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ reads

    def _has_table(self) -> bool:
        row = self._con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [TABLE]
        ).fetchone()
        return row is not None

    def _select(
        self, where: str = "", args: builtins.list[str] | None = None
    ) -> builtins.list[TrialRecord]:
        if not self._has_table():
            return []
        rows = self._con.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} {where} "  # noqa: S608
            "ORDER BY registered_at, trial_id",
            args or [],
        ).fetchall()
        return [
            TrialRecord(
                trial_id=str(r[0]),
                strategy_id=str(r[1]),
                params_json=str(r[2]),
                horizon=str(r[3]),
                strategy_code_hash=str(r[4]),
                feature_version=str(r[5]),
                engine_version=str(r[6]),
                registered_at=_utc(r[7]),
                rationale=str(r[8]),
            )
            for r in rows
        ]

    def get(self, trial_id: str) -> TrialRecord | None:
        found = self._select("WHERE trial_id = ?", [trial_id])
        return found[0] if found else None

    def is_registered(self, trial_id: str) -> bool:
        return self.get(trial_id) is not None

    def require_registered(self, trial_id: str) -> TrialRecord:
        """The registered trial, or ``UnregisteredTrialError``."""
        record = self.get(trial_id)
        if record is None:
            raise UnregisteredTrialError(
                f"trial {trial_id} is not registered: run `vnstratlab lab register` first "
                "(every trial is registered before it is backtested)"
            )
        return record

    def count(self, horizon: str | None = None) -> int:
        """Number of distinct trials ever registered (the DSR trial count)."""
        if not self._has_table():
            return 0
        if horizon is None:
            row = self._con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()  # noqa: S608
        else:
            row = self._con.execute(
                f"SELECT count(*) FROM {TABLE} WHERE horizon = ?",  # noqa: S608
                [horizon],
            ).fetchone()
        return int(row[0]) if row else 0

    def list(self, horizon: str | None = None) -> builtins.list[TrialRecord]:
        """Registered trials, oldest first; optionally only one horizon."""
        if horizon is None:
            return self._select()
        return self._select("WHERE horizon = ?", [horizon])

    # ------------------------------------------------------------------ the only write

    def register(
        self,
        spec: TrialSpec,
        rationale: str,
        *,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> RegisterResult:
        """Register ``spec`` once. Idempotent: an existing trial is left untouched (its original
        ``registered_at`` is returned). With ``dry_run`` nothing is written."""
        existing = self.get(spec.trial_id)
        if existing is not None:
            return RegisterResult(spec.trial_id, False, existing.registered_at)
        if dry_run:
            return RegisterResult(spec.trial_id, True, None)
        if self.read_only:
            raise TrialError("registry opened read-only: cannot register")
        stamp = _utc(now) if now is not None else datetime.now(UTC)
        self._con.execute(
            f"INSERT INTO {TABLE} ({', '.join(_COLUMNS)}) "  # noqa: S608
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [
                spec.trial_id,
                spec.strategy_id,
                spec.params_json,
                spec.horizon,
                spec.strategy_code_hash,
                spec.feature_version,
                spec.engine_version,
                stamp,
                rationale,
            ],
        )
        stored = self.require_registered(spec.trial_id)
        return RegisterResult(spec.trial_id, stored.registered_at == stamp, stored.registered_at)


def ensure_trial(
    registry: TrialRegistry,
    strategy: Strategy,
    horizon: Horizon,
    feature_version: str,
    engine_version: str = ENGINE_VERSION,
    code_hash: str | None = None,
) -> TrialSpec:
    """Guard for the walk-forward runner: return the trial's spec if it is registered, else raise
    ``UnregisteredTrialError``. Never registers anything itself."""
    spec = make_trial_spec(strategy, horizon, feature_version, engine_version, code_hash)
    registry.require_registered(spec.trial_id)
    return spec


def store_feature_version(store: MarketStore) -> str:
    """The single ``feature_version`` in ``features_daily`` of an open market store."""
    if not store.has_table("features_daily"):
        raise TrialError("no features in this store: run `vnstratlab features build`")
    rows = store.connection.execute(
        "SELECT DISTINCT feature_version FROM features_daily ORDER BY 1"
    ).fetchall()
    versions = [str(r[0]) for r in rows]
    if not versions:
        raise TrialError("features_daily is empty: run `vnstratlab features build`")
    if len(versions) > 1:
        raise TrialError(f"mixed feature versions {versions}: run `vnstratlab features build`")
    return versions[0]
