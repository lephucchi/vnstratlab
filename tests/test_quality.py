"""Data-quality checks, run status and `vnstratlab data status` (P1-T38). Synthetic data only."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from vnstratlab import cli
from vnstratlab.calendar import TradingCalendar
from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data import pipeline
from vnstratlab.data.pipeline import ingest
from vnstratlab.data.protocol import SourceError, SourceInfo, TickTable
from vnstratlab.data.quality import (
    CHECK_NAMES,
    DQResult,
    build_calendar,
    check_duplicate_rows,
    final_status,
    incomplete_years,
    run_checks,
)
from vnstratlab.data.store import MarketStore, RunRecord
from vnstratlab.paths import AppPaths, get_paths

runner = CliRunner()
START = date(2026, 3, 2)
END = date(2026, 3, 6)
DAYS = [date(2026, 3, d) for d in (2, 3, 4, 5, 6)]
NOW = datetime(2026, 3, 9, 12, 0, tzinfo=UTC)
TICKS = TickTable([(0, 10), (10_000, 50), (50_000, 100)], 0.07)
CAL = TradingCalendar()  # Mon-Fri; 2-6 March 2026 are sessions

Mutate = Callable[[dict[str, Any]], None]


# ------------------------------------------------------------------ builders


def bars(
    ticker: str = "AAA", days: Sequence[date] = DAYS, base: float = 20_000.0
) -> list[dict[str, Any]]:
    """Clean bars: on the tick grid, inside the limits, consistent OHLC, changing volume."""
    rows: list[dict[str, Any]] = []
    previous: float | None = None
    for i, day in enumerate(days):
        close = base + 50 * i
        ref = close if previous is None else previous
        ceiling, floor = TICKS.limits(pd.Series([ref]).to_numpy(dtype="float64"))
        rows.append(
            {
                "ticker": ticker,
                "date": day,
                "open": close,
                "high": close + 50,
                "low": close - 50,
                "close": close,
                "volume": 1_000 + i,
                "ref_price": ref,
                "ceiling": float(ceiling[0]),
                "floor": float(floor[0]),
            }
        )
        previous = close
    return rows


def store_with(
    tmp_path: Path,
    rows: list[dict[str, Any]],
    *,
    basis: str = "raw",
    derived: bool = False,
    start: date = START,
    end: date = END,
) -> MarketStore:
    frame = pd.DataFrame(rows)
    frame["value"] = frame["close"] * frame["volume"]
    frame["source"] = "synthetic_fake"
    frame["price_basis"] = basis
    frame["derived_limits"] = derived
    store = MarketStore(tmp_path / "m.duckdb", "synthetic" if basis == "synthetic" else "real")
    store.upsert_prices(frame, "run-1", NOW)
    store.record_run(
        RunRecord("run-1", "synthetic_fake", NOW, NOW, start, end, "AAA", 1, 1, 0, 0, "ok", None)
    )
    return store


def findings(store: MarketStore, check: str, **kwargs: Any) -> list[DQResult]:
    results = run_checks(store, "run-1", CAL, ticks=TICKS, **kwargs)
    return [r for r in results if r.check == check]


def broken(index: int, **changes: Any) -> list[dict[str, Any]]:
    rows = bars()
    rows[index].update(changes)
    return rows


# severity: (price_basis, derived_limits) -> expected severity of a limit/tick finding
STRICT = ("raw", False)
SOFT = [("split_adjusted", False), ("raw", True), ("split_adjusted", True)]


# ------------------------------------------------------------------ clean data


def test_clean_data_has_no_findings(tmp_path: Path) -> None:
    with store_with(tmp_path, bars()) as store:
        assert run_checks(store, "run-1", CAL, ticks=TICKS) == []


def test_every_check_name_is_documented() -> None:
    assert len(CHECK_NAMES) == len(set(CHECK_NAMES)) == 9


# ------------------------------------------------------------------ duplicate_rows


def test_duplicate_rows_fail_and_pass() -> None:
    frame = pd.DataFrame(bars())
    frame["source"] = "synthetic_fake"
    assert check_duplicate_rows(frame, "r", START, END) == []
    doubled = pd.concat([frame, frame.iloc[[1]]], ignore_index=True)
    found = check_duplicate_rows(doubled, "r", START, END)
    assert [(f.check, f.ticker, f.date, f.severity) for f in found] == [
        ("duplicate_rows", "AAA", DAYS[1], "error")
    ]


def test_duplicate_rows_is_an_error_even_for_adjusted_data() -> None:
    frame = pd.DataFrame(bars())
    frame["source"] = "x"
    doubled = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    assert check_duplicate_rows(doubled, "r", START, END)[0].severity == "error"


# ------------------------------------------------------------------ close_outside_limits


def outside_rows() -> list[dict[str, Any]]:
    rows = bars()
    over = rows[2]["ceiling"] + 50
    rows[2].update(close=over, high=over + 50)
    return rows


def test_close_outside_limits_passes_on_clean_data(tmp_path: Path) -> None:
    with store_with(tmp_path, bars()) as store:
        assert findings(store, "close_outside_limits") == []


def test_close_outside_limits_is_an_error_on_raw(tmp_path: Path) -> None:
    with store_with(tmp_path, outside_rows()) as store:
        found = findings(store, "close_outside_limits")
    assert [(f.ticker, f.date, f.severity) for f in found] == [("AAA", DAYS[2], "error")]


@pytest.mark.parametrize(("basis", "derived"), SOFT)
def test_close_outside_limits_is_a_warning_on_adjusted_or_derived(
    tmp_path: Path, basis: str, derived: bool
) -> None:
    with store_with(tmp_path, outside_rows(), basis=basis, derived=derived) as store:
        found = findings(store, "close_outside_limits")
    assert [f.severity for f in found] == ["warning"]


def test_close_below_floor_is_found(tmp_path: Path) -> None:
    rows = bars()
    under = rows[3]["floor"] - 50
    rows[3].update(close=under, low=under - 50, open=under, high=under + 50)
    with store_with(tmp_path, rows) as store:
        assert [f.date for f in findings(store, "close_outside_limits")] == [DAYS[3]]


# ------------------------------------------------------------------ off_tick


def test_off_tick_passes_on_clean_data(tmp_path: Path) -> None:
    with store_with(tmp_path, bars()) as store:
        assert findings(store, "off_tick") == []


def test_off_tick_is_an_error_on_raw(tmp_path: Path) -> None:
    rows = broken(1, close=20_075.0, high=20_100.0)  # 20075 is not a multiple of 50
    with store_with(tmp_path, rows) as store:
        found = findings(store, "off_tick")
    assert [(f.date, f.severity) for f in found] == [(DAYS[1], "error")]
    assert "close" in found[0].detail


@pytest.mark.parametrize(("basis", "derived"), SOFT)
def test_off_tick_is_a_warning_on_adjusted_or_derived(
    tmp_path: Path, basis: str, derived: bool
) -> None:
    rows = broken(1, close=20_075.0, high=20_100.0)
    with store_with(tmp_path, rows, basis=basis, derived=derived) as store:
        assert [f.severity for f in findings(store, "off_tick")] == ["warning"]


# ------------------------------------------------------------------ ohlc_inconsistent


@pytest.mark.parametrize("changes", [{"high": 20_000.0 - 50}, {"low": 20_000.0 + 100}])
def test_ohlc_inconsistent_is_an_error(tmp_path: Path, changes: dict[str, float]) -> None:
    with store_with(tmp_path, broken(0, **changes)) as store:
        found = findings(store, "ohlc_inconsistent")
    assert [(f.date, f.severity) for f in found] == [(DAYS[0], "error")]


@pytest.mark.parametrize(("basis", "derived"), [STRICT, *SOFT])
def test_ohlc_inconsistent_stays_an_error_for_every_basis(
    tmp_path: Path, basis: str, derived: bool
) -> None:
    with store_with(tmp_path, broken(0, high=19_000.0), basis=basis, derived=derived) as store:
        assert [f.severity for f in findings(store, "ohlc_inconsistent")] == ["error"]


# ------------------------------------------------------------------ zero_volume


def test_zero_volume_is_a_warning(tmp_path: Path) -> None:
    with store_with(tmp_path, broken(2, volume=0)) as store:
        found = findings(store, "zero_volume")
    assert [(f.date, f.severity) for f in found] == [(DAYS[2], "warning")]


def test_zero_volume_passes_with_volume(tmp_path: Path) -> None:
    with store_with(tmp_path, bars()) as store:
        assert findings(store, "zero_volume") == []


# ------------------------------------------------------------------ repeated_bar


def repeated_rows() -> list[dict[str, Any]]:
    rows = bars()
    rows[2].update(close=rows[1]["close"], open=rows[1]["close"], volume=rows[1]["volume"])
    return rows


def test_repeated_bar_is_a_warning_for_raw_and_adjusted(tmp_path: Path) -> None:
    with store_with(tmp_path, repeated_rows()) as store:
        found = findings(store, "repeated_bar")
    assert [(f.date, f.severity) for f in found] == [(DAYS[2], "warning")]


def test_repeated_bar_needs_both_close_and_volume_equal(tmp_path: Path) -> None:
    rows = repeated_rows()
    rows[2]["volume"] += 1
    with store_with(tmp_path, rows) as store:
        assert findings(store, "repeated_bar") == []


def test_repeated_bar_uses_the_previous_stored_row_before_the_run(tmp_path: Path) -> None:
    rows = bars(days=[date(2026, 2, 27), *DAYS[:1]])
    rows[1].update(close=rows[0]["close"], open=rows[0]["close"], volume=rows[0]["volume"])
    with store_with(tmp_path, rows, end=DAYS[0]) as store:
        assert [f.date for f in findings(store, "repeated_bar")] == [DAYS[0]]


# ------------------------------------------------------------------ large_move


def move_rows() -> list[dict[str, Any]]:
    rows = bars()
    jump = 24_000.0  # +20 % from 20_050 -> far above 15 %
    rows[2].update(close=jump, open=jump, high=jump + 50, low=jump - 50)
    return rows


def test_large_move_is_a_warning(tmp_path: Path) -> None:
    with store_with(tmp_path, move_rows(), basis="split_adjusted", derived=True) as store:
        found = findings(store, "large_move")
    # the jump and the fall back the next day are both larger than 15 %
    assert [(f.date, f.severity) for f in found] == [(DAYS[2], "warning"), (DAYS[3], "warning")]


def test_large_move_passes_below_threshold(tmp_path: Path) -> None:
    rows = bars()
    rows[2].update(close=22_000.0, open=22_000.0, high=22_050.0, low=21_950.0)  # about +9.8 %
    with store_with(tmp_path, rows) as store:
        assert findings(store, "large_move") == []


# ------------------------------------------------------------------ missing_ticker


def missing_rows() -> list[dict[str, Any]]:
    return [*bars("AAA"), *bars("BBB", days=[date(2026, 2, 27)])]


def test_missing_ticker_is_an_error_on_raw(tmp_path: Path) -> None:
    with store_with(tmp_path, missing_rows()) as store:
        found = findings(store, "missing_ticker")
    assert [(f.ticker, f.severity) for f in found] == [("BBB", "error")]


@pytest.mark.parametrize(("basis", "derived"), SOFT)
def test_missing_ticker_is_a_warning_on_adjusted_or_derived(
    tmp_path: Path, basis: str, derived: bool
) -> None:
    with store_with(tmp_path, missing_rows(), basis=basis, derived=derived) as store:
        assert [f.severity for f in findings(store, "missing_ticker")] == ["warning"]


def test_missing_ticker_passes_when_the_ticker_has_a_row_on_every_session(tmp_path: Path) -> None:
    rows = [*bars("AAA"), *bars("BBB", days=[date(2026, 2, 27), *DAYS])]
    with store_with(tmp_path, rows) as store:
        assert findings(store, "missing_ticker") == []


def test_ticker_starting_inside_the_range_is_not_missing(tmp_path: Path) -> None:
    rows = [*bars("AAA"), *bars("CCC", days=DAYS[3:])]  # ragged start, no earlier row
    with store_with(tmp_path, rows) as store:
        assert findings(store, "missing_ticker") == []


# ------------------------------------------------------------------ stale_data


def test_stale_data_is_an_error_for_every_basis(tmp_path: Path) -> None:
    rows = bars(days=DAYS[:3])  # data stops on 4 March, the run reaches 6 March
    for basis, derived in [STRICT, *SOFT]:
        path = tmp_path / f"{basis}-{derived}"
        path.mkdir()
        with store_with(path, rows, basis=basis, derived=derived) as store:
            found = findings(store, "stale_data")
        assert [(f.ticker, f.date, f.severity) for f in found] == [("", DAYS[2], "error")]


def test_stale_data_passes_when_latest_reaches_the_last_session(tmp_path: Path) -> None:
    with store_with(tmp_path, bars()) as store:
        assert findings(store, "stale_data") == []


def test_stale_data_respects_the_partial_bar_cutoff(tmp_path: Path) -> None:
    rows = bars(days=DAYS[:4])  # no bar for 6 March because it is not final yet
    with store_with(tmp_path, rows) as store:
        assert findings(store, "stale_data") != []
        assert findings(store, "stale_data", through=DAYS[3]) == []


def test_a_holiday_is_not_a_missing_session(tmp_path: Path) -> None:
    holiday = TradingCalendar([DAYS[4]])
    rows = bars(days=DAYS[:4])
    with store_with(tmp_path, rows) as store:
        assert run_checks(store, "run-1", holiday, ticks=TICKS) == []


# ------------------------------------------------------------------ calendar choice


def test_build_calendar_is_weekdays_minus_configured_holidays(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "home")
    cal = build_calendar(cfg)
    assert cal.observed_range is None  # stored sessions are never the reference
    assert cal.trading_days(START, END) == DAYS
    assert not cal.is_trading_day(date(2026, 4, 30))  # a listed 2026 holiday
    far = date(2031, 6, 2)  # no holiday data for 2031: plain weekdays
    assert cal.trading_days(far, far + timedelta(days=1)) == [far, far + timedelta(days=1)]


def test_incomplete_years(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "home")
    assert incomplete_years(cfg, START, END) == frozenset()
    assert incomplete_years(cfg, date(2026, 12, 28), date(2028, 1, 4)) == {2027, 2028}


# ------------------------------------------------------------------ status combination


def result(severity: str) -> DQResult:
    return DQResult("r", "zero_volume", "AAA", START, severity, "x")


def test_final_status_table() -> None:
    assert final_status("ok", []) == "ok"
    assert final_status("ok", [result("warning")]) == "ok_with_warnings"
    assert final_status("ok", [result("error"), result("warning")]) == "failed_dq"
    assert final_status("partial", [result("warning")]) == "partial"
    assert final_status("partial", []) == "partial"
    assert final_status("partial", [result("error")]) == "failed_dq"


# ------------------------------------------------------------------ pipeline integration


class FakeSource:
    """Hand-written frame source (raw basis). ``clean`` bars have source limits."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        basis: str = "raw",
        failures: dict[str, str] | None = None,
    ) -> None:
        self.info = SourceInfo("synthetic_fake", basis, True, None, None)  # type: ignore[arg-type]
        self._rows = rows
        self.failures = failures or {}

    def symbols(self, universe: Sequence[str]) -> dict[str, str]:
        return {t: t for t in universe}

    def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame(self._rows)

    def fetch_corporate_actions(
        self, tickers: Sequence[str], start: date, end: date
    ) -> pd.DataFrame:
        return pd.DataFrame(columns=["ticker", "ex_date", "type", "ratio_or_amount"])


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    return load_config(tmp_path / "home")


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return get_paths(tmp_path / "home")


