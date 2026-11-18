"""YahooSource adapter (P1-T37). Fake fetch only: no network, no yfinance."""

from __future__ import annotations

import socket
import sys
import types
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from vnstratlab import cli
from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.pipeline import ingest, partial_bar_cutoff, terms_accepted
from vnstratlab.data.protocol import SourceError, get_source
from vnstratlab.data.raw import read_raw
from vnstratlab.data.sources import yahoo
from vnstratlab.data.sources.yahoo import INSTALL_HINT, YahooSource
from vnstratlab.data.store import MarketStore
from vnstratlab.paths import AppPaths, get_paths

FIXTURES = Path(__file__).parent / "fixtures"
START = date(2026, 3, 2)
END = date(2026, 3, 6)
LATER = datetime(2026, 3, 9, 12, 30, 15, tzinfo=UTC)
runner = CliRunner()


def csv_fetch(name: str, calls: list[tuple[str, date, date]] | None = None) -> yahoo.FetchFn:
    """A fake fetch serving one symbol of a fixture, in Yahoo's shape (tz-aware date index)."""
    frame = pd.read_csv(FIXTURES / name)
    frame["Date"] = pd.to_datetime(frame["Date"], utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        if calls is not None:
            calls.append((symbol, start, end))
        part = frame[frame["symbol"] == symbol].drop(columns="symbol").set_index("Date")
        return part

    return fetch


class Sleeps:
    def __init__(self) -> None:
        self.values: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.values.append(seconds)


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    return load_config(tmp_path / "home")


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return get_paths(tmp_path / "home")


def make(cfg: AppConfig, fixture: str, sleeps: Sleeps | None = None) -> YahooSource:
    return YahooSource(cfg, fetch=csv_fetch(fixture), sleep=sleeps or Sleeps())


def stored(paths: AppPaths, sql: str) -> list[tuple[object, ...]]:
    with MarketStore(paths.market_db, "real", read_only=True) as store:
        return store.connection.execute(sql).fetchall()


# ------------------------------------------------------------------ config and registry


def test_defaults_and_registry(cfg: AppConfig) -> None:
    assert cfg.data.source == "yahoo"
    opts = cfg.data.yahoo
    assert (opts.symbol_suffix, opts.max_requests_per_minute, opts.retries) == (".VN", 30, 3)
    assert (opts.backoff_seconds, opts.final_after) == (2.0, "16:00")
    source = get_source("yahoo", cfg)
    info = source.info
    assert (info.name, info.price_basis, info.interim) == ("yahoo", "split_adjusted", True)
    assert info.requires_extra == "yahoo"
    assert info.terms_url == "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"
    assert source.symbols(["ACB", "VCB"]) == {"ACB": "ACB.VN", "VCB": "VCB.VN"}


# ------------------------------------------------------------------ 1. basic ingest


def test_basic_ingest_writes_rows_actions_and_snapshot(cfg: AppConfig, paths: AppPaths) -> None:
    calls: list[tuple[str, date, date]] = []
    source = YahooSource(cfg, fetch=csv_fetch("synthetic_yahoo_basic.csv", calls), sleep=Sleeps())
    report = ingest(cfg, paths, source, START, END, clock=lambda: LATER)
    assert (report.rows_in, report.rows_written, report.rows_dropped) == (10, 10, 0)
    assert report.status == "ok"
    assert report.db_path == paths.market_db
    assert {symbol for symbol, _, _ in calls} >= {"ACB.VN", "VCB.VN"}
    assert len(calls) == len({s for s, _, _ in calls})  # one request per symbol, actions included

    rows = stored(
        paths,
        "SELECT ticker, count(*), min(source), max(source), min(price_basis), "
        "bool_and(derived_limits) FROM prices_daily GROUP BY ticker ORDER BY ticker",
    )
    assert rows == [
        ("ACB", 5, "yahoo", "yahoo", "split_adjusted", True),
        ("VCB", 5, "yahoo", "yahoo", "split_adjusted", True),
    ]
    closes = stored(paths, "SELECT close FROM prices_daily WHERE ticker='ACB' ORDER BY date")
    assert [c[0] for c in closes] == [25000.0, 25050.0, 25100.0, 25050.0, 25150.0]  # not Adj Close
    actions = stored(
        paths, "SELECT ticker, ex_date, type, ratio_or_amount, source FROM corporate_actions"
    )
    assert sorted(actions) == [
        ("ACB", date(2026, 3, 4), "cash", 500.0, "yahoo"),
        ("VCB", date(2026, 3, 5), "stock", 0.1, "yahoo"),  # factor 1.1 -> bonus fraction
    ]
    assert report.raw_path is not None
    assert report.raw_path.is_file()
    raw = read_raw(report.raw_path)
    assert list(raw.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert len(raw) == 10
    assert stored(paths, "SELECT status FROM ingest_runs") == [("ok",)]


def test_dates_are_vietnam_dates(cfg: AppConfig) -> None:
    index = pd.DatetimeIndex(["2026-03-02 00:00:00+07:00"]).tz_convert("UTC")  # 17:00 UTC prev day
    history = pd.DataFrame(
        {"Open": [25000.0], "High": [25100.0], "Low": [24900.0], "Close": [25000.0], "Volume": [1]},
        index=index,
    )
    source = YahooSource(cfg, fetch=lambda s, a, b: history, sleep=Sleeps())
    frame = source.fetch_daily(["ACB"], START, END)
    assert list(frame["date"]) == [date(2026, 3, 2)]


def test_naive_index_rows_outside_window_and_missing_columns(cfg: AppConfig) -> None:
    index = pd.to_datetime(["2026-03-01", "2026-03-03", "2026-03-09"])
    history = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1}, index=index
    )
    source = YahooSource(cfg, fetch=lambda s, a, b: history, sleep=Sleeps())
    assert list(source.fetch_daily(["ACB"], START, END)["date"]) == [date(2026, 3, 3)]
    assert source.fetch_corporate_actions(["ACB"], START, END).empty
    broken = YahooSource(cfg, fetch=lambda s, a, b: history.drop(columns="Close"), sleep=Sleeps())
    assert broken.fetch_daily(["ACB"], START, END).empty
    assert "missing columns" in broken.failures["ACB"]


