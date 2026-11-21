"""Point-in-time features of the equity universe (pure; no I/O, no DuckDB). Card P1-T10.

``compute_features(adjusted, exec_, universe, asof_dates=None, actions=None)`` returns one row per
(ticker, date) of the ticker's GOOD sessions, with the columns of ``FEATURE_COLUMNS`` and
``feature_version``. Every feature at date ``t`` uses rows ``<= t`` only.

Inputs and basis (docs/data-pipeline.md, "Which series feeds what")
* returns, ratios and normalised indicators read ``prices_adjusted`` (``adj_*``);
* level and liquidity features (52-week distances, value traded, volume ratio, ATR) read
  ``prices_exec``. Distances and the volume ratio are restated into the share basis of day ``t``
  with the stock ex-date factors of ``actions`` (see ``groups.price_features``);
* ``atr_14`` is ``risk.atr.atr`` over the execution rows with the engine's ex-date factors.

Missing sessions
* A row with ``signal_ok = false`` (``dq_error``, ``scale_outlier_row``, ``scale_step_before``,
  ``non_hose_history``, ``duplicate_session``) is MISSING for every feature: it is dropped before
  any window is built and gets no output row. Nothing is interpolated.
* Windows count the ticker's stored good sessions, so window lengths are in AVAILABLE sessions,
  not calendar days. Recent real history misses about one session in five (GAP-07), so a
  250-session window spans more than 250 trading days there; the dry run prints the actual span.
  ``sessions_in_window`` sanity note: ``calendar_span_sessions(dates, n)`` (below) gives the
  median number of weekdays a window of ``n`` sessions covers; ``features build --dry-run``
  prints it. No resampling to the calendar.
* A good session without an execution row (ticker excluded, row omitted) has NaN level and
  liquidity features, and so does every window that contains it.

Cross-section (the tradable universe on a date)
* ``universe`` is the ticker list from config (membership plus known exits; plan section 0
  ``survivorship_warning``: it is today's list until P1-T05). A ticker is in the cross-section on
  date ``d`` when it has a good session on ``d`` and a non-NaN input.
* ``rs_20d_vs_group_median = ret_20d - median(ret_20d)``; ``ret_5d_vs_group_median`` likewise.
* ``rs_20d_rank`` = ``rank(ret_20d) / n`` with ties averaged, ``n`` the tickers with a ``ret_20d``
  that day, so the strongest ticker is 1.0 and the weakest ``1 / n``.
* Market context uses the EQUAL-WEIGHT UNIVERSE INDEX (it replaces VN30, GAP-03): its daily return
  is the mean of the session returns of the tickers that have one on that date, chained from 1.0
  on the first date. ``group_ew_vs_ma50 = index / mean(index, 50 dates) - 1``, ``group_ret_12m =
  index / index[250 dates back] - 1`` (windows in dates of the index, i.e. dates on which any
  universe ticker has a good session), ``group_breadth_ma50`` = share of the cross-section whose
  adjusted close is above its own 50-session average.

Warm-up: a feature is NaN until its window is full; never back-filled.

Deferred (GAP-11, P1-T07): valuation (P/B, E/P, ROE-justified P/B gap) and asset quality (NPL,
coverage, ROE). No empty columns exist for them; strategies S10-S13 stay blocked.

``feature_version`` hashes the code version, the windows and the sorted ``(ticker, adj_version)``
pairs of the input, one value for the whole build: a change of any ticker's ``adj_version``
changes it (cross-sectional features depend on every ticker).
"""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Collection, Iterable
from datetime import date

import numpy as np
import pandas as pd

from vnstratlab.features.groups import (
    FEATURE_COLUMNS,
    INDEX_MA,
    INDEX_RET,
    RS_WINDOW,
    WINDOWS,
    FloatArray,
    price_features,
)
from vnstratlab.risk.atr import ATR_WINDOW, atr

FEATURES_CODE_VERSION = "features-v1"
OUTPUT_COLUMNS = ("ticker", "date", *FEATURE_COLUMNS, "feature_version")
_STOCK_TYPES = ("stock", "bonus")


class FeatureError(ValueError):
    """Inputs the feature computation cannot use."""


def feature_version(adjusted: pd.DataFrame, universe: Collection[str]) -> str:
    """``features-v1:<hash>`` of the code version, windows and the input ``adj_version`` pairs."""
    wanted = set(universe)
    frame = adjusted[adjusted["ticker"].isin(wanted)]
    pairs = sorted(
        {(str(t), str(v)) for t, v in zip(frame["ticker"], frame["adj_version"], strict=True)}
    )
    text = f"{FEATURES_CODE_VERSION}|{sorted(WINDOWS.items())}|{pairs}"
    return f"{FEATURES_CODE_VERSION}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def calendar_span_sessions(dates: Iterable[date], n: int) -> float:
    """Median number of weekdays spanned by ``n`` consecutive stored sessions (sanity note A4).

    ``n`` when no session is missing; larger when sessions are missing. NaN when there are fewer
    than ``n`` dates."""
    days = np.array(sorted(pd.Timestamp(d).date() for d in dates), dtype="datetime64[D]")
    if len(days) < n or n < 2:
        return float("nan")
    spans = np.busday_count(days[: len(days) - n + 1], days[n - 1 :]) + 1
    return float(statistics.median(int(s) for s in spans))


def _prepare(frame: pd.DataFrame, columns: Iterable[str], what: str) -> pd.DataFrame:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise FeatureError(f"{what} lacks columns {missing}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"])
    return out


def _col(frame: pd.DataFrame, name: str) -> FloatArray:
    return frame[name].to_numpy(dtype=np.float64)


