"""Lab statistics: Sharpe, Deflated Sharpe Ratio and PBO on the walk-forward series (P1-T21).

The pure functions need numpy and scipy only. ``trial_stats`` reads ``oos_returns`` of a
``LabStore`` and returns one row per current trial and segment; ``lab.gate1`` values are read by
the callers (never defaulted here).

Gate inputs use the *historical* segment only (in-sample by design, engine.md section 12); the
*forward* segment (true out-of-sample) is reported separately with its own periods, Sharpe, skew
and kurtosis, but never a DSR or PBO.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NamedTuple, cast

import numpy as np
import pandas as pd
from scipy import stats as sps

from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.lab.store import STATS_COLUMNS

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig, Horizon
    from vnstratlab.lab.store import LabStore
    from vnstratlab.paths import AppPaths

EULER_GAMMA = 0.5772156649015329  # Euler-Mascheroni constant
_ZERO_STD = 1e-12
DEFAULT_CSCV_BLOCKS = 16
MAX_CSCV_COMBINATIONS = 20_000
HORIZONS = ("short", "medium", "long")
SEGMENTS = ("historical", "forward")
__all__ = [
    "HORIZONS",
    "SEGMENTS",
    "STATS_COLUMNS",
    "DSRResult",
    "add_gate_columns",
    "compute_lab_stats",
    "deflated_sharpe",
    "pbo_cscv",
    "sharpe",
    "skew_kurt",
    "trial_stats",
]


def sharpe(r: Sequence[float] | np.ndarray) -> float:
    """Non-annualised per-period Sharpe: mean / sample std (ddof 1), risk-free 0.

    NaN with fewer than 2 points or a (numerically) zero standard deviation.
    """
    x = np.asarray(r, dtype=float)
    if x.size < 2:
        return math.nan
    std = float(np.std(x, ddof=1))
    if not std > _ZERO_STD:
        return math.nan
    return float(np.mean(x) / std)


def skew_kurt(r: Sequence[float] | np.ndarray) -> tuple[float, float]:
    """Skewness (gamma3) and **non-excess** kurtosis (gamma4; a normal sample is about 3).

    Population (biased) moment estimators, as in the DSR paper. scipy's ``kurtosis`` returns
    excess kurtosis by default; ``fisher=False`` converts to non-excess. NaN for fewer than
    3 points or a constant series.
    """
    x = np.asarray(r, dtype=float)
    if x.size < 3 or not float(np.std(x)) > _ZERO_STD:
        return math.nan, math.nan
    return float(sps.skew(x, bias=True)), float(sps.kurtosis(x, fisher=False, bias=True))


class DSRResult(NamedTuple):
    dsr: float  # NaN when undefined; see ``reason``
    sr0: float  # the benchmark Sharpe (expected maximum of N trials under the null)
    reason: str | None


def deflated_sharpe(
    sr: float, t: int, skew: float, kurt: float, n_trials: int, var_trials: float
) -> DSRResult:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014, "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting and Non-Normality", J. Portfolio
    Management 40(5); plan Appendix C).

    ``sr`` is the observed **non-annualised** Sharpe over ``t`` periods, ``skew`` = gamma3 and
    ``kurt`` = gamma4, the **non-excess** kurtosis (3 for a normal; scipy's default is excess,
    so add 3), ``n_trials`` = N trials and ``var_trials`` = V, the variance of their Sharpe
    ratios::

        SR0 = sqrt(V) * ((1 - g) * Phi^-1(1 - 1/N) + g * Phi^-1(1 - 1/(N*e)))   g = Euler gamma
        DSR = Phi((SR - SR0) * sqrt(T - 1) / sqrt(1 - g3*SR + (g4 - 1)/4 * SR^2))

    N = 1 or V = 0 gives SR0 = 0, i.e. the plain Probabilistic Sharpe Ratio (PSR).
    The radicand is the variance term of the Sharpe estimator (Mertens 2002); when it is not
    positive the result is NaN with a reason.

    Verification: the formula is the paper's SR0 (expected maximum of N standard normals,
    Euler-Mascheroni approximation) fed into the PSR of the paper's section 2. The paper was
    not reachable offline; the tests reproduce, from memory of its worked example (annualised
    SR 2.5, V = 0.5 annualised, N = 100, T = 1250 daily, skew -3, kurtosis 10), SR0 = 0.1132
    and DSR = 0.9004, using an independent implementation (``statistics.NormalDist``). They
    also check the PSR special case and that gamma4 = 3 (a normal) reduces the denominator to
    sqrt(1 + SR^2 / 2), the iid-normal Sharpe variance, which fixes the non-excess convention.
    """
    if not (math.isfinite(sr) and math.isfinite(skew) and math.isfinite(kurt)):
        return DSRResult(math.nan, math.nan, "non-finite input")
    if t < 2:
        return DSRResult(math.nan, math.nan, "fewer than 2 periods")
    if n_trials < 1:
        return DSRResult(math.nan, math.nan, "n_trials < 1")
    if n_trials == 1 or not (math.isfinite(var_trials) and var_trials > 0):
        sr0 = 0.0
    else:
        z1 = float(sps.norm.ppf(1.0 - 1.0 / n_trials))
        z2 = float(sps.norm.ppf(1.0 - 1.0 / (n_trials * math.e)))
        sr0 = math.sqrt(var_trials) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)
    radicand = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if not radicand > 0:
        return DSRResult(math.nan, sr0, f"non-positive variance term {radicand:.6g}")
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(radicand)
    return DSRResult(float(sps.norm.cdf(z)), sr0, None)


