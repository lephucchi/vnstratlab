# Architecture decision records

One file per decision: `ADR-NNN-<slug>.md`. Status: proposed → accepted | rejected | superseded.
Only the owner moves an ADR to accepted.

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-python-core-recommend-only.md) | Python core; recommend-only; GitHub Actions for CI only | Accepted |
| ADR-002 | News parameter adopt/reject (pre-registered in P2-T01) | Planned |
| [ADR-003](ADR-003-engine-architecture.md) | Engine and architecture refinements | Accepted in part (1, 3, 4, 6–12; 2 and 5 deferred) |
| [ADR-005](ADR-005-long-horizon-monthly.md) | Long horizon uses monthly decision days; threshold conversions proposed | Accepted / proposed |
| [ADR-004](ADR-004-selection-method.md) | Recommendation follows the gated, weighted set; pre-registered rule for switching to #1 | Accepted |
| [ADR-006](ADR-006-synthetic-first.md) | Synthetic data first; no external data source until the owner picks one (supersedes D6) | Accepted (amended by ADR-007) |
| [ADR-007](ADR-007-yahoo-interim-source.md) | Yahoo Finance as interim Phase 1 price source; separate data pipeline; gap register | Accepted |

## Template

```markdown
# ADR-NNN: <title>
- Status: proposed
- Date: YYYY-MM-DD
- Deciders: owner

## Context
## Decision
## Consequences
## Alternatives considered
```