def _event_rows(dates: pd.DatetimeIndex, events: list[tuple[pd.Timestamp, float]]) -> FloatArray:
    """Per-row ex-date factor: ``1 + ratio`` on the first stored row on or after the ex-date.

    Events after the last stored row are ignored (unknown at that date); same rule as the
    engine's ``_add_factors``."""
    factors = np.ones(len(dates), dtype=np.float64)
    for ex_date, ratio in events:
        row = int(dates.searchsorted(ex_date, side="left"))
        if row < len(dates):
            factors[row] *= 1.0 + ratio
    return factors


def compute_features(
    adjusted: pd.DataFrame,
    exec_: pd.DataFrame,
    universe: Collection[str],
    asof_dates: Collection[date] | None = None,
    actions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Features of every (ticker, good session). See the module docstring.

    ``adjusted``: ``prices_adjusted`` rows (ticker, date, adj_high, adj_close, adj_version and
    optionally signal_ok). ``exec_``: ``prices_exec`` rows (ticker, date, high, low, close,
    volume). ``actions``: corporate actions (ticker, ex_date, type, ratio_or_amount); only
    ``stock`` / ``bonus`` rows count, and the caller removes events the rebuild marked suspect
    (``data.pipeline.load_execution_frame`` does). ``asof_dates`` limits the OUTPUT rows (the
    computation always uses the full history of the input).
    """
    adj = _prepare(adjusted, ("ticker", "date", "adj_high", "adj_close", "adj_version"), "adjusted")
    ex = _prepare(exec_, ("ticker", "date", "high", "low", "close", "volume"), "exec_")
    tickers = sorted(set(universe))
    version = feature_version(adj, tickers)
    adj = adj[adj["ticker"].isin(tickers)]
    if "signal_ok" in adj.columns:
        adj = adj[adj["signal_ok"].fillna(True).astype(bool)]  # signal_ok = false is MISSING
    ex = ex[ex["ticker"].isin(tickers)]

    stock_events: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    if actions is not None and not actions.empty:
        stock = actions[actions["type"].isin(_STOCK_TYPES)]
        for t, d, r in zip(
            stock["ticker"], stock["ex_date"], stock["ratio_or_amount"], strict=True
        ):
            stock_events.setdefault(str(t), []).append((pd.Timestamp(d), float(r)))

    parts: list[pd.DataFrame] = []
    for ticker in tickers:
        a = adj[adj["ticker"] == ticker].sort_values("date").drop_duplicates("date", keep="last")
        if a.empty:
            continue
        dates = pd.DatetimeIndex(a["date"])
        e = ex[ex["ticker"] == ticker].sort_values("date").drop_duplicates("date", keep="last")
        e = e[e["date"].isin(dates)]  # a row that is missing for signals is missing here too
        events = sorted(stock_events.get(ticker, []))
        atr_values = np.full(len(a), np.nan)
        if not e.empty:
            ex_dates = pd.DatetimeIndex(e["date"])
            series = atr(
                e["high"].reset_index(drop=True),
                e["low"].reset_index(drop=True),
                e["close"].reset_index(drop=True),
                ATR_WINDOW,
                _event_rows(ex_dates, events).tolist(),
            )
            atr_values = (
                pd.Series(series.to_numpy(), index=ex_dates).reindex(dates).to_numpy(dtype=float)
            )
        aligned = e.set_index("date").reindex(dates)

        computed = price_features(
            _col(a, "adj_close"),
            _col(a, "adj_high"),
            _col(aligned, "close"),
            _col(aligned, "high"),
            _col(aligned, "low"),
            _col(aligned, "volume"),
            np.cumprod(_event_rows(dates, events)),
            atr_values,
        )
        part = pd.DataFrame(computed)
        part.insert(0, "date", dates)
        part.insert(0, "ticker", ticker)
        parts.append(part)

    if not parts:
        return pd.DataFrame({c: pd.Series(dtype=float) for c in OUTPUT_COLUMNS})
    panel = pd.concat(parts, ignore_index=True)
    panel = _cross_section(panel)
    panel["feature_version"] = version
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    if asof_dates is not None:
        keep = {pd.Timestamp(d) for d in asof_dates}
        panel = panel[panel["date"].isin(keep)].reset_index(drop=True)
    out = panel[list(OUTPUT_COLUMNS)].copy()
    numeric = list(FEATURE_COLUMNS)
    out[numeric] = out[numeric].replace([np.inf, -np.inf], np.nan)
    out["date"] = [d.date() for d in out["date"]]
    return out


def _cross_section(panel: pd.DataFrame) -> pd.DataFrame:
    """Relative-strength, short-term group deviation and market-context columns."""
    by_date = panel.groupby("date", sort=True)
    ret20 = panel[f"ret_{RS_WINDOW}d"]
    panel["rs_20d_vs_group_median"] = ret20 - by_date[f"ret_{RS_WINDOW}d"].transform("median")
    panel["rs_20d_rank"] = by_date[f"ret_{RS_WINDOW}d"].rank(pct=True, method="average")
    panel["ret_5d_vs_group_median"] = panel["ret_5d"] - by_date["ret_5d"].transform("median")

    daily = by_date["_ret_1d"].mean().fillna(0.0)  # equal-weight universe index
    index = (1.0 + daily).cumprod()
    ma = index.rolling(INDEX_MA, min_periods=INDEX_MA).mean()
    market = pd.DataFrame(
        {
            "group_ew_vs_ma50": index / ma - 1.0,
            "group_ret_12m": index / index.shift(INDEX_RET) - 1.0,
            "group_breadth_ma50": by_date["_above_ma50"].mean(),
        }
    )
    panel = panel.join(market, on="date")
    return panel.drop(columns=["_ret_1d", "_above_ma50"])
