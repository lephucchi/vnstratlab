"""Current recommendations, a preview of P1-T25 (card X-stock-api; contract
``docs/cards/stock-insight-api.md``).

Recommend-only: the output is a list of suggested positions with a data label and a disclaimer; no
order is created, routed or confirmed.

How a recommendation is made (engine.md sections 7 and 9):

1. ``asof`` is the latest ``features_daily`` date of the source (or an earlier ``asof`` given by the
   caller). The decision is as at that close.
2. Every enabled strategy x horizon of the config is a trial. Only **registered** trials of the
   store's feature version and ``ENGINE_VERSION`` contribute; an enabled trial that is not
   registered is listed with ``registered: false`` and excluded (plan rule 3).
3. Each contributing strategy gets the feature rows <= ``asof`` through
   ``vnstratlab.demo.decision_targets`` (the walk-forward slicing, ``lookback_sessions`` included,
   ``asof_guard`` included). ``asof`` is rarely a decision day, so it is handed to
   ``decision_targets`` as the decision day of its (incomplete) period by ``_AsofCalendar``.
4. Preview combination until P1-T22 exists: equal weight across the contributing strategies
   (W = mean of w_i, a strategy not holding a ticker contributes 0), then once through the
   ``RiskLayer`` with the horizon book's capital (ATR sizing, max weight, max positions).
5. Lot, entry zone, stop and cost use ``engine.rules`` / ``engine.costs`` / ``risk``; nothing here
   adds a formula. ``stop_price = entry - atr_stop_multiple x ATR14``, rounded up to the tick (it is
   a sell level); the entry zone is ``[last_close, min(ceiling, last_close x (1 + round-lot
   slippage))]`` rounded down to the tick (it is a buy limit).

Read-only on the market store and the lab store.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.data.pipeline import ExecutionFrame, load_execution_frame
from vnstratlab.data.protocol import universe_tickers
from vnstratlab.data.store import MarketStore, kind_of_source
from vnstratlab.demo import decision_targets
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.engine.costs import CostModel
from vnstratlab.engine.rules import MarketRules, price_limits, round_limit_price, split_lots
from vnstratlab.features.build import load_features
from vnstratlab.lab.stats import add_gate_columns
from vnstratlab.lab.store import LabStore
from vnstratlab.lab.trials import TrialError, store_feature_version
from vnstratlab.lab.walkforward import config_pairs, data_label
from vnstratlab.risk import ATR_WINDOW, RiskLayer, atr
from vnstratlab.strategies.base import HORIZONS, Horizon, Strategy
from vnstratlab.strategies.registry import TrialSpec, make_trial_spec

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig
    from vnstratlab.paths import AppPaths

PREVIEW_NOTE_VI = "Chưa qua lab chọn lọc (P1-T22): trung bình đều các chiến lược đang bật."
DISCLAIMER_VI = (
    "Chỉ là khuyến nghị tham khảo, không phải lời mời mua bán. Bạn tự quyết định và tự đặt lệnh."
)
UNREGISTERED_NOTE_VI = (
    "Chưa đăng ký trial: không được tính. Đăng ký bằng `vnstratlab lab register` "
    "hoặc `vnstratlab backtest --all --register`."
)
_EPOCH = date(1990, 1, 1)
_FAR = date(2200, 1, 1)
_TOL = 1e-12


class InsightError(RuntimeError):
    """The request cannot be answered; ``code`` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def json_safe(value: Any) -> Any:
    """Recursively replace NaN / infinity by ``None`` and numpy scalars by Python numbers."""
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, date):
        return value.isoformat()
    return value


def json_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    """``json_safe`` of a mapping, as a dict."""
    out = json_safe(value)
    if not isinstance(out, dict):  # pragma: no cover (a mapping stays a dict)
        raise TypeError("expected a mapping")
    return out


# ------------------------------------------------------------------ inputs