def run_ingest(cfg: AppConfig, paths: AppPaths, source: FakeSource) -> Any:
    return ingest(cfg, paths, source, START, END, clock=lambda: NOW)


def stored_status(paths: AppPaths) -> list[tuple[Any, ...]]:
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        return store.connection.execute("SELECT status FROM ingest_runs").fetchall()


def test_clean_ingest_is_ok_and_writes_no_findings(cfg: AppConfig, paths: AppPaths) -> None:
    report = run_ingest(cfg, paths, FakeSource(bars()))
    assert report.status == "ok"
    assert report.dq == ()
    assert stored_status(paths) == [("ok",)]


def test_warnings_only_gives_ok_with_warnings(cfg: AppConfig, paths: AppPaths) -> None:
    report = run_ingest(cfg, paths, FakeSource(broken(2, volume=0)))
    assert report.status == "ok_with_warnings"
    assert [r.check for r in report.dq] == ["zero_volume"]
    assert stored_status(paths) == [("ok_with_warnings",)]
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        stored = store.read_dq_results(report.run_id)
    assert [(r.check, r.severity, r.ticker, r.date) for r in stored] == [
        ("zero_volume", "warning", "AAA", DAYS[2])
    ]


def test_error_gives_failed_dq_and_keeps_the_data(cfg: AppConfig, paths: AppPaths) -> None:
    report = run_ingest(cfg, paths, FakeSource(broken(0, high=19_000.0)))
    assert report.status == "failed_dq"
    assert stored_status(paths) == [("failed_dq",)]
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        assert store.row_count() == 5  # written data stays for inspection
        errors = [r for r in store.read_dq_results(report.run_id) if r.severity == "error"]
    assert [r.check for r in errors] == ["ohlc_inconsistent"]


