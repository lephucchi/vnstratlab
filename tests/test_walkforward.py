"""Walk-forward runner and `vnstratlab backtest` (P1-T20). Synthetic data only, no network."""

from __future__ import annotations

import _socket
import itertools
import shutil
import socket
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from engine_helpers import make_days
from vnstratlab import demo as demo_module
from vnstratlab.app.server import create_app
from vnstratlab.calendar import TradingCalendar
from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig, Costs, Slippage
from vnstratlab.data.pipeline import VN_TZ, ExecutionFrame
from vnstratlab.data.store import MarketStore
from vnstratlab.demo import demo_config
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.engine.loop import ACTION_COLUMNS
from vnstratlab.lab.store import LabStore
from vnstratlab.lab.trials import UnregisteredTrialError, store_feature_version
from vnstratlab.lab.walkforward import (
    PERIODS_PER_YEAR,
    WalkForwardError,
    fit_cutoff,
    load_inputs,
    load_summary,
    period_stats,
    prepare_inputs,
    run_backtest,
    run_trial,
)
from vnstratlab.paths import get_paths
from vnstratlab.runs import RunStore, run_pipeline
from vnstratlab.strategies.base import BaseStrategy, LookaheadError, Strategy
from vnstratlab.strategies.builtin.s01_weekly_reversal import S01WeeklyReversal
from vnstratlab.strategies.builtin.s17_equal_weight import S17EqualWeight
from vnstratlab.strategies.registry import TrialSpec, make_trial_spec

runner = CliRunner()
DATA_START = date(2015, 1, 1)
DATA_END = date(2016, 6, 30)
S17 = "S17_equal_weight"
ALL_MODES = ("ideal", "executable")


