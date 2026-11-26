"""Current recommendations and per-stock analysis (card X-stock-api). Synthetic data only."""

from __future__ import annotations

import _socket
import shutil
import socket
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from vnstratlab import demo as demo_module
from vnstratlab.app.server import create_app
from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.store import MarketStore
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.features.groups import FEATURE_COLUMNS
from vnstratlab.insight import stock as stock_module
from vnstratlab.insight.recommend import (
    DISCLAIMER_VI,
    InsightError,
    recommendations,
    size_position,
)
from vnstratlab.lab.store import LabStore
from vnstratlab.lab.trials import store_feature_version
from vnstratlab.lab.walkforward import config_pairs
from vnstratlab.paths import get_paths
from vnstratlab.runs import ParamError, RunManager, run_pipeline
from vnstratlab.runs import core as runs_core
from vnstratlab.strategies.registry import make_trial_spec

BASE = "http://127.0.0.1:8000"
HEADERS = {"X-Vnstratlab": "1"}
S17, S01 = "S17_equal_weight", "S01_weekly_reversal"
runner = CliRunner()
CUT = date(2016, 3, 16)  # a Wednesday in the middle of the synthetic window


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
def store_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One synthetic ingest + rebuild + features for the module (1.5 years, offline)."""
    root = tmp_path_factory.mktemp("insight_home")
    state = demo_module.new_state(root, date(2015, 1, 1), date(2016, 6, 30))
    demo_module.stage_ingest(state)
    demo_module.stage_rebuild(state)
    demo_module.stage_features(state)
    return get_paths(root).synthetic_market_db


def make_home(tmp_path: Path, store_file: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    paths = get_paths(home)
    paths.data_dir.mkdir(parents=True)
    shutil.copy(store_file, paths.synthetic_market_db)
    (home / "config.yaml").write_text(
        yaml.safe_dump({"data": {"source": "synthetic"}, "news": {"collect_raw": False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_HOME", str(home))
    return home


def register_trials(home: Path) -> None:
    """Register S17 on its horizons and S01 {n: 2}; every other enabled trial stays unregistered."""
    cfg, paths = load_config(home), get_paths(home)
    with MarketStore(paths.synthetic_market_db, "synthetic", read_only=True) as market:
        version = store_feature_version(market)
    with LabStore(paths.lab_db) as lab:
        for strategy, horizon in config_pairs(cfg, None):
            if strategy.id == S17 or (strategy.id == S01 and strategy.params == {"n": 2}):
                lab.register(make_trial_spec(strategy, horizon, version, ENGINE_VERSION), "test")


@pytest.fixture
def home(tmp_path: Path, store_file: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return make_home(tmp_path, store_file, monkeypatch)


@pytest.fixture
def registered(home: Path) -> Path:
    register_trials(home)
    return home


def wait_done(client: TestClient, run_id: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run: dict[str, Any] = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("success", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


# ------------------------------------------------------------------ AC 1: recommendations


def test_recommendations_count_only_registered_trials(home: Path) -> None:
    cfg, paths = load_config(home), get_paths(home)
    none_yet = recommendations(cfg, paths, "synthetic", "short")
    assert none_yet["targets"] == []
    assert none_yet["warnings"]  # nothing registered: said, not hidden
    assert none_yet["cash_weight"] == 1.0
    assert not any(s["registered"] for s in none_yet["strategies"])

    register_trials(home)
    body = recommendations(cfg, paths, "synthetic", "short")
    assert body["status"] == "preview"
    assert body["disclaimer_vi"] == DISCLAIMER_VI
    assert "SYNTHETIC" in body["label"]
    registered = [s for s in body["strategies"] if s["registered"]]
    assert {s["strategy_id"] for s in registered} == {S17, S01}
    assert all(s["weights"] for s in registered)
    assert all(
        not s["weights"] and "note_vi" in s for s in body["strategies"] if not s["registered"]
    )

    targets = body["targets"]
    assert targets
    total = sum(t["weight"] for t in targets)
    assert total <= 1.0 + 1e-9
    assert body["cash_weight"] == pytest.approx(1.0 - total)
    for target in targets:
        holders = sorted(s["strategy_id"] for s in registered if target["ticker"] in s["weights"])
        assert target["strategies"] == holders
        assert target["consensus"] == len(holders) >= 1
        assert target["lot_qty"] % target["lot_size"] == 0
        shares = target["lot_qty"] + target["odd_qty"]
        assert shares == int(target["weight"] * body["book_capital_vnd"] / target["last_close"])
    assert len({t["ticker"] for t in targets}) == len(targets)

    with pytest.raises(InsightError):
        recommendations(cfg, paths, "yahoo", "short")  # no store for that source


def test_lot_stop_and_cost_by_hand(engine_cfg: AppConfig) -> None:
    """52,700 VND, ATR 1,234, half of a 22,000,000 book (defaults: fee 0.15%, slippage 0.1% round
    and 0.3% odd lot, stop 2 x ATR, 7% limits, ticks 10 / 50 / 100)."""
    got = size_position(engine_cfg, 52_700.0, 1_234.0, 0.5, 22_000_000.0)
    # 11,000,000 / 52,700 = 208.7 -> 208 shares: 200 round + 8 odd
    assert (got["lot_qty"], got["odd_qty"], got["lots"]) == (200, 8, 2)
    assert got["notional_vnd"] == 208 * 52_700
    # ceiling 52,700 x 1.07 = 56,389 -> 56,300 (buy side rounds down); floor 49,011 -> 49,050
    assert (got["ceiling"], got["floor"]) == (56_300, 49_050)
    # entry zone [52,700, min(ceiling, 52,752.7)] rounded down to the tick (100)
    assert got["entry_zone"] == {"low": 52_700.0, "high": 52_700.0}
    # stop 52,700 - 2 x 1,234 = 50,232, rounded up to the tick (100) = 50,300
    assert got["stop_price"] == 50_300
    assert got["stop_pct"] == pytest.approx(2_400 / 52_700)
    assert got["risk_vnd"] == 208 * 2_400
    # round: fill 52,752.7, fee 0.15% of 200 x fill, slippage 200 x 52.7;
    # odd:   fill 52,858.1, fee 0.15% of 8 x fill,   slippage 8 x 158.1
    round_cost = 0.0015 * 200 * 52_752.7 + 200 * 52.7
    odd_cost = 0.0015 * 8 * 52_858.1 + 8 * 158.1
    assert got["est_cost_vnd"] == pytest.approx(round_cost + odd_cost)  # 28,264.91


def test_feature_labels_cover_every_feature() -> None:
    assert set(FEATURE_COLUMNS) <= set(stock_module.FEATURE_INFO)


# ------------------------------------------------------------------ AC 2: analysis, no lookahead


def cut_after(path: Path, day: date) -> None:
    """Delete every row dated after ``day`` from a copy of the store (it was never extended)."""
    con = duckdb.connect(str(path))
    try:
        for table, column in (
            ("features_daily", "date"),
            ("prices_exec", "date"),
            ("prices_adjusted", "date"),
            ("prices_daily", "date"),
            ("dq_results", "date"),
            ("corporate_actions", "ex_date"),
            ("exec_exclusions", "date"),
        ):
            con.execute(f"DELETE FROM {table} WHERE {column} > ?", [day])  # noqa: S608
    finally:
        con.close()


def run_stages(cfg: AppConfig, home: Path, asof: date | None) -> dict[str, Any]:
    st = stock_module.StockState(
        cfg, get_paths(home), "synthetic", "ACB", ("short", "medium"), asof=asof
    )
    stock_module.stage_load(st)
    stock_module.stage_features(st)
    stock_module.stage_signals(st)
    stock_module.stage_backtest(st)
    stock_module.stage_report(st)
    return {k: v for k, v in st.analysis.items() if k not in ("generated_at", "run_id")}


def test_analysis_has_every_block_and_ignores_rows_after_asof(
    registered: Path, tmp_path: Path, store_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_pipeline(
        registered,
        "stock_analysis",
        {"ticker": "acb", "source": "synthetic", "horizons": ["short", "medium"]},
    )
    result.raise_for_failure()
    assert result.status == "success"
    body = stock_module.load_latest(get_paths(registered), "synthetic", "ACB")
    assert body is not None
    assert body["run_id"] == result.run_id
    assert (
        get_paths(registered).logs_dir / "runs" / result.run_id / "stock_analysis.json"
    ).is_file()
    for block in (
        "ticker", "asof", "source", "synthetic", "label", "run_id", "generated_at", "price",
        "features", "strategies", "backtest", "risk", "quality", "recommendation", "chart",
    ):  # fmt: skip
        assert block in body
    assert body["synthetic"] is True
    assert "SYNTHETIC" in body["label"]
    assert set(body["price"]["change"]) == {"1W", "1M", "3M", "6M", "1Y", "YTD"}
    assert {s["strategy_id"] for s in body["strategies"]} == {S17, S01}
    assert {f["name"] for f in body["features"]} == set(FEATURE_COLUMNS)
    assert {f["unit"] for f in body["features"]} <= {"pct", "vnd", "ratio", "raw"}
    assert all(
        0 <= f["pct_rank_universe"] <= 1
        for f in body["features"]
        if f["pct_rank_universe"] is not None
    )
    assert set(body["risk"]["book"]) == {"short", "medium"}
    assert set(body["recommendation"]["by_horizon"]) == {"short", "medium"}
    assert body["recommendation"]["disclaimer_vi"] == DISCLAIMER_VI
    assert body["excluded_strategies"]  # enabled but unregistered: listed, not computed
    assert set(body["backtest"]["buy_hold"]) == {"cagr", "vol", "sharpe", "max_dd"}
    assert (
        len(body["chart"]["dates"]) == len(body["chart"]["close"]) == len(body["chart"]["volume"])
    )

    # rows after asof: the full store read at asof == the store without those rows
    cfg = load_config(registered)
    full = run_stages(cfg, registered, CUT)
    short_home = make_home(tmp_path / "short", store_file, monkeypatch)
    register_trials(short_home)
    cut_after(get_paths(short_home).synthetic_market_db, CUT)
    assert run_stages(load_config(short_home), short_home, None) == full
    assert full["asof"] == "2016-03-16"
    assert run_stages(cfg, registered, None)["asof"] == "2016-06-30"  # the cut really moved asof
    assert recommendations(cfg, get_paths(registered), "synthetic", "short", CUT) == (
        recommendations(load_config(short_home), get_paths(short_home), "synthetic", "short", None)
    )


# ------------------------------------------------------------------ AC 3 and 4: API and CLI


def test_stock_analysis_params_and_endpoints(registered: Path) -> None:
    client = TestClient(create_app(registered), base_url=BASE)
    manager = RunManager(registered)
    with pytest.raises(ParamError) as unknown:
        manager.start("stock_analysis", {"ticker": "ZZZZ"})
    assert unknown.value.code == "unknown_ticker"
    with pytest.raises(ParamError) as other:
        manager.start("demo", {"ticker": "ACB"})
    assert other.value.code == "params_not_accepted"
    bad = client.post("/api/stocks/ZZZZ/analyze", json={}, headers=HEADERS)
    assert bad.status_code == 422
    assert bad.json()["error"] == "unknown_ticker"
    assert client.post("/api/stocks/ACB/analyze", json={}).status_code == 403  # no guard header

    before = client.get("/api/stocks/ACB/analysis")
    assert before.status_code == 404
    assert before.json()["error"] == "no_analysis"
    started = client.post("/api/stocks/ACB/analyze", json={"horizons": ["short"]}, headers=HEADERS)
    assert started.status_code == 202
    assert started.json()["cli"] == "vnstratlab stock ACB"
    done = wait_done(client, started.json()["run_id"])
    assert done["status"] == "success", done
    got = client.get("/api/stocks/ACB/analysis").json()
    assert got["ticker"] == "ACB"
    assert set(got["recommendation"]["by_horizon"]) == {"short"}

    listing = client.get("/api/stocks").json()
    assert "ACB" in {t["ticker"] for t in listing["tickers"]}
    assert listing["disclaimer_vi"]
    both = client.get("/api/stocks/compare?tickers=ACB,VCB").json()
    assert [t["ticker"] for t in both["tickers"]] == ["ACB"]
    assert both["missing"] == ["VCB"]
    one = client.get("/api/recommendations?horizon=medium").json()
    assert one["horizon"] == "medium"
    assert one["status"] == "preview"
    assert one["label"]
    every = client.get("/api/recommendations/all").json()
    assert set(every["horizons"]) == {"short", "medium", "long"}
    assert client.get("/api/recommendations?horizon=weekly").status_code == 422

    again = client.post(f"/api/runs/{started.json()['run_id']}/rerun", headers=HEADERS)
    assert again.status_code == 202
    assert wait_done(client, again.json()["run_id"])["status"] == "success"


def test_cli_commands_and_listing(registered: Path) -> None:
    rec = runner.invoke(app, ["recommend", "--source", "synthetic", "--horizon", "short"])
    assert rec.exit_code == 0, rec.output
    assert "SYNTHETIC" in rec.output
    assert DISCLAIMER_VI in rec.output
    one = runner.invoke(app, ["stock", "ACB", "--source", "synthetic"])
    assert one.exit_code == 0, one.output
    assert "ACB | asof" in one.output
    assert "recommendation:" in one.output
    missing = runner.invoke(app, ["stock", "ZZZZ", "--source", "synthetic"])
    assert missing.exit_code == 1
    assert "ZZZZ" in missing.output

    client = TestClient(create_app(registered), base_url=BASE)
    paths = [c["path"] for c in client.get("/api/cli/commands").json()["commands"]]
    assert ["recommend"] in paths
    assert ["stock"] in paths
    pipelines = {p["id"]: p for p in client.get("/api/pipelines").json()["pipelines"]}
    assert pipelines["stock_analysis"]["cli"] == "vnstratlab stock <TICKER>"
    assert [t["id"] for t in pipelines["stock_analysis"]["tasks"]] == [
        "load", "features", "signals", "backtest", "report",
    ]  # fmt: skip
