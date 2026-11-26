"""DSR, PBO and trial_stats (P1-T21). Synthetic data only, no network."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from vnstratlab.app.server import create_app
from vnstratlab.cli import app
from vnstratlab.config.loader import load_config
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.lab.stats import (
    add_gate_columns,
    deflated_sharpe,
    pbo_cscv,
    sharpe,
    skew_kurt,
    trial_stats,
)
from vnstratlab.lab.store import LabStore
from vnstratlab.strategies.registry import TrialSpec

runner = CliRunner()
ND = NormalDist()
EULER = 0.5772156649015329
FEATURES = "feat-aaaa"
BASE = "http://127.0.0.1:8000"


def hand_dsr(sr: float, t: int, g3: float, g4: float, n: int, v: float) -> tuple[float, float]:
    """An independent implementation (statistics.NormalDist, no scipy)."""
    sr0 = 0.0
    if n > 1 and v > 0:
        sr0 = math.sqrt(v) * (
            (1 - EULER) * ND.inv_cdf(1 - 1 / n) + EULER * ND.inv_cdf(1 - 1 / (n * math.e))
        )
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr * sr)
    return sr0, ND.cdf(z)


# ------------------------------------------------------------------ pure functions


def test_sharpe_and_moments_conventions() -> None:
    assert sharpe([1.0, 2.0, 3.0]) == pytest.approx(2.0)  # mean 2, std (ddof 1) 1
    assert math.isnan(sharpe([0.01, 0.01, 0.01]))  # zero std
    assert math.isnan(sharpe([0.5]))
    assert math.isnan(sharpe([]))
    rng = np.random.default_rng(1)
    skew, kurt = skew_kurt(rng.normal(size=200_000))
    assert abs(skew) < 0.05
    assert kurt == pytest.approx(3.0, abs=0.1)  # non-excess: a normal is 3, not 0
    assert all(math.isnan(v) for v in skew_kurt([0.1, 0.1, 0.1, 0.1]))


def test_dsr_matches_the_hand_computed_value() -> None:
    # The paper's worked example (annualised SR 2.5, V 0.5, N 100, T 1250 daily, skew -3,
    # kurtosis 10), converted to per-period units.
    sr, v = 2.5 / math.sqrt(250), 0.5 / 250
    got = deflated_sharpe(sr, 1250, -3.0, 10.0, 100, v)
    assert got.reason is None
    assert got.sr0 == pytest.approx(0.11317200186513214, abs=1e-9)
    assert got.dsr == pytest.approx(0.9003968344493904, abs=1e-9)
    assert (got.sr0, got.dsr) == pytest.approx(hand_dsr(sr, 1250, -3.0, 10.0, 100, v), abs=1e-9)
    # another point, N = 10
    other = deflated_sharpe(0.2, 60, -0.5, 4.0, 10, 0.01)
    assert other.sr0 == pytest.approx(0.157459830134575, abs=1e-9)
    assert other.dsr == pytest.approx(0.6207257256529409, abs=1e-9)


def test_dsr_with_one_trial_is_the_psr_and_normal_kurtosis_is_not_excess() -> None:
    sr, t, g3, g4 = 0.2, 60, -0.5, 4.0
    psr = ND.cdf((sr - 0.0) * math.sqrt(t - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    one = deflated_sharpe(sr, t, g3, g4, 1, 0.01)
    assert one.sr0 == 0.0
    assert one.dsr == pytest.approx(psr, abs=1e-9)
    assert deflated_sharpe(sr, t, g3, g4, 25, 0.0).dsr == pytest.approx(psr, abs=1e-9)  # V = 0
    # gamma4 = 3 (normal) gives the iid-normal Sharpe variance 1 + SR^2/2
    normal = deflated_sharpe(sr, t, 0.0, 3.0, 1, 0.0).dsr
    assert normal == pytest.approx(ND.cdf(sr * math.sqrt(t - 1) / math.sqrt(1 + sr**2 / 2)))


def test_dsr_nan_with_a_reason() -> None:
    bad = deflated_sharpe(2.0, 50, 5.0, 1.0, 5, 0.01)  # 1 - 10 + 0 < 0
    assert math.isnan(bad.dsr)
    assert bad.reason is not None
    assert "non-positive" in bad.reason
    short = deflated_sharpe(0.1, 1, 0.0, 3.0, 5, 0.01)
    assert math.isnan(short.dsr)
    assert short.reason is not None
    nan_in = deflated_sharpe(math.nan, 50, 0.0, 3.0, 5, 0.01)
    assert math.isnan(nan_in.dsr)
    assert nan_in.reason is not None


def _zero_edge_pass_rate(seeds: int, *, t: int = 120, strategies: int = 50) -> float:
    """Share of seeds where the best of ``strategies`` zero-edge strategies has DSR < 0.95."""
    below = 0
    for seed in range(seeds):
        x = np.random.default_rng(seed).normal(0.0, 0.02, size=(t, strategies))
        srs = np.array([sharpe(x[:, j]) for j in range(strategies)])
        best = int(np.argmax(srs))
        skew, kurt = skew_kurt(x[:, best])
        dsr = deflated_sharpe(srs[best], t, skew, kurt, strategies, float(np.var(srs, ddof=1))).dsr
        below += dsr < 0.95
    return below / seeds


def test_zero_edge_best_is_not_significant_fast() -> None:
    # 20 seeds; looser bound than the plan's 90 % (small-sample noise: one miss in 20 is 5 %)
    assert _zero_edge_pass_rate(20) >= 0.8


@pytest.mark.slow
def test_zero_edge_best_is_not_significant_plan_bound() -> None:
    rate = _zero_edge_pass_rate(200)
    print(f"zero-edge DSR < 0.95 pass rate over 200 seeds: {rate:.3f}")
    assert rate >= 0.90


def test_strong_edge_is_significant() -> None:
    rng = np.random.default_rng(3)
    t, n = 250, 50
    x = rng.normal(0.0, 0.02, size=(t, n))
    x[:, 0] += 0.01  # a true Sharpe of 0.5 per period
    srs = np.array([sharpe(x[:, j]) for j in range(n)])
    skew, kurt = skew_kurt(x[:, 0])
    got = deflated_sharpe(srs[0], t, skew, kurt, n, float(np.var(srs, ddof=1)))
    assert int(np.argmax(srs)) == 0
    assert got.dsr > 0.95


def _pbo_noise(seeds: int, t: int = 256, n: int = 20, s: int = 16) -> list[float]:
    return [
        pbo_cscv(np.random.default_rng(seed).normal(size=(t, n)), s, seed=seed)[0]
        for seed in range(seeds)
    ]


def test_pbo_noise_near_half_and_edge_far_below_fast() -> None:
    values = _pbo_noise(6)
    assert abs(float(np.mean(values)) - 0.5) < 0.2  # looser than the slow bound (6 seeds)
    rng = np.random.default_rng(5)
    edge = rng.normal(size=(256, 20)) * 0.01 + np.linspace(0.0, 0.01, 20)  # persistent ranking
    pbo, lambdas = pbo_cscv(edge, 16)
    assert pbo < 0.1
    assert len(lambdas) == math.comb(16, 8)


@pytest.mark.slow
def test_pbo_noise_tolerance_plan_bound() -> None:
    values = _pbo_noise(100)
    mean, spread = float(np.mean(values)), float(np.std(values))
    print(f"PBO on pure noise over 100 seeds (s=16, N=20, T=256): mean {mean:.3f}, sd {spread:.3f}")
    assert abs(mean - 0.5) < 0.15
    assert all(0.0 <= v <= 1.0 for v in values)


def test_pbo_guards_and_determinism() -> None:
    x = np.random.default_rng(2).normal(size=(64, 6))
    assert math.isnan(pbo_cscv(x[:, :1], 8)[0])  # one trial
    assert math.isnan(pbo_cscv(x, 7)[0])  # odd s
    assert math.isnan(pbo_cscv(x[:10], 16)[0])  # fewer rows than blocks
    sampled = pbo_cscv(x, 16, seed=9, max_combinations=500)
    assert len(sampled[1]) == 500
    assert sampled == pbo_cscv(x, 16, seed=9, max_combinations=500)  # deterministic with the seed
    # a constant (zero-std) column is never the best in-sample
    const = np.column_stack([x[:, :3], np.zeros(64)])
    assert not math.isnan(pbo_cscv(const, 8)[0])


# ------------------------------------------------------------------ trial_stats on a store


def spec(name: str, horizon: str = "short", features: str = FEATURES) -> TrialSpec:
    return TrialSpec(
        trial_id=f"t{name:<15}".replace(" ", "0")[:16],
        strategy_id=f"S_{name}",
        params_json="{}",
        horizon=horizon,  # type: ignore[arg-type]
        strategy_code_hash="0" * 64,
        feature_version=features,
        engine_version=ENGINE_VERSION,
    )


def put(
    lab: LabStore,
    trial: TrialSpec,
    returns: np.ndarray | None,
    *,
    registered: date = date(2030, 1, 1),
    first: date = date(2020, 1, 3),
    mode: str = "executable",
) -> None:
    lab.register(trial, "synthetic test", now=datetime(2030, 1, 1, tzinfo=UTC))
    if returns is None:
        return
    ends = [first + timedelta(days=7 * i) for i in range(len(returns))]
    frame = pd.DataFrame({"period_end": ends, "ret": returns, "turnover": 0.1})
    lab.replace_oos(
        trial.trial_id,
        mode,
        "synthetic",
        frame,
        horizon=trial.horizon,
        feature_version=trial.feature_version,
        engine_version=trial.engine_version,
        registered_date=registered,
    )


@pytest.fixture
def lab(tmp_path: Path) -> LabStore:
    return LabStore(tmp_path / "lab.duckdb")


def test_trial_stats_counts_every_registered_trial_in_n(lab: LabStore) -> None:
    rng = np.random.default_rng(11)
    for name in ("a", "b", "c"):
        put(lab, spec(name), rng.normal(0.001, 0.02, 64))
    put(lab, spec("short"), rng.normal(0.0, 0.02, 3))  # too few periods, still counts
    put(lab, spec("empty"), None)  # registered, no rows at all
    put(lab, spec("other", "medium"), rng.normal(0.0, 0.02, 64))  # another horizon: not in N
    put(lab, spec("stale", features="feat-old0"), rng.normal(0.0, 0.02, 64))  # not current

    got = trial_stats(lab, "synthetic", "short", min_periods=52, seed=7, feature_version=FEATURES)
    hist = got[got["segment"] == "historical"].set_index("trial_id")
    assert len(hist) == 5
    assert set(hist["n_trials"]) == {5}
    assert hist.loc[spec("empty").trial_id, "periods"] == 0
    assert math.isnan(hist.loc[spec("empty").trial_id, "dsr"])
    assert hist.loc[spec("short").trial_id, "periods"] == 3
    finite = [sharpe(lab.oos_returns(spec(n).trial_id)["ret"].to_numpy()) for n in ("a", "b", "c")]
    assert hist["var_sr"].iloc[0] > 0
    assert hist["var_sr"].iloc[0] == pytest.approx(
        np.var([*finite, sharpe(lab.oos_returns(spec("short").trial_id)["ret"].to_numpy())], ddof=1)
    )
    assert not math.isnan(hist.loc[spec("a").trial_id, "dsr"])
    assert hist["pbo"].nunique() == 1  # over the 3 eligible trials, repeated
    assert not math.isnan(hist["pbo"].iloc[0])
    assert (got[got["segment"] == "forward"]["periods"] == 0).all()
    assert got["dsr"][got["segment"] == "forward"].isna().all()


def test_trial_stats_splits_historical_and_forward(lab: LabStore) -> None:
    rng = np.random.default_rng(4)
    ends_registered = date(2020, 1, 3) + timedelta(days=7 * 39)  # first 40 periods historical
    for name in ("a", "b"):
        put(lab, spec(name), rng.normal(0.0, 0.02, 60), registered=ends_registered)
    got = trial_stats(lab, "synthetic", "short", min_periods=10, seed=1)
    for _, group in got.groupby("trial_id"):
        periods = dict(zip(group["segment"], group["periods"], strict=True))
        assert periods == {"historical": 40, "forward": 20}
    forward = got[got["segment"] == "forward"]
    assert forward["sr"].notna().all()
    assert forward["pbo"].isna().all()


def test_gate_columns_use_the_frozen_config(lab: LabStore, tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    rng = np.random.default_rng(8)
    put(lab, spec("a"), rng.normal(0.0, 0.02, 60))
    put(lab, spec("b"), rng.normal(0.0, 0.02, 60))
    frame = trial_stats(lab, "synthetic", "short", min_periods=52, seed=1)
    gated = add_gate_columns(frame, cfg)
    hist = gated[gated["segment"] == "historical"]
    assert hist["periods_ok"].all()  # 60 >= 52 (short)
    fwd = gated[gated["segment"] == "forward"]
    assert fwd[["periods_ok", "dsr_ok", "pbo_ok"]].isna().all().all()
    assert (cfg.lab.gate1.dsr_min, cfg.lab.gate1.pbo_max) == (0.95, 0.5)


# ------------------------------------------------------------------ CLI, pipeline, endpoint


def test_cli_pipeline_and_endpoint_on_a_backtest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_network: None
) -> None:
    import _socket
    import shutil
    import socket
    from typing import Any

    from vnstratlab import demo as demo_module
    from vnstratlab.paths import get_paths
    from vnstratlab.runs import run_pipeline

    refuse = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> None:  # loopback for the TestClient
        if isinstance(address, tuple) and address[0] == "127.0.0.1":
            _socket.socket.connect(self, address)
        else:
            refuse(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    seed_home = tmp_path / "seed"
    st = demo_module.new_state(seed_home, date(2015, 1, 1), date(2016, 6, 30))
    demo_module.stage_ingest(st)
    demo_module.stage_rebuild(st)
    demo_module.stage_features(st)
    home = tmp_path / "stats-home"
    paths = get_paths(home)
    paths.data_dir.mkdir(parents=True)
    shutil.copy(get_paths(seed_home).synthetic_market_db, paths.synthetic_market_db)
    monkeypatch.setenv("APP_HOME", str(home))

    none_yet = runner.invoke(app, ["lab", "stats", "--source", "synthetic"])
    assert none_yet.exit_code == 0
    assert "no lab store" in none_yet.output

    result = run_pipeline(
        home,
        "backtest_all",
        {"source": "synthetic", "strategy": "S17_equal_weight", "register": True},
    )
    result.raise_for_failure()
    stats = result.state["lab_stats"]
    assert set(stats["segment"]) == {"historical", "forward"}

    out = runner.invoke(app, ["lab", "stats", "--source", "synthetic"])
    assert out.exit_code == 0, out.output
    assert "SYNTHETIC DATA" in out.output
    assert "S17" not in out.output  # trial ids, not strategy names, are listed
    assert "gate 1:" in out.output
    assert "pass" in out.output.lower()
    one = runner.invoke(app, ["lab", "stats", "--source", "synthetic", "--horizon", "long"])
    assert one.exit_code == 0
    assert one.output.count("long") >= 1
    assert "short " not in one.output

    client = TestClient(create_app(home), base_url=BASE)
    listing = client.get("/api/pipelines").json()["pipelines"]
    tasks = next(p for p in listing if p["id"] == "backtest_all")["tasks"]
    assert [t["id"] for t in tasks] == ["features", "backtest", "lab_stats", "report"]
    body = client.get("/api/lab/stats", params={"source": "synthetic"}).json()
    assert body["synthetic"] is True
    assert {"dsr", "pbo", "n_trials", "dsr_ok", "pbo_ok", "periods_ok"} <= set(body["columns"])
    assert {r["segment"] for r in body["rows"]} == {"historical", "forward"}
    assert {r["horizon"] for r in body["rows"]} == {"short", "medium", "long"}
    only = client.get("/api/lab/stats", params={"source": "synthetic", "horizon": "short"}).json()
    assert {r["horizon"] for r in only["rows"]} == {"short"}
    assert client.get("/api/lab/stats", params={"horizon": "weekly"}).status_code == 422
    assert client.get("/api/lab/stats", params={"source": "yahoo"}).json()["rows"] == []