def test_errors_win_over_partial_and_warnings_keep_partial(cfg: AppConfig, paths: AppPaths) -> None:
    failures = {"CCC": "synthetic timeout"}
    warned = run_ingest(cfg, paths, FakeSource(broken(2, volume=0), failures=failures))
    assert warned.status == "partial"
    assert warned.failed == failures
    assert [r.check for r in warned.dq] == ["zero_volume"]
    assert stored_status(paths) == [("partial",)]


def test_errors_with_failed_tickers_give_failed_dq(tmp_path: Path) -> None:
    home = tmp_path / "other"
    cfg = load_config(home)
    paths = get_paths(home)
    report = run_ingest(
        cfg, paths, FakeSource(broken(0, high=19_000.0), failures={"CCC": "synthetic timeout"})
    )
    assert report.status == "failed_dq"
    assert report.failed == {"CCC": "synthetic timeout"}


def test_dry_run_runs_no_checks_and_creates_nothing(
    cfg: AppConfig, paths: AppPaths, tmp_path: Path
) -> None:
    report = ingest(cfg, paths, FakeSource(bars()), START, END, dry_run=True, clock=lambda: NOW)
    assert report.dq == ()
    assert not (tmp_path / "home").exists()


def test_old_store_without_dq_table_reads_as_empty(tmp_path: Path) -> None:
    with store_with(tmp_path, bars()) as store:
        store.connection.execute("DROP TABLE dq_results")
        assert store.read_dq_results("run-1") == []


