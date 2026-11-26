"""Per-stock analysis (card X-stock-api; contract ``docs/cards/stock-insight-api.md``).

Recommend-only. One analysis is the ``stock_analysis`` pipeline: ``load`` -> ``features`` ->
``signals`` -> ``backtest`` -> ``report`` (``vnstratlab.runs.pipelines``). Each stage is a function
here working on a ``StockState``.

- **No lookahead.** The market is cut at ``asof`` when it is loaded; every signal goes through
  ``vnstratlab.demo.decision_targets`` (rows <= decision day, ``lookback_sessions``).
- **Only registered trials contribute.** An enabled trial that is not registered is listed under
  ``excluded_strategies`` and nothing is computed for it.
- **Backtest block.** The stored walk-forward ``oos_returns`` hold no per-ticker split, so the
  block is a per-ticker attribution run here: for each decision day of a trial the ticker's weight
  in that strategy times the ticker's adjusted-close return to the next decision day (and to
  ``asof`` for the last one), before costs, risk layer and the combination. ``basis`` says so.
- **Recommendation.** ``MUA`` when the preview portfolio (equal weight, risk layer; see
  ``vnstratlab.insight.recommend``) holds the ticker on that horizon; ``GIỮ`` when some strategies
  hold it but the combined portfolio does not (do not add); ``KHÔNG`` otherwise. ``BÁN`` is not
  produced: in recommend-only mode the app does not know what the user holds.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from vnstratlab.calendar import TradingCalendar
from vnstratlab.data.store import MarketStore, kind_of_source
from vnstratlab.demo import decision_targets
from vnstratlab.features.groups import FEATURE_GROUPS
from vnstratlab.insight.recommend import (
    DISCLAIMER_VI,
    InsightError,
    LabInfo,
    Market,
    Preview,
    Trial,
    json_dict,
    load_market,
    preview_horizon,
    read_lab,
    size_position,
)
from vnstratlab.lab import metrics
from vnstratlab.lab.walkforward import WARMUP_SESSIONS, data_label
from vnstratlab.strategies.base import HORIZONS, Horizon
from vnstratlab.strategies.schemas import STRATEGY_INFO

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig
    from vnstratlab.paths import AppPaths

TICKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,12}$")
HORIZON_VI = {"short": "ngắn hạn", "medium": "trung hạn", "long": "dài hạn"}
CHANGE_SESSIONS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 250}
CHART_SESSIONS = 750
COMPARE_MAX = 4
_YEAR = 250

# feature -> (Vietnamese label, short help)
FEATURE_INFO: dict[str, tuple[str, str]] = {
    "close_vs_ma20": (
        "Giá so với MA20",
        "Giá đóng cửa chia trung bình 20 phiên trừ 1; dương là trên đường trung bình.",
    ),
    "close_vs_ma50": (
        "Giá so với MA50",
        "Giá đóng cửa chia trung bình 50 phiên trừ 1; dương là xu hướng tăng trung hạn.",
    ),
    "ret_5d": (
        "Lợi suất 5 phiên",
        "Thay đổi giá điều chỉnh sau 5 phiên (khoảng một tuần).",
    ),
    "ret_20d": (
        "Lợi suất 20 phiên",
        "Thay đổi giá điều chỉnh sau 20 phiên (khoảng một tháng).",
    ),
    "ret_60d": (
        "Lợi suất 60 phiên",
        "Thay đổi giá điều chỉnh sau 60 phiên (khoảng một quý).",
    ),
    "ret_120d": (
        "Lợi suất 120 phiên",
        "Thay đổi giá điều chỉnh sau 120 phiên (khoảng nửa năm).",
    ),
    "ret_250d": (
        "Lợi suất 250 phiên",
        "Thay đổi giá điều chỉnh sau 250 phiên (khoảng một năm).",
    ),
    "ret_12m_skip1m": (
        "Động lượng 12 tháng (bỏ 1 tháng)",
        "Lợi suất từ 250 đến 21 phiên trước; bỏ tháng gần nhất.",
    ),
    "ret_6m_skip1m": (
        "Động lượng 6 tháng (bỏ 1 tháng)",
        "Lợi suất từ 126 đến 21 phiên trước; bỏ tháng gần nhất.",
    ),
    "dist_52w_high": (
        "Cách đỉnh 52 tuần",
        "Giá chia đỉnh 250 phiên trừ 1; gần 0 là sát đỉnh.",
    ),
    "dist_52w_low": (
        "Cách đáy 52 tuần",
        "Giá chia đáy 250 phiên trừ 1; gần 0 là sát đáy.",
    ),
    "high_20d_break": (
        "Vượt đỉnh 20 phiên (theo giá cao)",
        "Bằng 1 khi giá đóng cửa vượt giá cao nhất của 20 phiên trước.",
    ),
    "close_20d_break": (
        "Vượt đỉnh 20 phiên (theo giá đóng cửa)",
        "Bằng 1 khi giá đóng cửa vượt giá đóng cửa cao nhất của 20 phiên trước.",
    ),
    "rs_20d_vs_group_median": (
        "Sức mạnh so với nhóm (20 phiên)",
        "Lợi suất 20 phiên trừ trung vị của nhóm cùng ngày.",
    ),
    "rs_20d_rank": (
        "Thứ hạng sức mạnh trong nhóm",
        "Thứ hạng phần trăm của lợi suất 20 phiên trong nhóm (1 là mạnh nhất).",
    ),
    "rsi_14": (
        "RSI 14",
        "Chỉ số sức mạnh tương đối 14 phiên; dưới 30 là quá bán, trên 70 là quá mua.",
    ),
    "rsi_2": (
        "RSI 2",
        "RSI 2 phiên, rất nhạy; dùng cho tín hiệu hồi ngắn hạn.",
    ),
    "z_ma20": (
        "Z-score so với MA20",
        "Độ lệch của giá so với MA20 tính theo độ lệch chuẩn 20 phiên.",
    ),
    "ret_5d_vs_group_median": (
        "Lợi suất tuần so với nhóm",
        "Lợi suất 5 phiên trừ trung vị của nhóm; âm là yếu hơn nhóm.",
    ),
    "atr_14": (
        "ATR 14",
        "Biên độ dao động thực trung bình 14 phiên (giá điều chỉnh); dùng đặt mức cắt lỗ.",
    ),
    "std_20d": (
        "Biến động 20 phiên",
        "Độ lệch chuẩn lợi suất ngày trong 20 phiên.",
    ),
    "std_60d": (
        "Biến động 60 phiên",
        "Độ lệch chuẩn lợi suất ngày trong 60 phiên.",
    ),
    "vol_vs_avg20": (
        "Khối lượng so với bình quân 20 phiên",
        "Khối lượng hôm nay chia khối lượng trung bình 20 phiên.",
    ),
    "value_traded_20d": (
        "Giá trị giao dịch 20 phiên",
        "Giá trị khớp lệnh trung bình ngày trong 20 phiên (VND); đo thanh khoản.",
    ),
    "group_ew_vs_ma50": (
        "Chỉ số nhóm so với MA50",
        "Chỉ số bình quân đều của nhóm chia MA50 của nó trừ 1.",
    ),
    "group_breadth_ma50": (
        "Độ rộng nhóm trên MA50",
        "Tỷ lệ mã trong nhóm có giá trên MA50.",
    ),
    "group_ret_12m": (
        "Lợi suất nhóm 12 tháng",
        "Lợi suất 250 phiên của chỉ số nhóm bình quân đều.",
    ),
    "group_ret_6m": (
        "Lợi suất nhóm 6 tháng",
        "Lợi suất 126 phiên của chỉ số nhóm bình quân đều.",
    ),
    "ret_1d": (
        "Lợi suất 1 phiên",
        "Thay đổi giá điều chỉnh so với phiên trước.",
    ),
}


_VND_FEATURES = frozenset({"atr_14", "value_traded_20d"})
_RATIO_FEATURES = frozenset({"vol_vs_avg20"})
_RAW_FEATURES = frozenset(
    {"rsi_14", "rsi_2", "z_ma20", "high_20d_break", "close_20d_break", "rs_20d_rank"}
)


def feature_unit(name: str) -> str:
    """How the UI formats a feature: ``pct`` (a fraction, 0.05 is 5%), ``vnd``, ``ratio`` or
    ``raw``."""
    if name in _VND_FEATURES:
        return "vnd"
    if name in _RATIO_FEATURES:
        return "ratio"
    if name in _RAW_FEATURES:
        return "raw"
    return "pct"


def signal_of(strategy_id: str, params: Mapping[str, Any]) -> tuple[str, bool] | None:
    """The feature a strategy ranks on and whether the lowest value is preferred; None when the
    strategy has no single ranking feature (composite, pairs, group-level, 1/N, HRP)."""
    months = params.get("L_months")
    if strategy_id == "S01_weekly_reversal":
        return "ret_5d_vs_group_median", True
    if strategy_id == "S02_breakout_volume":
        return "close_20d_break", False
    if strategy_id == "S03_oversold_uptrend":
        return f"rsi_{params.get('rsi_len')}", True
    if strategy_id in ("S08_momentum", "S09_reversal") and months in (6, 12):
        return f"ret_{months}m_skip1m", strategy_id == "S09_reversal"
    if strategy_id == "S14_low_volatility":
        return "std_60d", True
    return None


# ------------------------------------------------------------------ state


@dataclass
class StockState:
    """Mutable state passed from one stage to the next (the stages are the runner's tasks)."""

    cfg: AppConfig
    paths: AppPaths
    source: str
    ticker: str
    horizons: tuple[Horizon, ...]
    run_id: str = ""
    asof: date | None = None  # tests cut the market here; the pipeline always uses the latest
    market: Market | None = None
    lab: LabInfo | None = None
    adjusted: pd.DataFrame = field(default_factory=pd.DataFrame)
    dq_findings_1y: int = 0
    price: dict[str, Any] = field(default_factory=dict)
    features: list[dict[str, Any]] = field(default_factory=list)
    previews: dict[str, Preview] = field(default_factory=dict)
    strategies: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    decisions: dict[str, dict[date, float]] = field(default_factory=dict)  # trial id -> day -> w
    backtest: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)


