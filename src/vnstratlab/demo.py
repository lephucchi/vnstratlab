"""``vnstratlab demo``: the whole Phase 1 pipeline, offline, on the synthetic market (P1-T32).

Ingest (``SyntheticSource``) -> rebuild -> features -> every enabled packaged trial -> simulator
in executable mode with the risk layer -> a summary. Everything happens in a fresh temporary app
home that is removed at the end, so the user's app home, market stores, trial registry and
terms file are never read or written. The config is the packaged defaults (no user config) with
``data.source = synthetic`` set in memory. No trial is registered: synthetic runs are not lab
evidence.

Constants (demo-only choices, not config defaults):

- ``DEMO_START`` / ``DEMO_END``: the simulated window, independent of today's date. Synthetic data
  is ingested from ``data.synthetic.start`` so the 250-session features are warm by ``DEMO_START``.
- ``COOLDOWN_SESSIONS``: the stop cooldown, one decision period of the book's horizon in sessions
  (5 for short, 21 for medium and long), because ``risk.stop_cooldown_sessions`` is null.
"""

from __future__ import annotations

import logging
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from vnstratlab.calendar import TradingCalendar, decision_days
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.pipeline import ExecutionFrame, ingest, load_execution_frame, rebuild
from vnstratlab.data.protocol import TickTable, universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource
from vnstratlab.data.store import MarketStore
from vnstratlab.engine import ENGINE_VERSION, SimResult, make_params, run_simulation
from vnstratlab.engine.loop import build_bars
from vnstratlab.features.build import build_features, load_features
from vnstratlab.lab.metrics import ann_vol, avg_turnover, cagr, max_drawdown, sharpe
from vnstratlab.paths import get_paths
from vnstratlab.risk import RiskLayer
from vnstratlab.strategies.base import Horizon, Strategy
from vnstratlab.strategies.registry import load_strategies, make_trial_spec

DEMO_START = date(2016, 1, 1)
DEMO_END = date(2020, 12, 31)
COOLDOWN_SESSIONS: dict[str, int] = {"short": 5, "medium": 21, "long": 21}
SOURCE = "synthetic"
WARNING_LINE = "SYNTHETIC DATA - results say nothing about the real market."
BENCHMARK_ID = "S17_equal_weight"
BENCHMARK_NOTE = "benchmark, no risk layer"
SUMMARY_COLUMNS = (
    "trial_id",
    "trial",
    "horizon",
    "CAGR",
    "vol",
    "Sharpe",
    "maxDD",
    "turnover",
    "trades",
)
_HORIZON_ORDER = {"short": 0, "medium": 1, "long": 2}


class DemoError(RuntimeError):
    """A demo stage failed or the request was refused; the message says what to do."""


@dataclass(frozen=True)
class DemoRow:
    """One trial's result. ``digest`` is ``SimResult.digest()``; ``equity`` has date, equity."""

    trial_id: str
    strategy_id: str
    params: str
    horizon: str
    benchmark: bool
    cagr: float
    vol: float
    sharpe: float
    max_dd: float
    turnover: float
    trades: int
    digest: str
    equity: pd.DataFrame
    is_trial: bool = True  # False for the benchmark row: not registered, not counted

    @property
    def label(self) -> str:
        text = self.strategy_id if not self.params else f"{self.strategy_id} {self.params}"
        return f"{text} ({BENCHMARK_NOTE})" if self.benchmark else text


@dataclass(frozen=True)
class DemoReport:
    rows: tuple[DemoRow, ...]
    skipped: tuple[tuple[str, str], ...]  # (strategy id, reason)
    start: date
    end: date
    data_start: date
    seconds: float
    out_dir: Path | None

    def summary_frame(self) -> pd.DataFrame:
        data = [
            (
                r.trial_id,
                r.label,
                r.horizon,
                r.cagr,
                r.vol,
                r.sharpe,
                r.max_dd,
                r.turnover,
                r.trades,
            )
            for r in self.rows
        ]
        return pd.DataFrame(data, columns=list(SUMMARY_COLUMNS))


def _short_params(params: Mapping[str, Any]) -> str:
    return " ".join(f"{k}={params[k]}" for k in sorted(params))


def _skipped(cfg: AppConfig) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for strategy_id, entry in cfg.strategies.items():
        if isinstance(entry, Mapping) and entry.get("enabled", True) is False:
            out.append((str(strategy_id), str(entry.get("reason", "no reason given"))))
    return tuple(out)


