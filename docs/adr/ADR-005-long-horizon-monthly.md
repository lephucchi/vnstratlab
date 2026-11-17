# ADR-005: Long horizon uses monthly decision days

- Status: **accepted** (decision days) · **proposed** (threshold conversions and tranches, §2)
- Date: 2026-11-17
- Deciders: owner
- Related: plan D8, §5.1; [engine.md §3](../engine.md#3-two-clocks); P1-T02

## Context

The plan set long-horizon decision days "after semi-annual and annual report seasons"
(about twice a year). The owner chose **monthly** decision days for the long horizon instead.
User-defined buy/sell dates for a personal portfolio belong to Phase 3 (portfolio optimisation),
not to the lab calendar.

## Decision

1. **Accepted.** `books.long.decision_day: last_trading_day_of_month` (same rule as medium).
   The anchor mechanism (`decision_anchors`) is removed from P1-T02.
2. **Proposed (owner to freeze).** Changing the period unit from ~6 months to 1 month silently
   changes the meaning of frozen lab values, so they must be converted explicitly:

| Key | Old value (half-year periods) | Meaning before | Proposed (monthly periods) | Why |
|---|---|---|---|---|
| `lab.gate1.min_periods.long` | 4 | ~2 years | **24** | Keep ~2 years of OOS evidence |
| `lab.gate2.block_size.long` | 1 | no overlap | **12** | 1-year holding outcomes overlap across 12 monthly decisions; block bootstrap must cover the overlap |
| `books.long.tranches` | — | — | **12** | One tranche rebalanced per month keeps a 1-year holding period per tranche (as medium uses 3) |
| `lab.weights.long.window` | null (all history) | all | **null** (unchanged) | Long still uses all history |

3. Phase 3 adds user-configurable buy/sell dates for the personal recommended portfolio
   (e.g. "rebalance my real portfolio on the 5th of each quarter"); that is a separate card.

## Consequences

- ~96 long-horizon decisions in 8 years, but outcomes overlap: still only **~8 non-overlapping
  1-year outcomes**. Reports must state both numbers; statistical power does not rise 12-fold.
- More frequent long-book trading: turnover and costs rise somewhat; tranches limit this to
  1/12 of the book per month.
- P1-T02 (calendar) implements monthly long decision days; P1-T22/T23 use the converted
  thresholds once frozen.

## Alternatives considered

- **Keep report-season anchors:** fewer, more meaningful decisions after fundamentals change, but
  irregular dates and only ~2 decisions a year. Not chosen by the owner.
- **Monthly without tranches:** the whole long book could turn over every month, which defeats
  the 1-year horizon. Rejected in the proposal.
