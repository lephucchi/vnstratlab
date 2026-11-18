# Roadmap

Releases map to milestones of the [implementation plan](plan/plan.md). Each minor release passes
gates G1–G4 ([qa-gates.md](qa-gates.md)).

| Release | Milestones | Cards | Highlights |
|---|---|---|---|
| **v0.0.x** | M1.0 | P1-T01 ✅ | Scaffold, CI, docs |
| **v0.1.0** | M1.0–M1.4 | P1-T02 … P1-T19, P1-T32, P1-T36 … P1-T38 | Config + calendar, data pipeline (synthetic market P1-T36, interim Yahoo prices P1-T37, quality checks + gap register P1-T38), features, simulator with HOSE rules, risk layer, strategy registry and built-ins, `backtest`, offline `demo` |
| **v0.2.0** | M1.5 | P1-T20 … P1-T23, P1-T33 | Walk-forward, DSR, PBO, SPA, MCS, weights, meta-backtest, stress tests, lab reports |
| **v0.3.0** | M1.6–M1.8 | P1-T24 … P1-T30 | Paper books, journal, `daily`, FastAPI, dashboard (5 pages), Telegram, scheduler in `serve`, backups |
| **v0.4.0** | Phase 2 | P2-T01 … P2-T08 | News normalisation, LLM scoring, news features, IC study, ADR-002 decision |
| **v0.5.0** | Phase 3 | P3-T01 … P3-T06 | Portfolio optimisation, lot-aware allocation, user-recorded fills, real-vs-recommended tracking |
| **v1.0.0** | — | — | Phase 1 stable for 3 months of nightly paper runs; API frozen |

> **Data source (ADR-007, 2026-11-18).** `vnstock` stopped working for free use on 2026-11-10
> (ADR-006). Phase 1 uses **Yahoo Finance as an interim price source** through an optional
> adapter, plus the synthetic market for tests, CI and `demo`. Known shortfalls are tracked in
> the [gap register](data-gaps.md) and closed by later cards. P1-T03 is replaced by P1-T36 +
> P1-T37. Fundamentals (P1-T07), flows (P1-T04) and news (P1-T09) still wait for a source.

## Schedule (data platform, M1.1)

Planned dates; the PO dashboard shows the live status of each card.

| Card | Title | Depends on | Planned | Branch |
|---|---|---|---|---|
| ADR-007 | Yahoo interim source, pipeline boundary, gap register | — | 2026-11-18 | `docs/adr-007-yahoo-interim` |
| [P1-T36](cards/P1-T36-datasource-synthetic.md) | `DataSource` protocol, market store, synthetic market, `ingest` | P1-T02 | 2026-11-19 | `feat/P1-T36-datasource-synthetic` |
| [P1-T37](cards/P1-T37-yahoo-source.md) | `YahooSource` adapter (optional `[yahoo]`) | P1-T36 | 2026-11-20 | `feat/P1-T37-yahoo-source` |
| [P1-T38](cards/P1-T38-quality-gaps.md) | Quality checks v0, gap register, `data status` | P1-T37 | 2026-11-21 | `feat/P1-T38-quality-gaps` |
| P1-T05 | Universe membership history (GAP-13) | P1-T02 | week of 2026-11-23 | — |
| P1-T06 | Corporate actions and adjusted prices (respects `price_basis`) | P1-T38 | week of 2026-11-23 | — |
| P1-T10 | Feature store v1 | P1-T06 | week of 2026-11-30 | — |
| P1-T11 … P1-T19 | Engine, risk, strategies | P1-T36 | 2026-11-30 → 2026-12-18 | — |
| P1-T32, P1-T35 | `demo`, `init` | P1-T19 | week of 2026-12-21 | — |
| release/v0.1.0 | Gate G3 (reality analyst) and G4 (owner) | all above | 2026-12-28 | — |

Gap-closing cards (holidays 2015–2025 for GAP-05, a raw-price `FileSource` for GAP-01/04) are
written when the owner schedules them.

## Cards added for the open-source version

| Card | Title | Release |
|---|---|---|
| P1-T36 | `DataSource` protocol, market store and synthetic market (ADR-006/007); unblocks the engine | v0.1 |
| P1-T37 | `YahooSource`: interim real price source, optional extra (ADR-007) | v0.1 |
| P1-T38 | Data-quality checks v0, gap register, `vnstratlab data status` (ADR-007) | v0.1 |
| P1-T32 | `vnstratlab demo`: synthetic dataset and offline end-to-end run | v0.1 |
| P1-T33 | `vnstratlab stress`: realism stress tests (costs, delay, liquidity, param noise, regimes) | v0.2 |
| P1-T34 | Cross-engine check harness (vectorbt, backtrader) for G3.2 | v0.2 |
| P1-T35 | `vnstratlab init` wizard and user config merge | v0.1 |

## Not planned

- Placing, routing or confirming orders with any broker ([ADR-001](adr/ADR-001-python-core-recommend-only.md)).
- Short selling, margin, derivatives, intraday trading.
- Hosted multi-user service.
