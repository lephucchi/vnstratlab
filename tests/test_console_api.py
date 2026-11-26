"""Console v2 API (X-console-api): config editing, strategy parameter sets, cancel / rerun,
overview and chart data, the built-in terminal. TestClient, synthetic data, no network."""

from __future__ import annotations

import _socket
import shutil
import socket
import sys
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from vnstratlab import demo as demo_module
from vnstratlab.app import api_data
from vnstratlab.app.server import create_app
from vnstratlab.config.loader import load_config
from vnstratlab.init_wizard import packaged_defaults
from vnstratlab.lab.trials import TrialRegistry
from vnstratlab.paths import get_paths
from vnstratlab.runs import Pipeline, Task
from vnstratlab.runs import core as runs_core
from vnstratlab.runs import pipelines as runs_pipelines
from vnstratlab.strategies.registry import (
    get_strategy_class,
    load_strategies,
    registered_ids,
)
from vnstratlab.strategies.schemas import STRATEGY_INFO, params_schema

HEADERS = {"X-Vnstratlab": "1"}
BASE = "http://127.0.0.1:8000"
FAKE_SECRETS = {
    "TELEGRAM_BOT_TOKEN": "fake-token-aaaa",
    "TELEGRAM_CHAT_ID": "fake-chat-bbbb",
    "PO_PASSWORD": "fake-password-cccc",
}


