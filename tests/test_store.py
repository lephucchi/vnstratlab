from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from vnstratlab.data.protocol import SourceError
from vnstratlab.data.store import MarketStore, RunRecord

NOW = datetime(2026, 3, 9, 12, 0, tzinfo=UTC)


def synthetic_prices(basis: str = "raw", source: str = "synthetic_fake") -> pd.DataFrame:
    rows = [
        ("AAA", date(2026, 3, 2), 10_000.0, 10_100.0, 9_900.0, 10_050.0, 1_000, 10_000.0),
        ("AAA", date(2026, 3, 3), 10_050.0, 10_200.0, 10_000.0, 10_150.0, 2_000, 10_050.0),
        ("BBB", date(2026, 3, 2), 20_000.0, 20_100.0, 19_900.0, 20_050.0, 3_000, 20_000.0),
    ]
    frame = pd.DataFrame(
        rows,
        columns=["ticker", "date", "open", "high", "low", "close", "volume", "ref_price"],
    )
    frame["value"] = frame["close"] * frame["volume"]
    frame["ceiling"] = frame["ref_price"] * 1.07
    frame["floor"] = frame["ref_price"] * 0.93
    frame["source"] = source
    frame["price_basis"] = basis
    frame["derived_limits"] = False
    return frame


def synthetic_actions(source: str = "synthetic_fake") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA"],
            "ex_date": [date(2026, 3, 3)],
            "type": ["cash"],
            "ratio_or_amount": [500.0],
            "source": [source],
        }
    )


