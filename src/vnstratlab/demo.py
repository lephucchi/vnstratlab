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
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from vnstratlab.calendar import TradingCalendar, decision_days
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.pipeline import ingest, load_execution_frame, rebuild
from vnstratlab.data.protocol import TickTable, universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource
from vnstratlab.data.store import MarketStore
from vnstratlab.engine import ENGINE_VERSION, make_params, run_simulation
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
WARNING_LINE = "SYNTHETIC DATA — results say nothing about the real market."
BENCHMARK_ID = "S17_equal_weight"
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

    @property
    def label(self) -> str:
        text = self.strategy_id if not self.params else f"{self.strategy_id} {self.params}"
        return f"{text} (benchmark)" if self.benchmark else text


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


def _prepare_store(cfg: AppConfig, home: Path, end: date) -> date:
    """Ingest, rebuild and build features in ``home``; returns the first ingested session."""
    paths = get_paths(home)
    data_start = cfg.data.synthetic.start
    report = ingest(cfg, paths, SyntheticSource(cfg), data_start, end)
    if report.status not in ("ok", "ok_with_warnings"):
        raise DemoError(f"ingest finished with status {report.status}: {report.failed}")
    with MarketStore(paths.market_db_for("synthetic"), "synthetic") as store:
        rebuild(store, SOURCE, TickTable.from_config(cfg))
        build_features(store, SOURCE, universe_tickers(cfg))
    return data_start


def _targets(
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
    """Target weights on each decision day, from the feature rows dated on or before it."""
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


@contextmanager
def _quiet_logs() -> Iterator[None]:
    """Hold back vnstratlab's warnings (one circuit-breaker line per blocked decision) so the
    table is readable; errors still show."""
    logger = logging.getLogger("vnstratlab")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous)


def run_demo(
    out_dir: Path | None = None,
    start: date = DEMO_START,
    end: date = DEMO_END,
    *,
    progress: Callable[[str], None] | None = None,
) -> DemoReport:
    """Run the demo on ``[start, end]`` and return one row per enabled packaged trial.

    With ``out_dir`` also write ``summary.csv`` and ``equity/<trial_id>.csv`` there (the directory
    must not exist or be empty; it is checked before anything runs). Raises ``DemoError`` (or the
    underlying error) when a stage fails; nothing is swallowed.
    """
    if end < start:
        raise DemoError(f"window end {end} is before start {start}")
    if out_dir is not None:
        check_out_dir(out_dir)
    with _quiet_logs():
        return _run(out_dir, start, end, progress)


def _run(
    out_dir: Path | None, start: date, end: date, progress: Callable[[str], None] | None
) -> DemoReport:
    note = progress or (lambda _msg: None)
    started = time.perf_counter()
    cfg = demo_config()
    strategies = load_strategies(cfg)
    tickers = universe_tickers(cfg)
    with tempfile.TemporaryDirectory(prefix="vnstratlab-demo-") as tmp:
        home = Path(tmp)
        note("ingest, rebuild and features on the synthetic market")
        data_start = _prepare_store(cfg, home, end)
        paths = get_paths(home)
        with MarketStore(paths.market_db_for("synthetic"), "synthetic", read_only=True) as store:
            features = load_features(store, data_start, end)
            frame = load_execution_frame(store, tickers, start, end, SOURCE)
    if features.empty:
        raise DemoError("no features were built: nothing to simulate")
    features = features.sort_values("date", kind="stable").reset_index(drop=True)
    feature_dates = pd.to_datetime(features["date"]).to_numpy(dtype="datetime64[ns]")
    session_dates = np.unique(feature_dates)
    feature_version = str(features["feature_version"].iloc[0])
    calendar = TradingCalendar.from_config(cfg)
    sessions = {pd.Timestamp(d).date() for d in frame.prices["date"]}
    risk = RiskLayer(cfg.risk)
    rows: list[DemoRow] = []
    for strategy in strategies:
        for horizon in strategy.horizons:
            note(f"{strategy.id} {horizon}")
            targets = _targets(
                strategy,
                horizon,
                features,
                feature_dates,
                session_dates,
                calendar,
                sessions,
                start,
                end,
            )
            capital = float(getattr(cfg.books, horizon).capital_vnd)
            params = make_params(cfg, "executable", capital, lots=True, odd_lots=True)
            result = run_simulation(
                frame.prices,
                frame.actions,
                targets,
                calendar,
                params,
                risk=risk,
                cooldown_sessions=COOLDOWN_SESSIONS[horizon],
            )
            spec = make_trial_spec(strategy, horizon, feature_version, ENGINE_VERSION)
            rows.append(
                DemoRow(
                    trial_id=spec.trial_id,
                    strategy_id=strategy.id,
                    params=_short_params(strategy.params),
                    horizon=horizon,
                    benchmark=strategy.id == BENCHMARK_ID,
                    cagr=cagr(result.returns),
                    vol=ann_vol(result.returns),
                    sharpe=sharpe(result.returns),
                    max_dd=max_drawdown(result.returns),
                    turnover=avg_turnover(result.turnover),
                    trades=len(result.trades),
                    digest=result.digest(),
                    equity=result.equity[["date", "equity"]].reset_index(drop=True),
                )
            )
    rows.sort(key=lambda r: (_HORIZON_ORDER[r.horizon], r.label, r.trial_id))
    report = DemoReport(
        rows=tuple(rows),
        skipped=_skipped(cfg),
        start=start,
        end=end,
        data_start=data_start,
        seconds=time.perf_counter() - started,
        out_dir=out_dir,
    )
    if out_dir is not None:
        write_outputs(report, out_dir)
    return report


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
    lines.append(f"trials run {len(report.rows)}, skipped {len(report.skipped)}")
    lines.append(f"run time {report.seconds:.1f} s")
    lines.append("no trials were registered (synthetic runs are not lab evidence)")
    if report.out_dir is not None:
        lines.append(f"files written to {report.out_dir}")
    return "\n".join(lines)