def _market(st: StockState) -> Market:
    if st.market is None:
        raise InsightError("not_loaded", "the load stage has not run")
    return st.market


# ------------------------------------------------------------------ stage: load


def stage_load(st: StockState) -> dict[str, Any]:
    """Read the market (cut at the latest features date), the lab and the ticker's prices."""
    st.market = load_market(st.cfg, st.paths, st.source, st.asof)
    market = st.market
    if st.ticker not in set(market.features["ticker"]):
        raise InsightError("unknown_ticker", f"{st.ticker} has no feature rows in {st.source}")
    st.lab = read_lab(st.cfg, st.paths, st.source)
    kind = kind_of_source(st.source)
    since = market.asof - timedelta(days=365)
    with MarketStore(st.paths.market_db_for(kind), kind, read_only=True) as store:
        st.adjusted = store.connection.execute(
            "SELECT date, adj_close, signal_ok FROM prices_adjusted "
            "WHERE ticker = ? AND source = ? AND date <= ? ORDER BY date",
            [st.ticker, st.source, market.asof],
        ).df()
        if store.has_table("dq_results"):
            row = store.connection.execute(
                "SELECT count(*) FROM dq_results WHERE ticker = ? AND date BETWEEN ? AND ?",
                [st.ticker, since, market.asof],
            ).fetchone()
            st.dq_findings_1y = int(row[0]) if row else 0
    st.adjusted["date"] = [pd.Timestamp(d).date() for d in st.adjusted["date"]]
    return {"asof": market.asof.isoformat(), "tickers": int(market.features["ticker"].nunique())}