# ------------------------------------------------------------------ CLI


def use_fake(monkeypatch: pytest.MonkeyPatch, source: FakeSource) -> None:
    monkeypatch.setattr(cli, "get_source", lambda name, cfg: source)


INGEST = ["ingest", "--source", "synthetic_fake", "--from", "2026-03-02", "--to", "2026-03-06"]


def test_cli_exit_codes_for_dq_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    args = [*INGEST, "--accept-source-terms"]
    use_fake(monkeypatch, FakeSource(broken(0, high=19_000.0)))
    failed = runner.invoke(app, args)
    assert failed.exit_code == 1, failed.output
    assert "failed_dq" in failed.output
    assert "ohlc_inconsistent" in failed.output
    use_fake(monkeypatch, FakeSource(broken(2, volume=0)))
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home2"))
    warned = runner.invoke(app, args)
    assert warned.exit_code == 0, warned.output
    assert "ok_with_warnings" in warned.output
    use_fake(monkeypatch, FakeSource(broken(2, volume=0), failures={"CCC": "boom"}))
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home3"))
    partial = runner.invoke(app, args)
    assert partial.exit_code == 3, partial.output


def test_data_status_on_an_empty_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    result = runner.invoke(app, ["data", "status"])
    assert result.exit_code == 0, result.output
    assert "no data yet" in result.output
    assert "gaps: " in result.output
    assert not home.exists()
    as_json = runner.invoke(app, ["data", "status", "--json"])
    payload = json.loads(as_json.output)
    assert payload["stores"] == []
    assert payload["gaps"]["counts"]["open"] >= 1


