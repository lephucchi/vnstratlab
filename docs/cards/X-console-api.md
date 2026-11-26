---
id: X-console-api
title: Console v2 API — overview, cancel/rerun, config editing, strategy param sets, price data
milestone: M1.4
release: v0.1.0
status: in-review
branch: feat/X-console-api-v2
due: 2026-11-28
---

### X-console-api — backend for Console v2

- Owner feedback 2026-11-26: the Console must let the user configure the tool (capital, costs,
  risk, data source) and add strategies (new param sets), and be more interactive.
- Implement exactly the contract in `docs/cards/console-v2-api.md` (copy it from the
  scratchpad path in the brief). The UI card X-console-ui builds against it in parallel; if you
  must change a field, list it in the handoff.

#### Rules

- **Config writes** go through the existing `vnstratlab.init_wizard` helpers (validate with the
  real loader in a scratch home, atomic write, `.bak-<stamp>` backup, keep unrelated user keys).
  Only whitelisted `editable` paths are writable; any other path → 422.
- **Parameters:** the packaged defaults stay frozen (never edit `defaults.yaml`). A user param
  set lives in the user `config.yaml`; adding one **registers its trials first** (append-only
  `TrialRegistry`), so every trial is counted (plan §6.4). Validation = the strategy's own
  `validate_params` + `horizons_allowed`. Packaged sets: enable/disable only.
- **`PARAMS_SCHEMA`** class attribute on each built-in strategy (name, type, allowed values or
  bounds, Vietnamese help). A test asserts every packaged param set validates against its
  schema and every schema value is accepted by `validate_params` (catches drift). Adding the
  attribute must not change the strategy code hash semantics beyond the module text change —
  note in the handoff that trial ids of built-ins change because the module source changes
  (ADR-003 §3) and confirm `lab trials` reflects it (that is expected and fine before v0.1.0).
  If you can avoid changing built-in modules by keeping schemas in a separate
  `strategies/schemas.py` mapping, prefer that (no trial id churn).
- **Cancel:** cooperative between tasks (the running task completes); remaining tasks
  `skipped`; run `failed`, reason `cancelled`.
- **Prices endpoint** reads the local store only; downsample to ≤ 3000 points.
- Recommend-only, loopback only, no secrets in any response (config responses must never
  include anything from `Settings`/`.env`); `tests/test_guardrails.py` unchanged and green.

#### Files

`src/vnstratlab/app/server.py` (+ `app/api_config.py`, `app/api_strategies.py` if cleaner; added during
the work: `app/api_data.py` for overview/prices/quality and `app/api_cli.py` for the terminal),
`src/vnstratlab/runs/core.py` (cancel, rerun), `src/vnstratlab/strategies/schemas.py` (new,
preferred) or built-in modules, `src/vnstratlab/strategies/registry.py` (load user param sets /
enabled overrides if not already supported), `src/vnstratlab/init_wizard.py` (reuse; small
generalisation allowed), `src/vnstratlab/config/models.py` only if user param-set entries need
a model change (no default changes), `tests/test_console_api.py`, `CHANGELOG.md`, this card
(`docs/cards/X-console-api.md`), the contract (`docs/cards/console-v2-api.md`).

#### Acceptance criteria (lean)

1. Config: GET shows editable fields with VERIFY flags; validate returns problems for an
   invalid value; PUT writes, backs up, keeps an unrelated user key; reset removes an override;
   a non-editable path → 422.
2. Strategies: GET lists all built-ins with schemas; POST adds a user param set, registers its
   trials and `load_strategies` then includes it; PATCH disables a packaged set (excluded from
   `load_strategies`); DELETE removes a user set and the trials remain in the registry.
3. Cancel and rerun work on a fake two-task pipeline.
4. Overview and prices endpoints return contract-shaped data on a synthetic home.
5. No secret ever appears in any response (test sets fake env secrets and scans responses).
6. `ruff`, `mypy`, `pytest` green.

#### Notes

P1-T20 (walk-forward) runs in parallel and adds one endpoint and a `backtest_all` pipeline in
`server.py` / `runs/pipelines.py`; X-65 touches `risk/layer.py`, `engine/loop.py`, `demo.py`.
Keep your changes localised to merge cleanly.
