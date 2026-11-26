"""The local FastAPI app behind ``vnstratlab serve`` (P1-T27a).

Loopback only: every request must carry a loopback ``Host``; a POST also needs the header
``X-Vnstratlab: 1`` and, when present, a loopback ``Origin``. There is no authentication beyond
that and no endpoint that places, routes or confirms orders. Nothing here returns a secret: the
settings object is never read.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from vnstratlab.config.loader import ConfigError, load_config
from vnstratlab.paths import get_paths
from vnstratlab.runs import (
    KEEP_RUNS,
    PIPELINES,
    SOURCE_PIPELINES,
    BusyError,
    RunError,
    RunManager,
)
from vnstratlab.runs.core import TERMINAL

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
GUARD_HEADER = "X-Vnstratlab"
POLL_SECONDS = 0.5


def is_loopback(host: str | None) -> bool:
    return host is not None and host.lower() in LOOPBACK_HOSTS


def _host_of(value: str, *, url: bool) -> str | None:
    try:
        return urlsplit(value if url else f"//{value}").hostname
    except ValueError:
        return None


class StartRequest(BaseModel):
    pipeline: str
    accept_terms: bool = False


def _error(status: int, code: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": code, **extra}, status_code=status)


def read_log(path: Path, offset: int, *, running: bool) -> tuple[str, int]:
    """Text of ``path`` from byte ``offset`` and the new offset. While the task runs only whole
    lines are returned, so a line being written is never cut."""
    if not path.is_file() or offset < 0:
        return "", max(offset, 0) if path.is_file() else 0
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
    if running:
        cut = data.rfind(b"\n") + 1
        data = data[:cut]
    return data.decode("utf-8", errors="replace"), offset + len(data)


def create_app(
    home: Path | None = None, *, pipeline_params: Mapping[str, Mapping[str, Any]] | None = None
) -> FastAPI:
    """Build the app for one app home. ``pipeline_params`` narrows a pipeline (tests use it to
    run the demo on a short window); the HTTP API itself accepts no parameters."""
    paths = get_paths(home)
    manager = RunManager(paths.home, pipeline_params)
    store = manager.store
    app = FastAPI(title="vnstratlab", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def loopback_guard(request: Request, call_next: Callable[[Request], Any]) -> Any:
        if not is_loopback(_host_of(request.headers.get("host", ""), url=False)):
            return _error(403, "forbidden", message="loopback host required")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if request.headers.get(GUARD_HEADER) != "1":
                return _error(403, "forbidden", message=f"header {GUARD_HEADER}: 1 required")
            if origin is not None and not is_loopback(_host_of(origin, url=True)):
                return _error(403, "forbidden", message="loopback origin required")
        return await call_next(request)

    @app.get("/api/pipelines")
    def pipelines() -> dict[str, Any]:
        return {
            "pipelines": [
                {
                    "id": p.id,
                    "label_vi": p.label_vi,
                    "needs_source_terms": p.id in SOURCE_PIPELINES,
                    "tasks": [
                        {"id": t.id, "label_vi": t.label_vi, "upstream": list(t.upstream)}
                        for t in p.ordered()
                    ],
                    "edges": [[u, t.id] for t in p.ordered() for u in t.upstream],
                }
                for p in PIPELINES.values()
            ]
        }

    @app.get("/api/runs")
    def list_runs(limit: int = 20) -> dict[str, Any]:
        return {"runs": store.list(min(max(limit, 1), KEEP_RUNS))}

    @app.get("/api/runs/{run_id}", response_model=None)
    def get_run(run_id: str) -> Any:
        run = store.get(run_id)
        return run if run is not None else _error(404, "not_found", run_id=run_id)

    @app.get("/api/runs/{run_id}/tasks/{task}/log", response_model=None)
    def get_log(run_id: str, task: str, offset: int = 0) -> Any:
        run = store.get(run_id)
        rec = next((t for t in (run or {}).get("tasks", []) if t["id"] == task), None)
        if rec is None:
            return _error(404, "not_found", run_id=run_id, task=task)
        text, new = read_log(
            store.run_dir(run_id) / f"{task}.log", offset, running=rec["status"] == "running"
        )
        return {"text": text, "offset": new, "status": rec["status"]}

    @app.get("/api/runs/{run_id}/events", response_model=None)
    def run_events(run_id: str) -> Any:
        if store.get(run_id) is None:
            return _error(404, "not_found", run_id=run_id)

        def sse(event: str, data: Mapping[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        def stream() -> Iterator[str]:
            statuses: dict[str, str] = {}
            offsets: dict[str, int] = {}
            while True:
                run = store.get(run_id)  # read the status first, then the logs: none is lost
                if run is None:
                    return
                for rec in run["tasks"]:
                    tid = rec["id"]
                    if statuses.get(tid) != rec["status"]:
                        statuses[tid] = rec["status"]
                        yield sse("task", {"task": tid, "status": rec["status"]})
                    text, new = read_log(
                        store.run_dir(run_id) / f"{tid}.log",
                        offsets.get(tid, 0),
                        running=rec["status"] == "running",
                    )
                    if text:
                        offsets[tid] = new
                        yield sse("log", {"task": tid, "text": text, "offset": new})
                if run["status"] in TERMINAL:
                    yield sse("end", {"status": run["status"], "reason": run.get("reason")})
                    return
                time.sleep(POLL_SECONDS)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/api/runs", response_model=None)
    def start_run(body: StartRequest) -> Any:
        from vnstratlab.data.pipeline import record_terms_acceptance, terms_accepted, terms_notice
        from vnstratlab.data.pipeline import utc_now as pipeline_now
        from vnstratlab.data.protocol import SourceError, get_source

        if body.pipeline not in PIPELINES:
            return _error(
                404, "unknown_pipeline", pipeline=body.pipeline, available=list(PIPELINES)
            )
        adapter = None
        if body.pipeline in SOURCE_PIPELINES:
            try:
                cfg = load_config(paths.home)
                adapter = get_source(cfg.data.source, cfg)
            except ConfigError as exc:
                return _error(422, "config_invalid", problems=list(exc.problems))
            except SourceError as exc:
                return _error(422, "source_error", message=str(exc))
            if not terms_accepted(paths, adapter) and not body.accept_terms:
                return _error(
                    409,
                    "terms_required",
                    source=adapter.info.name,
                    notice=terms_notice(adapter),
                )
        if manager.active_run_id is not None:
            return _error(409, "busy", active_run_id=manager.active_run_id)
        if adapter is not None and not terms_accepted(paths, adapter):
            record_terms_acceptance(paths, adapter, pipeline_now())
        try:
            run_id = manager.start(body.pipeline)
        except BusyError as exc:
            return _error(409, "busy", active_run_id=exc.active)
        except RunError as exc:
            return _error(422, "run_error", message=str(exc))
        return JSONResponse({"run_id": run_id, "pipeline": body.pipeline}, status_code=202)

    @app.get("/api/data/status")
    def data_status() -> dict[str, Any]:
        from vnstratlab.cli import build_data_status

        return build_data_status(paths)

    @app.get("/api/data/gaps")
    def data_gaps() -> dict[str, Any]:
        from vnstratlab.data.gaps import load_gaps

        register = load_gaps()
        return {
            "counts": register.open_counts(),
            "gaps": [g.model_dump(mode="json") for g in register.with_status(None)],
        }

    @app.get("/api/backtest/summary", response_model=None)
    def backtest_summary(source: str | None = None) -> Any:
        import duckdb

        from vnstratlab.lab.walkforward import (
            SEGMENT_LABELS,
            SUMMARY_COLUMNS,
            data_label,
            load_summary,
        )

        name = source
        if name is None:
            try:
                name = load_config(paths.home).data.source
            except ConfigError as exc:
                return _error(422, "config_invalid", problems=list(exc.problems))
        try:
            frame = load_summary(paths, name)
        except duckdb.Error as exc:  # the lab store is being written (a backtest is running)
            return _error(409, "lab_store_busy", message=str(exc))
        rows = frame.astype(object).where(frame.notna(), None).to_dict("records")
        return {
            "source": name,
            "synthetic": name == "synthetic",
            "label": data_label(name),
            "segments": SEGMENT_LABELS,
            "columns": list(SUMMARY_COLUMNS),
            "rows": rows,
        }

    @app.get("/api/results/{run_id}", response_model=None)
    def results(run_id: str) -> Any:
        import pandas as pd

        if store.get(run_id) is None:
            return _error(404, "not_found", run_id=run_id)
        out = store.run_dir(run_id) / "demo"
        summary_path = out / "summary.csv"
        if not summary_path.is_file():
            return _error(404, "no_results", run_id=run_id)
        summary = pd.read_csv(summary_path)
        records = summary.astype(object).where(summary.notna(), None).to_dict("records")
        equity: dict[str, Any] = {}
        for path in sorted((out / "equity").glob("*.csv")):
            frame = pd.read_csv(path)
            equity[path.stem] = {
                "dates": [str(d)[:10] for d in frame["date"]],
                "equity": [None if v != v else float(v) for v in frame["equity"]],
            }
        return {
            "run_id": run_id,
            "synthetic": True,
            "columns": list(summary.columns),
            "rows": records,
            "equity": equity,
        }

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
