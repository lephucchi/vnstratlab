from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.pipeline import ingest
from vnstratlab.data.protocol import SourceError, SourceInfo
from vnstratlab.data.raw import read_raw, write_raw
from vnstratlab.data.store import MarketStore
from vnstratlab.paths import AppPaths, get_paths

START = date(2026, 3, 2)
END = date(2026, 3, 6)
CLOCK_TIME = datetime(2026, 3, 9, 12, 30, 15, tzinfo=UTC)


def fixed_clock() -> datetime:
    return CLOCK_TIME


class SyntheticFakeSource:
    """Fake adapter: hand-written frame, optionally without limits."""

    def __init__(
        self,
        *,
        basis: str = "raw",
        with_limits: bool = False,
        closes: dict[tuple[str, date], float] | None = None,
        extra_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.info = SourceInfo("synthetic_fake", basis, True, None, None)  # type: ignore[arg-type]
        self._with_limits = with_limits
        self._closes = closes or {}
        self._extra = extra_rows or []

    def symbols(self, universe: Sequence[str]) -> dict[str, str]:
        return {t: t for t in universe}

    def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
        days = [date(2026, 3, d) for d in (2, 3, 4, 5, 6)]
        rows: list[dict[str, object]] = []
        for ticker, base in (("AAA", 9_990.0), ("BBB", 20_000.0)):
            for i, day in enumerate(days):
                close = self._closes.get((ticker, day), base + 10 * i)
                rows.append(
                    {
                        "ticker": ticker,
                        "date": day,
                        "open": close,
                        "high": close + 10,
                        "low": close - 10,
                        "close": close,
                        "volume": 1_000 + i,
                    }
                )
        rows += self._extra
        frame = pd.DataFrame(rows)
        if self._with_limits:
            frame["ref_price"] = frame["close"]
            frame["ceiling"] = frame["close"] * 1.07
            frame["floor"] = frame["close"] * 0.93
        keep = (frame["date"] >= start) & (frame["date"] <= end)
        return frame[keep].reset_index(drop=True)

    def fetch_corporate_actions(
        self, tickers: Sequence[str], start: date, end: date
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ticker": ["AAA"],
                "ex_date": [date(2026, 3, 4)],
                "type": ["cash"],
                "ratio_or_amount": [500.0],
            }
        )


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    return load_config(tmp_path / "home")


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return get_paths(tmp_path / "home")


def run(
    cfg: AppConfig,
    paths: AppPaths,
    source: SyntheticFakeSource,
    *,
    dry_run: bool = False,
    start: date = START,
    end: date = END,
):  # type: ignore[no-untyped-def]
    return ingest(cfg, paths, source, start, end, dry_run=dry_run, clock=fixed_clock)


def test_ingest_twice_is_idempotent(cfg: AppConfig, paths: AppPaths) -> None:
    first = run(cfg, paths, SyntheticFakeSource())
    second = run(cfg, paths, SyntheticFakeSource())
    assert (first.rows_in, first.rows_written, first.rows_changed) == (10, 10, 0)
    assert (second.rows_in, second.rows_written, second.rows_changed) == (10, 0, 0)
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        frame = store.read_prices(["AAA", "BBB"], START, END)
    assert len(frame) == 10
    assert set(frame["revision"]) == {0}


def test_changed_close_bumps_revision(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource())
    target = ("AAA", date(2026, 3, 4))
    report = run(cfg, paths, SyntheticFakeSource(closes={target: 9_999.0}))
    assert report.rows_changed >= 1
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        frame = store.read_prices(["AAA"], START, END).set_index("date")
    assert frame.loc[date(2026, 3, 4), "revision"] == 1
    assert frame.loc[date(2026, 3, 4), "close"] == 9_999.0
    assert frame.loc[date(2026, 3, 2), "revision"] == 0


def test_exactly_one_changed_row_with_source_limits(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource(with_limits=True))
    # last session of BBB: nothing later depends on this close
    target = ("BBB", date(2026, 3, 6))
    report = run(cfg, paths, SyntheticFakeSource(with_limits=True, closes={target: 20_050.0}))
    assert (report.rows_written, report.rows_changed) == (1, 1)