class _AsofCalendar(TradingCalendar):
    """Only ``asof`` is a session, so ``decision_days`` returns it as the decision day of the
    (incomplete) week or month it lies in. The slicing itself stays in ``decision_targets``."""

    def __init__(self, asof: date) -> None:
        super().__init__()
        self._asof = asof

    def is_trading_day(self, d: date) -> bool:
        return d == self._asof


@dataclass(frozen=True)
class Market:
    """Everything read from the market store, cut at ``asof`` (no later row is loaded)."""

    cfg: AppConfig
    source: str
    asof: date
    version: str
    features: pd.DataFrame  # sorted by date
    feature_dates: np.ndarray = field(repr=False)
    session_dates: np.ndarray = field(repr=False)
    frame: ExecutionFrame = field(repr=False)
    sessions: frozenset[date] = field(repr=False)
    atr_now: dict[str, float] = field(repr=False)  # ATR14 of each ticker at ``asof`` (exec basis)

    def last_row(self, ticker: str) -> pd.Series | None:
        """The execution row of ``ticker`` dated ``asof`` (None: no session that day)."""
        prices = self.frame.prices
        rows = prices[(prices["ticker"] == ticker) & (prices["date"] == self.asof)]
        return None if rows.empty else rows.iloc[0]


def _atr_at(frame: ExecutionFrame, asof: date) -> dict[str, float]:
    """Wilder ATR14 at ``asof`` per ticker from the execution prices; stock / bonus ex-dates divide
    the history as in the simulator (``risk.atr`` ``ex_factor``). NaN without a row at ``asof``."""
    actions = frame.actions
    out: dict[str, float] = {}
    for ticker, group in frame.prices.sort_values("date").groupby("ticker"):
        dates = [pd.Timestamp(d).date() for d in group["date"]]
        factors = [1.0] * len(dates)
        if not actions.empty:
            mine = actions[(actions["ticker"] == ticker) & actions["type"].isin(["stock", "bonus"])]
            for ex, ratio in zip(mine["ex_date"], mine["ratio_or_amount"], strict=True):
                row = bisect.bisect_left(dates, pd.Timestamp(ex).date())
                if row < len(dates):
                    factors[row] *= 1.0 + float(ratio)
        values = atr(group["high"], group["low"], group["close"], ATR_WINDOW, factors)
        out[str(ticker)] = float(values.iloc[-1]) if dates and dates[-1] == asof else math.nan
    return out


def load_market(cfg: AppConfig, paths: AppPaths, source: str, asof: date | None = None) -> Market:
    """Read features and execution prices of the universe up to ``asof`` (default: the latest
    features date). Raises ``InsightError`` when there is no store or no features."""
    kind = kind_of_source(source)
    db_path = paths.market_db_for(kind)
    if not db_path.is_file():
        raise InsightError("no_data", f"no store for source {source!r}: run `vnstratlab ingest`")
    end = asof if asof is not None else _FAR
    with MarketStore(db_path, kind, read_only=True) as store:
        try:
            version = store_feature_version(store)
        except TrialError as exc:
            raise InsightError("no_features", f"{exc}") from None
        features = load_features(store, _EPOCH, end, asof=end)
        if features.empty:
            raise InsightError("no_features", "no feature rows: run `vnstratlab features build`")
        last = max(pd.Timestamp(d).date() for d in features["date"])
        frame = load_execution_frame(store, universe_tickers(cfg), _EPOCH, last, source)
    features = features.sort_values("date", kind="stable").reset_index(drop=True)
    feature_dates = pd.to_datetime(features["date"]).to_numpy(dtype="datetime64[ns]")
    sessions = frozenset(pd.Timestamp(d).date() for d in frame.prices["date"])
    return Market(
        cfg,
        source,
        last,
        version,
        features,
        feature_dates,
        np.unique(feature_dates),
        frame,
        sessions,
        _atr_at(frame, last),
    )


# ------------------------------------------------------------------ trials and the lab