def test_schema_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "data" / "market.duckdb"
    with MarketStore(path, "real") as store:
        store.upsert_prices(synthetic_prices(), "r1", NOW)
    with MarketStore(path, "real") as store:
        assert len(store.read_prices(["AAA", "BBB"], date(2026, 1, 1), date(2026, 12, 31))) == 3
        tables = {
            row[0]
            for row in store.connection.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    assert {"prices_daily", "corporate_actions", "ingest_runs", "store_meta"} <= tables


def test_new_rows_get_revision_zero_and_metadata(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        result = store.upsert_prices(synthetic_prices(), "run-1", NOW)
        assert (result.inserted, result.changed, result.written) == (3, 0, 3)
        frame = store.read_prices(["AAA"], date(2026, 3, 2), date(2026, 3, 3))
    assert list(frame["revision"]) == [0, 0]
    assert set(frame["run_id"]) == {"run-1"}
    assert set(frame["price_basis"]) == {"raw"}
    assert list(frame["date"]) == [date(2026, 3, 2), date(2026, 3, 3)]


def test_identical_upsert_is_noop(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        store.upsert_prices(synthetic_prices(), "run-1", NOW)
        result = store.upsert_prices(synthetic_prices(), "run-2", NOW)
        assert (result.inserted, result.changed, result.written) == (0, 0, 0)
        frame = store.read_prices(["AAA", "BBB"], date(2026, 1, 1), date(2026, 12, 31))
    assert len(frame) == 3
    assert set(frame["revision"]) == {0}
    assert set(frame["run_id"]) == {"run-1"}


def test_changed_row_increments_revision(tmp_path: Path) -> None:
    changed = synthetic_prices()
    changed.loc[1, "close"] = 10_100.0
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        store.upsert_prices(synthetic_prices(), "run-1", NOW)
        result = store.upsert_prices(changed, "run-2", NOW)
        assert (result.inserted, result.changed, result.written) == (0, 1, 1)
        frame = store.read_prices(["AAA", "BBB"], date(2026, 1, 1), date(2026, 12, 31))
    by_key = frame.set_index(["ticker", "date"])
    assert by_key.loc[("AAA", date(2026, 3, 3)), "revision"] == 1
    assert by_key.loc[("AAA", date(2026, 3, 3)), "close"] == 10_100.0
    assert by_key.loc[("AAA", date(2026, 3, 3)), "run_id"] == "run-2"
    assert by_key.loc[("AAA", date(2026, 3, 2)), "revision"] == 0


def test_null_limits_round_trip_as_nan(tmp_path: Path) -> None:
    frame = synthetic_prices()
    frame["ref_price"] = float("nan")
    frame["ceiling"] = float("nan")
    frame["floor"] = float("nan")
    frame["derived_limits"] = True
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        store.upsert_prices(frame, "r", NOW)
        again = store.upsert_prices(frame, "r2", NOW)
        read = store.read_prices(["AAA"], date(2026, 1, 1), date(2026, 12, 31))
    assert again.written == 0
    assert read["ceiling"].isna().all()
    assert bool(read["derived_limits"].all())


def test_duplicate_keys_in_frame_rejected(tmp_path: Path) -> None:
    frame = pd.concat([synthetic_prices(), synthetic_prices()], ignore_index=True)
    with MarketStore(tmp_path / "m.duckdb", "real") as store, pytest.raises(SourceError):
        store.upsert_prices(frame, "r", NOW)


def test_missing_columns_rejected(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store, pytest.raises(SourceError):
        store.upsert_prices(synthetic_prices().drop(columns=["value"]), "r", NOW)


def test_real_frame_into_synthetic_store_raises(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "s.duckdb", "synthetic") as store:
        with pytest.raises(SourceError, match="synthetic"):
            store.upsert_prices(synthetic_prices(basis="raw"), "r", NOW)
        with pytest.raises(SourceError):
            store.upsert_corporate_actions(synthetic_actions("yahoo"), "r")


def test_synthetic_frame_into_real_store_raises(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        with pytest.raises(SourceError, match="real"):
            store.upsert_prices(synthetic_prices(basis="synthetic"), "r", NOW)
        with pytest.raises(SourceError):
            store.upsert_corporate_actions(synthetic_actions("synthetic"), "r")


def test_source_name_must_match_store_kind(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store, pytest.raises(SourceError):
        store.upsert_prices(synthetic_prices(basis="raw", source="synthetic"), "r", NOW)
    with MarketStore(tmp_path / "s.duckdb", "synthetic") as store, pytest.raises(SourceError):
        store.upsert_prices(synthetic_prices(basis="synthetic", source="yahoo"), "r", NOW)


def test_duplicate_run_id_is_not_replaced(tmp_path: Path) -> None:
    record = RunRecord(
        "r1", "s", NOW, NOW, date(2026, 3, 2), date(2026, 3, 3), "AAA", 1, 1, 0, 0, "ok", None
    )
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        store.record_run(record)
        with pytest.raises(duckdb.Error):
            store.record_run(record)


def test_reopening_with_other_kind_raises(tmp_path: Path) -> None:
    path = tmp_path / "x.duckdb"
    MarketStore(path, "synthetic").close()
    with pytest.raises(SourceError, match="kind"):
        MarketStore(path, "real")
    with MarketStore(path, "synthetic") as store:
        assert store.kind == "synthetic"


def test_corporate_action_upsert(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        first = store.upsert_corporate_actions(synthetic_actions(), "r1")
        again = store.upsert_corporate_actions(synthetic_actions(), "r2")
        changed = synthetic_actions()
        changed["ratio_or_amount"] = 700.0
        third = store.upsert_corporate_actions(changed, "r3")
        rows = store.read_corporate_actions(["AAA"])
    assert (first.inserted, again.written, third.changed) == (1, 0, 1)
    assert len(rows) == 1
    assert rows.loc[0, "ratio_or_amount"] == 700.0


def test_latest_date_and_previous_close(tmp_path: Path) -> None:
    with MarketStore(tmp_path / "m.duckdb", "real") as store:
        assert store.latest_date() is None
        assert store.previous_close("AAA", date(2026, 3, 3), "synthetic_fake") is None
        store.upsert_prices(synthetic_prices(), "r", NOW)
        assert store.latest_date() == date(2026, 3, 3)
        assert store.latest_date("BBB") == date(2026, 3, 2)
        assert store.latest_date("ZZZ") is None
        assert store.previous_close("AAA", date(2026, 3, 3), "synthetic_fake") == 10_050.0
        assert store.previous_close("AAA", date(2026, 3, 2), "synthetic_fake") is None


def test_record_run_and_read_only_open(tmp_path: Path) -> None:
    path = tmp_path / "m.duckdb"
    record = RunRecord(
        run_id="r1",
        source="synthetic_fake",
        started_at=NOW,
        finished_at=NOW,
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 3),
        tickers="AAA,BBB",
        rows_in=3,
        rows_written=3,
        rows_changed=0,
        rows_dropped=0,
        status="ok",
        raw_path="raw/x.parquet",
    )
    with MarketStore(path, "real") as store:
        store.record_run(record)
    with MarketStore(path, "real", read_only=True) as store:
        runs = store.connection.execute(
            "SELECT run_id, rows_in, status FROM ingest_runs"
        ).fetchall()
        assert runs == [("r1", 3, "ok")]
        assert store.latest_date() is None
