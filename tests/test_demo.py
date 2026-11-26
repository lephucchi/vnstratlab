"""`vnstratlab demo` (P1-T32): offline, isolated, deterministic. Synthetic data only."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from vnstratlab import demo as demo_module
from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.demo import (
    DEMO_END,
    DEMO_START,
    WARNING_LINE,
    DemoError,
    DemoReport,
    demo_config,
    format_report,
    run_demo,
)
from vnstratlab.strategies.registry import load_strategies

START = date(2017, 1, 1)
END = date(2017, 3, 31)
runner = CliRunner()


def expected_trials() -> int:
    """The packaged dry-run count: enabled strategy instances x their horizons."""
    return sum(len(s.horizons) for s in load_strategies(demo_config()))


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): (p.read_bytes() if p.is_file() else b"<dir>")
        for p in sorted(root.rglob("*"))
    }


@pytest.fixture(scope="module")
def full_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[DemoReport, Path]:
    out = tmp_path_factory.mktemp("demo_out") / "out"
    return run_demo(out, START, END), out


def small_config(*, with_blocked: bool = False) -> AppConfig:
    """Packaged config reduced to the S17 benchmark (fast), optionally with a blocked entry."""
    cfg = demo_config()
    strategies: dict[str, Any] = {
        "S17_equal_weight": {"horizons": ["short", "medium"], "params": [{}]}
    }
    if with_blocked:
        strategies["S06_blocked"] = {
            "enabled": False,
            "reason": "blocked on P1-T04 (synthetic reason)",
            "horizons": ["short"],
            "params": [{}],
        }
    return cfg.model_copy(update={"strategies": strategies})


def test_constants_are_fixed_dates() -> None:
    assert (DEMO_START.year, DEMO_START.month, DEMO_START.day) == (2016, 1, 1)
    assert (DEMO_END.year, DEMO_END.month, DEMO_END.day) == (2020, 12, 31)


def test_every_enabled_packaged_trial_runs_once(full_run: tuple[DemoReport, Path]) -> None:
    report, _ = full_run
    trials = [r for r in report.rows if r.is_trial]
    benchmarks = [r for r in report.rows if r.benchmark]
    s17 = [r for r in trials if r.strategy_id == "S17_equal_weight"]
    assert len(trials) == expected_trials()
    assert len(report.rows) == len(trials) + len(s17)  # one benchmark row per S17 horizon
    assert len({r.trial_id for r in report.rows}) == len(report.rows)
    assert (report.start, report.end) == (START, END)
    assert all(r.trades >= 0 and len(r.equity) > 50 for r in report.rows)
    assert {r.strategy_id for r in benchmarks} == {"S17_equal_weight"}
    assert not any(r.benchmark or "benchmark" in r.label for r in s17)  # packaged S17: a trial
    assert all(not r.is_trial and r.label.endswith("(benchmark) no risk layer") for r in benchmarks)
    horizons = [r.horizon for r in report.rows]
    order = {"short": 0, "medium": 1, "long": 2}
    assert horizons == sorted(horizons, key=order.__getitem__)


def test_two_runs_are_identical(full_run: tuple[DemoReport, Path], tmp_path: Path) -> None:
    first, first_out = full_run
    out = tmp_path / "again"
    second = run_demo(out, START, END)
    assert [r.digest for r in first.rows] == [r.digest for r in second.rows]
    assert [r.trial_id for r in first.rows] == [r.trial_id for r in second.rows]
    assert (first_out / "summary.csv").read_bytes() == (out / "summary.csv").read_bytes()


def test_strategies_only_see_features_up_to_asof(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    real = load_strategies

    def wrapped(cfg: AppConfig) -> list[Any]:
        found = real(cfg)
        for strategy in found:
            inner = strategy.target_weights

            def spy(
                features: pd.DataFrame,
                asof: pd.Timestamp,
                inner: Callable[..., pd.Series] = inner,
            ) -> pd.Series:
                calls.append((pd.to_datetime(features["date"]).max(), asof))
                return inner(features, asof)

            strategy.target_weights = spy  # type: ignore[method-assign]
        return found

    monkeypatch.setattr(demo_module, "load_strategies", wrapped)
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config())
    run_demo(None, START, date(2017, 6, 30))
    assert len(calls) > 20
    assert all(latest <= asof for latest, asof in calls)
    assert any(latest == asof for latest, asof in calls)  # the decision day itself is visible


def test_out_dir_holds_exactly_the_summary_and_one_equity_file_per_trial(
    full_run: tuple[DemoReport, Path],
) -> None:
    report, out = full_run
    assert sorted(p.name for p in out.iterdir()) == ["equity", "summary.csv"]
    files = sorted(p.name for p in (out / "equity").iterdir())
    assert files == sorted(f"{r.trial_id}.csv" for r in report.rows)
    summary = pd.read_csv(out / "summary.csv")
    assert list(summary.columns) == [
        "trial_id", "trial", "horizon", "CAGR", "vol", "Sharpe", "maxDD", "turnover", "trades",
    ]  # fmt: skip
    assert len(summary) == len(report.rows)
    equity = pd.read_csv(out / "equity" / files[0])
    assert list(equity.columns) == ["date", "equity"]


def test_non_empty_out_dir_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    out = tmp_path / "taken"
    out.mkdir()
    (out / "keep.txt").write_text("mine", encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(DemoError, match="not an empty directory"):
        run_demo(out, START, END)
    assert snapshot(tmp_path) == before
    file_path = tmp_path / "a_file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(DemoError):
        run_demo(file_path, START, END)


def test_report_lists_skipped_and_the_run_leaves_the_app_home_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config(with_blocked=True))
    home = tmp_path / "home"  # isolation: a demo run leaves the app home untouched
    (home / "data").mkdir(parents=True)
    (home / "data" / "market.duckdb").write_bytes(b"sentinel market store")
    (home / "data" / "lab.duckdb").write_bytes(b"sentinel trial registry")
    (home / "config.yaml").write_text("data:\n  source: yahoo\n", encoding="utf-8")
    monkeypatch.setenv("APP_HOME", str(home))
    monkeypatch.delitem(sys.modules, "vnstratlab.data.sources.yahoo", raising=False)
    before = snapshot(home)
    (tmp_path / "o").mkdir()  # an existing empty directory is used
    report = run_demo(tmp_path / "o", START, date(2017, 3, 31))
    assert snapshot(home) == before
    assert "vnstratlab.data.sources.yahoo" not in sys.modules  # no source library, no network
    assert len(list((tmp_path / "o" / "equity").iterdir())) == len(report.rows) == 4
    assert report.skipped == (("S06_blocked", "blocked on P1-T04 (synthetic reason)"),)
    text = format_report(report)
    assert text.splitlines()[0] == WARNING_LINE
    assert "skipped: S06_blocked: blocked on P1-T04 (synthetic reason)" in text
    assert "S17_equal_weight (benchmark) no risk layer" in text
    assert "trials run 2, skipped 1" in text
    assert "benchmark rows (2): S17 equal weight without the risk layer; not trials" in text
    assert "no trials were registered" in text
    assert f"files written to {tmp_path / 'o'}" in text
    assert "CAGR" in text
    quiet = format_report(report, quiet=True)
    assert quiet.splitlines()[0] == WARNING_LINE
    assert "CAGR" not in quiet
    assert "files written" not in format_report(
        report.__class__(**{**vars(report), "out_dir": None})
    )


def test_window_must_not_be_reversed() -> None:
    with pytest.raises(DemoError, match="before start"):
        run_demo(None, END, START)


def test_cli_demo_refuses_a_non_empty_out_dir(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["demo", "--quiet", "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert "not an empty directory" in result.output
    assert [p.name for p in tmp_path.iterdir()] == ["x.txt"]


def test_demo_window_is_ascii_warning_and_unchanged_by_user_config(
    full_run: tuple[DemoReport, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert WARNING_LINE.isascii()
    home = tmp_path / "home"
    home.mkdir()
    # a user config that would change the result if the demo read it
    plant = "books:\n  short:\n    capital_vnd: 1000000\n"
    (home / "config.yaml").write_text(plant, "utf-8")
    monkeypatch.setenv("APP_HOME", str(home))
    assert load_config(home).books.short.capital_vnd == 1_000_000  # the plant is effective
    assert demo_config().books.short.capital_vnd != 1_000_000
    again = run_demo(None, START, END)
    assert [r.digest for r in again.rows] == [r.digest for r in full_run[0].rows]


def test_run_demo_restores_the_logger_level_after_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise DemoError("synthetic failure")

    monkeypatch.setattr(demo_module, "stage_simulate", boom)
    logger = logging.getLogger("vnstratlab")
    monkeypatch.setattr(logger, "level", logging.ERROR)
    with pytest.raises(DemoError):
        run_demo(None, START, END)
    assert logger.level == logging.ERROR


def test_shared_bars_do_not_change_any_digest(
    full_run: tuple[DemoReport, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demo shares one bars table across trials; the old path rebuilt it per trial."""
    monkeypatch.setattr(demo_module, "build_bars", lambda _prices: None)  # old path
    old = run_demo(None, START, END)
    assert [(r.trial_id, r.digest) for r in old.rows] == [
        (r.trial_id, r.digest) for r in full_run[0].rows
    ]
    assert sum(r.is_trial for r in old.rows) == expected_trials()


