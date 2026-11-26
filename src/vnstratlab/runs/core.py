"""Run registry: pipelines of tasks, a runner with per-task logs, and the on-disk run store.

A *run* is one execution of a *pipeline* (a small DAG of tasks). Tasks run in topological order;
a task whose upstream did not succeed is ``skipped``. Each run lives in
``<home>/logs/runs/<run_id>/``: ``run.json`` (status, times, per-task summary) and one
``<task>.log`` per task, written from the ``vnstratlab`` logger records of the thread that runs
the task. Only the last ``KEEP_RUNS`` runs are kept.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
import traceback
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vnstratlab.paths import get_paths

KEEP_RUNS = 50
STATUSES = ("queued", "running", "success", "failed", "skipped")
TERMINAL = ("success", "failed")  # run statuses once it is over
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}-[a-z0-9_]+-[0-9a-f]{4}$")
_TASK_ID_RE = re.compile(r"^[a-z0-9_]+$")

_log = logging.getLogger("vnstratlab.runs")
_BUSY = threading.Lock()  # one run at a time per process
_active: set[str] = set()


class RunError(RuntimeError):
    """A pipeline is unknown or malformed, or a run failed."""


class BusyError(RunError):
    """Another run is in progress."""

    def __init__(self, active: str | None) -> None:
        super().__init__("another run is in progress")
        self.active = active


@dataclass
class RunContext:
    """What a task function receives. ``state`` carries objects between the tasks of one run."""

    home: Path
    run_dir: Path
    params: Mapping[str, Any]
    state: dict[str, Any] = field(default_factory=dict)
    exit_stack: ExitStack = field(default_factory=ExitStack)  # closed when the run ends
    progress: Callable[[str], None] | None = None

    def note(self, message: str) -> None:
        """A progress line: goes to the task log and to the caller's progress callback."""
        _log.info("%s", message)
        if self.progress is not None:
            self.progress(message)


TaskFn = Callable[[RunContext], Mapping[str, Any] | None]


@dataclass(frozen=True)
class Task:
    id: str
    label_vi: str
    fn: TaskFn
    upstream: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pipeline:
    id: str
    label_vi: str
    tasks: tuple[Task, ...]

    def __post_init__(self) -> None:
        ids = [t.id for t in self.tasks]
        if len(set(ids)) != len(ids):
            raise RunError(f"pipeline {self.id}: duplicate task ids")
        for t in self.tasks:
            if not _TASK_ID_RE.match(t.id):
                raise RunError(f"pipeline {self.id}: bad task id {t.id!r}")
            if not set(t.upstream) <= set(ids):
                raise RunError(f"pipeline {self.id}: task {t.id} has an unknown upstream")
        self.ordered()  # rejects cycles

    def ordered(self) -> list[Task]:
        """Tasks in topological order (declaration order breaks ties)."""
        done: set[str] = set()
        out: list[Task] = []
        pending = list(self.tasks)
        while pending:
            ready = next((t for t in pending if set(t.upstream) <= done), None)
            if ready is None:
                raise RunError(f"pipeline {self.id}: the task graph has a cycle")
            pending.remove(ready)
            done.add(ready.id)
            out.append(ready)
        return out


# ------------------------------------------------------------------ store


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    for attempt in range(10):  # a reader may hold the file for a moment (Windows)
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02)