@pytest.fixture(autouse=True)
def _loopback_only(no_network: None, monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.fixture(scope="module")
def synthetic_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One small synthetic store (ingest, rebuild, features) shared by the module."""
    root = tmp_path_factory.mktemp("console_data")
    state = demo_module.new_state(root, date(2015, 1, 1), date(2015, 6, 30))
    demo_module.stage_ingest(state)
    demo_module.stage_rebuild(state)
    demo_module.stage_features(state)
    return get_paths(root).data_dir


def make_home(tmp_path: Path, data: Path | None, config: dict[str, Any] | None) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    if data is not None:
        shutil.copytree(data, home / "data")
    if config is not None:
        (home / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return home


@pytest.fixture
def home(tmp_path: Path, synthetic_data: Path) -> Path:
    return make_home(
        tmp_path,
        synthetic_data,
        {"data": {"source": "synthetic"}, "news": {"collect_raw": False}},
    )


@pytest.fixture
def client(home: Path) -> TestClient:
    return TestClient(create_app(home), base_url=BASE)


def wait_done(client: TestClient, run_id: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run: dict[str, Any] = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("success", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def wait_for(predicate: Any, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not reached")


# ------------------------------------------------------------------ config


def test_config_get_validate_put_reset(client: TestClient, home: Path) -> None:
    got = client.get("/api/config").json()
    fields = {f["path"]: f for f in got["editable"]}
    assert fields["costs.brokerage_fee_pct"]["verify"] is True
    assert fields["books.short.capital_vnd"]["verify"] is False
    assert fields["data.source"]["options"] == ["yahoo", "synthetic"]
    assert got["exists"] is True
    assert got["file"].endswith("config.yaml")
    assert got["effective"]["data"]["source"] == "synthetic"
    assert got["defaults"]["data"]["source"] == "yahoo"

    bad = client.post(
        "/api/config/validate", json={"changes": {"costs.sales_tax_pct": 1.5}}, headers=HEADERS
    )
    assert bad.json()["ok"] is False
    assert bad.json()["problems"][0].startswith("costs.sales_tax_pct")
    not_editable = client.put("/api/config", json={"changes": {"lab.seed": 1}}, headers=HEADERS)
    assert not_editable.status_code == 422
    assert "lab.seed: not editable" in not_editable.json()["problems"]

    changes = {"books.short.capital_vnd": 20_000_000, "costs.brokerage_fee_pct": 0.002}
    put = client.put("/api/config", json={"changes": changes}, headers=HEADERS)
    assert put.status_code == 200
    body = put.json()
    assert {d["path"] for d in body["diff"]} == set(changes)
    assert body["backup"]
    assert Path(body["backup"]).is_file()
    saved = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert saved["news"] == {"collect_raw": False}  # an unrelated user key is kept
    assert saved["books"]["short"]["capital_vnd"] == 20_000_000
    assert load_config(home).books.short.capital_vnd == 20_000_000

    reset = client.post(
        "/api/config/reset", json={"paths": ["costs.brokerage_fee_pct"]}, headers=HEADERS
    )
    assert reset.status_code == 200
    saved = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert "costs" not in saved
    assert saved["books"]["short"]["capital_vnd"] == 20_000_000
    assert client.put("/api/config", json={"changes": {}}).status_code == 403  # needs the header


# ------------------------------------------------------------------ strategies


def test_schemas_match_validate_params() -> None:
    """Every packaged parameter set fits its schema and every schema value is accepted."""
    assert set(STRATEGY_INFO) == set(registered_ids())
    packaged = packaged_defaults()["strategies"]
    for sid, entry in packaged.items():
        cls = get_strategy_class(sid)
        specs = {p["name"]: p for p in params_schema(sid)}
        for params in entry["params"]:
            assert set(params) == set(specs), sid
            cls.validate_params(params)
            for name, value in params.items():
                spec = specs[name]
                if "allowed" in spec:
                    assert value in spec["allowed"], (sid, name)
                if "min" in spec:
                    exclusive = spec.get("min_exclusive", False)
                    assert value > spec["min"] if exclusive else value >= spec["min"], (sid, name)
        base = dict(entry["params"][0])
        for name, spec in specs.items():
            values = list(spec.get("allowed", []))
            if "min" in spec and not spec.get("min_exclusive"):
                values.append(spec["min"])
            if "max" in spec:
                values.append(spec["max"])
            for value in values:
                cls.validate_params({**base, name: value})
            if spec["type"] == "int" and "min" in spec:
                with pytest.raises(ValueError, match=r"must be"):
                    cls.validate_params({**base, name: spec["min"] - 1})
    get_strategy_class("S17_equal_weight").validate_params({})


def test_param_set_lifecycle(client: TestClient, home: Path) -> None:
    listing = client.get("/api/strategies").json()
    by_id = {s["id"]: s for s in listing["strategies"]}
    assert set(by_id) == set(registered_ids())
    s01 = by_id["S01_weekly_reversal"]
    assert s01["params_schema"][0]["name"] == "n"
    assert s01["horizons_allowed"] == ["short"]
    assert [p["origin"] for p in s01["param_sets"]] == ["packaged", "packaged"]
    assert listing["trials_total"] == 0
    assert all(not t["registered"] for t in s01["param_sets"][0]["trial_ids"])

    url = "/api/strategies/S01_weekly_reversal/param-sets"
    invalid = client.post(url, json={"params": {"n": 0}, "horizons": ["short"]}, headers=HEADERS)
    assert invalid.status_code == 422
    assert invalid.json()["problems"]
    wrong_h = client.post(url, json={"params": {"n": 5}, "horizons": ["long"]}, headers=HEADERS)
    assert wrong_h.status_code == 422
    dup = client.post(url, json={"params": {"n": 2}, "horizons": ["short"]}, headers=HEADERS)
    assert dup.status_code == 422

    added = client.post(url, json={"params": {"n": 5}, "horizons": ["short"]}, headers=HEADERS)
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["index"] == 2
    assert "Deflated Sharpe" in body["warning_vi"]
    trial_id = body["trial_ids"][0]["trial_id"]
    with TrialRegistry(get_paths(home).lab_db, read_only=True) as registry:
        assert registry.is_registered(trial_id)
    cfg = load_config(home)
    assert {"n": 5} in [s.params for s in load_strategies(cfg) if s.id == "S01_weekly_reversal"]

    patched = client.patch(
        "/api/strategies/S01_weekly_reversal/param-sets/0", json={"enabled": False}, headers=HEADERS
    )
    assert patched.status_code == 200
    params = [s.params for s in load_strategies(load_config(home)) if s.id == "S01_weekly_reversal"]
    assert {"n": 2} not in params
    assert {"n": 3} in params
    after = {s["id"]: s for s in client.get("/api/strategies").json()["strategies"]}
    sets = after["S01_weekly_reversal"]["param_sets"]
    assert [s["enabled"] for s in sets] == [False, True, True]
    assert sets[2]["origin"] == "user"
    assert sets[2]["trial_ids"][0]["registered"] is True

    packaged_delete = client.delete(f"{url}/1", headers=HEADERS)
    assert packaged_delete.status_code == 409
    deleted = client.delete(f"{url}/2", headers=HEADERS)
    assert deleted.status_code == 200
    assert deleted.json()["trials_kept"] is True
    params = [s.params for s in load_strategies(load_config(home)) if s.id == "S01_weekly_reversal"]
    assert {"n": 5} not in params
    with TrialRegistry(get_paths(home).lab_db, read_only=True) as registry:
        assert registry.is_registered(trial_id)  # append-only: the trial stays counted
    assert client.get("/api/strategies").json()["trials_total"] == 1


def test_param_set_needs_features_first(tmp_path: Path) -> None:
    home = make_home(tmp_path, None, {"data": {"source": "synthetic"}})
    client = TestClient(create_app(home), base_url=BASE)
    url = "/api/strategies/S01_weekly_reversal/param-sets"
    res = client.post(url, json={"params": {"n": 5}, "horizons": ["short"]}, headers=HEADERS)
    assert res.status_code == 409
    assert res.json()["error"] == "features_required"
    assert not (home / "config.yaml").exists() or "user_params" not in (
        home / "config.yaml"
    ).read_text(encoding="utf-8")


# ------------------------------------------------------------------ runs: cancel, rerun


def test_cancel_and_rerun(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def wait_task(ctx: Any) -> dict[str, Any]:
        ctx.cancel.wait(20)
        return {"cancelled": ctx.cancel.is_set()}

    pipeline = Pipeline(
        "fake2",
        "Giả",
        (Task("one", "Một", wait_task), Task("two", "Hai", lambda ctx: {}, ("one",))),
    )
    monkeypatch.setitem(runs_pipelines.PIPELINES, "fake2", pipeline)

    started = client.post("/api/runs", json={"pipeline": "fake2"}, headers=HEADERS)
    assert started.status_code == 202
    assert started.json()["cli"] is None
    run_id = started.json()["run_id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["tasks"][0]["status"] == "running")
    assert client.post(f"/api/runs/{run_id}/cancel", headers=HEADERS).status_code == 202
    run = wait_done(client, run_id)
    assert run["status"] == "failed"
    assert run["reason"] == "cancelled"
    assert [t["status"] for t in run["tasks"]] == ["success", "skipped"]
    assert client.post(f"/api/runs/{run_id}/cancel", headers=HEADERS).status_code == 409

    again = client.post(f"/api/runs/{run_id}/rerun", headers=HEADERS)
    assert again.status_code == 202
    assert again.json()["pipeline"] == "fake2"
    new_id = again.json()["run_id"]
    assert new_id != run_id
    assert client.post("/api/runs/nope/rerun", headers=HEADERS).status_code == 404
    client.post(f"/api/runs/{new_id}/cancel", headers=HEADERS)
    wait_done(client, new_id)


# ------------------------------------------------------------------ overview and data


def test_overview_prices_quality(client: TestClient) -> None:
    ov = client.get("/api/overview").json()
    assert ov["source"] == "synthetic"
    assert ov["active_run_id"] is None
    assert ov["store"]["kind"] == "synthetic"
    assert ov["store"]["rows"] > 0
    assert ov["store"]["first"] == "2015-01-01"
    assert ov["store"]["stale_days"] > 0
    assert set(ov["gaps"]) == {"high", "medium", "low"}
    assert ov["verify_count"] > 0
    assert ov["strategies"]["registered"] == len(registered_ids())
    assert ov["strategies"]["enabled"] > 0
    assert ov["strategies"]["trials"] == 0

    ticker = ov["store"]["tickers"][0]
    adj = client.get(f"/api/data/prices/{ticker}", params={"from": "2015-03-01"}).json()
    assert adj["ticker"] == ticker
    assert adj["kind"] == "synthetic"
    assert adj["dates"][0] >= "2015-03-01"
    assert len(adj["dates"]) == len(adj["close"]) == len(adj["volume"]) > 10
    exe = client.get(f"/api/data/prices/{ticker}", params={"series": "exec"}).json()
    assert exe["series"] == "exec"
    assert len(exe["dates"]) >= len(adj["dates"])
    assert client.get("/api/data/prices/NOPE").status_code == 404
    assert client.get(f"/api/data/prices/{ticker}", params={"series": "x"}).status_code == 422
    quality = client.get("/api/data/quality", params={"limit": 5}).json()
    assert isinstance(quality["rows"], list)
    assert len(quality["rows"]) <= 5

    keep = api_data.downsample(10_000)
    assert len(keep) <= api_data.MAX_POINTS
    assert keep[0] == 0
    assert keep[-1] == 9_999


def test_no_secret_in_any_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    for name, value in FAKE_SECRETS.items():
        monkeypatch.setenv(name, value)
    (home / ".env").write_text("TELEGRAM_BOT_TOKEN=fake-token-dddd\n", encoding="utf-8")
    ticker = client.get("/api/overview").json()["store"]["tickers"][0]
    texts = [
        client.get(url).text
        for url in (
            "/api/config",
            "/api/overview",
            "/api/strategies",
            "/api/cli/commands",
            "/api/runs",
            f"/api/data/prices/{ticker}",
            "/api/data/quality",
        )
    ]
    for text in texts:
        assert "fake-" not in text


# ------------------------------------------------------------------ terminal


def fake_launcher(args: list[str]) -> list[str]:
    code = "import sys; print('ARGS', sys.argv[1:], flush=True)"
    return [sys.executable, "-c", code, *args]


def slow_launcher(args: list[str]) -> list[str]:
    code = "import threading; print('started', flush=True); threading.Event().wait(60)"
    return [sys.executable, "-c", code]


def test_terminal_commands_and_safety(home: Path) -> None:
    client = TestClient(create_app(home, cli_launcher=fake_launcher), base_url=BASE)
    commands = {tuple(c["path"]): c for c in client.get("/api/cli/commands").json()["commands"]}
    assert commands[("data", "rebuild")]["allowed"] is True
    assert any(
        o["name"] == "--dry-run" and o["type"] == "bool"
        for o in commands[("data", "rebuild")]["options"]
    )
    assert commands[("serve",)]["allowed"] is False

    ran = client.post("/api/cli", json={"command": "vnstratlab doctor"}, headers=HEADERS)
    assert ran.status_code == 202
    assert ran.json()["argv"] == ["vnstratlab", "doctor"]
    run = wait_done(client, ran.json()["run_id"])
    assert run["pipeline"] == "cli"
    assert run["status"] == "success"
    assert run["tasks"][0]["summary"]["exit_code"] == 0
    log = client.get(f"/api/runs/{run['run_id']}/tasks/cli/log").json()["text"]
    assert "ARGS ['doctor']" in log

    # shell metacharacters are literal arguments: nothing is interpreted
    tricky = 'data rebuild --source "a;b && echo $(x) | y"'
    ran = client.post("/api/cli", json={"command": tricky}, headers=HEADERS)
    run = wait_done(client, ran.json()["run_id"])
    log = client.get(f"/api/runs/{run['run_id']}/tasks/cli/log").json()["text"]
    assert "'a;b && echo $(x) | y'" in log

    assert (
        client.post("/api/cli", json={"command": "serve"}, headers=HEADERS).json()["error"]
        == "not_allowed"
    )
    assert client.post("/api/cli", json={"command": "init"}, headers=HEADERS).status_code == 422
    for line in ("rm -rf /", "ls", "data status; ls", "", "doctor\nls"):
        res = client.post("/api/cli", json={"command": line}, headers=HEADERS)
        assert res.status_code == 422, line
    assert runs_core._active == set()


def test_terminal_terms_gate(home: Path, tmp_path: Path) -> None:
    default_home = make_home(tmp_path / "second", None, None)  # default source: yahoo
    client = TestClient(create_app(default_home, cli_launcher=fake_launcher), base_url=BASE)
    gated = client.post("/api/cli", json={"command": "ingest"}, headers=HEADERS)
    assert gated.status_code == 409
    assert gated.json()["error"] == "terms_required"
    assert gated.json()["source"] == "yahoo"
    assert gated.json()["notice"]
    ok = client.post("/api/cli", json={"command": "ingest", "accept_terms": True}, headers=HEADERS)
    assert ok.status_code == 202
    assert ok.json()["argv"][-1] == "--accept-source-terms"
    wait_done(client, ok.json()["run_id"])


def test_terminal_cancel_kills_the_command(home: Path) -> None:
    client = TestClient(create_app(home, cli_launcher=slow_launcher), base_url=BASE)
    ran = client.post("/api/cli", json={"command": "doctor"}, headers=HEADERS)
    run_id = ran.json()["run_id"]
    wait_for(lambda: "started" in client.get(f"/api/runs/{run_id}/tasks/cli/log").json()["text"])
    t0 = time.time()
    assert client.post(f"/api/runs/{run_id}/cancel", headers=HEADERS).status_code == 202
    run = wait_done(client, run_id, timeout=20)
    assert time.time() - t0 < 15
    assert run["status"] == "failed"
    assert run["reason"] == "cancelled"
    assert run["tasks"][0]["summary"]["exit_code"] != 0


def test_pipelines_show_their_cli_equivalent(client: TestClient) -> None:
    items = {p["id"]: p for p in client.get("/api/pipelines").json()["pipelines"]}
    assert items["demo"]["cli"] == "vnstratlab demo"
    assert items["rebuild"]["cli"] == "vnstratlab data rebuild"
