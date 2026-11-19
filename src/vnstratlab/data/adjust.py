"""Adjusted prices for signals and reconstructed prices for execution (pure, no I/O).

Two series are built from stored ``prices_daily`` rows and ``corporate_actions`` (engine.md
section 2, "Phase 1 data constraints"):

* ``prices_adjusted`` for signals and features: backward, multiplicative (ratio method).
  Stock events scale earlier ``raw`` / ``synthetic`` rows by ``1 / (1 + ratio)``. Rows that are
  already ``split_adjusted`` are never scaled by a split again (ADR-007 section 5); cash
  dividends adjust every row: earlier rows are scaled by ``1 - D / P`` where ``P`` is the close
  of the session before the ex-date, expressed in that session's raw share basis.
* ``prices_exec`` for the simulator. ``raw`` / ``synthetic`` rows are copied unchanged.
  ``split_adjusted`` rows are rebuilt with ``F(t) = prod(1 + ratio_e)`` over the ticker's stock
  events with ``ex_date > t``: open/high/low/close ``= nearest_tick(stored * F(t))`` clipped to
  ``[floor, ceiling]``, volume ``= floor(stored / F(t))`` (assumption: Yahoo scales volume like
  prices; open question in docs/reports/data-source-yahoo.md) and
  ``ref(t) = round_down_to_tick(stored_close(t-1) * F(t))``. On a stock ex-date that is the
  theoretical ex-price; on a cash ex-date Yahoo's close is not cash-adjusted, so ``ref`` stays at
  the previous close (residual of GAP-02). Ceiling and floor follow from the HOSE rules.

Nothing is repaired or invented: a session with an error-level data-quality finding, or one with
no usable reference price, is left out of the execution series (the engine reads a missing row as
a suspension) and counted.

Scale-discontinuity check (engine.md section 2). The reconstruction assumes the stored history
is in ONE share scale. At each stock ex-date the first good session ``j`` on or after it is
compared with the previous good session ``p``: the reconstructed open
``open[j] * F(j)`` must lie within tolerance of ``close[p] * F(j)``, the previous reconstructed
close divided by every event ratio between the two sessions. ``F(p) / F(j)`` is exactly the
product of those ratios, so the stored ratios cancel and the test is ``|open[j] / close[p] - 1| <=
tolerance``: a plain discontinuity test on the stored series. The tolerance is the HOSE limit plus
1 % for tick rounding (:func:`precondition_tolerance`). It catches a store that is not in one
scale at an event (an unrescaled history, GAP-08) or a jump beyond the daily limit. It does NOT
detect a stored ratio that is wrong but was applied consistently by the source, a reverse split,
or an event whose true ratio is below the tolerance (GAP-06). A ticker that fails is excluded
from execution (kind ``scale_discontinuity``); an event with only bad sessions after it is
excluded as ``precondition_unverifiable``. Every exclusion is counted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Collection

    from vnstratlab.data.protocol import TickTable

ADJ_METHOD = "ratio-v1"
EXEC_BASIS = "exec_reconstructed"
SPLIT_ADJUSTED = "split_adjusted"
# [VERIFY] Whether Yahoo's dividend amounts are split-adjusted is NOT settled by the repository
# fixtures (docs/reports/data-source-yahoo.md). Until evidence says yes, amounts are used as
# stored; flipping this (or passing the argument) multiplies them by F(ex_date).
DIVIDENDS_SPLIT_ADJUSTED = False
_TOLERANCE_SLACK = 0.01
_STOCK_TYPES = ("stock", "bonus")

ADJUSTED_COLUMNS = (
    "ticker",
    "date",
    "source",
    "price_basis",
    "adj_open",
    "adj_high",
    "adj_low",
    "adj_close",
    "adj_factor",
    "adj_version",
    "dq_error",
)
EXEC_COLUMNS = (
    "ticker",
    "date",
    "source",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ref_price",
    "ceiling",
    "floor",
    "price_basis",
    "stock_factor",
)
EXCLUSION_COLUMNS = ("source", "ticker", "kind", "date", "detail")
_NEEDED = (
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ref_price",
    "price_basis",
    "source",
)

FloatArray = npt.NDArray[np.float64]


def precondition_tolerance(ticks: TickTable) -> float:
    """Allowed relative deviation of the ex-date open: the daily price limit plus 1 %."""
    return ticks.limit_pct + _TOLERANCE_SLACK


@dataclass(frozen=True)
class Exclusion:
    """One thing left out of the execution series (``date`` is the session, or for a
    precondition failure the ex-date of the failing event).

    Kinds: ``scale_discontinuity`` / ``precondition_unverifiable`` (the whole ticker),
    ``dq_error`` (one session with an error-level
    data-quality finding), ``no_reference`` (one session without a usable reference price).
    """

    ticker: str
    kind: str
    date: date | None
    detail: str


@dataclass(frozen=True)
class RebuildReport:
    """Counts of one rebuild; every exclusion is listed in ``exclusions``."""

    source: str
    price_rows: int
    adjusted_rows: int
    exec_rows: int
    excluded_tickers: tuple[str, ...]
    excluded_ticker_rows: int
    bad_rows_omitted: int
    no_reference_omitted: int
    exclusions: tuple[Exclusion, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RebuildResult:
    adjusted: pd.DataFrame
    execution: pd.DataFrame
    report: RebuildReport
    exclusions: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)


@dataclass(frozen=True)
class _Events:
    stock: list[tuple[date, float]]
    cash: list[tuple[date, float]]


def _events(actions: pd.DataFrame, ticker: str) -> _Events:
    stock: list[tuple[date, float]] = []
    cash: list[tuple[date, float]] = []
    if not actions.empty:
        for r in actions[actions["ticker"] == ticker].to_dict("records"):
            amount = r["ratio_or_amount"]
            if amount is None or not np.isfinite(amount) or amount <= 0:
                continue
            day = pd.Timestamp(r["ex_date"]).date()
            if r["type"] in _STOCK_TYPES:
                stock.append((day, float(amount)))
            elif r["type"] == "cash":
                cash.append((day, float(amount)))
    return _Events(sorted(stock), sorted(cash))


def _version(events: _Events, dividends_split_adjusted: bool) -> str:
    text = f"{ADJ_METHOD}|{int(dividends_split_adjusted)}|{events.stock}|{events.cash}"
    return f"{ADJ_METHOD}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def _factor(ordinals: npt.NDArray[np.int64], stock: list[tuple[date, float]]) -> FloatArray:
    """``F`` for each ordinal date: product of ``1 + ratio`` over events with ex_date > date."""
    factor = np.ones(len(ordinals), dtype=np.float64)
    for ex_date, ratio in stock:
        factor[ordinals < ex_date.toordinal()] *= 1.0 + ratio
    return factor


def _factor_at(day: date, stock: list[tuple[date, float]]) -> float:
    out = 1.0
    for ex_date, ratio in stock:
        if ex_date > day:
            out *= 1.0 + ratio
    return out


def build_series(
    prices: pd.DataFrame,
    actions: pd.DataFrame,
    ticks: TickTable,
    bad_rows: Collection[tuple[str, date]] = (),
    dividends_split_adjusted: bool = DIVIDENDS_SPLIT_ADJUSTED,
) -> RebuildResult:
    """Build the adjusted and execution series of ONE source.

    ``prices`` holds stored ``prices_daily`` rows of that source; ``actions`` its corporate
    actions. ``bad_rows`` are ``(ticker, date)`` pairs with an error-level DQ finding. The
    result is deterministic: rows sorted by ticker and date, no timestamps.
    """
    missing = [c for c in _NEEDED if c not in prices.columns]
    if missing:
        raise ValueError(f"prices are missing columns: {', '.join(missing)}")
    sources = sorted({str(s) for s in prices["source"].unique()})
    if len(sources) > 1:
        raise ValueError(f"build_series works on one source at a time, got {sources}")
    source = sources[0] if sources else ""
    bad = set(bad_rows)
    frame = prices.copy()
    frame["date"] = [pd.Timestamp(d).date() for d in frame["date"]]
    frame = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    tolerance = precondition_tolerance(ticks)

    adjusted: list[pd.DataFrame] = []
    execution: list[pd.DataFrame] = []
    exclusions: list[Exclusion] = []
    warnings: list[str] = []
    excluded: list[str] = []
    excluded_rows = 0
    for ticker, group in frame.groupby("ticker", sort=True):
        name = str(ticker)
        events = _events(actions, name)
        adjusted.append(_adjust(group, name, events, bad, dividends_split_adjusted, warnings))
        built, found, dropped_all = _execution(group, name, events, bad, ticks, tolerance)
        exclusions += found
        if dropped_all:
            excluded.append(name)
            # rows dropped only because of the ticker; bad rows are counted as dq_error
            only_ticker = (group["price_basis"] == SPLIT_ADJUSTED).to_numpy() & ~np.array(
                [(name, d) in bad for d in group["date"]], dtype=bool
            )
            excluded_rows += int(only_ticker.sum())
        execution.append(built)

    adj = _concat(adjusted, ADJUSTED_COLUMNS)
    exe = _concat(execution, EXEC_COLUMNS)
    exclusions.sort(key=lambda e: (e.ticker, e.date or date.min, e.kind))
    kinds = [e.kind for e in exclusions]
    report = RebuildReport(
        source=source,
        price_rows=len(frame),
        adjusted_rows=len(adj),
        exec_rows=len(exe),
        excluded_tickers=tuple(excluded),
        excluded_ticker_rows=excluded_rows,
        bad_rows_omitted=kinds.count("dq_error"),
        no_reference_omitted=kinds.count("no_reference"),
        exclusions=tuple(exclusions),
        warnings=tuple(warnings),
    )
    table = pd.DataFrame(
        {
            "source": source,
            "ticker": [e.ticker for e in exclusions],
            "kind": [e.kind for e in exclusions],
            "date": [e.date for e in exclusions],
            "detail": [e.detail for e in exclusions],
        },
        columns=list(EXCLUSION_COLUMNS),
    )
    return RebuildResult(adj, exe, report, table)


def _concat(parts: list[pd.DataFrame], columns: tuple[str, ...]) -> pd.DataFrame:
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame({c: [] for c in columns})
    return pd.concat(parts, ignore_index=True)[list(columns)]


# ------------------------------------------------------------------ adjusted series


def _adjust(
    group: pd.DataFrame,
    ticker: str,
    events: _Events,
    bad: set[tuple[str, date]],
    dividends_split_adjusted: bool,
    warnings: list[str],
) -> pd.DataFrame:
    dates = list(group["date"])
    ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
    basis = group["price_basis"].to_numpy(dtype=object)
    is_split = basis == SPLIT_ADJUSTED
    close = group["close"].to_numpy(dtype=np.float64)
    stock_f = _factor(ordinals, events.stock)
    multiplier = np.ones(len(group), dtype=np.float64)
    for ex_date, ratio in events.stock:
        multiplier[(ordinals < ex_date.toordinal()) & ~is_split] /= 1.0 + ratio
    for ex_date, amount in events.cash:
        before = int(np.searchsorted(ordinals, ex_date.toordinal(), side="left")) - 1
        if before < 0:
            continue  # no stored session before the ex-date: nothing to adjust
        # previous close in its raw share basis; split_adjusted closes are divided by F
        prev_raw = close[before] * (stock_f[before] if is_split[before] else 1.0)
        paid = amount * (_factor_at(ex_date, events.stock) if dividends_split_adjusted else 1.0)
        ratio_paid = paid / prev_raw
        if not np.isfinite(ratio_paid) or ratio_paid >= 1.0:
            warnings.append(f"{ticker} {ex_date}: cash dividend {amount} ignored (>= close)")
            continue
        multiplier[: before + 1] *= 1.0 - ratio_paid
    out = pd.DataFrame(
        {
            "ticker": ticker,
            "date": dates,
            "source": group["source"].to_numpy(dtype=object),
            "price_basis": basis,
            "adj_open": group["open"].to_numpy(dtype=np.float64) * multiplier,
            "adj_high": group["high"].to_numpy(dtype=np.float64) * multiplier,
            "adj_low": group["low"].to_numpy(dtype=np.float64) * multiplier,
            "adj_close": close * multiplier,
            "adj_factor": multiplier,
            "adj_version": _version(events, dividends_split_adjusted),
            "dq_error": [(ticker, d) in bad for d in dates],
        }
    )
    return out


# ------------------------------------------------------------------ execution series


def _precondition(
    ticker: str,
    dates: list[date],
    open_: FloatArray,
    close: FloatArray,
    stock_f: FloatArray,
    events: _Events,
    skip: npt.NDArray[np.bool_],
    tolerance: float,
) -> Exclusion | None:
    """First stock event whose ex-date shows a scale discontinuity (see module docstring)."""
    ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
    good = np.flatnonzero(~skip)
    checked: set[int] = set()
    for ex_date, _ in events.stock:
        start = int(np.searchsorted(ordinals, ex_date.toordinal(), side="left"))
        if start >= len(dates):
            continue  # no stored session on or after the ex-date: nothing to execute
        after = good[good >= start]
        if len(after) == 0:
            return Exclusion(
                ticker,
                "precondition_unverifiable",
                ex_date,
                "every stored session on or after the ex-date is a bad source row",
            )
        j = int(after[0])
        before = good[good < j]
        if len(before) == 0 or j in checked:
            continue  # no earlier session to compare with, or already compared
        checked.add(j)
        p = int(before[-1])
        expected = close[p] * stock_f[j]
        observed = open_[j] * stock_f[j]
        deviation = abs(observed / expected - 1.0)
        if not deviation <= tolerance:
            ratios = [r for d, r in events.stock if dates[p] < d <= dates[j]]
            return Exclusion(
                ticker,
                "scale_discontinuity",
                ex_date,
                f"open {open_[j]:.2f} on {dates[j]} vs previous close {close[p]:.2f} on "
                f"{dates[p]} (deviation {deviation:.1%} > {tolerance:.1%}; stored event "
                f"ratio(s) {', '.join(f'{r:.4f}' for r in ratios)})",
            )
    return None


def _execution(
    group: pd.DataFrame,
    ticker: str,
    events: _Events,
    bad: set[tuple[str, date]],
    ticks: TickTable,
    tolerance: float,
) -> tuple[pd.DataFrame, list[Exclusion], bool]:
    """``(execution rows, exclusions, ticker_excluded)`` for one ticker."""
    dates = list(group["date"])
    ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
    is_split = (group["price_basis"] == SPLIT_ADJUSTED).to_numpy()
    is_bad = np.array([(ticker, d) in bad for d in dates], dtype=bool)
    found = [
        Exclusion(ticker, "dq_error", d, "error-level data-quality finding in the latest run")
        for d, b in zip(dates, is_bad, strict=True)
        if b
    ]
    keep = ~is_bad
    open_ = group["open"].to_numpy(dtype=np.float64)
    high = group["high"].to_numpy(dtype=np.float64)
    low = group["low"].to_numpy(dtype=np.float64)
    close = group["close"].to_numpy(dtype=np.float64)
    stored_ref = group["ref_price"].to_numpy(dtype=np.float64)
    stock_f = _factor(ordinals, events.stock)

    ticker_excluded = False
    if is_split.any():
        failure = _precondition(ticker, dates, open_, close, stock_f, events, is_bad, tolerance)
        if failure is not None:
            found.append(failure)
            keep &= ~is_split
            ticker_excluded = True

    base = np.empty(len(group), dtype=np.float64)
    base[0] = stored_ref[0]
    base[1:] = close[:-1]
    ref = ticks.round_down(base * stock_f)
    no_ref = is_split & ~np.isfinite(ref) & keep
    found += [
        Exclusion(ticker, "no_reference", d, "no previous close or stored reference price")
        for d, n in zip(dates, no_ref, strict=True)
        if n
    ]
    keep &= ~no_ref

    ceiling_, floor_ = ticks.limits(np.where(np.isfinite(ref), ref, 1.0))

    def rebuilt(values: FloatArray) -> FloatArray:
        return np.clip(ticks.nearest(values * stock_f), floor_, ceiling_)

    volume = np.floor(np.round(group["volume"].to_numpy(dtype=np.float64) / stock_f, 6))
    stored_ceiling = group["ceiling"].to_numpy(dtype=np.float64)
    stored_floor = group["floor"].to_numpy(dtype=np.float64)
    out = pd.DataFrame(
        {
            "ticker": ticker,
            "date": dates,
            "source": group["source"].to_numpy(dtype=object),
            "open": np.where(is_split, rebuilt(open_), open_),
            "high": np.where(is_split, rebuilt(high), high),
            "low": np.where(is_split, rebuilt(low), low),
            "close": np.where(is_split, rebuilt(close), close),
            "volume": np.where(is_split, volume, group["volume"].to_numpy(dtype=np.float64)),
            "ref_price": np.where(is_split, ref, stored_ref),
            "ceiling": np.where(is_split, ceiling_, stored_ceiling),
            "floor": np.where(is_split, floor_, stored_floor),
            "price_basis": np.where(
                is_split, EXEC_BASIS, group["price_basis"].to_numpy(dtype=object)
            ),
            "stock_factor": np.where(is_split, stock_f, 1.0),
        }
    )
    out["volume"] = out["volume"].astype(np.int64)
    return out[keep].reset_index(drop=True), found, ticker_excluded


def execution_actions(
    actions: pd.DataFrame,
    split_adjusted_tickers: Collection[str],
    dividends_split_adjusted: bool = DIVIDENDS_SPLIT_ADJUSTED,
) -> pd.DataFrame:
    """Actions for the engine. Cash amounts of reconstructed tickers are multiplied by
    ``F(ex_date)`` only when the dividend amounts are known to be split-adjusted ([VERIFY])."""
    out = actions.copy()
    if out.empty or not dividends_split_adjusted:
        return out
    wanted = set(split_adjusted_tickers)
    for ticker in wanted:
        stock = _events(actions, ticker).stock
        mask = ((out["ticker"] == ticker) & (out["type"] == "cash")).to_numpy()
        out.loc[mask, "ratio_or_amount"] = [
            float(a) * _factor_at(pd.Timestamp(d).date(), stock)
            for a, d in zip(out.loc[mask, "ratio_or_amount"], out.loc[mask, "ex_date"], strict=True)
        ]
    return out