# ------------------------------------------------------------------ 2. filler rows


def test_filler_rows_dropped_and_genuine_zero_volume_kept(
    cfg: AppConfig, paths: AppPaths, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    source = make(cfg, "synthetic_yahoo_holiday.csv")
    report = ingest(cfg, paths, source, START, END, clock=lambda: LATER)
    assert (report.rows_in, report.rows_written, report.rows_dropped) == (5, 4, 1)
    days = [r[0] for r in stored(paths, "SELECT date FROM prices_daily ORDER BY date")]
    assert date(2026, 3, 4) not in days  # filler: zero volume, all prices = previous close
    assert date(2026, 3, 5) in days  # zero volume but the price moved: genuine
    assert "ACB" in caplog.text
    assert "2026-03-04" in caplog.text


def test_filler_first_row_uses_stored_previous_close(cfg: AppConfig, paths: AppPaths) -> None:
    ingest(
        cfg,
        paths,
        make(cfg, "synthetic_yahoo_holiday.csv"),
        START,
        date(2026, 3, 3),
        clock=lambda: LATER,
    )
    # A later window whose first row (03-04) repeats the stored 03-03 close of 25050.
    report = ingest(
        cfg,
        paths,
        make(cfg, "synthetic_yahoo_holiday.csv"),
        date(2026, 3, 4),
        END,
        clock=lambda: datetime(2026, 3, 9, 12, 31, tzinfo=UTC),
    )
    assert report.rows_dropped == 1
    assert report.rows_written == 2


def test_dry_run_applies_the_rules_without_writing(cfg: AppConfig, paths: AppPaths) -> None:
    source = make(cfg, "synthetic_yahoo_holiday.csv")
    report = ingest(cfg, paths, source, START, END, dry_run=True, clock=lambda: LATER)
    assert report.rows_dropped == 1
    assert report.dry_run
    assert report.status == "ok"
    assert len(report.preview["prices"]) == 4
    assert not paths.home.exists()
    ingest(cfg, paths, source, START, END, clock=lambda: LATER)
    again = ingest(cfg, paths, source, START, END, dry_run=True, clock=lambda: LATER)
    assert again.rows_dropped == 1
    assert again.rows_written == 0


# ------------------------------------------------------------------ 3. partial bar


def test_partial_bar_dropped_before_final_after_and_kept_after(
    cfg: AppConfig, paths: AppPaths
) -> None:
    source = make(cfg, "synthetic_yahoo_basic.csv")
    before = datetime(2026, 3, 6, 8, 59, tzinfo=UTC)  # 15:59 in Ho Chi Minh City
    assert partial_bar_cutoff(source, END, before) == date(2026, 3, 6)
    report = ingest(cfg, paths, source, START, END, clock=lambda: before)
    assert (report.rows_written, report.rows_dropped) == (8, 2)
    assert date(2026, 3, 6) not in [r[0] for r in stored(paths, "SELECT date FROM prices_daily")]

    final = datetime(2026, 3, 6, 9, 0, tzinfo=UTC)  # 16:00
    assert partial_bar_cutoff(source, END, final) is None
    report = ingest(cfg, paths, source, START, END, clock=lambda: final)
    assert (report.rows_written, report.rows_dropped) == (2, 0)  # only the two 03-06 rows are new


def test_partial_bar_rule_needs_end_to_reach_today(cfg: AppConfig) -> None:
    source = make(cfg, "synthetic_yahoo_basic.csv")
    early = datetime(2026, 3, 6, 1, 0, tzinfo=UTC)
    assert partial_bar_cutoff(source, date(2026, 3, 5), early) is None
    assert partial_bar_cutoff(source, date(2026, 3, 6), early) == date(2026, 3, 6)


# ------------------------------------------------------------------ 4. re-scaled history


def test_resplit_updates_earlier_rows_with_revision_and_keeps_snapshot(
    cfg: AppConfig, paths: AppPaths
) -> None:
    first = ingest(
        cfg,
        paths,
        make(cfg, "synthetic_yahoo_basic.csv"),
        START,
        END,
        clock=lambda: LATER,
    )
    second = ingest(
        cfg,
        paths,
        make(cfg, "synthetic_yahoo_resplit.csv"),
        START,
        END,
        clock=lambda: datetime(2026, 3, 9, 12, 45, tzinfo=UTC),
    )
    assert (second.rows_written, second.rows_changed) == (3, 3)  # 03-04 ref_price moved too
    rows = stored(
        paths, "SELECT date, close, revision FROM prices_daily WHERE ticker='ACB' ORDER BY date"
    )
    assert rows[:2] == [(date(2026, 3, 2), 22700.0, 1), (date(2026, 3, 3), 22750.0, 1)]
    assert rows[2][2] == 1  # derived reference price follows the re-scaled close
    assert [r[2] for r in rows[3:]] == [0, 0]
    assert first.raw_path is not None
    assert second.raw_path is not None
    assert first.raw_path != second.raw_path
    assert first.raw_path.is_file()
    assert read_raw(first.raw_path).query("ticker == 'ACB'")["close"].iloc[0] == 25000.0


# ------------------------------------------------------------------ 5. missing yfinance


def _accept(args: list[str]) -> list[str]:
    return [*args, "--accept-source-terms"]


def test_missing_yfinance_exits_1_with_install_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    monkeypatch.setitem(sys.modules, "yfinance", None)  # makes `import yfinance` fail
    args = _accept(["ingest", "--source", "yahoo", "--from", "2026-03-02", "--to", "2026-03-06"])
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert INSTALL_HINT in result.output
    with pytest.raises(SourceError, match="vnstratlab"):
        yahoo.yfinance_fetch("ACB.VN", START, END)


def test_default_fetch_calls_yfinance_history_with_documented_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    frame = pd.DataFrame({"Close": [1.0]})

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            seen["symbol"] = symbol

        def history(self, **kwargs: object) -> pd.DataFrame:
            seen.update(kwargs)
            return frame

    fake = types.ModuleType("yfinance")
    fake.Ticker = FakeTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    assert yahoo.yfinance_fetch("ACB.VN", START, END) is frame
    assert seen == {
        "symbol": "ACB.VN",
        "start": "2026-03-02",
        "end": "2026-03-07",  # end + 1 day: Yahoo's end is exclusive
        "auto_adjust": False,
        "actions": True,
    }


# ------------------------------------------------------------------ 6. retries and partial


def test_retry_uses_exponential_backoff_with_injected_sleep(cfg: AppConfig) -> None:
    sleeps = Sleeps()
    inner = csv_fetch("synthetic_yahoo_basic.csv")
    attempts: list[str] = []

    def flaky(symbol: str, start: date, end: date) -> pd.DataFrame:
        attempts.append(symbol)
        if len(attempts) <= 2:
            raise ConnectionError("synthetic outage")
        return inner(symbol, start, end)

    source = YahooSource(cfg, fetch=flaky, sleep=sleeps)
    frame = source.fetch_daily(["ACB"], START, END)
    assert len(attempts) == 3
    assert len(frame) == 5
    assert sleeps.values == [2.0, 4.0]
    assert source.failures == {}


def test_rate_limit_sleeps_between_tickers(cfg: AppConfig) -> None:
    sleeps = Sleeps()
    source = YahooSource(cfg, fetch=csv_fetch("synthetic_yahoo_basic.csv"), sleep=sleeps)
    source.fetch_daily(["ACB", "VCB", "CTG"], START, END)
    assert sleeps.values == [2.0, 2.0]  # 60 s / 30 requests per minute, between requests


def test_ticker_failing_every_time_gives_partial_run(cfg: AppConfig, paths: AppPaths) -> None:
    sleeps = Sleeps()
    inner = csv_fetch("synthetic_yahoo_basic.csv")

    def broken_vcb(symbol: str, start: date, end: date) -> pd.DataFrame:
        if symbol == "VCB.VN":
            raise TimeoutError("synthetic timeout")
        return inner(symbol, start, end)

    source = YahooSource(cfg, fetch=broken_vcb, sleep=sleeps)
    report = ingest(cfg, paths, source, START, END, clock=lambda: LATER)
    assert report.status == "partial"
    assert list(report.failed) == ["VCB"]
    assert "TimeoutError" in report.failed["VCB"]
    assert report.rows_written == 5
    assert stored(paths, "SELECT status FROM ingest_runs") == [("partial",)]
    assert {r[0] for r in stored(paths, "SELECT DISTINCT ticker FROM prices_daily")} == {"ACB"}
    assert sleeps.values.count(8.0) == 1  # 2 + 4 + 8: three retries for the failing ticker


def test_all_tickers_failing_raises_and_writes_nothing(cfg: AppConfig, paths: AppPaths) -> None:
    def down(symbol: str, start: date, end: date) -> pd.DataFrame:
        raise ConnectionError("synthetic outage")

    source = YahooSource(cfg, fetch=down, sleep=Sleeps())
    with pytest.raises(SourceError, match="every ticker failed"):
        ingest(cfg, paths, source, START, END, clock=lambda: LATER)
    assert not paths.market_db.exists()


def test_cli_reports_partial_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    inner = csv_fetch("synthetic_yahoo_basic.csv")

    def broken_vcb(symbol: str, start: date, end: date) -> pd.DataFrame:
        if symbol == "VCB.VN":
            raise TimeoutError("synthetic timeout")
        return inner(symbol, start, end)

    monkeypatch.setattr(
        yahoo, "build", lambda cfg: YahooSource(cfg, fetch=broken_vcb, sleep=Sleeps())
    )
    args = _accept(["ingest", "--source", "yahoo", "--from", "2026-03-02", "--to", "2026-03-06"])
    result = runner.invoke(app, args)
    assert result.exit_code == 3, result.output
    assert "status partial" in result.output
    assert "VCB" in result.output


# ------------------------------------------------------------------ 7. terms


@pytest.fixture
def fake_yahoo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    monkeypatch.setattr(
        yahoo,
        "build",
        lambda cfg: YahooSource(cfg, fetch=csv_fetch("synthetic_yahoo_basic.csv"), sleep=Sleeps()),
    )
    return home


INGEST = ["ingest", "--source", "yahoo", "--from", "2026-03-02", "--to", "2026-03-06"]


def test_terms_non_interactive_without_acceptance_exits_1(fake_yahoo: Path) -> None:
    result = runner.invoke(app, INGEST)
    assert result.exit_code == 1
    assert "legal.yahoo.com" in result.output
    assert "--accept-source-terms" in result.output
    assert not (fake_yahoo / "state").exists()
    assert not (fake_yahoo / "data").exists()


def test_accept_flag_writes_state_and_second_run_does_not_ask(fake_yahoo: Path) -> None:
    first = runner.invoke(app, _accept(INGEST))
    assert first.exit_code == 0, first.output
    assert "legal.yahoo.com" in first.output
    state = fake_yahoo / "state" / "accepted_sources.json"
    assert "yahoo" in state.read_text(encoding="utf-8")
    again = [*INGEST[:-1], "2026-03-05"]  # another window: a new run id in the same second
    second = runner.invoke(app, again)
    assert second.exit_code == 0, second.output
    assert "legal.yahoo.com" not in second.output
    assert (fake_yahoo / "data" / "market.duckdb").is_file()
    assert terms_accepted(get_paths(fake_yahoo), YahooSource(load_config(fake_yahoo)))


def test_terms_interactive_yes_and_no(fake_yahoo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_is_interactive", lambda: True)
    refused = runner.invoke(app, INGEST, input="n\n")
    assert refused.exit_code == 1
    assert not (fake_yahoo / "state").exists()
    accepted = runner.invoke(app, INGEST, input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert (fake_yahoo / "state" / "accepted_sources.json").is_file()


def test_dry_run_with_acceptance_creates_no_files(fake_yahoo: Path) -> None:
    fake_yahoo.mkdir()
    result = runner.invoke(app, _accept([*INGEST, "--dry-run"]))
    assert result.exit_code == 0, result.output
    assert list(fake_yahoo.iterdir()) == []


def test_corrupt_state_file_counts_as_not_accepted(fake_yahoo: Path) -> None:
    state = fake_yahoo / "state"
    state.mkdir(parents=True)
    (state / "accepted_sources.json").write_text("{not json", encoding="utf-8")
    assert runner.invoke(app, INGEST).exit_code == 1
    (state / "accepted_sources.json").write_text("[1]", encoding="utf-8")
    assert runner.invoke(app, INGEST).exit_code == 1
    assert runner.invoke(app, _accept(INGEST)).exit_code == 0


def test_synthetic_source_needs_no_terms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-03"]
    assert runner.invoke(app, args).exit_code == 0


# ------------------------------------------------------------------ 8. VNSTOCK_API_KEY gone


def test_vnstock_key_is_gone_from_src_and_env_example() -> None:
    root = Path(__file__).resolve().parents[1]
    hits = [
        str(path)
        for path in [*(root / "src").rglob("*"), root / ".env.example"]
        if path.is_file()
        and path.suffix in {".py", ".yaml", ".example", ""}
        and "vnstock_api_key" in path.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    assert hits == []


# ------------------------------------------------------------------ 9. no network, no yfinance


def test_socket_guard_blocks_connections() -> None:
    with pytest.raises(AssertionError, match="network access"):
        socket.socket().connect(("127.0.0.1", 9))


def test_tests_run_without_yfinance_installed() -> None:
    assert sys.modules.get("yfinance") is None


# ------------------------------------------------------------------ split factors, pre-flight


def test_reverse_split_factor_is_not_stored_but_warned(cfg: AppConfig) -> None:
    index = pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04"])
    history = pd.DataFrame(
        {
            "Open": 1.0,
            "High": 1.0,
            "Low": 1.0,
            "Close": 1.0,
            "Volume": 1,
            "Dividends": 0.0,
            "Stock Splits": [0.0, 0.5, 1.15],
        },
        index=index,
    )
    source = YahooSource(cfg, fetch=lambda s, a, b: history, sleep=Sleeps())
    actions = source.fetch_corporate_actions(["ACB"], START, END)
    assert [(a.type, a.ratio_or_amount) for a in actions.itertuples()] == [("stock", 0.15)]
    assert len(source.warnings) == 1
    assert "reverse split" in source.warnings[0]


def test_cli_prints_reverse_split_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    inner = csv_fetch("synthetic_yahoo_basic.csv")

    def with_reverse(symbol: str, start: date, end: date) -> pd.DataFrame:
        frame = inner(symbol, start, end)
        if symbol == "ACB.VN":
            frame["Stock Splits"] = [0.0, 0.5, 0.0, 0.0, 0.0]
        return frame

    monkeypatch.setattr(
        yahoo, "build", lambda cfg: YahooSource(cfg, fetch=with_reverse, sleep=Sleeps())
    )
    result = runner.invoke(app, _accept(INGEST))
    assert result.exit_code == 0, result.output
    assert "reverse split" in result.output


def test_preflight_missing_module_exits_1_without_asking_or_storing_terms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    monkeypatch.setitem(sys.modules, "yfinance", None)
    monkeypatch.setattr(cli, "_is_interactive", lambda: True)
    result = runner.invoke(app, INGEST, input="y" + chr(10))
    assert result.exit_code == 1
    assert INSTALL_HINT in result.output
    assert "legal.yahoo.com" not in result.output
    assert not (home / "state").exists()