# ------------------------------------------------------------------ stage: features


def _ticker_exec(market: Market, ticker: str) -> pd.DataFrame:
    prices = market.frame.prices
    return prices[prices["ticker"] == ticker].sort_values("date").reset_index(drop=True)


def _price_block(st: StockState) -> dict[str, Any]:
    market, cfg = _market(st), st.cfg
    rows = _ticker_exec(market, st.ticker)
    if rows.empty:
        raise InsightError("no_data", f"no execution prices for {st.ticker}")
    last = rows.iloc[-1]
    close = float(last["close"])
    adj = pd.Series(
        st.adjusted["adj_close"].to_numpy(dtype=float), index=st.adjusted["date"], dtype=float
    ).dropna()
    rets = adj.pct_change().dropna()
    change: dict[str, float | None] = {}
    for label, n in CHANGE_SESSIONS.items():
        change[label] = float(adj.iloc[-1] / adj.iloc[-1 - n] - 1.0) if len(adj) > n else None
    ytd = adj[[d.year < market.asof.year for d in adj.index]]
    change["YTD"] = float(adj.iloc[-1] / ytd.iloc[-1] - 1.0) if len(ytd) else None
    year = rows.tail(_YEAR)
    high, low = float(year["high"].max()), float(year["low"].min())
    volume = rows["volume"].astype(float)
    adv_value = float((rows["close"] * rows["volume"]).tail(20).mean())
    adv_volume = float(volume.tail(20).mean())
    atr14 = market.atr_now.get(st.ticker, math.nan)
    capital = float(cfg.books.short.capital_vnd)
    sized = size_position(cfg, close, atr14, 0.0, capital)
    return {
        "last_close": close,
        "change": change,
        "high_52w": high,
        "low_52w": low,
        "dist_high_52w": close / high - 1.0,
        "dist_low_52w": close / low - 1.0,
        "vol_20d_ann": metrics.ann_vol(rets.tail(20)) if len(rets) >= 20 else None,
        "vol_60d_ann": metrics.ann_vol(rets.tail(60)) if len(rets) >= 60 else None,
        "max_dd_1y": metrics.max_drawdown(rets.tail(_YEAR)) if len(rets) else None,
        "atr14": atr14,
        "adv20_value_vnd": adv_value,
        "volume_vs_adv20": float(volume.iloc[-1]) / adv_volume if adv_volume > 0 else None,
        "ceiling": sized["ceiling"],
        "floor": sized["floor"],
        "lot_size": sized["lot_size"],
    }


