"""`vnstratlab demo` (P1-T32): offline, isolated, deterministic. Synthetic data only."""

from __future__ import annotations

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
END = date(2017, 12, 31)
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
    assert len(report.rows) == expected_trials()
    assert len({r.trial_id for r in report.rows}) == len(report.rows)
    assert (report.start, report.end) == (START, END)
    assert all(r.trades >= 0 and len(r.equity) > 200 for r in report.rows)
    benchmarks = [r for r in report.rows if r.benchmark]
    assert {r.strategy_id for r in benchmarks} == {"S17_equal_weight"}
    horizons = [r.horizon for r in report.rows]
    order = {"short": 0, "medium": 1, "long": 2}
    assert horizons == sorted(horizons, key=order.__getitem__)


def test_isolation_leaves_the_app_home_byte_for_byte_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "data" / "market.duckdb").write_bytes(b"sentinel market store")
    (home / "data" / "lab.duckdb").write_bytes(b"sentinel trial registry")
    (home / "config.yaml").write_text("data:\n  source: yahoo\n", encoding="utf-8")
    monkeypatch.setenv("APP_HOME", str(home))
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config())
    before = snapshot(home)
    run_demo(None, START, date(2017, 3, 31))
    assert snapshot(home) == before


def test_no_network_and_no_yahoo_import(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("socket connect attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.delitem(sys.modules, "vnstratlab.data.sources.yahoo", raising=False)
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config())
    run_demo(None, START, date(2017, 3, 31))
    assert "vnstratlab.data.sources.yahoo" not in sys.modules


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


def test_empty_existing_out_dir_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config())
    out = tmp_path / "empty"
    out.mkdir()
    report = run_demo(out, START, date(2017, 3, 31))
    assert (out / "summary.csv").is_file()
    assert len(list((out / "equity").iterdir())) == len(report.rows) == 2


def test_report_text_starts_with_the_warning_and_lists_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config(with_blocked=True))
    report = run_demo(tmp_path / "o", START, date(2017, 3, 31))
    assert report.skipped == (("S06_blocked", "blocked on P1-T04 (synthetic reason)"),)
    text = format_report(report)
    assert text.splitlines()[0] == WARNING_LINE
    assert "skipped: S06_blocked: blocked on P1-T04 (synthetic reason)" in text
    assert "S17_equal_weight (benchmark)" in text
    assert "trials run 2, skipped 1" in text
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


def test_cli_demo_quiet_exits_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(demo_module, "demo_config", lambda: small_config(with_blocked=True))
    real = demo_module.run_demo

    def short(out_dir: Path | None, **kwargs: Any) -> DemoReport:
        return real(out_dir, START, date(2017, 3, 31), **kwargs)

    monkeypatch.setattr(demo_module, "run_demo", short)
    result = runner.invoke(app, ["demo", "--quiet"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0].startswith("SYNTHETIC DATA")
    assert "trials run 2, skipped 1" in result.output


def test_cli_demo_refuses_a_non_empty_out_dir(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["demo", "--quiet", "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert "not an empty directory" in result.output
    assert [p.name for p in tmp_path.iterdir()] == ["x.txt"]