@dataclass(frozen=True)
class Trial:
    """One enabled strategy on one horizon."""

    strategy: Strategy
    horizon: Horizon
    spec: TrialSpec
    registered: bool


@dataclass(frozen=True)
class LabInfo:
    """What is read from ``lab.duckdb``: registered trial ids, the trial count and trial_stats."""

    registered: frozenset[str]
    n_trials: int
    stats: pd.DataFrame  # historical, executable rows of the source with the gate columns


def read_lab(cfg: AppConfig, paths: AppPaths, source: str) -> LabInfo:
    """Read-only; an absent lab store means nothing is registered."""
    if not paths.lab_db.is_file():
        return LabInfo(frozenset(), 0, pd.DataFrame())
    with LabStore(paths.lab_db, read_only=True) as lab:
        records = lab.list()
        stats = lab.trial_stats_rows(source=source, mode="executable")
        n_trials = lab.count()
    gated = add_gate_columns(stats, cfg) if not stats.empty else stats
    if not gated.empty:
        gated = gated[gated["segment"] == "historical"]
    registered = frozenset(r.trial_id for r in records if r.engine_version == ENGINE_VERSION)
    return LabInfo(registered, n_trials, gated)


def enabled_trials(market: Market, lab: LabInfo, horizon: Horizon | None = None) -> list[Trial]:
    """The enabled config trials (of ``horizon``, or all), each flagged registered or not."""
    out: list[Trial] = []
    for strategy, h in config_pairs(market.cfg, None):
        if horizon is not None and h != horizon:
            continue
        spec = make_trial_spec(strategy, h, market.version, ENGINE_VERSION)
        out.append(Trial(strategy, h, spec, spec.trial_id in lab.registered))
    return out


def asof_weights(market: Market, trial: Trial) -> pd.Series:
    """The trial's target weights as at ``market.asof`` (rows <= asof, ``lookback_sessions``)."""
    day = market.asof
    targets = decision_targets(
        trial.strategy,
        trial.horizon,
        market.features,
        market.feature_dates,
        market.session_dates,
        _AsofCalendar(day),
        {day},
        day,
        day,
    )
    found = targets.get(day)
    return found if found is not None else pd.Series(dtype=float)


# ------------------------------------------------------------------ sizing


def size_position(
    cfg: AppConfig, close: float, atr14: float, weight: float, capital: float
) -> dict[str, Any]:
    """Lot split, entry zone, stop and buy cost for ``weight`` of ``capital`` at ``close``."""
    rules = MarketRules.from_config(cfg)
    costs = CostModel.from_config(cfg)
    ceiling, floor = price_limits(close, cfg.market.rules.price_limit_pct.value, rules.tick_bands)
    lot_qty, odd_qty = split_lots(weight * capital / close, rules.round_lot, True)
    high = round_limit_price(
        min(ceiling, close * (1.0 + costs.slip_round)), "buy", rules.tick_bands
    )
    cost = 0.0
    for qty, lot in ((lot_qty, "round"), (odd_qty, "odd")):
        if qty > 0:
            fill = costs.fill_price(close, "buy", lot)  # type: ignore[arg-type]
            cost += costs.fee(qty * fill) + qty * (fill - close)
    stop: float | None = None
    stop_pct: float | None = None
    if not math.isnan(atr14):
        stop = round_limit_price(
            RiskLayer(cfg.risk).stop_price(close, atr14), "sell", rules.tick_bands
        )
        stop_pct = (close - stop) / close
    shares = lot_qty + odd_qty
    return {
        "lot_size": rules.round_lot,
        "lot_qty": lot_qty,
        "lots": lot_qty // rules.round_lot,
        "odd_qty": odd_qty,
        "notional_vnd": shares * close,
        "entry_zone": {"low": close, "high": high},
        "ceiling": ceiling,
        "floor": floor,
        "atr14": atr14,
        "stop_price": stop,
        "stop_pct": stop_pct,
        "risk_vnd": None if stop is None else shares * (close - stop),
        "est_cost_vnd": cost,
    }