def _feature_block(st: StockState) -> list[dict[str, Any]]:
    market = _market(st)
    cross = market.features[pd.to_datetime(market.features["date"]) == pd.Timestamp(market.asof)]
    cross = cross.set_index("ticker")
    if st.ticker not in cross.index:
        return []
    out: list[dict[str, Any]] = []
    for group, names in FEATURE_GROUPS.items():
        for name in names:
            if name not in cross.columns:
                continue
            values = pd.to_numeric(cross[name], errors="coerce")
            value = float(values[st.ticker])
            rank = float(values.rank(pct=True)[st.ticker]) if math.isfinite(value) else None
            label, help_vi = FEATURE_INFO.get(name, (name, ""))
            out.append(
                {
                    "name": name,
                    "label_vi": label,
                    "group": group,
                    "unit": feature_unit(name),
                    "value": value,
                    "pct_rank_universe": rank,
                    "help_vi": help_vi,
                }
            )
    return out


def stage_features(st: StockState) -> dict[str, Any]:
    st.price = _price_block(st)
    st.features = _feature_block(st)
    return {"features": len(st.features), "last_close": st.price["last_close"]}


# ------------------------------------------------------------------ stage: signals


def _history_start(market: Market) -> date:
    days = [pd.Timestamp(d).date() for d in market.session_dates]
    return days[min(WARMUP_SESSIONS, len(days) - 1)]


def _decisions(market: Market, trial: Trial, ticker: str) -> dict[date, float]:
    """The trial's weight in ``ticker`` on each decision day from the warm-up to ``asof``."""
    targets = decision_targets(
        trial.strategy,
        trial.horizon,
        market.features,
        market.feature_dates,
        market.session_dates,
        TradingCalendar.from_config(market.cfg),
        set(market.sessions),
        _history_start(market),
        market.asof,
    )
    return {d: float(w.get(ticker, 0.0)) for d, w in sorted(targets.items())}


def _rank(
    market: Market, feature: str, ascending: bool, ticker: str
) -> tuple[int | None, int | None]:
    cross = market.features[pd.to_datetime(market.features["date"]) == pd.Timestamp(market.asof)]
    if feature not in cross.columns:
        return None, None
    values = pd.to_numeric(cross.set_index("ticker")[feature], errors="coerce").dropna()
    if ticker not in values.index:
        return None, len(values)
    return int(values.rank(ascending=ascending, method="min")[ticker]), len(values)


def _reason_vi(trial: Trial, ticker: str, holds: bool, weight: float, rank: int | None,
               of: int | None, label: str | None) -> str:  # fmt: skip
    name = STRATEGY_INFO.get(trial.strategy.id, {}).get("name_vi", trial.strategy.id)
    where = f", xếp hạng {rank}/{of} theo {label}" if rank is not None and label else ""
    if holds:
        return f"{name} đang giữ {ticker} (tỷ trọng {weight * 100:.0f}%{where})."
    return f"{name} không giữ {ticker}{where}."