def test_benchmark_row_runs_without_the_risk_layer_and_holds_the_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config())
    real = demo_module.run_simulation
    seen: list[tuple[bool, int]] = []  # (risk layer used, max positions held on any session)

    def spy(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        most = int(result.positions.groupby("date").size().max())
        seen.append((kwargs["risk"] is not None, most))
        return result

    monkeypatch.setattr(demo_module, "run_simulation", spy)
    report = run_demo(None, START, END)
    max_positions = demo_config().risk.max_positions
    with_risk = [n for used, n in seen if used]
    without = [n for used, n in seen if not used]
    assert len(with_risk) == 2
    assert len(without) == 2  # S17 short + medium, each once more
    assert all(n <= max_positions for n in with_risk)
    assert all(n > max_positions for n in without)  # about the whole universe
    assert [r.is_trial for r in report.rows].count(False) == 2


def test_breaker_warns_once_per_transition_not_per_decision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = small_config()
    tight = cfg.risk.model_copy(update={"circuit_breaker_drawdown_pct": 0.001})
    monkeypatch.setattr(demo_module, "demo_config", lambda: cfg.model_copy(update={"risk": tight}))
    caplog.set_level(logging.DEBUG, logger="vnstratlab")
    run_demo(None, START, END)
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    layer_debug = [r for r in caplog.records if r.name == "vnstratlab.risk.layer"]
    transitions = [r for r in warns if r.name == "vnstratlab.engine.loop"]
    assert transitions
    assert all(r.getMessage().startswith("circuit_breaker_o") for r in transitions)
    assert not [r for r in warns if r.name == "vnstratlab.risk.layer"]
    assert layer_debug  # blocked decisions are still logged, at DEBUG, never as a warning