def test_data_status_after_an_ingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    rows = [*bars("AAA"), *bars("CCC", days=DAYS[2:])]  # ragged start
    use_fake(monkeypatch, FakeSource(rows[:5] + [{**r, "volume": 0} for r in rows[5:6]] + rows[6:]))
    assert runner.invoke(app, [*INGEST, "--accept-source-terms"]).exit_code == 0
    text = runner.invoke(app, ["data", "status"])
    assert text.exit_code == 0, text.output
    for fragment in ("market.duckdb", "AAA", "CCC", "2026-03-04 .. 2026-03-06", "last runs"):
        assert fragment in text.output
    assert "ok_with_warnings" in text.output
    assert "checks of last run" in text.output
    assert "GAP-01" in text.output
    payload = json.loads(runner.invoke(app, ["data", "status", "--json"]).output)
    store = payload["stores"][0]
    assert store["kind"] == "real"
    assert {t["ticker"]: t["first"] for t in store["tickers"]} == {
        "AAA": "2026-03-02",
        "CCC": "2026-03-04",
    }
    assert store["runs"][0]["status"] == "ok_with_warnings"
    assert store["last_run_checks"]["warnings"] == 1
    assert store["last_run_checks"]["errors"] == 0


def test_data_status_lists_the_first_ten_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    days = [date(2026, 3, 2) + timedelta(days=i) for i in range(0, 5)]
    rows = [r for t in "ABCDEFGHIJKL" for r in bars(t, days=days)]
    for r in rows:
        if r["date"] == DAYS[0]:
            r["high"] = 19_950.0  # below open and close on 12 tickers
    use_fake(monkeypatch, FakeSource(rows))
    assert runner.invoke(app, [*INGEST, "--accept-source-terms"]).exit_code == 1
    payload = json.loads(runner.invoke(app, ["data", "status", "--json"]).output)
    checks = payload["stores"][0]["last_run_checks"]
    assert checks["errors"] == 12
    assert len(checks["first_errors"]) == 10