def stage_signals(st: StockState, note: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Each registered trial's signal for the ticker at ``asof`` and its decision history."""
    market, lab = _market(st), st.lab
    if lab is None:
        raise InsightError("not_loaded", "the load stage has not run")
    log = note or (lambda _msg: None)
    st.strategies, st.excluded, st.previews, st.decisions = [], [], {}, {}
    for horizon in st.horizons:
        preview = preview_horizon(market, lab, horizon)
        st.previews[horizon] = preview
        for trial in preview.trials:
            tid = trial.spec.trial_id
            base = {
                "strategy_id": trial.strategy.id,
                "params": dict(trial.strategy.params),
                "horizon": horizon,
                "trial_id": tid,
            }
            if not trial.registered:
                st.excluded.append({**base, "registered": False})
                continue
            log(f"{trial.strategy.id} {horizon}")
            weight = float(preview.weights[tid].get(st.ticker, 0.0))
            holds = weight > 0.0
            signal = signal_of(trial.strategy.id, trial.strategy.params)
            rank, of = _rank(market, signal[0], signal[1], st.ticker) if signal else (None, None)
            value: float | None = None
            if signal is not None:
                cross = market.features[
                    (market.features["ticker"] == st.ticker)
                    & (pd.to_datetime(market.features["date"]) == pd.Timestamp(market.asof))
                ]
                if not cross.empty and signal[0] in cross.columns:
                    value = float(cross.iloc[0][signal[0]])
            history = _decisions(market, trial, st.ticker)
            st.decisions[tid] = history
            picked = [d for d, w in history.items() if w > 0.0]
            label = FEATURE_INFO.get(signal[0], (signal[0], ""))[0] if signal else None
            st.strategies.append(
                {
                    **base,
                    "holds": holds,
                    "weight": weight,
                    "rank": rank,
                    "of": of,
                    "signal": {"name": signal[0] if signal else None, "value": value},
                    "reason_vi": _reason_vi(trial, st.ticker, holds, weight, rank, of, label),
                    "history": {
                        "selected_share": len(picked) / len(history) if history else None,
                        "last_selected": picked[-1].isoformat() if picked else None,
                        "n_decisions": len(history),
                    },
                }
            )
    return {"strategies": len(st.strategies), "excluded": len(st.excluded)}


# ------------------------------------------------------------------ stage: backtest


def _runs(flags: Sequence[bool]) -> list[int]:
    out: list[int] = []
    run = 0
    for flag in flags:
        if flag:
            run += 1
        elif run:
            out.append(run)
            run = 0
    if run:
        out.append(run)
    return out


def attribution(decisions: Mapping[date, float], adj: pd.Series, asof: date) -> dict[str, Any]:
    """Weighted adjusted-close return of the ticker over the periods its weight was held."""
    days = sorted(decisions)
    ends = [*days[1:], asof]
    contribution, hits, held = 0.0, 0, 0
    flags: list[bool] = []
    for start, end in zip(days, ends, strict=True):
        weight = decisions[start]
        flags.append(weight > 0.0)
        if weight <= 0.0 or end <= start:
            continue
        p0, p1 = _adj_at(adj, start), _adj_at(adj, end)
        if p0 is None or p1 is None or p0 <= 0:
            continue
        ret = p1 / p0 - 1.0
        contribution += weight * ret
        held += 1
        hits += ret > 0
    lengths = _runs(flags)
    return {
        "periods_held": held,
        "contribution_return": contribution,
        "hit_rate": hits / held if held else None,
        "avg_hold_periods": float(np.mean(lengths)) if lengths else None,
    }


def _adj_at(adj: pd.Series, day: date) -> float | None:
    """Adjusted close on ``day`` or the last session before it."""
    index = int(adj.index.searchsorted(day, side="right")) - 1
    return float(adj.iloc[index]) if index >= 0 else None


def stage_backtest(st: StockState) -> dict[str, Any]:
    market = _market(st)
    adj = pd.Series(
        st.adjusted["adj_close"].to_numpy(dtype=float), index=st.adjusted["date"], dtype=float
    ).dropna()
    rets = adj.pct_change().dropna()
    buy_hold = {
        "cagr": metrics.cagr(rets),
        "vol": metrics.ann_vol(rets),
        "sharpe": metrics.sharpe(rets),
        "max_dd": metrics.max_drawdown(rets),
    }
    by_strategy = [
        {
            "strategy_id": s["strategy_id"],
            "horizon": s["horizon"],
            "trial_id": s["trial_id"],
            **attribution(st.decisions[s["trial_id"]], adj, market.asof),
        }
        for s in st.strategies
    ]
    st.backtest = {
        "basis": "attribution",
        "note_vi": "Đóng góp của mã trong từng chiến lược: tỷ trọng x lợi suất giữa hai ngày "
        "quyết định, chưa tính phí, lớp rủi ro và việc kết hợp chiến lược.",
        "buy_hold": buy_hold,
        "by_strategy": by_strategy,
    }
    return {"by_strategy": len(by_strategy)}


# ------------------------------------------------------------------ stage: report


_BOOK_FIELDS = (
    "lot_qty",
    "odd_qty",
    "notional_vnd",
    "stop_price",
    "stop_pct",
    "risk_vnd",
    "est_cost_vnd",
)


def _risk_block(st: StockState) -> dict[str, Any]:
    market, cfg = _market(st), st.cfg
    close = float(st.price["last_close"])
    atr14 = market.atr_now.get(st.ticker, math.nan)
    book: dict[str, Any] = {}
    for horizon, preview in st.previews.items():
        weight = float(preview.final.get(st.ticker, 0.0))
        sized = size_position(cfg, close, atr14, weight, preview.capital)
        book[horizon] = {
            "capital_vnd": preview.capital,
            "weight": weight,
            **{k: sized[k] for k in _BOOK_FIELDS},
        }
    return {"book": book}


def _quality_block(st: StockState) -> dict[str, Any]:
    from vnstratlab.data.gaps import GapError, load_gaps

    market = _market(st)
    gaps: list[str] = []
    if st.source != "synthetic":
        try:
            gaps = [g.id for g in load_gaps().with_status("open")]
        except GapError:
            gaps = []
    excl = market.frame.exclusions
    actions = market.frame.actions
    recent: list[dict[str, Any]] = []
    if not actions.empty:
        since = market.asof - timedelta(days=365)
        mine = actions[actions["ticker"] == st.ticker]
        for rec in mine.to_dict("records"):
            ex = pd.Timestamp(rec["ex_date"]).date()
            if since <= ex <= market.asof:
                recent.append(
                    {"ex_date": ex, "type": rec["type"], "ratio_or_amount": rec["ratio_or_amount"]}
                )
    return {
        "gaps": gaps,
        "exec_exclusions": int((excl["ticker"] == st.ticker).sum()) if not excl.empty else 0,
        "dq_findings_1y": st.dq_findings_1y,
        "corporate_actions": recent,
    }


def _recommendation(st: StockState) -> dict[str, Any]:
    by_horizon: dict[str, Any] = {}
    parts: list[str] = []
    for horizon, preview in st.previews.items():
        mine = [s for s in st.strategies if s["horizon"] == horizon]
        of = len(mine)
        consensus = sum(1 for s in mine if s["holds"])
        weight = float(preview.final.get(st.ticker, 0.0))
        if weight > 0.0:
            action = "MUA"
            reason = (
                f"{consensus}/{of} chiến lược đang giữ {st.ticker}; sau lớp rủi ro tỷ trọng "
                f"đề xuất {weight * 100:.1f}% sổ {HORIZON_VI[horizon]}."
            )
        elif consensus > 0:
            action = "GIỮ"
            reason = (
                f"{consensus}/{of} chiến lược giữ {st.ticker} nhưng danh mục kết hợp sau lớp "
                "rủi ro không có mã này: chưa nên mua thêm."
            )
        elif of == 0:
            action = "KHÔNG"
            reason = "Chưa có trial đã đăng ký cho khung này nên chưa có khuyến nghị."
        else:
            action = "KHÔNG"
            reason = f"Không chiến lược nào trong {of} chiến lược giữ {st.ticker}."
        by_horizon[horizon] = {
            "action": action,
            "consensus": consensus,
            "of": of,
            "weight": weight,
            "reason_vi": reason,
        }
        parts.append(f"{HORIZON_VI[horizon]}: {action} ({consensus}/{of})")
    summary = (
        f"{st.ticker} (xem trước, chưa qua lab chọn lọc): " + "; ".join(parts) + ". "
        "Trung bình đều các chiến lược đã đăng ký rồi qua lớp rủi ro."
    )
    return {"by_horizon": by_horizon, "summary_vi": summary, "disclaimer_vi": DISCLAIMER_VI}


def _chart(st: StockState) -> dict[str, Any]:
    market = _market(st)
    adj = st.adjusted.tail(CHART_SESSIONS)
    rows = _ticker_exec(market, st.ticker).set_index("date")["volume"]
    dates = [d for d in adj["date"]]
    volume = [int(rows[d]) if d in rows.index else None for d in dates]
    visible = set(dates)
    markers: list[dict[str, Any]] = []
    for s in st.strategies:
        history = st.decisions[s["trial_id"]]
        sequence = list(history.items())
        if market.asof not in history:
            sequence.append((market.asof, float(s["weight"])))
        previous = False
        for day, weight in sequence:
            now = weight > 0.0
            if now != previous and day in visible:
                markers.append(
                    {"date": day, "strategy_id": s["strategy_id"], "side": "in" if now else "out"}
                )
            previous = now
    markers.sort(key=lambda m: (m["date"], m["strategy_id"]))
    return {
        "basis": "adjusted",
        "dates": dates,
        "close": [float(v) for v in adj["adj_close"]],
        "volume": volume,
        "markers": markers,
    }


def stage_report(st: StockState) -> dict[str, Any]:
    """Assemble the contract's analysis body and store it (run folder and the latest copy)."""
    market = _market(st)
    st.analysis = json_dict(
        {
            "ticker": st.ticker,
            "asof": market.asof,
            "source": st.source,
            "synthetic": st.source == "synthetic",
            "label": data_label(st.source),
            "run_id": st.run_id,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "disclaimer_vi": DISCLAIMER_VI,
            "price": st.price,
            "features": st.features,
            "strategies": st.strategies,
            "excluded_strategies": st.excluded,
            "backtest": st.backtest,
            "risk": _risk_block(st),
            "quality": _quality_block(st),
            "recommendation": _recommendation(st),
            "chart": _chart(st),
        }
    )
    return {"ticker": st.ticker, "asof": market.asof.isoformat()}


def store_analysis(paths: AppPaths, run_dir: Path, analysis: Mapping[str, Any]) -> Path:
    """Write the JSON into the run folder and as the latest analysis of (source, ticker)."""
    from vnstratlab.runs.core import _write_json

    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "stock_analysis.json", analysis)
    latest = latest_path(paths, str(analysis["source"]), str(analysis["ticker"]))
    latest.parent.mkdir(parents=True, exist_ok=True)
    _write_json(latest, analysis)
    return latest


