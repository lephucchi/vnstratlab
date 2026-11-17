# ADR-004: Recommendation follows the gated, weighted strategy set

- Status: **accepted**
- Date: 2026-11-17
- Deciders: owner
- Related: plan D10, [end-to-end-flow.md §3](../end-to-end-flow.md#why-replay-many-windows-not-one), P1-T22, P1-T23

## Context

The lab replays every trial walk-forward and could recommend either (a) the gated,
MCS-weighted set of strategies, or (b) the single best strategy of the last window
("#1", the `last_winner` selector). A single window's winner is often luck; but the owner wants
evidence, not opinion, to decide.

## Decision

1. **Default: (a).** Recommendations follow gate 1 → gate 2 → MCS → shrunk Hedge weights, with
   `hold_benchmark` as fallback (plan D10, Appendix B). The dashboard always shows the full
   leaderboard, including the #1 trial.
2. **Pre-registered switching rule.** For a given horizon, the recommendation switches to (b)
   only if the meta-backtest (P1-T23) shows **all** of:
   1. Measured on **executable, after-cost** period returns of that horizon, over the full
      meta-backtest span.
   2. `last_winner` beats the gated selection: paired difference (b − a) has a **one-sided
      block-bootstrap p < 0.10** (block size and reps from `lab.gate2`, seed from `lab.seed`).
   3. Max drawdown of (b) is **not worse than (a) by more than 1 percentage point**.
   4. At least the gate-1 minimum number of periods for that horizon.
3. The rule may be edited by the owner **only before** P1-T23 first produces results. After
   that, changes require a new ADR and are reported as a new trial of the selection method.
4. The switch is evaluated at each minor release (gate G3) and recorded in the readiness report.

## Consequences

- P1-T23 must output the statistics in rule 2 per horizon, reproducibly from a script.
- `selection_runs.status` gains the value `last_winner` if the rule ever triggers for a horizon.
- No change to plan §2; this ADR makes D10's evaluation explicit.

## Alternatives considered

- **Always #1:** simplest, highest risk of following luck. Rejected by the owner.
- **Decide after seeing P1-T23 numbers:** invites a post-hoc choice. Rejected in favour of the
  pre-registered rule above.
