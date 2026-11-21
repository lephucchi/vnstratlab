"""S04 long-only bank pairs (card P1-T16; plan section 7; docs/strategies.md S04).

Basis: Gatev, Goetzmann & Rouwenhorst (2006), pairs trading. This version is LONG-ONLY: there is
no short leg, so it only buys the laggard of a stretched pair. Long-only halves the hedge (the
market and sector exposure of the short leg is gone), so the result is closer to a short-term
reversal strategy than to a market-neutral pairs strategy and must be read that way, together
with the cost stress test. Frozen params: ``{form: 250, k: 5, entry_z: 2.0, max_hold: 10}``.

History contract: ``lookback_sessions = form``. The strategy reads the feature ``ret_1d`` of
every feature row dated <= ``asof`` (all of them are, by ``asof_guard``). Sessions are the dates
present in the frame (union over tickers); a missing return stays NaN (no fill). Fewer than
``form`` sessions, or ``asof`` not being the last session of the frame, gives all cash.

Rule as implemented
* Formation window: the last ``form`` sessions ending at ``asof``. Pairs ``(A, B)``, ``A < B`` by
  symbol, are ranked by the Pearson correlation of ``ret_1d`` over the days both are observed; a
  pair needs at least 80 % of the window observed for both (else it is skipped). The top ``k``
  pairs are kept (correlation rounded to 12 decimals, ties by ``(A, B)``).
* Spread: on the days where BOTH returns are observed (a day with a missing leg contributes
  nothing and has no spread value), ``spread_t = cumulative(log1p(ret_A) - log1p(ret_B))``, i.e.
  the log price ratio up to a constant. ``z_t = (spread_t - mean) / std`` with the mean and the
  sample std (ddof 1) of the spread over the window. The window is FIXED at ``asof`` for every
  session in it: the z of an earlier session uses statistics that include later sessions of the
  window. That is not lookahead (all inputs are <= ``asof``) but it differs from a rolling z that
  a live system would have seen on that earlier day; it is a stateless re-derivation.
* Open at ``asof`` (stateless: the window is replayed from its start, onset-based clock). An
  onset is a session with ``|z| > entry_z`` whose previous session had ``|z| <= entry_z`` or no
  z (the window start counts as no z). A position opens at an onset; the onset session is
  session 1, so sessions 1..``max_hold`` are held and it closes on the next one. It also closes
  when z changes sign or is exactly 0 (the zero cross). After a time stop with ``|z|`` still
  beyond ``entry_z`` there is NO re-entry until z has come back to ``|z| <= entry_z`` and
  breaks out again (a new onset). The side is fixed at the onset; later onsets while open are
  ignored. A session without a spread value neither crosses nor opens, and ``asof`` itself must
  have one.
* Long the laggard of the entry: ``z > 0`` means A outperformed B, so B is bought; ``z < 0``
  buys A. Each open pair holds ``1 / k``; two open pairs on the same laggard add up. The total is
  at most 1; fewer open pairs than ``k`` leave the rest in cash.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import combinations
from numbers import Real
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from vnstratlab.strategies.base import BaseStrategy, Horizon
from vnstratlab.strategies.registry import register_strategy

FloatArray = npt.NDArray[np.float64]

FEATURE = "ret_1d"
SCORE_DECIMALS = 12
MIN_OBSERVED_NUM, MIN_OBSERVED_DEN = 4, 5  # 80 % of the window
MIN_SPREAD_POINTS = 3


def return_panel(features: pd.DataFrame, asof: pd.Timestamp, sessions: int) -> pd.DataFrame | None:
    """Daily returns (rows = the last ``sessions`` sessions ending at ``asof``, columns = tickers).

    Sessions are the dates present in ``features`` (union over tickers). Returns ``None`` when the
    frame has fewer than ``sessions`` sessions or ``asof`` is not its last session. A return
    that is NaN, infinite or <= -1 is NaN (not observed). No fill.
    """
    missing = [c for c in ("ticker", "date", FEATURE) if c not in features.columns]
    if missing:
        raise ValueError(f"features lack columns {missing}")
    frame = features[["ticker", "date", FEATURE]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("more than one feature row per ticker and date")
    dates = sorted(frame["date"].unique())
    if len(dates) < sessions or pd.Timestamp(dates[-1]) != pd.Timestamp(asof).normalize():
        return None
    window = frame[frame["date"].isin(dates[-sessions:])]
    panel = window.pivot(index="date", columns="ticker", values=FEATURE)
    panel = panel.apply(pd.to_numeric, errors="coerce").sort_index().sort_index(axis=1)
    panel = panel.astype(float)
    cleaned: pd.DataFrame = panel.where(np.isfinite(panel) & (panel > -1.0))
    return cleaned


def enough_observed(count: int, sessions: int) -> bool:
    """At least 80 % of the window observed (integer arithmetic, no float fuzz)."""
    return count * MIN_OBSERVED_DEN >= sessions * MIN_OBSERVED_NUM


def pair_correlation(a: FloatArray, b: FloatArray, sessions: int) -> float:
    """Pearson correlation over the days both are observed; NaN if too few days or no variance."""
    both = np.isfinite(a) & np.isfinite(b)
    if not enough_observed(int(both.sum()), sessions):
        return math.nan
    x, y = a[both], b[both]
    if float(np.std(x)) == 0.0 or float(np.std(y)) == 0.0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def top_pairs(panel: pd.DataFrame, k: int) -> list[tuple[str, str, float]]:
    """The ``k`` most correlated pairs ``(A, B, corr)`` with ``A < B`` (ties by symbols)."""
    values = {str(t): panel[t].to_numpy(dtype=float) for t in panel.columns}
    sessions = len(panel)
    scored: list[tuple[float, str, str]] = []
    for a, b in combinations(sorted(values), 2):
        corr = pair_correlation(values[a], values[b], sessions)
        if math.isfinite(corr):
            scored.append((round(corr, SCORE_DECIMALS), a, b))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [(a, b, corr) for corr, a, b in scored[:k]]


def spread_z(ret_a: FloatArray, ret_b: FloatArray) -> FloatArray:
    """z-scored cumulative log-return spread A - B, one value per session of the window.

    Only sessions where both returns are observed have a value (others NaN). The mean and the
    sample std (ddof 1) are taken over those sessions. All NaN when fewer than 3 sessions or no
    variation.
    """
    both = np.isfinite(ret_a) & np.isfinite(ret_b)
    z = np.full(len(ret_a), math.nan)
    if int(both.sum()) < MIN_SPREAD_POINTS:
        return z
    spread = np.cumsum(np.log1p(ret_a[both]) - np.log1p(ret_b[both]))
    std = float(np.std(spread, ddof=1))
    if not math.isfinite(std) or std <= 1e-12:
        return z
    z[both] = (spread - float(np.mean(spread))) / std
    return z


def open_side(z: FloatArray, entry_z: float, max_hold: int) -> int:
    """+1 if the pair is open with A ahead (buy B), -1 if open with B ahead (buy A), else 0.

    Replays the window (the last element of ``z`` is ``asof``). Onset: a session with
    ``|z| > entry_z`` whose previous session had ``|z| <= entry_z`` or no z (the window start
    counts as no z). A position opens at an onset (side fixed by the sign of z there; the onset
    session is session 1) and closes when z changes sign or hits exactly 0, or on the session
    after ``max_hold`` sessions (sessions 1..``max_hold`` are held). While open, later onsets
    are ignored. After a time stop there is no re-entry until z has come back inside the band
    and broken out again (a new onset). NaN sessions neither cross nor expire a sign; the last
    session must have a value.
    """
    if not math.isfinite(float(z[-1])):
        return 0
    side = 0
    onset = 0
    for t, value in enumerate(z):
        if side and math.isfinite(float(value)) and float(value) * side <= 0:
            side = 0  # zero cross
        elif side and t - onset >= max_hold:
            side = 0  # time stop
        previous = float(z[t - 1]) if t > 0 else math.nan
        is_onset = abs(value) > entry_z and not abs(previous) > entry_z  # NaN compares False
        if not side and is_onset:
            side = 1 if value > 0 else -1
            onset = t
    return side


def positive_float(name: str, value: Any) -> None:
    if (
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be a positive finite number")


def positive_int(name: str, value: Any, minimum: int = 1) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@register_strategy
class S04BankPairs(BaseStrategy):
    """Long the laggard of the most correlated stretched pairs. See the module docstring."""

    id = "S04_bank_pairs"
    lookback_sessions = 250  # the frozen param set; an instance carries its own form

    def __init__(self, params: Mapping[str, Any], horizons: Sequence[Horizon]) -> None:
        super().__init__(params, horizons)
        self.lookback_sessions = int(self.params["form"])

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        if set(params) != {"form", "k", "entry_z", "max_hold"}:
            raise ValueError("S04 params must be exactly {form, k, entry_z, max_hold}")
        positive_int("form", params["form"], MIN_SPREAD_POINTS)
        positive_int("k", params["k"])
        positive_float("entry_z", params["entry_z"])
        positive_int("max_hold", params["max_hold"])

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        k = self.params["k"]
        panel = return_panel(features, asof, self.params["form"])
        if panel is None:
            return pd.Series(dtype=float)  # not enough history: all cash
        weights: dict[str, float] = {}
        for a, b, _ in top_pairs(panel, k):
            side = open_side(
                spread_z(panel[a].to_numpy(), panel[b].to_numpy()),
                float(self.params["entry_z"]),
                self.params["max_hold"],
            )
            if side:
                laggard = b if side > 0 else a
                weights[laggard] = weights.get(laggard, 0.0) + 1.0 / k
        return pd.Series(weights, dtype=float).sort_index()
