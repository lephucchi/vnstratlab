"""Walk-forward runner: out-of-sample return series per registered trial (P1-T20).

For every trial, on every decision day ``d`` of its horizon, the strategy is handed only the
feature rows dated on or before ``d`` (its last ``lookback_sessions`` sessions, the slicing of
``vnstratlab.demo.decision_targets``) and goes through ``BaseStrategy.target_weights`` (the
``asof_guard`` and weight validation). The orders are created at the close of ``d`` and fill at the
next open (engine rule). The return stored for ``period_end = d'`` (the next decision day) is the
compounded return from the close of ``d`` to the close of ``d'``; the sessions before the first
decision day and after the last one belong to no complete period and are dropped.

No lookahead, by construction:

- the strategy input is a slice of ``features_daily``, which holds past-looking features only; a
  "tomorrow's return" signal cannot be built from it, and any row dated after ``d`` is neither
  passed nor accepted (``asof_guard``);
- the simulator sees prices of later sessions but only trades what was decided on earlier days;
- the result for a period never depends on data after its end (tests re-run on a truncated
  window and compare).

A trial runs only if it is in ``trial_registry`` (``ensure_trial``); ``run_backtest`` registers
the config trials first only when asked (``register=True``).

Fitted components (S07, S16; P1-T31) are not implemented here. ``fit_cutoff`` is the documented
hook: a model fitted for decision day ``d`` may use only sessions up to ``fit_cutoff`` (purge =
label length, plus an embargo), so that no training label reaches past ``d``.

Each mode is one simulator run: ``ideal`` (fractional shares, no risk layer) and ``executable``
(the horizon book's capital, lots and odd lots on, ``RiskLayer``, stop cooldown of one decision
period). Constants below are runner choices, not config defaults.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.config.models import AppConfig
from vnstratlab.data.pipeline import VN_TZ, ExecutionFrame, load_execution_frame
from vnstratlab.data.protocol import universe_tickers
from vnstratlab.data.store import MarketStore, kind_of_source
from vnstratlab.demo import COOLDOWN_SESSIONS, decision_targets
from vnstratlab.engine import ENGINE_VERSION, make_params, run_simulation
from vnstratlab.engine.loop import SimResult, period_returns, period_turnover
from vnstratlab.features.build import load_features
from vnstratlab.features.groups import YEAR_WINDOW
from vnstratlab.lab import metrics
from vnstratlab.lab.store import MODES, LabStore
from vnstratlab.lab.trials import TrialRecord, TrialRegistry, ensure_trial, store_feature_version
from vnstratlab.paths import AppPaths
from vnstratlab.risk import RiskLayer
from vnstratlab.strategies.base import Horizon, Strategy
from vnstratlab.strategies.registry import TrialSpec, load_strategies, make_trial_spec

WARMUP_SESSIONS = YEAR_WINDOW  # the longest feature window: the first decision day follows it
PERIODS_PER_YEAR: dict[str, int] = {"short": 52, "medium": 12, "long": 12}
SEGMENTS = ("historical", "forward")
SUMMARY_COLUMNS = (
    "trial_id",
    "strategy_id",
    "params",
    "horizon",
    "mode",
    "segment",
    "periods",
    "cagr",
    "vol",
    "sharpe",
    "max_dd",
    "avg_turnover",
)
SEGMENT_LABELS = {
    "historical": "historical walk-forward (in-sample by design)",
    "forward": "forward (true OOS)",
}
SYNTHETIC_LABEL = "SYNTHETIC DATA: results say nothing about the real market."
YAHOO_LABEL = "interim Yahoo, survivorship-biased (GAP-13)"
_PERIOD_COLUMNS = ("period_end", "ret", "turnover")
_HORIZON_ORDER = {"short": 0, "medium": 1, "long": 2}


class WalkForwardError(RuntimeError):
    """The walk-forward run cannot start (no features, unknown strategy, ...)."""


def data_label(source: str) -> str:
    """The data label printed with every result of ``source``."""
    if source == "synthetic":
        return SYNTHETIC_LABEL
    if source == "yahoo":
        return YAHOO_LABEL
    return f"source {source}"


def fit_cutoff(
    session_dates: Sequence[date],
    decision_day: date,
    label_sessions: int,
    embargo_sessions: int = 0,
) -> date | None:
    """Last session a fitted component may train on for ``decision_day`` (hook for S07/S16).

    A training row dated ``s`` carries a label that looks ``label_sessions`` sessions ahead, so it
    is usable only if that label is fully known on ``decision_day`` (purge); ``embargo_sessions``
    more are skipped. ``None`` when there is no such session. No current strategy is fitted.
    """
    if label_sessions < 0 or embargo_sessions < 0:
        raise ValueError("label_sessions and embargo_sessions must be >= 0")
    ordered = sorted(session_dates)
    known = [i for i, s in enumerate(ordered) if s <= decision_day]
    if not known:
        return None
    idx = known[-1] - label_sessions - embargo_sessions
    return ordered[idx] if idx >= 0 else None


# ------------------------------------------------------------------ inputs


@dataclass(frozen=True)
class WalkForwardInputs:
    """Everything the runner reads: features, execution prices, calendar and the window."""

    features: pd.DataFrame  # sorted by date; includes the warm-up history before ``start``
    frame: ExecutionFrame
    calendar: TradingCalendar
    feature_version: str
    source: str
    start: date
    end: date
    feature_dates: np.ndarray = field(repr=False)
    session_dates: np.ndarray = field(repr=False)
    sessions: frozenset[date] = field(repr=False)


def prepare_inputs(
    features: pd.DataFrame,
    frame: ExecutionFrame,
    calendar: TradingCalendar,
    feature_version: str,
    source: str,
    start: date,
    end: date,
) -> WalkForwardInputs:
    """Sort the features and derive the lookup arrays used for the decision slices."""
    if features.empty:
        raise WalkForwardError("no features: run `vnstratlab features build` first")
    ordered = features.sort_values("date", kind="stable").reset_index(drop=True)
    feature_dates = pd.to_datetime(ordered["date"]).to_numpy(dtype="datetime64[ns]")
    sessions = frozenset(pd.Timestamp(d).date() for d in frame.prices["date"])
    return WalkForwardInputs(
        ordered,
        frame,
        calendar,
        feature_version,
        source,
        start,
        end,
        feature_dates,
        np.unique(feature_dates),
        sessions,
    )


def default_start(store: MarketStore) -> date:
    """The ``WARMUP_SESSIONS``-th feature session (or the first one if there are fewer)."""
    rows = store.connection.execute(
        "SELECT DISTINCT date FROM features_daily ORDER BY date"
    ).fetchall()
    if not rows:
        raise WalkForwardError("features_daily is empty: run `vnstratlab features build`")
    days = [pd.Timestamp(r[0]).date() for r in rows]
    return days[min(WARMUP_SESSIONS, len(days) - 1)]


def load_inputs(
    store: MarketStore,
    cfg: AppConfig,
    source: str,
    start: date | None = None,
    end: date | None = None,
) -> WalkForwardInputs:
    """Read features and execution prices of the configured universe from an open store."""
    version = store_feature_version(store)
    first = start if start is not None else default_start(store)
    last = end
    if last is None:
        row = store.connection.execute("SELECT max(date) FROM features_daily").fetchone()
        if row is None or row[0] is None:
            raise WalkForwardError("features_daily is empty: run `vnstratlab features build`")
        last = pd.Timestamp(row[0]).date()
    features = load_features(store, date(1990, 1, 1), last)
    frame = load_execution_frame(store, universe_tickers(cfg), first, last, source)
    if frame.prices.empty:
        raise WalkForwardError(f"no execution prices in {first} .. {last}: run `data rebuild`")
    calendar = TradingCalendar.from_config(cfg)
    return prepare_inputs(features, frame, calendar, version, source, first, last)


# ------------------------------------------------------------------ one trial


@dataclass(frozen=True)
class TrialRun:
    """One trial's out-of-sample periods per mode (``period_end``, ``ret``, ``turnover``)."""

    spec: TrialSpec
    record: TrialRecord
    periods: dict[str, pd.DataFrame]