def test_data_status_on_the_synthetic_market(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    ingest_args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-06"]
    done = runner.invoke(app, ingest_args)
    assert done.exit_code == 0, done.output
    payload = json.loads(runner.invoke(app, ["data", "status", "--json"]).output)
    store = payload["stores"][0]
    assert store["file"] == "market-synthetic.duckdb"
    assert store["kind"] == "synthetic"
    assert store["last_run_checks"]["errors"] == 0


def test_doctor_prints_the_open_gap_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert re.search(r"^gaps: \d+ open \(high \d+, medium \d+, low \d+\)$", result.output, re.M)


# ------------------------------------------------------------------ G2 review fixes


def test_interior_hole_is_a_suspension_warning_even_on_raw_data(tmp_path: Path) -> None:
    rows = [*bars("AAA"), *bars("BBB", days=[date(2026, 2, 27), DAYS[0], DAYS[3], DAYS[4]])]
    with store_with(tmp_path, rows) as store:
        found = findings(store, "missing_ticker")
    assert [(f.ticker, f.date, f.severity) for f in found] == [("BBB", DAYS[1], "warning")]
    assert "2 interior session(s)" in found[0].detail
    assert f"{DAYS[1]}..{DAYS[2]}" in found[0].detail


@pytest.mark.parametrize(("basis", "derived"), [STRICT, *SOFT])
def test_interior_hole_is_a_warning_for_every_basis(
    tmp_path: Path, basis: str, derived: bool
) -> None:
    rows = [*bars("AAA"), *bars("BBB", days=[DAYS[0], DAYS[2], DAYS[3], DAYS[4]])]
    with store_with(tmp_path, rows, basis=basis, derived=derived) as store:
        assert [f.severity for f in findings(store, "missing_ticker")] == ["warning"]


def test_trailing_gap_follows_the_severity_table(tmp_path: Path) -> None:
    rows = [*bars("AAA"), *bars("BBB", days=DAYS[:3])]  # BBB stops after 4 March
    with store_with(tmp_path, rows) as store:
        found = findings(store, "missing_ticker")
    assert [(f.ticker, f.date, f.severity) for f in found] == [("BBB", DAYS[3], "error")]
    assert "2 trailing session(s)" in found[0].detail
    path = tmp_path / "adj"
    path.mkdir()
    with store_with(path, rows, basis="split_adjusted") as store:
        assert [f.severity for f in findings(store, "missing_ticker")] == ["warning"]
    path = tmp_path / "weak"
    path.mkdir()
    with store_with(path, rows) as store:
        found = findings(store, "missing_ticker", incomplete_years=frozenset({2026}))
    assert [f.severity for f in found] == ["warning"]


def test_interior_and_trailing_gaps_give_two_findings(tmp_path: Path) -> None:
    rows = [*bars("AAA"), *bars("BBB", days=[DAYS[0], DAYS[2]])]
    with store_with(tmp_path, rows) as store:
        found = findings(store, "missing_ticker")
    assert [(f.date, f.severity) for f in found] == [(DAYS[3], "error"), (DAYS[1], "warning")]


def test_multi_year_default_synthetic_ingest_does_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    args = ["ingest", "--source", "synthetic", "--from", "2015-01-01", "--to", "2020-12-31"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    with MarketStore(tmp_path / "home" / "data" / "market-synthetic.duckdb", "synthetic") as store:
        rows = store.connection.execute("SELECT status FROM ingest_runs").fetchall()
    assert rows[0][0] in {"ok", "ok_with_warnings"}


def test_data_commands_survive_a_cp1252_pipe(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "PYTHONIOENCODING": "cp1252",
        "APP_HOME": str(tmp_path / "home"),
        "PYTHONUTF8": "0",
    }
    status = subprocess.run(
        [sys.executable, "-m", "vnstratlab", "data", "status", "--json"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout.decode("ascii"))["gaps"]["counts"] is not None
    gaps = subprocess.run(
        [sys.executable, "-m", "vnstratlab", "data", "gaps"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert gaps.returncode == 0, gaps.stderr
    text = subprocess.run(
        [sys.executable, "-m", "vnstratlab", "data", "status"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert text.returncode == 0, text.stderr


def test_stale_data_is_a_warning_in_an_incomplete_year(tmp_path: Path) -> None:
    rows = bars(days=DAYS[:3])
    with store_with(tmp_path, rows) as store:
        found = findings(store, "stale_data", incomplete_years=frozenset({2026}))
    assert [(f.date, f.severity) for f in found] == [(DAYS[2], "warning")]


def test_stale_data_stays_an_error_for_a_complete_year_in_a_mixed_range(tmp_path: Path) -> None:
    mon = date(2026, 12, 28)  # 28-31 December 2026 are complete-year sessions; 2027 is partial
    days = [mon, mon + timedelta(days=1)]
    with store_with(tmp_path, bars(days=days), start=mon, end=date(2027, 1, 8)) as store:
        found = findings(store, "stale_data", incomplete_years=frozenset({2027}))
    assert [f.severity for f in found] == ["error"]
    assert found[0].detail.endswith("2026-12-31")
    path = tmp_path / "ok"
    path.mkdir()
    days = [mon + timedelta(days=i) for i in range(4)]  # data reaches the last 2026 session
    with store_with(path, bars(days=days), start=mon, end=date(2027, 1, 8)) as store:
        found = findings(store, "stale_data", incomplete_years=frozenset({2027}))
    assert [f.severity for f in found] == ["warning"]


def test_ingest_into_an_incomplete_year_reports_stale_data_as_a_warning(
    cfg: AppConfig, paths: AppPaths
) -> None:
    days = [date(2027, 1, 4), date(2027, 1, 5)]  # the store ends 5 Jan; the run reaches 8 Jan
    report = ingest(
        cfg, paths, FakeSource(bars(days=days)), days[0], date(2027, 1, 8), clock=lambda: NOW
    )
    stale = [r for r in report.dq if r.check == "stale_data"]
    assert [(r.severity, r.date) for r in stale] == [("warning", days[1])]
    assert report.status == "ok_with_warnings"
    assert not [r for r in report.dq if r.severity == "error"]


def test_ohlc_inconsistent_uses_the_limit_tolerance(tmp_path: Path) -> None:
    noise = broken(0, high=20_000.0 - 5e-7, low=20_000.0 + 5e-7)  # below the 1e-6 tolerance
    with store_with(tmp_path, noise) as store:
        assert findings(store, "ohlc_inconsistent") == []
    path = tmp_path / "real"
    path.mkdir()
    with store_with(path, broken(0, high=20_000.0 - 1e-3)) as store:
        assert [f.severity for f in findings(store, "ohlc_inconsistent")] == ["error"]


def weekdays(count: int) -> list[date]:
    days: list[date] = []
    day = date(2018, 1, 1)  # a Monday
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def long_split_adjusted(days: list[date], ex_index: int, breach_index: int) -> list[dict[str, Any]]:
    """Sessions before ``ex_index`` carry rescaled (off-grid) prices; one genuine breach later."""
    rows: list[dict[str, Any]] = []
    for i, day in enumerate(days):
        base = 20_000.0 + 50.0 * (i % 2)
        ref = 20_000.0 + 50.0 * ((i - 1) % 2)
        ceiling, floor = TICKS.limits(pd.Series([ref]).to_numpy(dtype="float64"))
        scale = 1.1 if i < ex_index else 1.0
        close = 25_000.0 if i == breach_index else base
        rows.append(
            {
                "ticker": "AAA",
                "date": day,
                "open": round(base / scale, 4),
                "high": round((max(base, close) + 50.0) / scale, 4),
                "low": round((min(base, close) - 50.0) / scale, 4),
                "close": round(close / scale, 4),
                "volume": 1_000 + i,
                "ref_price": round(ref / scale, 4),
                "ceiling": float(ceiling[0]) / scale,
                "floor": float(floor[0]) / scale,
            }
        )
    return rows


def test_long_split_adjusted_history_gives_summaries_and_keeps_a_real_breach(
    tmp_path: Path,
) -> None:
    days = weekdays(2_000)
    rows = long_split_adjusted(days, ex_index=1_500, breach_index=1_800)
    with store_with(
        tmp_path, rows, basis="split_adjusted", derived=True, start=days[0], end=days[-1]
    ) as store:
        events = pd.DataFrame(
            [{"ticker": "AAA", "ex_date": days[1_500], "type": "stock", "ratio_or_amount": 0.1}]
        )
        events["source"] = "synthetic_fake"
        store.upsert_corporate_actions(events, "run-1", "real")
        results = run_checks(store, "run-1", CAL, ticks=TICKS)
    assert len(results) < 10  # not thousands of rows
    off = [r for r in results if r.check == "off_tick"]
    assert len(off) == 1
    assert off[0].severity == "warning"
    assert off[0].date == days[0]
    assert "1500 session(s)" in off[0].detail
    assert str(days[1_499]) in off[0].detail
    outside = [r for r in results if r.check == "close_outside_limits"]
    assert [(r.date, r.severity) for r in outside] == [(days[1_800], "warning")]
    assert all(r.severity == "warning" for r in results)


def test_rescaled_history_of_raw_data_is_still_reported_per_row(tmp_path: Path) -> None:
    days = weekdays(30)
    rows = long_split_adjusted(days, ex_index=20, breach_index=25)
    with store_with(
        tmp_path, rows, basis="raw", derived=False, start=days[0], end=days[-1]
    ) as store:
        results = run_checks(store, "run-1", CAL, ticks=TICKS)
    assert len([r for r in results if r.check == "off_tick"]) >= 20  # hard rows: no summarising
    assert all(r.severity == "error" for r in results if r.check == "off_tick")


def test_dq_results_are_inserted_in_one_batch_and_atomically(tmp_path: Path) -> None:
    from vnstratlab.data.store import DQRecord

    with store_with(tmp_path, bars()) as store:
        day = date(2026, 3, 2)
        records = [
            DQRecord("run-1", "off_tick", f"T{i:04d}", day, "warning", "x") for i in range(1_500)
        ]
        store.record_dq_results(records)
        assert len(store.read_dq_results("run-1")) == 1_500
        clash = [DQRecord("run-1", "zero_volume", "NEW", day, "warning", "x"), records[0]]
        with pytest.raises(Exception, match=r"(?i)constraint|duplicate"):
            store.record_dq_results(clash)
        assert len(store.read_dq_results("run-1")) == 1_500  # all or nothing
        store.record_dq_results([])


def test_findings_and_status_are_written_in_one_transaction(
    cfg: AppConfig, paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = MarketStore.set_run_status

    def failing(self: MarketStore, run_id: str, status: str) -> None:
        if status != "dq_crashed":
            raise RuntimeError("synthetic failure while setting the status")
        real(self, run_id, status)

    monkeypatch.setattr(MarketStore, "set_run_status", failing)
    with pytest.raises(SourceError, match="dq_crashed"):
        run_ingest(cfg, paths, FakeSource(broken(2, volume=0)))  # one finding to store
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        assert store.connection.execute("SELECT count(*) FROM dq_results").fetchall() == [(0,)]
        assert store.row_count() == 5  # data was committed
    assert stored_status(paths) == [("dq_crashed",)]


def test_a_crash_inside_the_checks_marks_dq_crashed_not_error(
    cfg: AppConfig, paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(*args: Any, **kwargs: Any) -> list[DQResult]:
        raise RuntimeError("synthetic check bug")

    monkeypatch.setattr(pipeline, "run_checks", crash)
    with pytest.raises(SourceError, match="dq_crashed") as caught:
        run_ingest(cfg, paths, FakeSource(bars()))
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert stored_status(paths) == [("dq_crashed",)]  # not "error": the data is committed
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        assert store.row_count() == 5


def test_cli_exits_1_when_the_checks_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))

    def crash(*args: Any, **kwargs: Any) -> list[DQResult]:
        raise RuntimeError("synthetic check bug")

    monkeypatch.setattr(pipeline, "run_checks", crash)
    args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-06"]
    result = runner.invoke(app, args)
    assert result.exit_code == 1, result.output
    assert "dq_crashed" in result.output
    with MarketStore(tmp_path / "home" / "data" / "market-synthetic.duckdb", "synthetic") as store:
        assert store.connection.execute("SELECT status FROM ingest_runs").fetchall() == [
            ("dq_crashed",)
        ]