def _pooled_sharpes(n: np.ndarray, s1: np.ndarray, s2: np.ndarray) -> np.ndarray:
    """Sharpe per (combination, column) from pooled blocks: n rows (C,), sums s1 and sums of
    squares s2 (C, N). A constant column gets -inf so it is never the best and ranks last."""
    nn = n[:, None]
    mean = s1 / nn
    var = (s2 - nn * mean * mean) / (nn - 1.0)
    ok = var > _ZERO_STD**2
    out = np.full(s1.shape, -np.inf)
    out[ok] = mean[ok] / np.sqrt(var[ok])
    return out


def pbo_cscv(
    matrix: np.ndarray,
    s: int = DEFAULT_CSCV_BLOCKS,
    *,
    seed: int = 0,
    max_combinations: int = MAX_CSCV_COMBINATIONS,
) -> tuple[float, list[float]]:
    """Probability of Backtest Overfitting by combinatorially symmetric cross-validation
    (Bailey, Borwein, Lopez de Prado & Zhu, 2015).

    ``matrix`` is T rows (periods) by N columns (trials). The rows are cut into ``s`` contiguous
    blocks (``array_split``; sizes differ by at most one). Every choice of ``s/2`` blocks is a
    training set and the other half the test set. The best trial in-sample (Sharpe) gets the
    relative rank omega = rank / (N + 1) among the N trials out-of-sample (average rank for
    ties, best = highest), and lambda = ln(omega / (1 - omega)). PBO is the share of lambda <= 0.
    With more than ``max_combinations`` choices, a deterministic sample (``seed``) is used.

    Returns ``(pbo, lambdas)``; ``(nan, [])`` when N < 2, ``s`` is odd or < 2, or T < ``s``.
    """
    x = np.asarray(matrix, dtype=float)
    if x.ndim != 2 or x.shape[1] < 2 or s < 2 or s % 2 or x.shape[0] < s:
        return math.nan, []
    n_trials = x.shape[1]
    blocks = np.array_split(np.arange(x.shape[0]), s)
    count = np.array([len(b) for b in blocks], dtype=float)
    sums = np.stack([x[b].sum(axis=0) for b in blocks])
    squares = np.stack([(x[b] ** 2).sum(axis=0) for b in blocks])
    half = s // 2
    if math.comb(s, half) <= max_combinations:
        chosen = list(itertools.combinations(range(s), half))
    else:
        rng = np.random.default_rng(seed)
        seen: set[tuple[int, ...]] = set()
        while len(seen) < max_combinations:
            seen.add(tuple(sorted(rng.choice(s, size=half, replace=False).tolist())))
        chosen = sorted(seen)
    train = np.zeros((len(chosen), s))
    for i, combo in enumerate(chosen):
        train[i, list(combo)] = 1.0
    test = 1.0 - train
    sr_in = _pooled_sharpes(train @ count, train @ sums, train @ squares)
    sr_out = _pooled_sharpes(test @ count, test @ sums, test @ squares)
    best = np.argmax(sr_in, axis=1)
    best_out = sr_out[np.arange(len(chosen)), best]
    below = (sr_out < best_out[:, None]).sum(axis=1)
    equal = (sr_out == best_out[:, None]).sum(axis=1)
    rank = below + (equal + 1.0) / 2.0  # average rank of the selected trial, best = highest
    omega = rank / (n_trials + 1.0)
    lambdas = np.log(omega / (1.0 - omega)).tolist()
    return float(np.mean(np.asarray(lambdas) <= 0.0)), lambdas