def check_out_dir(out_dir: Path) -> None:
    """``out_dir`` must not exist or be an empty directory; anything else is refused."""
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise DemoError(f"--out {out_dir} exists and is not an empty directory: refusing to write")


def demo_config() -> AppConfig:
    """Packaged defaults only (an empty home: no user config) with the synthetic source."""
    with tempfile.TemporaryDirectory(prefix="vnstratlab-demo-cfg-") as empty_home:
        cfg = load_config(Path(empty_home))
    return cfg.model_copy(update={"data": cfg.data.model_copy(update={"source": SOURCE})})


def decision_targets(
    strategy: Strategy,
    horizon: Horizon,
    features: pd.DataFrame,
    feature_dates: np.ndarray,
    session_dates: np.ndarray,
    calendar: TradingCalendar,
    sessions: set[date],
    start: date,
    end: date,
) -> dict[date, pd.Series]:
    """Target weights on each decision day, from the feature rows dated on or before it.

    Shared with the walk-forward runner (``vnstratlab.lab.walkforward``): the strategy gets the
    last ``lookback_sessions`` sessions up to and including the decision day, never a later row.
    """
    lookback = max(1, int(getattr(strategy, "lookback_sessions", 1)))
    targets: dict[date, pd.Series] = {}
    for day in decision_days(calendar, horizon, start, end):
        if day not in sessions:
            continue
        stop = np.datetime64(day)
        hi = int(np.searchsorted(feature_dates, stop, side="right"))
        # the strategy's declared history (BaseStrategy.lookback_sessions): its last sessions
        # up to and including the decision day, never a row after it
        i = max(0, int(np.searchsorted(session_dates, stop, side="right")) - lookback)
        lo = int(np.searchsorted(feature_dates, session_dates[i], side="left"))
        targets[day] = strategy.target_weights(features.iloc[lo:hi], pd.Timestamp(day))
    return targets


@dataclass
class DemoState:
    """Mutable state passed from one demo stage to the next (the stages are the runner's tasks)."""

    start: date
    end: date
    home: Path  # temporary app home holding the synthetic store (never the user's home)
    cfg: AppConfig
    out_dir: Path | None = None  # an extra copy destination (``vnstratlab demo --out``)
    artifact_dir: Path | None = None  # where the report stage writes summary.csv and equity/
    started: float = field(default_factory=time.perf_counter)
    data_start: date | None = None
    prepared: _Prepared | None = None
    plans: list[tuple[Strategy, Horizon, dict[date, pd.Series]]] = field(default_factory=list)
    rows: list[DemoRow] = field(default_factory=list)
    report: DemoReport | None = None


@dataclass(frozen=True)
class _Prepared:
    frame: ExecutionFrame
    calendar: TradingCalendar
    feature_version: str


def new_state(
    home: Path,
    start: date = DEMO_START,
    end: date = DEMO_END,
    *,
    out_dir: Path | None = None,
    artifact_dir: Path | None = None,
) -> DemoState:
    """A fresh state; the config is the packaged defaults with the synthetic source."""
    if end < start:
        raise DemoError(f"window end {end} is before start {start}")
    return DemoState(start, end, home, demo_config(), out_dir=out_dir, artifact_dir=artifact_dir)


def stage_ingest(st: DemoState) -> dict[str, Any]:
    """Ingest the synthetic market into the temporary home."""
    st.data_start = st.cfg.data.synthetic.start
    report = ingest(st.cfg, get_paths(st.home), SyntheticSource(st.cfg), st.data_start, st.end)
    if report.status not in ("ok", "ok_with_warnings"):
        raise DemoError(f"ingest finished with status {report.status}: {report.failed}")
    return {"rows_in": report.rows_in, "rows_written": report.rows_written, "status": report.status}


def stage_rebuild(st: DemoState) -> dict[str, Any]:
    with MarketStore(get_paths(st.home).market_db_for("synthetic"), "synthetic") as store:
        rep = rebuild(store, SOURCE, TickTable.from_config(st.cfg))
    return {"price_rows": rep.price_rows, "adjusted_rows": rep.adjusted_rows}


def stage_features(st: DemoState) -> dict[str, Any]:
    with MarketStore(get_paths(st.home).market_db_for("synthetic"), "synthetic") as store:
        rep = build_features(store, SOURCE, universe_tickers(st.cfg))
    return {"rows": rep.rows, "feature_version": rep.feature_version}