# ------------------------------------------------------------------ one horizon


@dataclass(frozen=True)
class Preview:
    """The combined, risk-checked portfolio of one horizon (before it is rendered as JSON)."""

    horizon: Horizon
    capital: float
    trials: list[Trial]
    weights: dict[str, pd.Series]  # trial id -> asof weights (registered trials only)
    combined: pd.Series  # equal-weight mean before the risk layer
    final: pd.Series  # after the risk layer, > 0 only


def preview_horizon(market: Market, lab: LabInfo, horizon: Horizon) -> Preview:
    """Equal weight over the registered trials of ``horizon``, then once through the risk layer."""
    cfg = market.cfg
    trials = enabled_trials(market, lab, horizon)
    weights = {t.spec.trial_id: asof_weights(market, t) for t in trials if t.registered}
    capital = float(getattr(cfg.books, horizon).capital_vnd)
    combined = pd.Series(dtype=float)
    if weights:
        frame = pd.DataFrame(weights).fillna(0.0)
        combined = frame.mean(axis=1)
        combined = combined[combined > _TOL].sort_index()
    closes: dict[str, float] = {}
    for ticker in combined.index:
        row = market.last_row(str(ticker))
        if row is not None:
            closes[str(ticker)] = float(row["close"])
    decision = RiskLayer(cfg.risk).apply(
        combined,
        equity=capital,
        prices_close=closes,
        atr={t: market.atr_now.get(t, math.nan) for t in closes},
        held={},
        peak_equity=capital,
    )
    final = decision.weights[decision.weights > _TOL]
    return Preview(horizon, capital, trials, weights, combined, final)


def _evidence(lab: LabInfo, trials: list[Trial]) -> dict[str, Any]:
    contributing = {t.spec.trial_id: t for t in trials if t.registered}
    dsr: dict[str, float] = {}
    passed: list[str] = []
    stats = lab.stats
    if not stats.empty:
        for row in stats[stats["trial_id"].isin(list(contributing))].to_dict("records"):
            trial = contributing[str(row["trial_id"])]
            value = row.get("dsr")
            if isinstance(value, float) and math.isfinite(value):
                sid = trial.strategy.id  # several parameter sets: the lowest DSR is shown
                dsr[sid] = min(dsr.get(sid, value), value)
            if all(row.get(c) is True for c in ("periods_ok", "dsr_ok", "pbo_ok")):
                passed.append(trial.strategy.id)
    return {
        "trials_counted": lab.n_trials,
        "trials_contributing": len(contributing),
        "dsr_by_strategy": dsr,
        "gate1_pass": sorted(set(passed)),  # strategy ids
    }