# ------------------------------------------------------------------ reading


def latest_path(paths: AppPaths, source: str, ticker: str) -> Path:
    if not TICKER_RE.match(ticker) or not re.match(r"^[A-Za-z0-9_-]+$", source):
        raise InsightError("bad_ticker", f"bad ticker or source: {ticker!r} {source!r}")
    return paths.logs_dir / "stock_analysis" / source / f"{ticker.upper()}.json"


def load_latest(paths: AppPaths, source: str, ticker: str) -> dict[str, Any] | None:
    path = latest_path(paths, source, ticker)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def compare(paths: AppPaths, source: str, tickers: Sequence[str]) -> dict[str, Any]:
    """The ``price`` and ``recommendation`` blocks of up to ``COMPARE_MAX`` stored analyses."""
    if not tickers or len(tickers) > COMPARE_MAX:
        raise InsightError("bad_tickers", f"give 1 to {COMPARE_MAX} tickers")
    found: list[dict[str, Any]] = []
    missing: list[str] = []
    for ticker in tickers:
        body = load_latest(paths, source, ticker)
        if body is None:
            missing.append(ticker.upper())
            continue
        found.append(
            {
                "ticker": body["ticker"],
                "asof": body["asof"],
                "run_id": body.get("run_id"),
                "price": body["price"],
                "recommendation": body["recommendation"],
            }
        )
    return {
        "source": source,
        "synthetic": source == "synthetic",
        "label": data_label(source),
        "disclaimer_vi": DISCLAIMER_VI,
        "tickers": found,
        "missing": missing,
    }