def stage_strategies(st: DemoState) -> dict[str, Any]:
    """Load the features and compute every enabled trial's target weights (no simulation yet)."""
    if st.data_start is None:
        raise DemoError("the ingest stage has not run")
    log = logging.getLogger("vnstratlab.demo")
    cfg = st.cfg
    strategies = load_strategies(cfg)
    paths = get_paths(st.home)
    with MarketStore(paths.market_db_for("synthetic"), "synthetic", read_only=True) as store:
        features = load_features(store, st.data_start, st.end)
        frame = load_execution_frame(store, universe_tickers(cfg), st.start, st.end, SOURCE)
    if features.empty:
        raise DemoError("no features were built: nothing to simulate")
    features = features.sort_values("date", kind="stable").reset_index(drop=True)
    feature_dates = pd.to_datetime(features["date"]).to_numpy(dtype="datetime64[ns]")
    session_dates = np.unique(feature_dates)
    calendar = TradingCalendar.from_config(cfg)
    sessions = {pd.Timestamp(d).date() for d in frame.prices["date"]}
    version = str(features["feature_version"].iloc[0])
    st.prepared = _Prepared(frame, calendar, version)
    st.plans = []
    for strategy in strategies:
        for horizon in strategy.horizons:
            log.info("targets %s %s", strategy.id, horizon)
            targets = decision_targets(
                strategy,
                horizon,
                features,
                feature_dates,
                session_dates,
                calendar,
                sessions,
                st.start,
                st.end,
            )
            st.plans.append((strategy, horizon, targets))
    return {"trials": len(st.plans)}


def _row(
    trial_id: str, strategy: Any, horizon: str, result: SimResult, *, benchmark: bool = False
) -> DemoRow:
    return DemoRow(
        trial_id=trial_id,
        strategy_id=strategy.id,
        params=_short_params(strategy.params),
        horizon=horizon,
        benchmark=benchmark,
        cagr=cagr(result.returns),
        vol=ann_vol(result.returns),
        sharpe=sharpe(result.returns),
        max_dd=max_drawdown(result.returns),
        turnover=avg_turnover(result.turnover),
        trades=len(result.trades),
        digest=result.digest(),
        equity=result.equity[["date", "equity"]].reset_index(drop=True),
        is_trial=not benchmark,
    )


