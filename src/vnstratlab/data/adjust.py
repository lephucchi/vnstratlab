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
or an event whose true ratio is below the tolerance (GAP-06).

A failing event is classified before anything is excluded (P1-T06b; Yahoo evidence in
docs/reports/data-source-yahoo.md):

* outlier row (``scale_outlier_row``): the first ``k <= MAX_OUTLIER_SESSIONS`` good sessions from
  the ex-date deviate, but the next good session is back within tolerance of the previous good
  close in the same basis (``close[p] * F[j]``), is nearer that old level than the stepped level
  (``close[p]`` times the stored ratios) and breaks continuity with the last outlier close
  (P1-T06c: a persistent step followed by a normal move is not "back in scale"). Those ``k`` rows
  are omitted, the ticker stays.
  The first session after them takes the last non-omitted close as its reference (the last traded
  price, as after a suspension); no price is invented or interpolated.
* persistent step (``scale_step_before``): the open steps by the stored event ratio (within
  tolerance) and none of the next ``MAX_OUTLIER_SESSIONS + 1`` good sessions returns to the old
  level (nearer the old level than the stepped one, within tolerance), while the first of them
  continues from the new level. The event is *suspect*: it does not
  match a real price adjustment at that date, so it is never applied to holdings
  (``load_execution_frame`` drops it). Every row of the ticker through the first good session on or
  after the ex-date is excluded (one exclusion row with the count, dated the ex-date); later rows
  stay.
* anything else keeps the whole-ticker exclusion (``scale_discontinuity``); an event with only bad
  sessions after it is excluded as ``precondition_unverifiable``.

Pre-HOSE history (``non_hose_history``, GAP-04): on a ``split_adjusted`` ticker a session whose
open or close is more than the tolerance away from the previous stored close is outside the HOSE
band. The execution series starts after the LAST such session that is followed by at least
``MIN_HOSE_RUN = 60`` in-band sessions; rows up to and including it are excluded (one
exclusion row with the count, dated the last excluded session). Only an out-of-band session that
belongs to a cluster may be that cut point (P1-T06d): the trailing window of ``NON_HOSE_WINDOW``
good sessions ending at it must hold at least ``NON_HOSE_MIN_OUT_OF_BAND`` out-of-band sessions.
An isolated out-of-band session (a data glitch) is neither a cut point nor does it interrupt the
run of in-band sessions. Sessions within
``MAX_OUTLIER_SESSIONS`` of a stock ex-date and the first session on or after a cash ex-date (the
reference price drops by the dividend) are not tested; a history with no such session is left as
is. Every row is counted once, under the first of: ``dq_error``, ``non_hose_history``,
``scale_outlier_row``, ``scale_step_before``.