def list_stocks(cfg: AppConfig, paths: AppPaths, source: str) -> dict[str, Any]:
    """``GET /api/stocks``: every ticker of the store with its last close and 1-day change."""
    from vnstratlab.data.protocol import universe_tickers

    kind = kind_of_source(source)
    db = paths.market_db_for(kind)
    if not db.is_file():
        raise InsightError("no_data", f"no store for source {source!r}")
    with MarketStore(db, kind, read_only=True) as store:
        if not store.has_table("prices_adjusted"):
            raise InsightError("no_data", "no adjusted prices yet: run `vnstratlab data rebuild`")
        rows = store.connection.execute(
            "SELECT ticker, date, adj_close, signal_ok FROM prices_adjusted WHERE source = ? "
            "QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC) <= 2 "
            "ORDER BY ticker, date",
            [source],
        ).fetchall()
        execs = {
            str(t): float(c)
            for t, c in store.connection.execute(
                "SELECT ticker, close FROM prices_exec WHERE source = ? "
                "QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC) = 1",
                [source],
            ).fetchall()
        }
    universe = set(universe_tickers(cfg))
    by_ticker: dict[str, list[tuple[Any, ...]]] = {}
    for row in rows:
        by_ticker.setdefault(str(row[0]), []).append(row)
    out: list[dict[str, Any]] = []
    for ticker, pair in sorted(by_ticker.items()):
        last = pair[-1]
        change = float(last[2] / pair[-2][2] - 1.0) if len(pair) == 2 and pair[-2][2] else None
        out.append(
            {
                "ticker": ticker,
                "group": cfg.universe.sector if ticker in universe else None,
                "last": pd.Timestamp(last[1]).date().isoformat(),
                "last_close": execs.get(ticker),
                "change_1d": change,
                "in_universe": ticker in universe,
                "signal_ok": bool(last[3]) if last[3] is not None else True,
            }
        )
    return json_dict(
        {
            "source": source,
            "synthetic": source == "synthetic",
            "label": data_label(source),
            "disclaimer_vi": DISCLAIMER_VI,
            "tickers": out,
        }
    )