def stage_simulate(st: DemoState, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run the simulator (executable mode, risk layer) for each planned trial, plus one
    benchmark row per horizon of S17 without the risk layer (not a trial)."""
    note = progress or (lambda _msg: None)
    prep, cfg = st.prepared, st.cfg
    if prep is None:
        raise DemoError("the strategies stage has not run")
    risk = RiskLayer(cfg.risk)
    st.rows = []
    bars = build_bars(prep.frame.prices)  # same price frame for every trial: build once
    benchmarks: list[DemoRow] = []
    for strategy, horizon, targets in st.plans:
        note(f"{strategy.id} {horizon}")
        capital = float(getattr(cfg.books, horizon).capital_vnd)
        params = make_params(cfg, "executable", capital, lots=True, odd_lots=True)

        run = partial(
            run_simulation,
            prep.frame.prices,
            prep.frame.actions,
            targets,
            prep.calendar,
            params,
            cooldown_sessions=COOLDOWN_SESSIONS[horizon],
            bars=bars,
        )
        spec = make_trial_spec(strategy, horizon, prep.feature_version, ENGINE_VERSION)
        st.rows.append(_row(spec.trial_id, strategy, horizon, run(risk=risk)))
        if strategy.id == BENCHMARK_ID:
            # Equal weight without the risk layer: capital, lots, costs and T+ only. Not a
            # trial: never registered and not in the trial count.
            note(f"{strategy.id} {horizon} (benchmark, no risk layer)")
            bench_id = f"benchmark_{strategy.id}_{horizon}"
            benchmarks.append(_row(bench_id, strategy, horizon, run(risk=None), benchmark=True))
    st.rows.extend(benchmarks)
    return {"trials": len(st.rows) - len(benchmarks), "benchmarks": len(benchmarks)}


def stage_report(st: DemoState) -> dict[str, Any]:
    """Sort the rows, build the report and write the files (artifact dir and ``--out``)."""
    if st.data_start is None:
        raise DemoError("the ingest stage has not run")
    rows = sorted(st.rows, key=lambda r: (_HORIZON_ORDER[r.horizon], r.label, r.trial_id))
    st.report = DemoReport(
        rows=tuple(rows),
        skipped=_skipped(st.cfg),
        start=st.start,
        end=st.end,
        data_start=st.data_start,
        seconds=time.perf_counter() - st.started,
        out_dir=st.out_dir,
    )
    for target in (st.artifact_dir, st.out_dir):
        if target is not None:
            write_outputs(st.report, target)
    trials = sum(r.is_trial for r in rows)
    return {"trials": trials, "skipped": len(st.report.skipped)}


def run_demo(
    out_dir: Path | None = None,
    start: date = DEMO_START,
    end: date = DEMO_END,
    *,
    progress: Callable[[str], None] | None = None,
    record_home: Path | None = None,
) -> DemoReport:
    """Run the demo on ``[start, end]`` and return one row per enabled packaged trial.

    It runs as the ``demo`` pipeline of ``vnstratlab.runs``. With ``record_home`` the run (status,
    logs, files) is recorded under that app home; without it, in a temporary one. With ``out_dir``
    also write ``summary.csv`` and ``equity/<trial_id>.csv`` there (the directory must not exist
    or be empty; it is checked before anything runs). Raises ``DemoError`` (or the underlying
    error) when a stage fails; nothing is swallowed.
    """
    from vnstratlab.runs import run_pipeline

    if end < start:
        raise DemoError(f"window end {end} is before start {start}")
    if out_dir is not None:
        check_out_dir(out_dir)
    params = {"start": start, "end": end, "out_dir": out_dir}
    if record_home is not None:
        result = run_pipeline(record_home, "demo", params, progress=progress)
    else:
        with tempfile.TemporaryDirectory(prefix="vnstratlab-demo-run-") as tmp:
            result = run_pipeline(Path(tmp), "demo", params, progress=progress)
    result.raise_for_failure()
    demo_state = result.state["demo"]
    assert isinstance(demo_state, DemoState)  # noqa: S101
    assert demo_state.report is not None  # noqa: S101
    return demo_state.report


def write_outputs(report: DemoReport, out_dir: Path) -> None:
    """``summary.csv`` (full precision) and ``equity/<trial_id>.csv``; nothing else."""
    check_out_dir(out_dir)
    equity_dir = out_dir / "equity"
    equity_dir.mkdir(parents=True, exist_ok=True)
    report.summary_frame().to_csv(out_dir / "summary.csv", index=False, lineterminator="\n")
    for row in report.rows:
        row.equity.to_csv(equity_dir / f"{row.trial_id}.csv", index=False, lineterminator="\n")


def _pct(value: float) -> str:
    return "n/a" if value != value else f"{value * 100:.1f}%"


def format_report(report: DemoReport, *, quiet: bool = False) -> str:
    """Console text: the synthetic warning first, the table (unless quiet), then the footer."""
    lines = [WARNING_LINE]
    if not quiet:
        header = ("trial", "horizon", "CAGR", "vol", "Sharpe", "maxDD", "turnover", "trades")
        table = [
            (
                r.label,
                r.horizon,
                _pct(r.cagr),
                _pct(r.vol),
                "n/a" if r.sharpe != r.sharpe else f"{r.sharpe:.2f}",
                _pct(r.max_dd),
                f"{r.turnover:.3f}",
                str(r.trades),
            )
            for r in report.rows
        ]
        widths = [max(len(x[i]) for x in [header, *table]) for i in range(len(header))]
        for n, record in enumerate([header, *table]):
            cells = [
                c.ljust(widths[i]) if i < 2 else c.rjust(widths[i]) for i, c in enumerate(record)
            ]
            lines.append("  ".join(cells).rstrip())
            if n == 0:
                lines.append("  ".join("-" * w for w in widths))
    for strategy_id, reason in report.skipped:
        lines.append(f"skipped: {strategy_id}: {reason}")
    lines.append(
        f"data window {report.start} .. {report.end} "
        f"(synthetic data from {report.data_start}, features warm)"
    )
    trials = sum(r.is_trial for r in report.rows)
    lines.append(f"trials run {trials}, skipped {len(report.skipped)}")
    if trials != len(report.rows):
        lines.append(
            f"benchmark rows ({len(report.rows) - trials}): S17 equal weight without the risk "
            "layer; not trials, not registered, not counted"
        )
    lines.append(f"run time {report.seconds:.1f} s")
    lines.append("no trials were registered (synthetic runs are not lab evidence)")
    if report.out_dir is not None:
        lines.append(f"files written to {report.out_dir}")
    return "\n".join(lines)
