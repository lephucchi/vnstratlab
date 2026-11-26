"""Run registry (P1-T27a): DAG runner, per-task logs, retention, interrupted runs."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from vnstratlab import demo as demo_module
from vnstratlab.cli import app
from vnstratlab.demo import demo_config, run_demo
from vnstratlab.runs import (
    BusyError,
    Pipeline,
    RunContext,
    RunStore,
    Task,
    create_run,
    execute_run,
    run_inline,
)
from vnstratlab.runs import core as runs_core

runner = CliRunner()


@pytest.fixture(autouse=True)
def _idle() -> Iterator[None]:
    """No test may leave the process-wide run slot taken."""
    yield
    assert not runs_core._active


def small_config() -> Any:
    cfg = demo_config()
    strategies = {"S17_equal_weight": {"horizons": ["short", "medium"], "params": [{}]}}
    return cfg.model_copy(update={"strategies": strategies})


def ok(_ctx: RunContext) -> dict[str, Any]:
    logging.getLogger("vnstratlab.test").info("working")
    return {"rows": 3}


def boom(_ctx: RunContext) -> None:
    raise ValueError("synthetic failure")


def test_demo_run_six_tasks_logs_and_summary_equals_the_cli_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    monkeypatch.setattr(demo_module, "demo_config", small_config)
    real = demo_module.run_demo

    def short(out_dir: Path | None, **kwargs: Any) -> Any:
        return real(out_dir, date(2017, 1, 1), date(2017, 3, 31), **kwargs)

    monkeypatch.setattr(demo_module, "run_demo", short)
    out = tmp_path / "out"
    result = runner.invoke(app, ["demo", "--quiet", "--out", str(out)])
    assert result.exit_code == 0, result.output

    store = RunStore(home)
    (run,) = store.list()
    assert [t["status"] for t in run["tasks"]] == ["success"] * 6
    assert [t["id"] for t in run["tasks"]] == [
        "ingest",
        "rebuild",
        "features",
        "strategies",
        "simulate",
        "report",
    ]
    run_dir = store.run_dir(run["run_id"])
    assert all((run_dir / f"{t['id']}.log").is_file() for t in run["tasks"])
    assert (run_dir / "demo" / "summary.csv").read_bytes() == (out / "summary.csv").read_bytes()
    listing = runner.invoke(app, ["runs", "show", run["run_id"]])
    assert listing.exit_code == 0
    assert "simulate" in listing.output


def test_failed_task_marks_downstream_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pipeline = Pipeline(
        "t", "t", (Task("a", "a", ok), Task("b", "b", boom, ("a",)), Task("c", "c", ok, ("b",)))
    )
    before = logging.getLogger("vnstratlab").level
    run_id = create_run(tmp_path, pipeline)
    result = execute_run(tmp_path, pipeline, run_id)
    run = RunStore(tmp_path).get(run_id)
    assert run is not None
    assert result.status == "failed"
    assert run["status"] == "failed"
    assert [t["status"] for t in run["tasks"]] == ["success", "failed", "skipped"]
    assert run["tasks"][0]["summary"] == {"rows": 3}
    log = (RunStore(tmp_path).run_dir(run_id) / "b.log").read_text(encoding="utf-8")
    assert "Traceback" in log
    assert "ValueError: synthetic failure" in log
    assert "INFO vnstratlab.test: working" in (
        RunStore(tmp_path).run_dir(run_id) / "a.log"
    ).read_text(encoding="utf-8")
    assert logging.getLogger("vnstratlab").level == before  # logger state restored


def test_a_second_run_is_busy_while_one_is_active(tmp_path: Path) -> None:
    pipeline = Pipeline("t", "t", (Task("a", "a", ok),))
    run_id = create_run(tmp_path, pipeline)
    with pytest.raises(BusyError):
        create_run(tmp_path, pipeline)
    execute_run(tmp_path, pipeline, run_id)
    execute_run_again = create_run(tmp_path, pipeline)  # the slot is free again
    execute_run(tmp_path, pipeline, execute_run_again)


def test_retention_keeps_the_last_50_runs(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    for n in range(55):
        folder = store.root / f"20200101T0000{n:02d}-demo-abcd"
        folder.mkdir(parents=True)
        (folder / "run.json").write_text("{}", encoding="utf-8")
    pipeline = Pipeline("t", "t", (Task("a", "a", ok),))
    run_id = create_run(tmp_path, pipeline)
    execute_run(tmp_path, pipeline, run_id)
    names = sorted(p.name for p in store.root.iterdir())
    assert len(names) == 50
    assert run_id in names
    assert "20200101T000000-demo-abcd" not in names


def test_an_interrupted_run_loads_as_failed(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = "20200101T000000-demo-abcd"
    store.run_dir(run_id).mkdir(parents=True)
    tasks = [
        {"id": "a", "status": "running", "error": None},
        {"id": "b", "status": "queued", "error": None},
    ]
    store.save({"run_id": run_id, "status": "running", "tasks": tasks})
    run = store.get(run_id)
    assert run is not None
    assert (run["status"], run["reason"]) == ("failed", "interrupted")
    assert [t["status"] for t in run["tasks"]] == ["failed", "skipped"]
    assert store.get("../escape") is None  # run ids are validated


def test_run_inline_records_the_run_and_keeps_the_exit_code(tmp_path: Path) -> None:
    def clean() -> None:
        raise typer.Exit(code=0)

    def bad() -> None:
        raise typer.Exit(code=3)

    with pytest.raises(typer.Exit) as clean_exit:
        run_inline(tmp_path, "ingest", "Tải dữ liệu", clean)
    with pytest.raises(typer.Exit) as bad_exit:
        run_inline(tmp_path, "ingest", "Tải dữ liệu", bad)
    assert (clean_exit.value.exit_code, bad_exit.value.exit_code) == (0, 3)
    statuses = sorted(r["status"] for r in RunStore(tmp_path).list())
    assert statuses == ["failed", "success"]


def test_run_demo_window_must_not_be_reversed_before_any_run(tmp_path: Path) -> None:
    with pytest.raises(demo_module.DemoError, match="before start"):
        run_demo(None, date(2017, 2, 1), date(2017, 1, 1), record_home=tmp_path)
    assert RunStore(tmp_path).list() == []