def _periods(result: SimResult, days: Sequence[date]) -> pd.DataFrame:
    """Complete periods: close of each decision day to the close of the next one."""
    ends = sorted(days)
    if len(ends) < 2:
        return pd.DataFrame({c: [] for c in _PERIOD_COLUMNS})
    ret = period_returns(result.returns, ends)
    turn = period_turnover(result.turnover, ends)
    # the first element is the stretch before the first decision day: nothing was held
    return pd.DataFrame(
        {
            "period_end": list(ret.index[1:]),
            "ret": ret.to_numpy(dtype=float)[1:],
            "turnover": turn.to_numpy(dtype=float)[1:],
        }
    )


def _simulate(
    inputs: WalkForwardInputs,
    cfg: AppConfig,
    horizon: Horizon,
    mode: str,
    targets: Mapping[date, pd.Series],
) -> SimResult:
    prices, actions = inputs.frame.prices, inputs.frame.actions
    if mode == "ideal":
        return run_simulation(prices, actions, targets, inputs.calendar, make_params(cfg, "ideal"))
    capital = float(getattr(cfg.books, horizon).capital_vnd)
    params = make_params(cfg, "executable", capital, lots=True, odd_lots=True)
    return run_simulation(
        prices,
        actions,
        targets,
        inputs.calendar,
        params,
        risk=RiskLayer(cfg.risk),
        cooldown_sessions=COOLDOWN_SESSIONS[horizon],
    )