def render_horizon(market: Market, lab: LabInfo, preview: Preview) -> dict[str, Any]:
    """The ``GET /api/recommendations`` body of one horizon."""
    cfg = market.cfg
    strategies: list[dict[str, Any]] = []
    holders: dict[str, list[str]] = {}
    for trial in preview.trials:
        weights = preview.weights.get(trial.spec.trial_id)
        held = {} if weights is None else {str(t): float(w) for t, w in weights.items() if w > _TOL}
        for ticker in held:
            holders.setdefault(ticker, []).append(trial.strategy.id)
        item: dict[str, Any] = {
            "strategy_id": trial.strategy.id,
            "params": dict(trial.strategy.params),
            "trial_id": trial.spec.trial_id,
            "registered": trial.registered,
            "weights": held,
        }
        if not trial.registered:
            item["note_vi"] = UNREGISTERED_NOTE_VI
        strategies.append(item)
    targets: list[dict[str, Any]] = []
    for key, weight in sorted(preview.final.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        ticker = str(key)
        row = market.last_row(ticker)
        if row is None:  # the risk layer never keeps a ticker without a price
            continue
        close = float(row["close"])
        sized = size_position(
            cfg, close, market.atr_now.get(str(ticker), math.nan), float(weight), preview.capital
        )
        ids = sorted(holders.get(str(ticker), []))
        targets.append(
            {
                "ticker": str(ticker),
                "weight": float(weight),
                "consensus": len(ids),
                "strategies": ids,
                "last_close": close,
                **sized,
            }
        )
    warnings: list[str] = []
    if not any(t.registered for t in preview.trials):
        warnings.append("Không có trial nào đã đăng ký cho khung này: " + UNREGISTERED_NOTE_VI)
    return json_dict(
        {
            "asof": market.asof,
            "source": market.source,
            "synthetic": market.source == "synthetic",
            "label": data_label(market.source),
            "status": "preview",
            "note_vi": PREVIEW_NOTE_VI,
            "disclaimer_vi": DISCLAIMER_VI,
            "horizon": preview.horizon,
            "book_capital_vnd": preview.capital,
            "strategies": strategies,
            "targets": targets,
            "cash_weight": max(0.0, 1.0 - float(preview.final.sum())),
            "evidence": _evidence(lab, preview.trials),
            "warnings": warnings,
        }
    )


def recommendations(
    cfg: AppConfig,
    paths: AppPaths,
    source: str,
    horizon: Horizon,
    asof: date | None = None,
) -> dict[str, Any]:
    """``GET /api/recommendations`` for one horizon."""
    if horizon not in HORIZONS:
        raise InsightError("bad_horizon", f"horizon must be one of {list(HORIZONS)}")
    market = load_market(cfg, paths, source, asof)
    lab = read_lab(cfg, paths, source)
    return render_horizon(market, lab, preview_horizon(market, lab, horizon))


def all_recommendations(
    cfg: AppConfig, paths: AppPaths, source: str, asof: date | None = None
) -> dict[str, Any]:
    """``GET /api/recommendations/all``: the three horizons from one read of the store."""
    market = load_market(cfg, paths, source, asof)
    lab = read_lab(cfg, paths, source)
    return {
        "horizons": {
            h: render_horizon(market, lab, preview_horizon(market, lab, h)) for h in HORIZONS
        }
    }


# ------------------------------------------------------------------ text for the CLI


def format_recommendations(body: Mapping[str, Any]) -> str:
    """Console text of one horizon: label, preview note, the table and the disclaimer."""
    lines = [
        str(body["label"]),
        f"{body['horizon']} | asof {body['asof']} | vốn sổ {body['book_capital_vnd']:,.0f} VND "
        f"| {body['note_vi']}",
    ]
    for item in body["strategies"]:
        if not item["registered"]:
            lines.append(f"  skipped (not registered): {item['strategy_id']} {item['params']}")
    for text in body["warnings"]:
        lines.append(f"  ! {text}")
    targets = body["targets"]
    if targets:
        header = ("ticker", "weight", "cons", "close", "lots", "odd", "notional", "stop", "cost")
        table = [
            (
                t["ticker"],
                f"{t['weight'] * 100:.1f}%",
                str(t["consensus"]),
                f"{t['last_close']:,.0f}",
                str(t["lot_qty"]),
                str(t["odd_qty"]),
                f"{t['notional_vnd']:,.0f}",
                "n/a" if t["stop_price"] is None else f"{t['stop_price']:,.0f}",
                f"{t['est_cost_vnd']:,.0f}",
            )
            for t in targets
        ]
        widths = [max(len(x[i]) for x in [header, *table]) for i in range(len(header))]
        for n, rec in enumerate([header, *table]):
            lines.append(
                "  ".join(
                    c.ljust(widths[i]) if i == 0 else c.rjust(widths[i]) for i, c in enumerate(rec)
                ).rstrip()
            )
            if n == 0:
                lines.append("  ".join("-" * w for w in widths))
    else:
        lines.append("  no recommended stock for this horizon")
    lines.append(f"  cash {body['cash_weight'] * 100:.1f}%")
    lines.append(str(body["disclaimer_vi"]))
    return "\n".join(lines)
