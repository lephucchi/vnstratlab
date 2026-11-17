# Roadmap

Releases map to milestones of the [implementation plan](plan/plan.md). Each minor release passes
gates G1–G4 ([qa-gates.md](qa-gates.md)).

| Release | Milestones | Cards | Highlights |
|---|---|---|---|
| **v0.0.x** | M1.0 | P1-T01 ✅ | Scaffold, CI, docs |
| **v0.1.0** | M1.0–M1.4 | P1-T02 … P1-T19, P1-T32 | Config + calendar, synthetic market (P1-T36), features, simulator with HOSE rules, risk layer, strategy registry and built-ins, `backtest`, offline `demo` |
| **v0.2.0** | M1.5 | P1-T20 … P1-T23, P1-T33 | Walk-forward, DSR, PBO, SPA, MCS, weights, meta-backtest, stress tests, lab reports |
| **v0.3.0** | M1.6–M1.8 | P1-T24 … P1-T30 | Paper books, journal, `daily`, FastAPI, dashboard (5 pages), Telegram, scheduler in `serve`, backups |
| **v0.4.0** | Phase 2 | P2-T01 … P2-T08 | News normalisation, LLM scoring, news features, IC study, ADR-002 decision |
| **v0.5.0** | Phase 3 | P3-T01 … P3-T06 | Portfolio optimisation, lot-aware allocation, user-recorded fills, real-vs-recommended tracking |
| **v1.0.0** | — | — | Phase 1 stable for 3 months of nightly paper runs; API frozen |

> **Data source (ADR-006, 2026-11-17).** `vnstock` stopped working for free use on 2026-11-10.
> Phase 1 continues on synthetic data; real-data cards (P1-T03, P1-T04, P1-T06, P1-T07,
> P1-T08, P1-T09) wait for the owner's source decision and move to the release after it.

## Cards added for the open-source version

| Card | Title | Release |
|---|---|---|
| P1-T36 | `DataSource` protocol and synthetic market (ADR-006); unblocks the engine | v0.1 |
| P1-T32 | `vnstratlab demo`: synthetic dataset and offline end-to-end run | v0.1 |
| P1-T33 | `vnstratlab stress`: realism stress tests (costs, delay, liquidity, param noise, regimes) | v0.2 |
| P1-T34 | Cross-engine check harness (vectorbt, backtrader) for G3.2 | v0.2 |
| P1-T35 | `vnstratlab init` wizard and user config merge | v0.1 |

## Not planned

- Placing, routing or confirming orders with any broker ([ADR-001](adr/ADR-001-python-core-recommend-only.md)).
- Short selling, margin, derivatives, intraday trading.
- Hosted multi-user service.
