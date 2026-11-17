# ADR-003: Engine and architecture refinements

- Status: **proposed** (owner decision required; plan §2 and §6 are unchanged until accepted)
- Date: 2026-11-17
- Deciders: owner
- Related: [engine.md](../engine.md), [strategies.md](../strategies.md), plan D11, §6.4

## Context

Writing the detailed engine spec exposed gaps and choices that the plan v1.1 leaves open or
that touch fixed decisions. Each item below can be accepted or rejected on its own.

## Proposals

| # | Proposal | Touches | Why | Cost |
|---|---|---|---|---|
| 1 | **Layered architecture with a pure domain core** (engine, rules, strategies, risk, feature maths) that imports no I/O; enforced with `import-linter` in CI | §5 layout | Fast, deterministic tests without databases; data sources and storage swappable | One CI job, discipline |
| 2 | **Vectorised fast path for ideal mode**, allowed only behind a CI property test proving equality with the event loop on random synthetic data | D11 | Lab runs all trials × periods × bootstraps; event loop may be the bottleneck | Second code path, guarded by test |
| 3 | **Trial identity includes code**: `hash(strategy_id, params, strategy_code_hash, feature_version, engine_version)` | §6.4.3–4 | A code edit with unchanged params would otherwise reuse a trial and escape the DSR count | Trial count grows with every edit (intended) |
| 4 | **Split reports at `registered_at`**: history before = "in-sample by design", after = forward OOS | P1-T22, P1-T23 | Params chosen in 2026 with 2015–2026 in view are not OOS on that history | None |
| 5 | **Effective number of trials** for DSR (cluster trials by return correlation) reported **next to** the raw count; gates keep the raw count unless the owner switches | P1-T21 | Correlated variants (S08/S13, S10/S11) make the raw count overly harsh; showing both keeps it honest | Small |
| 6 | **Execution on raw prices, signals on adjusted**; corporate actions applied to holdings; `corporate_actions` gains `pay_date` and `listing_date`; config gains `rights_policy` and `cash_dividend_pay_lag_days` fallback | P1-T06 schema, P1-T11 | Limits, ticks and lot values are defined on raw prices; dividends and new shares arrive later than the ex-date | Two columns, two keys |
| 7 | **Order lifecycle config**: `unfilled_buy: cancel`, `unfilled_sell: carry`, `unsettled_sell: queue_until_sellable`, `max_carry_sessions: 5` | P1-T11, config | Behaviour must be explicit and tested | New config keys (frozen once accepted) |
| 8 | **Stop wins over rebalance**, stopped ticker in cooldown for one decision period | P1-T12, config | Avoids sell-then-rebuy churn on the same day | New key `risk.stop_cooldown_sessions` |
| 9 | **Cash ledger with buckets** and `[VERIFY]` key `cash_proceeds_offset` | P1-T11, hose.yaml | When sale proceeds can fund buys changes executable returns | New VERIFY item |
| 10 | **Run manifest** (version, commit, engine_version, resolved config + hash, data snapshot, seeds, trial ids) stored per run | P1-T20+, journal | G3 reproducibility; any number in a report traceable | Small table |
| 11 | **Combine strategies on weights**, then one risk-layer pass; show `consensus` | P1-T22, P1-T24 | Netted portfolio, no internal churn | None |
| 12 | **`order_events` log** of blocked/carried/cancelled orders with reasons | P1-T11 | Quantifies how much each HOSE rule costs (G3 realism) | Small table |

## Decision

Pending. Proposed default: accept 1, 3, 4, 6–12 now (clarifications and safety); accept 2 and
5 when benchmarks (P1-T20/T21) show a need.

## Consequences if accepted

- plan §2 D11 gains a note on the guarded fast path (2); §6.4 rule 3 gains the code-hash rule (3).
- `defaults.yaml` / `hose.yaml` gain the keys in 6, 7, 8, 9 (owner freezes values); plan §5.5 `corporate_actions` gains `pay_date`, `listing_date` (6).
- P1-T11, P1-T12, P1-T13, P1-T20–T23 acceptance criteria gain the corresponding tests.
- New CI job: `import-linter` contracts (1).

## Alternatives considered

- **Keep trial identity = (strategy, params)** — simpler, but code edits silently reuse trials. Rejected in proposal.
- **Simulate on adjusted prices only** — simpler data, but breaks limit/tick/lot realism. Rejected.
- **Single combined event loop for lab and books without fast path** — simplest; acceptable if benchmarks show it is fast enough (then proposal 2 is dropped).
