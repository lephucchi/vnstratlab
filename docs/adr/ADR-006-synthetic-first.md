# ADR-006: Synthetic data first; no external data source until the owner picks one

- Status: **accepted**
- Date: 2026-11-17
- Deciders: owner
- Supersedes: plan decision **D6** (data source `vnstock`, free Community tier)
- Related: [data-source review: vnstock](../reports/data-source-vnstock.md),
  [data-sources.md](../data-sources.md), P1-T03, P1-T11, P1-T32, new card P1-T36

## Context

D6 assumed `vnstock` as a free library over public Vietnamese market endpoints: no account,
anyone can run the lab. The review of 2026-11-17 found that this no longer holds:

- every `vnstock` release before generation 6 stopped authenticating on 2026-11-10, and the
  package is no longer installable from PyPI;
- generation 6 reaches data only through official broker Open APIs with each user's own
  brokerage account and keys (bring-your-own-key);
- `vnstock` 6 itself is proprietary (expiring releases, remote switch-off, no reverse
  engineering) and is not acceptable as a dependency; the companion `vnstock-oapi` permits free
  "extension packages" under conditions (user installs it, own keys, no redistribution, no
  orders);
- the only source usable in an unattended nightly loop today is SSI FastConnect Data, which
  needs an SSI account; raw vs. adjusted prices, fees, rate limits and IP policy are unknown.

Choosing a source now would block the engine on questions that do not affect it.

## Decision

1. **No external market data source in Phase 1 until the owner picks one.** D6 is superseded.
   Candidates stay open: SSI via `vnstock-oapi` with user keys, another free licence-clean
   daily source, or exchange publications. The choice gets its own ADR.
2. **Synthetic first.** New card **P1-T36** builds the `DataSource` protocol (from P1-T03) and a
   deterministic, seeded synthetic market for the default universe: daily OHLCV, HOSE price
   limits, tick sizes, lots, suspensions, corporate-action events and regime changes. It is
   the data for the engine, features, strategies, lab, tests, CI and `vnstratlab demo`.
3. **Card order.** P1-T11 (simulator) depends on P1-T02 and **P1-T36** instead of P1-T06.
   P1-T03, P1-T04, P1-T06 (real-data part), P1-T07, P1-T08 (real-data part) and P1-T09 are
   **blocked on the source decision**. Logic that can be proven on synthetic fixtures
   (price adjustment, DQ checks) may be built earlier against P1-T36.
4. **Rules unchanged.** No real market data in the repo, CI, artifacts or docs; synthetic data
   is labelled as such everywhere it is shown; no result on synthetic data is presented as
   evidence about the real market.

## Consequences

- v0.1 ships the engine, risk layer, strategies and `demo` on synthetic data; real-data
  ingestion moves to the release after the source decision.
- `VNSTOCK_API_KEY` in `.env` is obsolete (old keys no longer work). It stays in `Settings`
  until the source ADR, which renames or removes it.
- Engine tests gain realistic fixtures early (limits, ticks, lots, corporate actions), which the
  hand-computed P1-T11 cases need anyway.

## Alternatives considered

- **SSI via `vnstock-oapi` now:** needs an SSI account and keys before any engine work, and its
  own reads of `SSI_*` keys conflict with the `Settings`-only secrets rule (needs an ADR).
  Deferred, not rejected.
- **`vnstock` 6:** proprietary terms; rejected as a dependency.
- **Search for another free source first:** no ready replacement found; would stall the engine.