def run_trial(
    inputs: WalkForwardInputs,
    registry: TrialRegistry,
    cfg: AppConfig,
    strategy: Strategy,
    horizon: Horizon,
    modes: Sequence[str] = MODES,
) -> TrialRun:
    """Walk one registered trial forward; ``UnregisteredTrialError`` if it is not registered.

    The check happens before any strategy code runs.
    """
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        raise ValueError(f"unknown mode(s) {unknown}; expected {MODES}")
    spec = ensure_trial(registry, strategy, horizon, inputs.feature_version)
    record = registry.require_registered(spec.trial_id)
    targets = decision_targets(
        strategy,
        horizon,
        inputs.features,
        inputs.feature_dates,
        inputs.session_dates,
        inputs.calendar,
        set(inputs.sessions),
        inputs.start,
        inputs.end,
    )
    days = list(targets)
    periods = {
        mode: _periods(_simulate(inputs, cfg, horizon, mode, targets), days) for mode in modes
    }
    return TrialRun(spec, record, periods)


# ------------------------------------------------------------------ summary


def _scale(horizon: str) -> float:
    return math.sqrt(PERIODS_PER_YEAR[horizon] / metrics.SESSIONS_PER_YEAR)


def period_stats(ret: pd.Series, turnover: pd.Series, horizon: str) -> dict[str, float]:
    """Metrics of a period-return series (``metrics`` formulas with the horizon's periods/year)."""
    n = len(ret)
    ppy = PERIODS_PER_YEAR[horizon]
    if n == 0:
        nan = math.nan
        return {
            "periods": 0,
            "cagr": nan,
            "vol": nan,
            "sharpe": nan,
            "max_dd": nan,
            "turnover": 0.0,
        }
    growth = 1.0 + metrics.total_return(ret)
    cagr = -1.0 if growth <= 0 else float(growth ** (ppy / n) - 1.0)
    return {
        "periods": n,
        "cagr": cagr,
        "vol": metrics.ann_vol(ret) * _scale(horizon),
        "sharpe": metrics.sharpe(ret) * _scale(horizon),
        "max_dd": metrics.max_drawdown(ret),
        "turnover": metrics.avg_turnover(turnover),
    }


def summary_rows(store: TrialRegistry, oos: pd.DataFrame) -> pd.DataFrame:
    """Per trial, mode and segment (historical = in-sample by design, forward = true OOS)."""
    records = {r.trial_id: r for r in store.list()}
    out: list[tuple[object, ...]] = []
    for (trial_id, mode), group in oos.groupby(["trial_id", "mode"], sort=True):
        rec = records.get(str(trial_id))
        if rec is None:
            continue
        for segment in SEGMENTS:
            flag = segment == "historical"
            part = group[group["in_sample_by_design"] == flag].sort_values("period_end")
            stats = period_stats(part["ret"], part["turnover"], rec.horizon)
            out.append(
                (
                    rec.trial_id,
                    rec.strategy_id,
                    rec.params_json,
                    rec.horizon,
                    str(mode),
                    segment,
                    int(stats["periods"]),
                    stats["cagr"],
                    stats["vol"],
                    stats["sharpe"],
                    stats["max_dd"],
                    stats["turnover"],
                )
            )
    frame = pd.DataFrame(out, columns=list(SUMMARY_COLUMNS))
    if frame.empty:
        return frame
    frame["_h"] = frame["horizon"].map(_HORIZON_ORDER)
    frame = frame.sort_values(
        ["_h", "strategy_id", "params", "mode", "segment"], kind="stable"
    ).drop(columns="_h")
    return frame.reset_index(drop=True)


def _pct(value: float) -> str:
    return "n/a" if value != value else f"{value * 100:.1f}%"


