"""`vnstratlab serve` and its API (P1-T27a): TestClient, synthetic data, no network."""

from __future__ import annotations

import _socket
import re
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from vnstratlab import demo as demo_module
from vnstratlab.app.server import create_app
from vnstratlab.cli import app as cli_app
from vnstratlab.runs import Pipeline, Task, create_run, execute_run
from vnstratlab.runs import core as runs_core

HEADERS = {"X-Vnstratlab": "1"}
BASE = "http://127.0.0.1:8000"
WINDOW = {"demo": {"start": "2017-01-01", "end": "2017-03-31"}}


@pytest.fixture(autouse=True)
def _loopback_only(no_network: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """asyncio's self-pipe on Windows connects to 127.0.0.1 (a socketpair); allow exactly that.
    Any other address still fails the test (tests/conftest.py)."""
    refuse = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> None:
        if isinstance(address, tuple) and address[0] == "127.0.0.1":
            _socket.socket.connect(self, address)
        else:
            refuse(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture(autouse=True)
def _idle() -> Iterator[None]:
    yield
    deadline = time.time() + 30
    while runs_core._active and time.time() < deadline:
        time.sleep(0.05)
    assert not runs_core._active


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    cfg = demo_module.demo_config()
    small = cfg.model_copy(
        update={
            "strategies": {"S17_equal_weight": {"horizons": ["short", "medium"], "params": [{}]}}
        }
    )
    monkeypatch.setattr(demo_module, "demo_config", lambda: small)
    return TestClient(create_app(tmp_path / "home", pipeline_params=WINDOW), base_url=BASE)


def wait_done(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.time() + 120
    while time.time() < deadline:
        run: dict[str, Any] = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("success", "failed"):
            return run
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_demo_run_through_the_api(client: TestClient) -> None:
    listing = client.get("/api/pipelines").json()["pipelines"]
    demo = next(p for p in listing if p["id"] == "demo")
    assert next(t["id"] for t in demo["tasks"]) == "ingest"
    assert ["features", "strategies"] in demo["edges"]

    started = client.post("/api/runs", json={"pipeline": "demo"}, headers=HEADERS)
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    run = wait_done(client, run_id)
    assert run["status"] == "success", run
    assert [t["status"] for t in run["tasks"]] == ["success"] * 6

    first = client.get(f"/api/runs/{run_id}/tasks/ingest/log").json()
    assert first["status"] == "success"
    rest = client.get(f"/api/runs/{run_id}/tasks/simulate/log", params={"offset": 0}).json()
    again = client.get(
        f"/api/runs/{run_id}/tasks/simulate/log", params={"offset": rest["offset"]}
    ).json()
    assert rest["offset"] > 0
    assert again == {"text": "", "offset": rest["offset"], "status": "success"}

    results = client.get(f"/api/results/{run_id}").json()
    assert results["synthetic"] is True
    assert len(results["rows"]) == 4  # 2 S17 trials + 2 benchmark rows (no risk layer)
    trial_id = results["rows"][0]["trial_id"]
    assert len(results["equity"][trial_id]["dates"]) > 20

    events = client.get(f"/api/runs/{run_id}/events").text
    assert "event: end" in events
    assert client.get("/api/runs", params={"limit": 5}).json()["runs"][0]["run_id"] == run_id

    status = client.get("/api/data/status").json()
    assert status["stores"] == []  # the demo never writes the user's stores
    assert "counts" in client.get("/api/data/gaps").json()


def test_post_needs_the_header_and_a_loopback_origin(client: TestClient) -> None:
    body = {"pipeline": "demo"}
    assert client.post("/api/runs", json=body).status_code == 403
    evil = {**HEADERS, "Origin": "http://evil.example"}
    assert client.post("/api/runs", json=body, headers=evil).status_code == 403
    assert TestClient(client.app).get("/api/runs").status_code == 403  # Host: testserver
    assert runs_core._active == set()


def test_unknown_pipeline_and_odd_ids_are_404(client: TestClient) -> None:
    assert client.post("/api/runs", json={"pipeline": "nope"}, headers=HEADERS).status_code == 404
    assert client.get("/api/runs/..%2f..%2fetc").status_code == 404
    assert client.get("/api/runs/20200101T000000-demo-abcd").status_code == 404


def test_a_second_start_is_409_busy(client: TestClient, tmp_path: Path) -> None:
    pipeline = Pipeline("t", "t", (Task("a", "a", lambda _c: None),))
    run_id = create_run(tmp_path / "other", pipeline)  # holds the process-wide slot
    try:
        busy = client.post("/api/runs", json={"pipeline": "demo"}, headers=HEADERS)
        assert busy.status_code == 409
        assert busy.json()["error"] == "busy"
    finally:
        execute_run(tmp_path / "other", pipeline, run_id)


def test_yahoo_refresh_needs_the_terms_then_records_them(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / "config.yaml").write_text("data:\n  source: yahoo\n", encoding="utf-8")
    calls: list[str] = []

    def fake_ingest(*_a: Any, **_k: Any) -> Any:  # never reaches Yahoo
        calls.append("ingest")
        return SimpleNamespace(
            status="ok", warnings=(), failed={}, rows_in=0, rows_written=0,
            rows_changed=0, rows_dropped=0,
        )  # fmt: skip

    monkeypatch.setattr("vnstratlab.data.pipeline.ingest", fake_ingest)
    accepted = home / "state" / "accepted_sources.json"

    refused = client.post("/api/runs", json={"pipeline": "refresh"}, headers=HEADERS)
    assert refused.status_code == 409
    assert refused.json()["error"] == "terms_required"
    assert "yahoo" in refused.json()["notice"].lower()
    assert not accepted.exists()

    ok = client.post(
        "/api/runs", json={"pipeline": "refresh", "accept_terms": True}, headers=HEADERS
    )
    assert ok.status_code == 202
    assert "yahoo" in accepted.read_text(encoding="utf-8")
    wait_done(client, ok.json()["run_id"])


def test_serve_refuses_a_non_loopback_host() -> None:
    result = CliRunner().invoke(cli_app, ["serve", "--host", "0.0.0.0", "--no-open"])  # noqa: S104
    assert result.exit_code == 1
    assert "loopback" in result.output


def test_no_order_endpoints_exist(client: TestClient) -> None:
    paths = " ".join(getattr(r, "path", "") for r in client.app.routes)  # type: ignore[attr-defined]
    assert not re.search(r"order|broker|trade|execute|credential|secret|token", paths, re.I)