``prices_adjusted.signal_ok`` is false for exactly the rows counted under ``dq_error``,
``non_hose_history``, ``scale_outlier_row`` and ``scale_step_before``; features treat a false row
as missing (P1-T10). A whole-ticker exclusion does not clear it.
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
# Yahoo's cash dividend amounts are split-adjusted (evidence: docs/reports/data-source-yahoo.md
# section 5): the raw-basis payment is amount * F(ex_date). Applies to ``split_adjusted`` rows
# only; ``raw`` / ``synthetic`` amounts are used as stored.
DIVIDENDS_SPLIT_ADJUSTED = True
# Most consecutive good sessions from a stock ex-date that count as one out-of-scale episode.
MAX_OUTLIER_SESSIONS = 2
# Consecutive in-band sessions that end the pre-HOSE history window.
MIN_HOSE_RUN = 60
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
    "signal_ok",
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
EXCLUSION_COLUMNS = ("source", "ticker", "kind", "date", "detail", "rows")
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
    ``dq_error`` (one session with an error-level data-quality finding), ``no_reference`` (one
    session without a usable reference price), ``scale_outlier_row`` (one out-of-scale session),
    ``scale_step_before`` (``rows`` sessions through a suspect event's first session; ``date`` is
    the ex-date) and ``non_hose_history`` (``rows`` sessions up to ``date``).
    """

    ticker: str
    kind: str
    date: date | None
    detail: str
    rows: int = 1


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
    outlier_rows_omitted: int = 0
    step_rows_excluded: int = 0
    suspect_events: int = 0
    non_hose_rows_excluded: int = 0
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
        built, found, run = _execution(group, name, events, bad, ticks, tolerance)
        exclusions += found
        if run.ticker_excluded:
            excluded.append(name)
            excluded_rows += run.ticker_rows  # rows not already counted under another kind
        execution.append(built)
        # a suspect event (persistent step) is no share-count event: signals ignore it as well
        applied = _Events([e for e in events.stock if e[0] not in run.suspect], events.cash)
        adjusted.append(
            _adjust(group, name, applied, bad, dividends_split_adjusted, warnings, run.unusable)
        )

    adj = _concat(adjusted, ADJUSTED_COLUMNS)
    exe = _concat(execution, EXEC_COLUMNS)
    exclusions.sort(key=lambda e: (e.ticker, e.date or date.min, e.kind))

    def rows_of(kind: str) -> int:
        return sum(e.rows for e in exclusions if e.kind == kind)

    report = RebuildReport(
        source=source,
        price_rows=len(frame),
        adjusted_rows=len(adj),
        exec_rows=len(exe),
        excluded_tickers=tuple(excluded),
        excluded_ticker_rows=excluded_rows,
        bad_rows_omitted=rows_of("dq_error"),
        no_reference_omitted=rows_of("no_reference"),
        outlier_rows_omitted=rows_of("scale_outlier_row"),
        step_rows_excluded=rows_of("scale_step_before"),
        suspect_events=sum(1 for e in exclusions if e.kind == "scale_step_before"),
        non_hose_rows_excluded=rows_of("non_hose_history"),
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
            "rows": [e.rows for e in exclusions],
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
    unusable: npt.NDArray[np.bool_] | None = None,
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
        # only split_adjusted sources carry split-adjusted amounts; raw / synthetic stay as stored
        scale = (
            _factor_at(ex_date, events.stock)
            if dividends_split_adjusted and is_split[before]
            else 1.0
        )
        paid = amount * scale
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
            "signal_ok": ~unusable if unusable is not None else np.ones(len(group), dtype=bool),
        }
    )
    return out


# ------------------------------------------------------------------ execution series


@dataclass(frozen=True)
class _Outlier:
    row: int
    previous: int
    back: int  # first good session back within tolerance


@dataclass(frozen=True)
class _Step:
    ex_dates: list[date]  # every stock ex-date whose first good session is ``first``
    first: int
    previous: int
    detail: str


@dataclass(frozen=True)
class _ScaleCheck:
    failure: Exclusion | None = None
    outliers: list[_Outlier] = field(default_factory=list)
    steps: list[_Step] = field(default_factory=list)


@dataclass(frozen=True)
class _Run:
    """Ticker-level outcome of :func:`_execution`."""

    ticker_excluded: bool = False
    ticker_rows: int = 0  # rows lost only to the ticker exclusion (not counted under another kind)
    suspect: frozenset[date] = frozenset()  # ex-dates of suspect events
    unusable: npt.NDArray[np.bool_] | None = None  # rows signals must treat as missing


# Cluster rule of the non-HOSE cut (P1-T06d). PENDING OWNER APPROVAL: keep as module constants.
# Real pre-HOSE history shows ~16-23 out-of-band sessions per year; other tickers at most 5.
NON_HOSE_WINDOW = 250  # trailing good sessions inspected for a candidate cut session
NON_HOSE_MIN_OUT_OF_BAND = 10  # out-of-band sessions the window must hold for the cut to qualify


def _non_hose_cut(
    ordinals: npt.NDArray[np.int64],
    open_: FloatArray,
    close: FloatArray,
    events: _Events,
    tolerance: float,
    is_bad: npt.NDArray[np.bool_],
) -> int | None:
    """Index of the last session of the pre-HOSE history, or ``None`` (see module docstring).

    A candidate must belong to a cluster (``NON_HOSE_WINDOW`` / ``NON_HOSE_MIN_OUT_OF_BAND``,
    pending owner approval). Bad source rows are neutral and never serve as the previous close:
    each move is measured against the previous good close (as in :func:`_scale_check`).
    """
    n = len(ordinals)
    if n < MIN_HOSE_RUN:
        return None
    neutral = np.zeros(n, dtype=bool)
    for ex_date, _ in events.stock:
        start = int(np.searchsorted(ordinals, ex_date.toordinal(), side="left"))
        neutral[start : start + MAX_OUTLIER_SESSIONS + 1] = True
    for ex_date, _ in events.cash:  # the reference price drops by the dividend on its ex-date
        start = int(np.searchsorted(ordinals, ex_date.toordinal(), side="left"))
        neutral[start : start + 1] = True
    outside = np.zeros(n, dtype=bool)
    good = np.flatnonzero(~is_bad)
    if len(good) > 1:
        cur, prev = good[1:], good[:-1]  # each good session and the good session before it
        with np.errstate(divide="ignore", invalid="ignore"):
            move_open = np.abs(open_[cur] / close[prev] - 1.0)
            move_close = np.abs(close[cur] / close[prev] - 1.0)
        outside[cur] = ((move_open > tolerance) | (move_close > tolerance)) & ~neutral[cur]
    # out-of-band sessions in the window of NON_HOSE_WINDOW good sessions ending at each good one
    cum = np.concatenate(([0], np.cumsum(outside[good])))
    rank = np.arange(len(good))
    window = cum[rank + 1] - cum[np.maximum(rank + 1 - NON_HOSE_WINDOW, 0)]
    clustered = np.zeros(n, dtype=bool)
    clustered[good] = window >= NON_HOSE_MIN_OUT_OF_BAND
    calm = 0  # in-band sessions after the current index; isolated out-of-band ones are noise
    for i in range(n - 1, -1, -1):
        if not outside[i]:
            calm += 1
        elif clustered[i] and calm >= MIN_HOSE_RUN:
            return i
    return None


def _scale_check(
    ticker: str,
    dates: list[date],
    open_: FloatArray,
    close: FloatArray,
    stock_f: FloatArray,
    events: _Events,
    skip: npt.NDArray[np.bool_],
    tolerance: float,
    after_date: date | None,
) -> _ScaleCheck:
    """Classify every stock event whose ex-date shows a scale discontinuity.

    ``skip`` marks rows that cannot serve as a comparison (bad rows, pre-HOSE history); events on
    or before ``after_date`` are not checked. Returns the first failure that cannot be repaired
    (the whole ticker goes) or else the outlier rows and suspect steps found.
    """
    ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
    skip = skip.copy()
    result = _ScaleCheck()
    seen: dict[int, _Step | None] = {}
    for ex_date, _ in events.stock:
        if after_date is not None and ex_date <= after_date:
            continue
        start = int(np.searchsorted(ordinals, ex_date.toordinal(), side="left"))
        if start >= len(dates):
            continue  # no stored session on or after the ex-date: nothing to execute
        after = np.flatnonzero(~skip[start:]) + start
        if len(after) == 0:
            return _ScaleCheck(
                Exclusion(
                    ticker,
                    "precondition_unverifiable",
                    ex_date,
                    "every stored session on or after the ex-date is a bad source row",
                )
            )
        j = int(after[0])
        before = np.flatnonzero(~skip[:j])
        if len(before) == 0:
            continue  # no earlier session to compare with
        if j in seen:
            step = seen[j]
            if step is not None:
                step.ex_dates.append(ex_date)  # the same step covers this event too
            continue
        seen[j] = None
        p = int(before[-1])
        level = close[p] * stock_f[j]

        def off(i: int, level: float = level) -> float:
            return abs(float(open_[i] * stock_f[i]) / level - 1.0)

        deviation = off(j)
        if deviation <= tolerance:
            continue
        ratios = [r for d, r in events.stock if dates[p] < d <= dates[j]]
        total = float(np.prod([1.0 + r for r in ratios]))

        def at_old_level(i: int, level: float = level, total: float = total) -> bool:
            """Within tolerance of the old level and nearer it than the stepped level."""
            value = float(open_[i] * stock_f[i])
            return off(i) <= tolerance and abs(value - level) < abs(value - level * total)

        def back_in_scale(m: int, after: npt.NDArray[np.intp] = after) -> bool:
            i, last = int(after[m]), int(after[m - 1])
            broken = abs(open_[i] / close[last] - 1.0) > tolerance  # not continuing the outlier
            return at_old_level(i) and broken

        back = next(
            (m for m in range(1, MAX_OUTLIER_SESSIONS + 1) if m < len(after) and back_in_scale(m)),
            None,
        )
        if back is not None:  # the first `back` good sessions are out-of-scale rows
            for i in after[:back]:
                result.outliers.append(_Outlier(int(i), p, int(after[back])))
                skip[i] = True
            continue
        following = [int(i) for i in after[1 : MAX_OUTLIER_SESSIONS + 2]]
        stepped = abs(open_[j] / (close[p] * total) - 1.0) <= tolerance
        stays = (
            len(following) > 0
            and not any(at_old_level(i) for i in following)
            and abs(open_[following[0]] / close[j] - 1.0) <= tolerance
        )
        ratio_text = ", ".join(f"{r:.4f}" for r in ratios)
        if stepped and stays:
            detail = (
                f"open {open_[j]:.2f} on {dates[j]} vs previous close {close[p]:.2f} on "
                f"{dates[p]}: the level steps by the stored ratio(s) {ratio_text} and stays; the "
                "event does not match a price adjustment and is not applied"
            )
            step = _Step([ex_date], j, p, detail)
            seen[j] = step
            result.steps.append(step)
            continue
        return _ScaleCheck(
            Exclusion(
                ticker,
                "scale_discontinuity",
                ex_date,
                f"open {open_[j]:.2f} on {dates[j]} vs previous close {close[p]:.2f} on "
                f"{dates[p]} (deviation {deviation:.1%} > {tolerance:.1%}; stored event "
                f"ratio(s) {ratio_text})",
            )
        )
    return result


def _execution(
    group: pd.DataFrame,
    ticker: str,
    events: _Events,
    bad: set[tuple[str, date]],
    ticks: TickTable,
    tolerance: float,
) -> tuple[pd.DataFrame, list[Exclusion], _Run]:
    """``(execution rows, exclusions, ticker-level outcome)`` for one ticker."""
    dates = list(group["date"])
    ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
    is_split = (group["price_basis"] == SPLIT_ADJUSTED).to_numpy()
    is_bad = np.array([(ticker, d) in bad for d in dates], dtype=bool)
    found = [
        Exclusion(
            ticker, "dq_error", d, "error-level data-quality finding (row checks, full history)"
        )
        for d, b in zip(dates, is_bad, strict=True)
        if b
    ]
    claimed = is_bad.copy()  # every row is counted under exactly one kind
    open_ = group["open"].to_numpy(dtype=np.float64)
    high = group["high"].to_numpy(dtype=np.float64)
    low = group["low"].to_numpy(dtype=np.float64)
    close = group["close"].to_numpy(dtype=np.float64)
    stored_ref = group["ref_price"].to_numpy(dtype=np.float64)
    stock_f = _factor(ordinals, events.stock)

    run = _Run()
    omitted_outlier = np.zeros(len(group), dtype=bool)
    if is_split.any():
        skip = is_bad.copy()
        cut = _non_hose_cut(ordinals, open_, close, events, tolerance, is_bad)
        cut_date: date | None = None
        if cut is not None:
            cut_date = dates[cut]
            window = np.zeros(len(group), dtype=bool)
            window[: cut + 1] = True
            window &= is_split & ~claimed
            skip[: cut + 1] = True
            if window.any():
                found.append(
                    Exclusion(
                        ticker,
                        "non_hose_history",
                        cut_date,
                        f"{int(window.sum())} sessions from {dates[int(np.argmax(window))]} to "
                        f"{cut_date} move outside the HOSE band (another exchange's history, "
                        "GAP-04)",
                        int(window.sum()),
                    )
                )
                claimed |= window
        check = _scale_check(
            ticker, dates, open_, close, stock_f, events, skip, tolerance, cut_date
        )
        if check.failure is not None:
            found.append(check.failure)
            run = _Run(True, int((is_split & ~claimed).sum()))
        else:
            for item in check.outliers:
                found.append(
                    Exclusion(
                        ticker,
                        "scale_outlier_row",
                        dates[item.row],
                        f"open {open_[item.row]:.2f} vs previous good close "
                        f"{close[item.previous]:.2f} on {dates[item.previous]}; back in scale on "
                        f"{dates[item.back]}",
                    )
                )
                omitted_outlier[item.row] = True
                claimed[item.row] = True
            suspect: set[date] = set()
            for step in check.steps:
                window = np.zeros(len(group), dtype=bool)
                window[: step.first + 1] = True
                window &= is_split & ~claimed
                count = int(window.sum())
                claimed |= window
                for k, ex_date in enumerate(step.ex_dates):
                    suspect.add(ex_date)
                    found.append(
                        Exclusion(
                            ticker,
                            "scale_step_before",
                            ex_date,
                            f"{count if k == 0 else 0} execution rows through {dates[step.first]} "
                            f"excluded; {step.detail}",
                            count if k == 0 else 0,
                        )
                    )
            run = _Run(False, 0, frozenset(suspect))
    run = _Run(run.ticker_excluded, run.ticker_rows, run.suspect, claimed.copy())

    keep = ~claimed
    if run.ticker_excluded:
        keep &= ~is_split
    base = np.empty(len(group), dtype=np.float64)
    base[0] = stored_ref[0]
    base[1:] = close[:-1]
    for i in range(1, len(group)):
        if omitted_outlier[i - 1]:
            base[i] = base[i - 1]  # last traded price before the omitted out-of-scale row(s)
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
    return out[keep].reset_index(drop=True), found, run


def execution_actions(
    actions: pd.DataFrame,
    split_adjusted_tickers: Collection[str],
    dividends_split_adjusted: bool = DIVIDENDS_SPLIT_ADJUSTED,
) -> pd.DataFrame:
    """Actions for the engine. Cash amounts of reconstructed tickers are multiplied by
    ``F(ex_date)`` only when the dividend amounts are known to be split-adjusted."""
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