def trial_stats(
    store: LabStore,
    source: str,
    horizon: str,
    mode: str = "executable",
    *,
    min_periods: int,
    seed: int,
    feature_version: str | None = None,
    s: int = DEFAULT_CSCV_BLOCKS,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Statistics of the current trials of ``horizon`` (``STATS_COLUMNS``; two rows per trial).

    Current = ``ENGINE_VERSION`` and, when given, ``feature_version`` (the P1-T20b filter).
    ``n_trials`` (N) counts **every** current registered trial of the horizon, also those with
    no or too few periods; ``var_sr`` is the sample variance (ddof 1) of the finite historical
    Sharpe ratios among them (NaN with fewer than two). PBO is computed over the trials with at
    least ``min_periods`` historical periods, aligned on the ``period_end`` they all share, and
    repeated on each historical row of the horizon. DSR and PBO exist for the historical segment
    only; the forward row carries periods, sr, skew and kurt.
    """
    stamp = now if now is not None else datetime.now(UTC)
    records = [
        r
        for r in store.list(horizon)
        if r.engine_version == ENGINE_VERSION
        and (feature_version is None or r.feature_version == feature_version)
    ]
    oos = store.oos_returns(source=source, mode=mode)
    series: dict[str, dict[str, pd.Series]] = {}
    for rec in records:
        part = oos[oos["trial_id"] == rec.trial_id].sort_values("period_end")
        series[rec.trial_id] = {
            seg: part[part["in_sample_by_design"] == (seg == "historical")].set_index("period_end")[
                "ret"
            ]
            for seg in SEGMENTS
        }
    n_trials = len(records)
    finite = np.array(
        [
            v
            for v in (sharpe(x["historical"].to_numpy()) for x in series.values())
            if math.isfinite(v)
        ]
    )
    var_sr = float(np.var(finite, ddof=1)) if finite.size >= 2 else math.nan

    eligible = [tid for tid, x in series.items() if len(x["historical"]) >= min_periods]
    pbo = math.nan
    if len(eligible) >= 2:
        aligned = pd.concat([series[t]["historical"].rename(t) for t in eligible], axis=1).dropna()
        pbo, _ = pbo_cscv(aligned.to_numpy(), s, seed=seed)

    rows: list[dict[str, object]] = []
    for rec in records:
        for segment in SEGMENTS:
            ret = series[rec.trial_id][segment].to_numpy()
            sr = sharpe(ret)
            skew, kurt = skew_kurt(ret)
            historical = segment == "historical"
            dsr = math.nan
            if historical:
                dsr = deflated_sharpe(sr, len(ret), skew, kurt, n_trials, var_sr).dsr
            rows.append(
                {
                    "trial_id": rec.trial_id,
                    "horizon": horizon,
                    "mode": mode,
                    "source": source,
                    "segment": segment,
                    "periods": len(ret),
                    "sr": sr,
                    "skew": skew,
                    "kurt": kurt,
                    "dsr": dsr,
                    "n_trials": n_trials if historical else math.nan,
                    "var_sr": var_sr if historical else math.nan,
                    "pbo": pbo if historical else math.nan,
                    "computed_at": stamp,
                    "feature_version": rec.feature_version,
                    "engine_version": rec.engine_version,
                }
            )
    return pd.DataFrame(rows, columns=list(STATS_COLUMNS))


def add_gate_columns(frame: pd.DataFrame, cfg: AppConfig) -> pd.DataFrame:
    """Gate-1 pass/fail columns (historical rows only; a NaN input fails; forward rows: None)."""
    out = frame.copy()
    gate = cfg.lab.gate1
    hist = out["segment"] == "historical"
    need = out["horizon"].map(lambda h: gate.min_periods[cast("Horizon", h)])
    for name, ok in (
        ("periods_ok", out["periods"] >= need),
        ("dsr_ok", out["dsr"] >= gate.dsr_min),
        ("pbo_ok", out["pbo"] <= gate.pbo_max),
    ):
        out[name] = ok.astype(object).where(hist, None)
    return out


def compute_lab_stats(
    cfg: AppConfig,
    paths: AppPaths,
    source: str,
    horizon: str | None = None,
    mode: str = "executable",
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Compute ``trial_stats`` for the horizon(s), store them in ``lab.duckdb`` and return them.

    Replaces the stored rows of (source, horizon, mode). Empty frame without a lab store.
    """
    from vnstratlab.lab.store import LabStore
    from vnstratlab.lab.walkforward import current_feature_version

    empty = pd.DataFrame(columns=list(STATS_COLUMNS))
    if not paths.lab_db.is_file():
        return empty
    version = current_feature_version(paths, source)
    parts: list[pd.DataFrame] = []
    with LabStore(paths.lab_db) as store:
        for h in [horizon] if horizon else HORIZONS:
            frame = trial_stats(
                store,
                source,
                h,
                mode,
                min_periods=cfg.lab.gate1.min_periods[cast("Horizon", h)],
                seed=cfg.lab.seed,
                feature_version=version,
                now=now,
            )
            store.replace_trial_stats(frame, source, h, mode)
            parts.append(frame)
    return pd.concat(parts, ignore_index=True) if parts else empty