def test_dry_run_writes_nothing(
    cfg: AppConfig, paths: AppPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    report = run(cfg, paths, SyntheticFakeSource(), dry_run=True)
    assert not home.exists()
    assert report.dry_run
    assert report.rows_in == 10
    assert report.rows_written == 0
    assert report.db_path is None
    assert report.raw_path is None
    assert set(report.preview) == {"prices", "corporate_actions"}
    assert len(report.preview["prices"]) == 10


def test_dry_run_leaves_existing_store_untouched(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource())
    before = sorted(p.name for p in paths.home.rglob("*"))
    report = run(
        cfg, paths, SyntheticFakeSource(closes={("AAA", date(2026, 3, 5)): 9_000.0}), dry_run=True
    )
    assert report.rows_written == 0
    assert sorted(p.name for p in paths.home.rglob("*")) == before
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        assert set(store.read_prices(["AAA"], START, END)["revision"]) == {0}


def test_raw_snapshot_round_trips(cfg: AppConfig, paths: AppPaths) -> None:
    source = SyntheticFakeSource()
    report = run(cfg, paths, source)
    assert report.raw_path is not None
    assert report.raw_path.parent == paths.raw_dir / "synthetic_fake"
    assert report.raw_path.name == f"{report.run_id}.parquet"
    assert report.raw_path.is_file()
    original = source.fetch_daily(["AAA", "BBB"], START, END)
    back = read_raw(report.raw_path)
    pd.testing.assert_frame_equal(back, original, check_dtype=False)


def test_write_raw_and_read_raw(paths: AppPaths) -> None:
    frame = pd.DataFrame({"ticker": ["A"], "date": [date(2026, 3, 2)], "close": [1.0]})
    path = write_raw(paths, "src", "run-x", frame)
    assert path == paths.raw_dir / "src" / "run-x.parquet"
    pd.testing.assert_frame_equal(read_raw(path), frame, check_dtype=False)


def test_run_id_is_deterministic_for_clock_and_inputs(cfg: AppConfig, paths: AppPaths) -> None:
    a = run(cfg, paths, SyntheticFakeSource())
    b = run(cfg, paths, SyntheticFakeSource())
    c = run(cfg, paths, SyntheticFakeSource(), end=date(2026, 3, 5))
    assert a.run_id == b.run_id
    assert a.run_id.startswith("20260309T123015Z-")
    assert c.run_id != a.run_id


def test_ingest_run_row_recorded(cfg: AppConfig, paths: AppPaths) -> None:
    report = run(cfg, paths, SyntheticFakeSource())
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        row = store.connection.execute(
            "SELECT source, rows_in, rows_written, rows_changed, rows_dropped, status, raw_path "
            "FROM ingest_runs WHERE run_id = ?",
            [report.run_id],
        ).fetchone()
        actions = store.read_corporate_actions(["AAA"])
    assert row == ("synthetic_fake", 10, 10, 0, 0, "ok", str(report.raw_path))
    assert list(actions["type"]) == ["cash"]
    assert list(actions["source"]) == ["synthetic_fake"]


def test_derived_limits_when_source_has_none(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource())
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        frame = store.read_prices(["AAA"], START, END).set_index("date")
    first = frame.loc[date(2026, 3, 2)]
    assert pd.isna(first["ref_price"])
    assert pd.isna(first["ceiling"])
    assert pd.isna(first["floor"])
    # day 2: ref = previous close 9,990 (just under the 10,000 band edge)
    second = frame.loc[date(2026, 3, 3)]
    assert second["ref_price"] == 9_990.0
    assert second["ceiling"] == 10_650.0
    assert second["floor"] == 9_300.0
    assert bool(frame["derived_limits"].all())
    # day 3: ref = 10,000 -> 10,700 / 9,300
    third = frame.loc[date(2026, 3, 4)]
    assert (third["ref_price"], third["ceiling"], third["floor"]) == (10_000.0, 10_700.0, 9_300.0)


def test_derived_limits_use_stored_close_across_runs(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource(), end=date(2026, 3, 3))
    run(cfg, paths, SyntheticFakeSource(), start=date(2026, 3, 4))
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        frame = store.read_prices(["AAA"], START, END).set_index("date")
    assert frame.loc[date(2026, 3, 4), "ref_price"] == frame.loc[date(2026, 3, 3), "close"]
    assert set(frame["revision"]) == {0}


def test_source_limits_are_kept_and_not_flagged_derived(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource(with_limits=True))
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        frame = store.read_prices(["AAA"], START, END)
    assert not frame["derived_limits"].any()
    assert not frame["ref_price"].isna().any()


def test_value_defaults_to_close_times_volume(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource())
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        frame = store.read_prices(["BBB"], START, END)
    assert (frame["value"] == frame["close"] * frame["volume"]).all()


def test_bad_rows_are_dropped_and_counted(cfg: AppConfig, paths: AppPaths) -> None:
    extra: list[dict[str, object]] = [
        # duplicate key (kept last), non-positive price, out-of-range date
        {
            "ticker": "AAA",
            "date": date(2026, 3, 2),
            "open": 9_990.0,
            "high": 10_000.0,
            "low": 9_980.0,
            "close": 9_990.0,
            "volume": 5,
        },
        {
            "ticker": "CCC",
            "date": date(2026, 3, 2),
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 5,
        },
    ]
    report = run(cfg, paths, SyntheticFakeSource(extra_rows=extra))
    assert report.rows_in == 12
    assert report.rows_dropped == 2
    assert report.rows_written == 10


def test_missing_columns_raise_source_error(cfg: AppConfig, paths: AppPaths) -> None:
    class Broken(SyntheticFakeSource):
        def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
            return super().fetch_daily(tickers, start, end).drop(columns=["volume"])

    with pytest.raises(SourceError, match="volume"):
        run(cfg, paths, Broken())


def test_real_and_synthetic_use_different_files(cfg: AppConfig, paths: AppPaths) -> None:
    run(cfg, paths, SyntheticFakeSource(basis="raw"))
    run(cfg, paths, SyntheticFakeSource(basis="synthetic"))
    assert paths.market_db.is_file()
    assert paths.synthetic_market_db.is_file()
    assert paths.market_db != paths.synthetic_market_db
    assert paths.market_db_for("real") == paths.market_db
    assert paths.market_db_for("synthetic") == paths.synthetic_market_db
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        assert set(store.read_prices(["AAA"], START, END)["price_basis"]) == {"raw"}
    with MarketStore(paths.synthetic_market_db, "synthetic", read_only=True) as store:
        assert set(store.read_prices(["AAA"], START, END)["price_basis"]) == {"synthetic"}


def test_ingest_into_wrong_kind_store_raises(cfg: AppConfig, paths: AppPaths) -> None:
    MarketStore(paths.market_db, "synthetic").close()  # a synthetic store at the real path
    with pytest.raises(SourceError, match="kind"):
        run(cfg, paths, SyntheticFakeSource(basis="raw"))


def test_failed_fetch_writes_nothing(cfg: AppConfig, paths: AppPaths) -> None:
    class Exploding(SyntheticFakeSource):
        def fetch_corporate_actions(
            self, tickers: Sequence[str], start: date, end: date
        ) -> pd.DataFrame:
            raise SourceError("boom")

    with pytest.raises(SourceError, match="boom"):
        run(cfg, paths, Exploding())
    assert not paths.home.exists()


# ------------------------------------------------------------------ CLI

runner = CliRunner()


def test_cli_dry_run_creates_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("APP_HOME", str(home))
    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            "synthetic",
            "--from",
            "2026-03-02",
            "--to",
            "2026-03-06",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert list(home.iterdir()) == []
    assert "dry run" in result.output.lower()
    assert "ACB" in result.output


def test_cli_ingest_writes_synthetic_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-06"]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert (home / "data" / "market-synthetic.duckdb").is_file()
    assert not (home / "data" / "market.duckdb").exists()
    assert len(list((home / "data" / "raw" / "synthetic").glob("*.parquet"))) == 1
    second = runner.invoke(app, args)
    assert second.exit_code == 0
    assert "written" in second.output


def test_cli_default_source_and_resume_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    assert (
        runner.invoke(app, ["ingest", "--from", "2026-03-02", "--to", "2026-03-04"]).exit_code == 0
    )
    result = runner.invoke(app, ["ingest", "--to", "2026-03-06"])
    assert result.exit_code == 0, result.output
    with MarketStore(home / "data" / "market-synthetic.duckdb", "synthetic", read_only=True) as s:
        assert s.latest_date() == date(2026, 3, 6)


def test_cli_up_to_date_is_a_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    runner.invoke(app, ["ingest", "--from", "2026-03-02", "--to", "2026-03-04"])
    result = runner.invoke(app, ["ingest", "--to", "2026-03-04"])
    assert result.exit_code == 0
    assert "up to date" in result.output.lower()


def test_cli_unknown_source_exits_2_and_lists_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["ingest", "--source", "nope"])
    assert result.exit_code == 2
    assert "synthetic" in result.output
    assert not (tmp_path / "home").exists()


def test_cli_rejects_bad_dates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    assert runner.invoke(app, ["ingest", "--from", "2020-13-45"]).exit_code == 2
    assert runner.invoke(app, ["ingest", "--to", "soon"]).exit_code == 2
    result = runner.invoke(app, ["ingest", "--from", "2026-03-06", "--to", "2026-03-02"])
    assert result.exit_code == 2
