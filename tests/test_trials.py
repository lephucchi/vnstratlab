"""Trial registry: registration, idempotence, count and the ensure_trial guard (P1-T13)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from test_strategies_base import SyntheticEqualWeight, SyntheticOther
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.lab.trials import (
    TrialError,
    TrialRegistry,
    UnregisteredTrialError,
    ensure_trial,
    store_feature_version,
)
from vnstratlab.strategies.registry import TrialSpec, make_trial_spec

T0 = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)


@pytest.fixture
def registry(tmp_path: Path) -> Iterator[TrialRegistry]:
    with TrialRegistry(tmp_path / "data" / "lab.duckdb") as reg:
        yield reg


def spec_of(
    cls: type[SyntheticEqualWeight] = SyntheticEqualWeight,
    top: int = 1,
    fv: str = "fv1",
    engine: str = ENGINE_VERSION,
    code_hash: str | None = None,
) -> TrialSpec:
    return make_trial_spec(cls({"top": top}, ("short",)), "short", fv, engine, code_hash)


def test_unregistered_trial_is_refused_until_registered(registry: TrialRegistry) -> None:
    strategy = SyntheticEqualWeight({"top": 2}, ("short",))
    with pytest.raises(UnregisteredTrialError, match="lab register"):
        ensure_trial(registry, strategy, "short", "fv1")
    with pytest.raises(UnregisteredTrialError):
        registry.require_registered("nope")
    assert registry.count() == 0  # ensure_trial never registers on its own
    spec = spec_of(top=2)
    registry.register(spec, "config")
    assert ensure_trial(registry, strategy, "short", "fv1") == spec
    assert registry.require_registered(spec.trial_id).rationale == "config"


def test_ensure_trial_is_tied_to_every_identity_part(registry: TrialRegistry) -> None:
    strategy = SyntheticEqualWeight({"top": 2}, ("short",))
    registry.register(spec_of(top=2), "config")
    ensure_trial(registry, strategy, "short", "fv1")
    for kwargs in (
        {"feature_version": "fv2"},
        {"feature_version": "fv1", "engine_version": "engine-next"},
    ):
        with pytest.raises(UnregisteredTrialError):
            ensure_trial(registry, strategy, "short", **kwargs)  # type: ignore[arg-type]
    edited = spec_of(top=2, code_hash="edited")  # a code edit is a different, unregistered trial
    with pytest.raises(UnregisteredTrialError):
        registry.require_registered(edited.trial_id)
    with pytest.raises(UnregisteredTrialError):
        ensure_trial(registry, SyntheticEqualWeight({"top": 3}, ("short",)), "short", "fv1")


def test_count_idempotence_and_new_trials(registry: TrialRegistry) -> None:
    specs = [
        spec_of(SyntheticEqualWeight, 1),
        spec_of(SyntheticEqualWeight, 2),
        spec_of(SyntheticOther, 1),
    ]
    for spec in specs:
        assert registry.register(spec, "config", now=T0).created
    assert registry.count() == 3
    for spec in specs:  # re-registering is idempotent
        assert not registry.register(spec, "config").created
    assert registry.count() == 3

    registry.register(spec_of(SyntheticEqualWeight, 3), "config")  # one param changed
    assert registry.count() == 4

    base = specs[0]
    variants = [
        spec_of(SyntheticEqualWeight, 1, code_hash="other-source"),  # code edit
        spec_of(SyntheticEqualWeight, 1, fv="fv2"),
        spec_of(SyntheticEqualWeight, 1, engine="engine-v2"),
    ]
    assert len({base.trial_id, *(v.trial_id for v in variants)}) == 4
    seen = registry.count()
    for v in variants:
        registry.register(v, "config")
        assert registry.count() == seen + 1
        seen += 1
    assert registry.count() == 7  # all ever registered, never decremented


def test_count_and_list_by_horizon(registry: TrialRegistry) -> None:
    s = SyntheticEqualWeight({"top": 1}, ("short", "medium"))
    registry.register(make_trial_spec(s, "short", "fv", "e"), "config", now=T0)
    registry.register(make_trial_spec(s, "medium", "fv", "e"), "config", now=T0)
    registry.register(make_trial_spec(s, "medium", "fv", "e2"), "config", now=T0)
    assert registry.count() == 3
    assert registry.count("short") == 1
    assert registry.count("medium") == 2
    assert registry.count("long") == 0
    assert [r.horizon for r in registry.list("medium")] == ["medium", "medium"]
    assert len(registry.list()) == 3
    assert registry.get("missing") is None


def test_registered_at_is_utc_stored_and_never_changes(registry: TrialRegistry) -> None:
    spec = spec_of()
    plus7 = timezone(timedelta(hours=7))
    first = registry.register(spec, "config", now=datetime(2026, 11, 20, 16, 30, tzinfo=plus7))
    assert first.created
    assert first.registered_at == T0 + timedelta(hours=0)  # 16:30+07:00 == 09:30 UTC
    stored = registry.require_registered(spec.trial_id).registered_at
    assert stored == T0
    assert stored.utcoffset() == timedelta(0)

    again = registry.register(spec, "another rationale", now=T0 + timedelta(days=30))
    assert not again.created
    assert again.registered_at == T0  # a second register does not change it
    record = registry.require_registered(spec.trial_id)
    assert record.registered_at == T0
    assert record.rationale == "config"  # nor the rationale
    assert registry.count() == 1
    with pytest.raises(ValueError, match="timezone-aware"):
        registry.register(spec_of(top=9), "config", now=datetime(2026, 1, 1))


def test_registered_at_defaults_to_now_utc(registry: TrialRegistry) -> None:
    before = datetime.now(UTC)
    result = registry.register(spec_of(), "config")
    assert result.registered_at is not None
    assert before - timedelta(seconds=1) <= result.registered_at <= datetime.now(UTC)


def test_registry_is_append_only_by_api(registry: TrialRegistry) -> None:
    public = {n for n in dir(registry) if not n.startswith("_")}
    assert not {n for n in public if n.startswith(("delete", "update", "remove", "drop", "set"))}
    assert {"register", "count", "list", "get", "require_registered"} <= public


def test_dry_run_computes_ids_and_writes_nothing(registry: TrialRegistry) -> None:
    spec = spec_of()
    result = registry.register(spec, "config", dry_run=True)
    assert result.created
    assert result.registered_at is None
    assert registry.count() == 0
    registry.register(spec, "config", now=T0)
    dry = registry.register(spec, "config", dry_run=True)
    assert not dry.created
    assert dry.registered_at == T0


def test_data_persists_across_open_and_read_only_cannot_write(tmp_path: Path) -> None:
    path = tmp_path / "lab.duckdb"
    with TrialRegistry(path) as reg:
        reg.register(spec_of(), "config", now=T0)
    with TrialRegistry(path, read_only=True) as ro:
        assert ro.count() == 1
        assert ro.list()[0].registered_at == T0
        with pytest.raises(TrialError, match="read-only"):
            ro.register(spec_of(top=5), "config")
        assert ro.register(spec_of(), "config").created is False  # existing: no write needed
    with TrialRegistry(path) as again:
        assert again.count() == 1


def test_read_only_on_a_file_without_the_table(tmp_path: Path) -> None:
    path = tmp_path / "empty.duckdb"
    duckdb.connect(str(path)).close()
    with TrialRegistry(path, read_only=True) as ro:
        assert ro.count() == 0
        assert ro.count("short") == 0
        assert ro.list() == []


def test_store_feature_version(tmp_path: Path) -> None:
    from vnstratlab.data.store import MarketStore

    with MarketStore(tmp_path / "m.duckdb", "synthetic") as store:
        with pytest.raises(TrialError, match="features build"):
            store_feature_version(store)
        store.connection.execute(
            "CREATE TABLE features_daily (ticker VARCHAR, feature_version VARCHAR)"
        )
        with pytest.raises(TrialError, match="empty"):
            store_feature_version(store)
        store.connection.execute("INSERT INTO features_daily VALUES ('AAA', 'v1')")
        assert store_feature_version(store) == "v1"
        store.connection.execute("INSERT INTO features_daily VALUES ('BBB', 'v2')")
        with pytest.raises(TrialError, match="mixed"):
            store_feature_version(store)
