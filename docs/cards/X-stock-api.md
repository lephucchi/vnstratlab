---
id: X-stock-api
title: Current recommendations (preview) and per-stock analysis — backend, CLI, pipeline
milestone: M1.5
release: v0.2.0
status: in-progress
branch: feat/X-stock-api
due: 2026-11-28
---

### X-stock-api — recommendations preview and per-stock analysis

- Owner request 2026-11-26: "Kết quả" must show which stocks are recommended; the user wants to
  pick a single stock, run an analysis, and get numbers, strategy signals and a recommendation.
- Implement the contract `docs/cards/stock-insight-api.md` (copy from the scratchpad path in the
  brief). UI card X-stock-ui builds against it in parallel.

#### Rules

- **Recommend-only.** No order placement/routing/confirmation, no broker, no credentials;
  `tests/test_guardrails.py` unchanged and green. Every response carries `label` (SYNTHETIC or
  "interim Yahoo, survivorship-biased (GAP-13)") and the Vietnamese disclaimer.
- **No lookahead.** Signals use feature rows ≤ asof with each strategy's `lookback_sessions`
  (reuse `demo.decision_targets` / walk-forward slicing — do not duplicate it).
- **Every trial counted.** Only registered trials contribute; unregistered enabled strategies are
  listed with `registered: false` and excluded, with a note (register via `lab register` /
  `backtest --register`).
- **Preview combination.** Equal weight across contributing strategies, then the risk layer once
  (engine.md §9), `status: "preview"`. Do not invent selection logic — P1-T22 replaces it.
- **Lot / stop / cost math** reuses `engine.rules`, `engine.costs`, `risk` (ATR, stop) — no new
  formulas. Hand-computed test for one ticker.
- **Runs.** New pipeline `stock_analysis` needs per-run params (ticker, source, horizons): extend
  `runs` so a pipeline can take validated params from `POST` (only this pipeline accepts params;
  ticker must exist in the store). Store the analysis JSON in the run folder and an index so
  `GET /api/stocks/{ticker}/analysis` returns the latest. `cli` field on the pipeline.
- Read-only on market data; real data never leaves the machine.

#### Files

`src/vnstratlab/insight/` (new: `recommend.py`, `stock.py`), `src/vnstratlab/runs/` (params
support, `stock_analysis` pipeline), `src/vnstratlab/app/` (new `api_insight.py` + routes),
`src/vnstratlab/app/api_cli.py` (cli mapping only), `src/vnstratlab/cli.py` (`recommend`,
`stock`), `tests/test_insight.py`, `docs/getting-started.md` (short section), `CHANGELOG.md`,
this card (`docs/cards/X-stock-api.md`) and the contract.

#### Acceptance criteria (lean)

1. Recommendations on a synthetic store: targets sum ≤ 1, consensus counts correct, lot math and
   stop price hand-checked for one ticker, only registered trials contribute.
2. Analysis run for one ticker ends success; the JSON has every contract block; signals use only
   rows ≤ asof (test with a store extended by future rows that must not change the result).
3. `stock_analysis` rejects an unknown ticker (422) and accepts params only for this pipeline.
4. CLI `recommend` and `stock ACB` (synthetic) print the summary; both appear in
   `/api/cli/commands`.
5. Guardrails unchanged; `ruff`, `mypy`, `pytest` green.