def format_summary(summary: pd.DataFrame, source: str) -> str:
    """Console table: the data label first, then one line per trial, mode and segment."""
    lines = [data_label(source)]
    header = (
        "strategy",
        "params",
        "hzn",
        "mode",
        "segment",
        "N",
        "CAGR",
        "vol",
        "Sharpe",
        "maxDD",
        "turn",
    )
    table = [
        (
            str(r["strategy_id"]),
            str(r["params"]),
            str(r["horizon"]),
            str(r["mode"]),
            str(r["segment"]),
            str(r["periods"]),
            _pct(float(r["cagr"])),
            _pct(float(r["vol"])),
            "n/a" if r["sharpe"] != r["sharpe"] else f"{float(r['sharpe']):.2f}",
            _pct(float(r["max_dd"])),
            f"{float(r['avg_turnover']):.2f}",
        )
        for r in summary.to_dict("records")
    ]
    widths = [max(len(x[i]) for x in [header, *table]) for i in range(len(header))]
    for n, record in enumerate([header, *table]):
        cells = [c.ljust(widths[i]) if i < 5 else c.rjust(widths[i]) for i, c in enumerate(record)]
        lines.append("  ".join(cells).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    lines.append(
        f"historical = {SEGMENT_LABELS['historical']}; forward = {SEGMENT_LABELS['forward']}"
    )
    return "\n".join(lines)


# ------------------------------------------------------------------ orchestration


@dataclass(frozen=True)
class BacktestResult:
    source: str
    label: str
    trials: tuple[str, ...]  # trial ids run
    modes: tuple[str, ...]
    registered_now: tuple[str, ...]  # trial ids registered by this call (``register=True``)
    rows_written: int
    feature_version: str


def select_strategies(cfg: AppConfig, strategy_id: str | None) -> list[Strategy]:
    """Enabled config strategies; with ``strategy_id`` only its parameter sets."""
    strategies = load_strategies(cfg)
    if strategy_id is not None:
        chosen = [s for s in strategies if s.id == strategy_id]
        if not chosen:
            raise WalkForwardError(
                f"strategy {strategy_id!r} is not enabled in the config; "
                f"available: {', '.join(sorted({s.id for s in strategies})) or 'none'}"
            )
        return chosen
    if not strategies:
        raise WalkForwardError("no enabled strategies in config: nothing to backtest")
    return strategies


def run_backtest(
    cfg: AppConfig,
    paths: AppPaths,
    *,
    source: str,
    strategy_id: str | None = None,
    modes: Sequence[str] = MODES,
    register: bool = False,
    run_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    progress: Callable[[str], None] | None = None,
    now: datetime | None = None,
) -> BacktestResult:
    """Walk every selected trial forward on the store of ``source`` and store the OOS returns.

    Every trial is checked against the registry before any of them runs (so an unregistered trial
    stops the whole call with ``UnregisteredTrialError``); with ``register=True`` the missing ones
    are registered first. Re-running replaces the trial's rows for the same source and modes.
    """
    note = progress or (lambda _msg: None)
    strategies = select_strategies(cfg, strategy_id)
    db_path = paths.market_db_for(kind_of_source(source))
    if not db_path.is_file():
        raise WalkForwardError(f"no store at {db_path}: run `vnstratlab ingest` first")
    with MarketStore(db_path, kind_of_source(source), read_only=True) as market:
        inputs = load_inputs(market, cfg, source, start, end)
    version = inputs.feature_version
    registered_now: list[str] = []
    pairs = [(s, h) for s in strategies for h in s.horizons]
    with LabStore(paths.lab_db) as lab:
        if register:
            for strategy, horizon in pairs:
                spec = make_trial_spec(strategy, horizon, version, ENGINE_VERSION)
                if lab.register(spec, "config").created:
                    registered_now.append(spec.trial_id)
            if registered_now:
                note(f"registered {len(registered_now)} new trial(s) before running")
        for strategy, horizon in pairs:  # fail before any trial runs
            ensure_trial(lab, strategy, horizon, version)
        written = 0
        ran: list[str] = []
        for strategy, horizon in pairs:
            note(f"{strategy.id} {horizon}")
            run = run_trial(inputs, lab, cfg, strategy, horizon, modes)
            registered_date = run.record.registered_at.astimezone(VN_TZ).date()
            for mode, frame in run.periods.items():
                written += lab.replace_oos(
                    run.spec.trial_id,
                    mode,
                    source,
                    frame,
                    horizon=horizon,
                    feature_version=version,
                    engine_version=ENGINE_VERSION,
                    registered_date=registered_date,
                    run_id=run_id,
                    now=now,
                )
            ran.append(run.spec.trial_id)
    return BacktestResult(
        source,
        data_label(source),
        tuple(ran),
        tuple(modes),
        tuple(registered_now),
        written,
        version,
    )


def load_summary(
    paths: AppPaths,
    source: str,
    trial_ids: Sequence[str] | None = None,
    modes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """The summary of the stored rows of ``source`` (read-only; empty if nothing is stored)."""
    if not paths.lab_db.is_file():
        return pd.DataFrame(columns=list(SUMMARY_COLUMNS))
    with LabStore(paths.lab_db, read_only=True) as lab:
        oos = lab.oos_returns(source=source)
        if trial_ids is not None:
            oos = oos[oos["trial_id"].isin(list(trial_ids))]
        if modes is not None:
            oos = oos[oos["mode"].isin(list(modes))]
        return summary_rows(lab, oos)
