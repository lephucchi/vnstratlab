---
id: P1-T21
title: Lab statistics — Sharpe, Deflated Sharpe Ratio, PBO (CSCV)
milestone: M1.5 Lab
release: v0.2.0
status: in-progress
branch: feat/P1-T21-dsr-pbo
due: 2026-11-30
---

### P1-T21 — DSR and PBO on the walk-forward series

- Depends on: P1-T20 / P1-T20b (`oos_returns` per registered trial, merged).
- Spec: plan P1-T21 and **Appendix C** (DSR formula); engine.md §12; config `lab.gate1`
  (`dsr_min: 0.95`, `pbo_max: 0.5`, `min_periods`) — values frozen, read only.
- Full G2 (statistics math), one round. Lean tests, but the plan's statistical acceptance
  tests are required (mark the heavy ones `@pytest.mark.slow`; keep one fast version each).

#### Functions (`src/vnstratlab/lab/stats.py`, pure, numpy/scipy only)

1. `sharpe(r)` — non-annualised per-period Sharpe (mean / sample std, ddof 1); NaN when
   std = 0 or fewer than 2 points.
2. `deflated_sharpe(sr, t, skew, kurt, n_trials, var_trials)` — Appendix C exactly:
   `SR0 = sqrt(V)·((1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(N·e)))`,
   `DSR = Φ((SR−SR0)·sqrt(T−1)/sqrt(1−γ3·SR+(γ4−1)/4·SR²))` with γ = Euler–Mascheroni,
   γ4 = **non-excess** kurtosis (state it; scipy's default is excess — convert). Docstring
   cites Bailey & López de Prado (2014) and the check you did against the paper (reproduce
   the paper's numeric example if you can access it; otherwise a hand-computed value).
   Edge cases: N = 1 → SR0 = 0 (plain PSR); V = 0 → SR0 = 0; negative radicand → NaN with a
   reason.
3. `pbo_cscv(matrix, s=16)` — Probability of Backtest Overfitting via combinatorially
   symmetric cross-validation (Bailey, Borwein, López de Prado & Zhu 2015): split T rows into
   `s` blocks, all C(s, s/2) train/test combinations (cap and sample deterministically with
   `lab.seed` if too many), pick the best trial in-sample by Sharpe, take its out-of-sample
   relative rank ω, logit λ = ln(ω/(1−ω)); PBO = share of λ ≤ 0. Return PBO and the λ list.
4. `trial_stats(store, source, horizon, mode="executable")` — for the current versions
   (same filter as P1-T20b): per trial T, SR, skew, kurt, DSR (N = **all registered trials of
   that horizon**, V = variance of their SRs — trials without enough periods still count in N),
   and PBO over the horizon's trial matrix aligned on common `period_end`s. Uses only the
   **historical (in-sample by design)** segment for gate inputs and reports forward separately.

#### Storage, CLI, API, Console

- `lab.duckdb` table `trial_stats(trial_id, horizon, mode, source, segment, periods, sr,
  skew, kurt, dsr, n_trials, var_sr, pbo, computed_at, feature_version, engine_version)`.
- `vnstratlab lab stats [--horizon H] [--source S] [--mode M]` prints the table with
  gate-1 pass/fail columns (DSR ≥ dsr_min, PBO ≤ pbo_max, periods ≥ min_periods) — no
  selection yet (P1-T22). `GET /api/lab/stats?horizon=&source=` returns the rows. Add a
  `lab_stats` task to the `backtest_all` pipeline after `backtest` (summary: counts passing
  each gate). The `cli` field for the pipeline stays `vnstratlab backtest --all`.

#### Acceptance criteria

1. DSR hand-computed value matches (1e-9); PSR special case (N = 1) matches the PSR formula.
2. Plan test: 50 zero-edge synthetic strategies (iid normal), best SR's DSR < 0.95 in ≥ 90 %
   of 200 seeds (slow); fast version with 20 seeds and a looser bound documented.
3. Strong-edge synthetic strategy → DSR > 0.95.
4. PBO on pure noise within a documented tolerance of 0.5 (e.g. 0.5 ± 0.15 at s = 16 over
   seeds; slow); a strong-edge set gives PBO well below 0.5.
5. `trial_stats` counts every registered trial of the horizon in N, including ones with too
   few periods; test with a registered trial that has no rows.
6. CLI / endpoint / pipeline task return the rows; `ruff`, `mypy`, `pytest` green.

#### Files

`src/vnstratlab/lab/stats.py` (new), `src/vnstratlab/lab/store.py` (trial_stats table),
`src/vnstratlab/cli.py` (`lab stats`), `src/vnstratlab/runs/pipelines.py` (`lab_stats` task),
`src/vnstratlab/app/server.py` (one endpoint), `tests/test_lab_stats.py`, `docs/engine.md` §12
(as implemented), `CHANGELOG.md`, this card (`docs/cards/P1-T21-dsr-pbo.md`).

#### Out of scope

SPA, MCS, weights, selection (P1-T22); Console UI for lab stats (later).