@pytest.fixture(autouse=True)
def _loopback_only(no_network: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint test's TestClient needs asyncio's loopback self-pipe on Windows."""
    refuse = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> None:
        if isinstance(address, tuple) and address[0] == "127.0.0.1":
            _socket.socket.connect(self, address)
        else:
            refuse(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


# ------------------------------------------------------------------ shared synthetic store


@pytest.fixture(scope="module")
def store_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One synthetic ingest + rebuild + features for the module (1.5 years, offline)."""
    home = tmp_path_factory.mktemp("wf_home")
    st = demo_module.new_state(home, DATA_START, DATA_END)
    demo_module.stage_ingest(st)
    demo_module.stage_rebuild(st)
    demo_module.stage_features(st)
    return get_paths(home).synthetic_market_db


@pytest.fixture
def home(store_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh app home holding a copy of the synthetic store and no lab.duckdb."""
    target = tmp_path / "wf-app-home"
    paths = get_paths(target)
    paths.data_dir.mkdir(parents=True)
    shutil.copy(store_file, paths.synthetic_market_db)
    monkeypatch.setenv("APP_HOME", str(target))
    return target


@pytest.fixture(scope="module")
def cfg() -> AppConfig:
    return demo_config()


def small(cfg: AppConfig, **strategies: Any) -> AppConfig:
    return cfg.model_copy(update={"strategies": strategies})


# ------------------------------------------------------------------ hand-built market


def hand_market(days: list[date]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """3 tickers, gapless random-walk prices on 50 VND ticks (never near a limit), and features."""
    rng = np.random.default_rng(7)
    rows: list[dict[str, Any]] = []
    for ticker, level in (("AAA", 20_000.0), ("BBB", 30_000.0), ("CCC", 15_000.0)):
        close = level
        for day in days:
            open_ = close  # no overnight gap: a fill at the open costs what the sizing assumed
            new_close = open_ + 50.0 * int(rng.integers(-3, 4))
            rows.append(
                {
                    "ticker": ticker,
                    "date": day,
                    "open": open_,
                    "high": max(open_, new_close),
                    "low": min(open_, new_close),
                    "close": new_close,
                    "volume": 1_000_000,
                    "ref_price": close,
                    "ceiling": close * 1.07,
                    "floor": close * 0.93,
                    "price_basis": "synthetic",
                }
            )
            close = new_close
    prices = pd.DataFrame(rows)
    features = prices[["ticker", "date"]].assign(feature_version="fv-test")
    return prices, features


def hand_inputs(days: list[date], start: date, end: date) -> Any:
    prices, features = hand_market(days)
    frame = ExecutionFrame(prices, pd.DataFrame(columns=list(ACTION_COLUMNS)), pd.DataFrame())
    return prepare_inputs(features, frame, TradingCalendar(), "fv-test", "synthetic", start, end)


def register(lab: LabStore, strategy: Strategy, horizon: Any, version: str, now: datetime) -> None:
    lab.register(make_trial_spec(strategy, horizon, version, ENGINE_VERSION), "test", now=now)


T_REG = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)


# ------------------------------------------------------------------ AC 1: no lookahead


class Recorder(BaseStrategy):
    """Test-local strategy that records the newest feature date it is handed on each call."""

    id = "T_recorder"
    lookback_sessions = 3
    seen: ClassVar[list[tuple[date, date, int]]] = []

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        newest = pd.to_datetime(features["date"]).max().date()
        Recorder.seen.append((asof.date(), newest, int(features["date"].nunique())))
        return pd.Series(dtype=float)


def test_runner_never_hands_a_strategy_rows_after_asof(tmp_path: Path, cfg: AppConfig) -> None:
    days = make_days(30)
    inputs = hand_inputs(days, days[0], days[-1])
    strategy = Recorder({}, ("short",))
    Recorder.seen = []
    with LabStore(tmp_path / "lab.duckdb") as lab:
        register(lab, strategy, "short", "fv-test", T_REG)
        run = run_trial(inputs, lab, cfg, strategy, "short", ("ideal",))
    assert len(Recorder.seen) >= 3
    assert all(newest <= asof for asof, newest, _ in Recorder.seen)  # never a later row
    assert all(newest == asof for asof, newest, _ in Recorder.seen)  # and the asof row is there
    assert all(n <= Recorder.lookback_sessions for _, _, n in Recorder.seen)  # only its lookback
    assert (run.periods["ideal"]["ret"] == 0.0).all()  # all cash


def test_a_row_dated_after_asof_is_refused_by_the_asof_guard() -> None:
    days = make_days(30)
    _, features = hand_market(days)
    with pytest.raises(LookaheadError, match="dated after asof"):
        S17EqualWeight({}, ("short",)).target_weights(features, pd.Timestamp(days[10]))


def test_results_do_not_depend_on_data_after_the_period(
    store_file: Path, cfg: AppConfig, tmp_path: Path
) -> None:
    """Truncating the data at 2016-03-31 leaves every earlier period unchanged (both modes).

    A strategy that needs 'tomorrow's return' has no input to build it from: the runner passes
    ``features_daily`` rows (past-looking by construction) dated on or before the decision day.
    """
    strategy = S01WeeklyReversal({"n": 2}, ("short",))
    cut = date(2016, 3, 31)
    with MarketStore(store_file, "synthetic", read_only=True) as market:
        short = load_inputs(market, cfg, "synthetic", end=cut)
        full = load_inputs(market, cfg, "synthetic")
    assert full.end > cut >= short.end
    with LabStore(tmp_path / "lab.duckdb") as lab:
        register(lab, strategy, "short", full.feature_version, T_REG)
        a = run_trial(short, lab, cfg, strategy, "short")
        b = run_trial(full, lab, cfg, strategy, "short")
    for mode in ALL_MODES:
        got, longer = a.periods[mode], b.periods[mode]
        assert len(got) > 8
        assert len(longer) > len(got)
        pd.testing.assert_frame_equal(got, longer.iloc[: len(got)].reset_index(drop=True))


# ------------------------------------------------------------------ AC 2: registered first


def test_unregistered_trial_is_refused_and_register_flag_registers_first(
    home: Path, cfg: AppConfig
) -> None:
    paths = get_paths(home)
    only = small(cfg, **{S17: {"horizons": ["short"], "params": [{}]}})
    with pytest.raises(UnregisteredTrialError, match="not registered"):
        run_backtest(only, paths, source="synthetic")
    with LabStore(paths.lab_db, read_only=True) as lab:
        assert lab.count() == 0
        assert lab.oos_returns().empty  # nothing ran
    result = run_backtest(only, paths, source="synthetic", register=True)
    assert len(result.registered_now) == 1
    assert result.rows_written > 0
    again = run_backtest(only, paths, source="synthetic")  # now it is registered
    assert again.registered_now == ()


# ------------------------------------------------------------------ AC 3: hand-computed S17


def test_trials_come_from_the_registry_and_unrunnable_ones_are_reported(
    home: Path, cfg: AppConfig
) -> None:
    paths = get_paths(home)
    both = small(cfg, **{S17: {"horizons": ["short", "medium"], "params": [{}]}})
    run_backtest(both, paths, source="synthetic", register=True)
    short_only = small(cfg, **{S17: {"horizons": ["short"], "params": [{}]}})
    with MarketStore(paths.synthetic_market_db, "synthetic", read_only=True) as market:
        version = store_feature_version(market)
    strategy = S17EqualWeight({}, ("long",))
    stale = make_trial_spec(strategy, "long", version, ENGINE_VERSION, "0" * 64)
    gone = TrialSpec("u" * 16, "S99_gone", "{}", "long", "0" * 64, version, ENGINE_VERSION)
    with LabStore(paths.lab_db) as lab:
        lab.register(stale, "test")  # a code hash that is not the current module's
        lab.register(gone, "test")
    result = run_backtest(short_only, paths, source="synthetic")
    with LabStore(paths.lab_db, read_only=True) as lab:
        horizons = set(lab.oos_returns()["horizon"])
    assert horizons == {"short", "medium"}  # medium left the config but still runs
    assert len(result.trials) == 2
    reasons = {n.trial_id: n.reason for n in result.not_runnable}
    assert "hash mismatch" in reasons[stale.trial_id]
    assert "unknown strategy id" in reasons["u" * 16]
    assert len(reasons) == 2  # nothing skipped silently

    piped = run_pipeline(home, "backtest_all", {"source": "synthetic", "register": True})
    piped.raise_for_failure()
    task = piped.state["backtest"]
    assert set(reasons) <= {n.trial_id for n in task.not_runnable}
    run = RunStore(home).get(piped.run_id)
    assert run is not None
    summary = next(t for t in run["tasks"] if t["id"] == "backtest")["summary"]
    assert summary["not_runnable_count"] == 2
    assert {n["trial_id"] for n in summary["not_runnable"]} == set(reasons)


def test_summary_shows_only_trials_of_the_current_engine_version(
    home: Path, cfg: AppConfig
) -> None:
    paths = get_paths(home)
    only = small(cfg, **{S17: {"horizons": ["short"], "params": [{}]}})
    run_backtest(only, paths, source="synthetic", register=True)
    with MarketStore(paths.synthetic_market_db, "synthetic", read_only=True) as market:
        version = store_feature_version(market)
    old = make_trial_spec(S17EqualWeight({}, ("short",)), "short", version, "engine-old")
    rows = pd.DataFrame({"period_end": [date(2016, 1, 8)], "ret": [0.01], "turnover": [0.1]})
    with LabStore(paths.lab_db) as lab:
        lab.register(old, "test")
        lab.replace_oos(
            old.trial_id,
            "ideal",
            "synthetic",
            rows,
            horizon="short",
            feature_version=version,
            engine_version="engine-old",
            registered_date=date(2016, 1, 1),
        )
    current = load_summary(paths, "synthetic")
    assert len(current) > 0
    assert old.trial_id not in set(current["trial_id"])
    assert old.trial_id in set(load_summary(paths, "synthetic", all_versions=True)["trial_id"])


def frictionless(cfg: AppConfig) -> AppConfig:
    free = Costs(
        brokerage_fee_pct=0.0, sales_tax_pct=0.0, slippage_pct=Slippage(round_lot=0.0, odd_lot=0.0)
    )
    return cfg.model_copy(update={"costs": free})


def hand_equal_weight(prices: pd.DataFrame, decisions: list[date]) -> list[float]:
    """Fractional equal-weight book, no costs: sized on the decision-day close (equity / N / close)
    and traded at the next open (engine.md section 4); returns close-to-close per period."""
    opens = prices.pivot(index="date", columns="ticker", values="open")
    closes = prices.pivot(index="date", columns="ticker", values="close")
    days = list(closes.index)
    shares = pd.Series(0.0, index=closes.columns)
    cash, equity_at = 1e12, {}  # the ideal capital: cash never binds
    pending = pd.Series(0.0, index=closes.columns)
    for day in days:
        cash -= float((pending * opens.loc[day]).sum())  # yesterday's decision fills at this open
        shares = shares + pending
        pending = pending * 0.0
        equity_at[day] = cash + float((shares * closes.loc[day]).sum())
        if day in decisions:
            pending = equity_at[day] / len(shares) / closes.loc[day] - shares
    ends = [d for d in days if d in decisions]
    return [equity_at[b] / equity_at[a] - 1.0 for a, b in itertools.pairwise(ends)]


def test_s17_ideal_equals_hand_computed_equal_weight_and_executable_costs_more(
    tmp_path: Path, cfg: AppConfig
) -> None:
    days = make_days(40)
    inputs = hand_inputs(days, days[0], days[-1])
    strategy = S17EqualWeight({}, ("short",))
    with LabStore(tmp_path / "lab.duckdb") as lab:
        register(lab, strategy, "short", "fv-test", T_REG)
        free = run_trial(inputs, lab, frictionless(cfg), strategy, "short")
        costly = run_trial(inputs, lab, cfg, strategy, "short")
    decisions = [d for d in days if d.weekday() == 4 and d != days[-1]]  # Fridays that are decided
    assert len(decisions) >= 5
    expected = hand_equal_weight(inputs.frame.prices, decisions)
    ideal = free.periods["ideal"]
    assert list(ideal["period_end"]) == decisions[1:]
    assert len(ideal) == len(expected)
    np.testing.assert_allclose(ideal["ret"].to_numpy(), expected, rtol=0, atol=1e-9)
    # executable (lots, 11M book, costs, risk layer) earns less than the frictionless ideal
    growth = lambda r: float(np.prod(1.0 + r))  # noqa: E731
    assert growth(costly.periods["executable"]["ret"]) < growth(ideal["ret"])
    assert growth(costly.periods["ideal"]["ret"]) < growth(ideal["ret"])  # default costs on too


# ------------------------------------------------------------------ AC 4: idempotent, in-sample tag


def test_rerun_is_idempotent_and_rows_are_tagged_around_registered_at(
    home: Path, cfg: AppConfig
) -> None:
    paths = get_paths(home)
    only = small(cfg, **{S17: {"horizons": ["short"], "params": [{}]}})
    with MarketStore(paths.synthetic_market_db, "synthetic", read_only=True) as market:
        version = store_feature_version(market)
    registered_at = datetime(2016, 3, 15, 20, 0, tzinfo=UTC)  # 2016-03-16 03:00 in Vietnam
    boundary = registered_at.astimezone(VN_TZ).date()
    with LabStore(paths.lab_db) as lab:
        register(lab, S17EqualWeight({}, ("short",)), "short", version, registered_at)
    run_backtest(only, paths, source="synthetic", run_id="r1", now=datetime(2026, 1, 1, tzinfo=UTC))
    with LabStore(paths.lab_db, read_only=True) as lab:
        first = lab.oos_returns()
    run_backtest(only, paths, source="synthetic", run_id="r2", now=datetime(2026, 2, 1, tzinfo=UTC))
    with LabStore(paths.lab_db, read_only=True) as lab:
        second = lab.oos_returns()
    key = ["trial_id", "mode", "period_end", "source", "ret", "turnover", "in_sample_by_design"]
    pd.testing.assert_frame_equal(first[key], second[key])
    assert len(second) == len(first) > 0
    assert set(second["run_id"]) == {"r2"}  # replaced, not appended
    assert set(second["mode"]) == set(ALL_MODES)
    assert set(second["source"]) == {"synthetic"}
    ends = pd.to_datetime(second["period_end"]).dt.date
    assert (second["in_sample_by_design"] == (ends <= boundary)).all()
    assert second["in_sample_by_design"].nunique() == 2  # both segments occur
    summary = load_summary(paths, "synthetic")
    assert set(summary["segment"]) == {"historical", "forward"}
    assert (summary["periods"] > 0).all()


def test_period_stats_use_the_horizon_periods_per_year() -> None:
    monthly = pd.Series([0.01] * 12)
    stats = period_stats(monthly, pd.Series([0.2] * 12), "medium")
    assert PERIODS_PER_YEAR == {"short": 52, "medium": 12, "long": 12}
    assert stats["cagr"] == pytest.approx(1.01**12 - 1)
    weekly = period_stats(pd.Series([0.01, -0.01] * 26), pd.Series([0.0] * 52), "short")
    assert weekly["vol"] == pytest.approx(0.01 * np.sqrt(52) * np.sqrt(52 / 51), rel=1e-9)
    assert period_stats(pd.Series(dtype=float), pd.Series(dtype=float), "short")["periods"] == 0


def test_fit_cutoff_hook_purges_label_length_and_embargo() -> None:
    sessions = make_days(20)
    day = sessions[10]
    assert fit_cutoff(sessions, day, 0) == day
    assert fit_cutoff(sessions, day, 5) == sessions[5]
    assert fit_cutoff(sessions, day, 5, 2) == sessions[3]
    assert fit_cutoff(sessions, day, 15) is None
    with pytest.raises(ValueError, match="must be >= 0"):
        fit_cutoff(sessions, day, -1)


# ------------------------------------------------------------------ AC 5: CLI, pipeline, endpoint


@pytest.fixture
def backtested(home: Path) -> Callable[..., Any]:
    def go(*args: str) -> Any:
        return runner.invoke(app, ["backtest", "--source", "synthetic", *args])

    return go


def test_backtest_all_synthetic_runs_every_packaged_trial(
    home: Path, backtested: Callable[..., Any]
) -> None:
    expected = sum(len(s.horizons) for s in demo_module.load_strategies(demo_config()))
    refused = backtested("--all")
    assert refused.exit_code == 1
    assert "not registered" in refused.output

    result = backtested("--all", "--register")
    assert result.exit_code == 0, result.output
    out = result.output
    assert out.count("\n") > expected * 2
    assert "SYNTHETIC DATA" in out
    assert f"registered {expected} new trial(s) first" in out
    assert f"trials run {expected}" in out
    for strategy in ("S00_composite", S17, "S08_momentum", "S18_hrp"):
        assert strategy in out
    paths = get_paths(home)
    with LabStore(paths.lab_db, read_only=True) as lab:
        stored = lab.oos_returns()
    assert stored["trial_id"].nunique() == expected
    assert set(stored["mode"]) == set(ALL_MODES)

    one = backtested("--strategy", S17, "--mode", "ideal")
    assert one.exit_code == 0, one.output
    assert "executable" not in one.output.split("\n", 1)[1]
    assert "registered" not in one.output.split("trials run")[0]  # nothing registered this time


def test_backtest_needs_one_selector_and_a_known_strategy(
    home: Path, backtested: Callable[..., Any]
) -> None:
    assert backtested().exit_code != 0
    assert backtested("--all", "--strategy", S17).exit_code != 0
    unknown = backtested("--strategy", "S99_nothing")
    assert unknown.exit_code == 1
    assert "no registered trial" in unknown.output


def test_backtest_all_pipeline_and_summary_endpoint(home: Path) -> None:
    result = run_pipeline(
        home, "backtest_all", {"source": "synthetic", "strategy": S17, "register": True}
    )
    result.raise_for_failure()
    assert result.status == "success"
    assert [t for t in result.errors] == []
    summary = result.state["backtest_summary"]
    assert set(summary["strategy_id"]) == {S17}
    assert set(summary["horizon"]) == {"short", "medium", "long"}

    client = TestClient(create_app(home), base_url="http://127.0.0.1:8000")
    listing = client.get("/api/pipelines").json()["pipelines"]
    tasks = next(p for p in listing if p["id"] == "backtest_all")["tasks"]
    assert [t["id"] for t in tasks] == ["features", "backtest", "lab_stats", "report"]
    body = client.get("/api/backtest/summary", params={"source": "synthetic"}).json()
    assert body["synthetic"] is True
    assert "SYNTHETIC" in body["label"]
    assert len(body["rows"]) == len(summary)
    assert {"trial_id", "mode", "segment", "periods", "cagr", "sharpe"} <= set(body["columns"])
    assert {r["segment"] for r in body["rows"]} == {"historical", "forward"}
    empty = client.get("/api/backtest/summary", params={"source": "yahoo"}).json()
    assert empty["rows"] == []
    assert "Yahoo" in empty["label"]


def test_missing_store_or_features_stop_with_a_clear_message(
    tmp_path: Path, cfg: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "empty"))
    with pytest.raises(WalkForwardError, match="no store"):
        run_backtest(load_config(tmp_path), get_paths(), source="synthetic", register=True)
