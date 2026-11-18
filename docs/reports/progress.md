# Progress log

One line per merge into `develop`, appended by the manager (see [workflow.md](../workflow.md#8-progress-log)).

```
date       | card   | PR / commit      | summary                                   | tests          | review
2026-11-17 | P1-T01 | initial commit   | scaffold, CLI stubs, CI, docs, ADR-001    | 23 passed, 98% | owner
2026-11-17 | P1-T02 | squash to develop | config loader + trading calendar, HOSE 2026 holidays | 97 passed, 98% | G2 round 2 request changes fixed; round 3 skipped by owner
2026-11-17 | chore  | PR #1 squash     | PO login (encrypted Pages data), plain env names, Pages deploy fix | 118 passed, 98% | G2 round 2 approve
2026-11-18 | ADR-007 | PR #13 squash    | ADR-007 Yahoo interim source, data pipeline design, gap register (14), cards P1-T36..T38 | 118 passed, 98% | owner (docs only)
2026-11-18 | P1-T36 | PR #15 squash    | DataSource protocol, DuckDB market store (raw snapshots, revisions, kind guard, atomic ingest), synthetic market, ingest CLI | 198 passed, 96.5% | G2 round 3 approve
```