class RunStore:
    """Reads and writes ``<home>/logs/runs``."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.root = get_paths(home).logs_dir / "runs"

    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID_RE.match(run_id):
            raise KeyError(run_id)
        return self.root / run_id

    def save(self, run: Mapping[str, Any]) -> None:
        path = self.run_dir(str(run["run_id"])) / "run.json"
        _write_json(path, run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        try:
            path = self.run_dir(run_id) / "run.json"
        except KeyError:
            return None
        data: Any = None
        for _ in range(10):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except FileNotFoundError:
                return None
            except (PermissionError, ValueError):
                time.sleep(0.02)
        if not isinstance(data, dict):
            return None
        return self._reconcile(data)

    @staticmethod
    def _reconcile(run: dict[str, Any]) -> dict[str, Any]:
        """A run that is not live in this process but says queued/running was interrupted."""
        if run.get("status") in ("queued", "running") and run.get("run_id") not in _active:
            run["status"] = "failed"
            run["reason"] = "interrupted"
            for task in run.get("tasks", []):
                if task["status"] == "running":
                    task["status"] = "failed"
                    task["error"] = "interrupted"
                elif task["status"] == "queued":
                    task["status"] = "skipped"
        return run

    def list(self, limit: int = KEEP_RUNS) -> list[dict[str, Any]]:
        """Newest first."""
        if not self.root.is_dir():
            return []
        names = sorted((p.name for p in self.root.iterdir() if p.is_dir()), reverse=True)
        runs = (self.get(n) for n in names[: max(0, limit)])
        return [r for r in runs if r is not None]

    def prune(self, keep: int = KEEP_RUNS) -> None:
        if not self.root.is_dir():
            return
        names = sorted(p.name for p in self.root.iterdir() if p.is_dir())
        for name in names[: max(0, len(names) - keep)]:
            if name not in _active:
                shutil.rmtree(self.root / name, ignore_errors=True)


# ------------------------------------------------------------------ logs


class _TaskLog(logging.FileHandler):
    """Writes the ``vnstratlab`` records of one thread to one file."""

    def __init__(self, path: Path, thread_id: int) -> None:
        super().__init__(path, mode="w", encoding="utf-8")
        self._thread_id = thread_id
        self.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        self.addFilter(lambda record: record.thread == self._thread_id)


@contextlib.contextmanager
def _capture(path: Path) -> Iterator[None]:
    logger = logging.getLogger("vnstratlab")
    previous = logger.level
    handler = _TaskLog(path, threading.get_ident())
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    if previous == logging.NOTSET or previous > logging.INFO:
        logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous)


# ------------------------------------------------------------------ runner


@dataclass
class RunResult:
    run_id: str
    status: str
    state: dict[str, Any]
    errors: dict[str, BaseException]  # task id -> the exception that failed it

    def raise_for_failure(self) -> None:
        for exc in self.errors.values():
            raise exc


def make_run_id(pipeline_id: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{pipeline_id}-{secrets.token_hex(2)}"


def _blank_run(run_id: str, pipeline: Pipeline, params: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "pipeline": pipeline.id,
        "label_vi": pipeline.label_vi,
        "status": "queued",
        "reason": None,
        "created_at": _now(),
        "started_at": None,
        "ended_at": None,
        "duration_s": None,
        "params": {k: v for k, v in params.items() if v is not None},
        "tasks": [
            {
                "id": t.id,
                "label_vi": t.label_vi,
                "upstream": list(t.upstream),
                "status": "queued",
                "started_at": None,
                "ended_at": None,
                "duration_s": None,
                "summary": {},
                "error": None,
            }
            for t in pipeline.tasks
        ],
    }


def create_run(home: Path, pipeline: Pipeline, params: Mapping[str, Any] | None = None) -> str:
    """Claim the process-wide run slot and write the queued record. Raises ``BusyError``."""
    if not _BUSY.acquire(blocking=False):
        raise BusyError(next(iter(_active), None))
    try:
        store = RunStore(home)
        run_id = make_run_id(pipeline.id)
        store.run_dir(run_id).mkdir(parents=True, exist_ok=True)
        _active.add(run_id)
        store.save(_blank_run(run_id, pipeline, params or {}))
        store.prune()
    except BaseException:
        _BUSY.release()
        raise
    return run_id


def execute_run(
    home: Path,
    pipeline: Pipeline,
    run_id: str,
    params: Mapping[str, Any] | None = None,
    *,
    progress: Callable[[str], None] | None = None,
) -> RunResult:
    """Run a record made by ``create_run`` to the end (releases the run slot)."""
    try:
        return _execute(home, pipeline, run_id, params or {}, progress)
    finally:
        _active.discard(run_id)
        _BUSY.release()


def _execute(
    home: Path,
    pipeline: Pipeline,
    run_id: str,
    params: Mapping[str, Any],
    progress: Callable[[str], None] | None,
) -> RunResult:
    store = RunStore(home)
    run_dir = store.run_dir(run_id)
    run = store.get(run_id) or _blank_run(run_id, pipeline, params)
    by_id = {t["id"]: t for t in run["tasks"]}
    errors: dict[str, BaseException] = {}
    ctx = RunContext(home, run_dir, dict(params), progress=progress)
    t_run = time.perf_counter()
    run.update(status="running", started_at=_now())
    store.save(run)
    try:
        with ctx.exit_stack:
            for task in pipeline.ordered():
                rec = by_id[task.id]
                if any(by_id[u]["status"] != "success" for u in task.upstream):
                    rec["status"] = "skipped"
                    store.save(run)
                    continue
                _run_task(store, run, rec, task, ctx, run_dir / f"{task.id}.log", errors)
        run["status"] = "failed" if errors else "success"
    except BaseException:
        run["status"] = "failed"
        run["reason"] = "interrupted"
        for rec in run["tasks"]:
            if rec["status"] == "running":
                rec.update(status="failed", error="interrupted")
        raise
    finally:
        run["ended_at"] = _now()
        run["duration_s"] = round(time.perf_counter() - t_run, 3)
        if errors and not run.get("reason"):
            run["reason"] = "task failed: " + ", ".join(errors)
        store.save(run)
    return RunResult(run_id, str(run["status"]), ctx.state, errors)


def _run_task(
    store: RunStore,
    run: dict[str, Any],
    rec: dict[str, Any],
    task: Task,
    ctx: RunContext,
    log_path: Path,
    errors: dict[str, BaseException],
) -> None:
    rec.update(status="running", started_at=_now())
    store.save(run)
    t0 = time.perf_counter()
    with _capture(log_path):
        try:
            summary = task.fn(ctx)
        except Exception as exc:
            _log.error("task %s failed", task.id)
            for line in traceback.format_exception(exc):
                for part in line.rstrip("\n").split("\n"):
                    _log.error("%s", part)
            errors[task.id] = exc
            rec.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        else:
            rec.update(status="success", summary=dict(summary or {}))
    rec["ended_at"] = _now()
    rec["duration_s"] = round(time.perf_counter() - t0, 3)
    store.save(run)


def run_pipeline(
    home: Path,
    pipeline_id: str,
    params: Mapping[str, Any] | None = None,
    *,
    progress: Callable[[str], None] | None = None,
) -> RunResult:
    """Run a packaged pipeline in the calling thread (the CLI path). Raises ``BusyError``."""
    from vnstratlab.runs.pipelines import get_pipeline

    pipeline = get_pipeline(pipeline_id)
    run_id = create_run(home, pipeline, params)
    return execute_run(home, pipeline, run_id, params, progress=progress)


def run_inline(home: Path, pipeline_id: str, label_vi: str, body: Callable[[], None]) -> None:
    """Run ``body`` (an existing CLI command body) as the single task of a run, in this thread.

    The run appears in the history. Whatever ``body`` raises is re-raised unchanged; an exit with
    code 0 counts as success, any other exception or exit code as a failed task.
    """
    clean_exits: list[Exception] = []

    def task_fn(_ctx: RunContext) -> None:
        try:
            body()
        except Exception as exc:
            if getattr(exc, "exit_code", None) == 0:
                clean_exits.append(exc)
                return
            raise

    pipeline = Pipeline(pipeline_id, label_vi, (Task(pipeline_id, label_vi, task_fn),))
    run_id = create_run(home, pipeline, {})
    result = execute_run(home, pipeline, run_id)
    result.raise_for_failure()
    if clean_exits:
        raise clean_exits[0]


class RunManager:
    """Starts pipelines in a background thread; the API's handle on the runner."""

    def __init__(self, home: Path, params: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.home = home
        self.store = RunStore(home)
        self._params = dict(params or {})  # per-pipeline params (a test hook narrows the demo)

    @property
    def active_run_id(self) -> str | None:
        return next(iter(_active), None)

    def start(self, pipeline_id: str) -> str:
        from vnstratlab.runs.pipelines import get_pipeline

        pipeline = get_pipeline(pipeline_id)
        params = self._params.get(pipeline_id, {})
        run_id = create_run(self.home, pipeline, params)
        thread = threading.Thread(
            target=self._run, args=(pipeline, run_id, params), name=f"run-{run_id}", daemon=True
        )
        thread.start()
        return run_id

    def _run(self, pipeline: Pipeline, run_id: str, params: Mapping[str, Any]) -> None:
        with contextlib.suppress(BaseException):  # the failure is recorded in run.json
            execute_run(self.home, pipeline, run_id, params)