# ------------------------------------------------------------------ text for the CLI


def format_analysis(body: Mapping[str, Any]) -> str:
    """Console summary of one analysis: label, numbers, signals and the recommendation."""
    price = body["price"]
    change = price["change"]

    def pct(value: Any) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"

    lines = [
        str(body["label"]),
        f"{body['ticker']} | asof {body['asof']} | close {price['last_close']:,.0f} VND "
        f"| ATR14 {price['atr14'] if price['atr14'] is None else format(price['atr14'], ',.0f')}",
        "change  " + "  ".join(f"{k} {pct(v)}" for k, v in change.items()),
        f"52w high {price['high_52w']:,.0f} ({pct(price['dist_high_52w'])})  "
        f"low {price['low_52w']:,.0f} ({pct(price['dist_low_52w'])})  "
        f"vol20 {pct(price['vol_20d_ann'])}  maxDD 1y {pct(price['max_dd_1y'])}",
        "signals:",
    ]
    for s in body["strategies"]:
        mark = "HOLD" if s["holds"] else "-   "
        lines.append(
            f"  {mark} {s['horizon']:<6} {s['strategy_id']} {s['params']}  {s['reason_vi']}"
        )
    for s in body["excluded_strategies"]:
        lines.append(f"  skipped (not registered): {s['strategy_id']} {s['horizon']}")
    lines.append("recommendation:")
    for horizon, rec in body["recommendation"]["by_horizon"].items():
        lines.append(f"  {horizon:<6} {rec['action']:<5} {rec['reason_vi']}")
    for horizon, book in body["risk"]["book"].items():
        if book["weight"] > 0:
            stop = "n/a" if book["stop_price"] is None else f"{book['stop_price']:,.0f}"
            lines.append(
                f"  {horizon:<6} lots {book['lot_qty']} + odd {book['odd_qty']}, "
                f"notional {book['notional_vnd']:,.0f} VND, stop {stop}, "
                f"cost {book['est_cost_vnd']:,.0f}"
            )
    lines.append(str(body["recommendation"]["summary_vi"]))
    lines.append(str(body["recommendation"]["disclaimer_vi"]))
    return "\n".join(lines)


def parse_horizons(values: Sequence[str] | None) -> tuple[Horizon, ...]:
    """Validate a horizon list (default: all three)."""
    if not values:
        return HORIZONS
    bad = [v for v in values if v not in HORIZONS]
    if bad:
        raise InsightError("bad_horizon", f"unknown horizon(s) {bad}; expected {list(HORIZONS)}")
    return tuple(h for h in HORIZONS if h in values)
