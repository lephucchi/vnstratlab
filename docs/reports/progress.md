# Progress log

One line per merge into `develop`, appended by the manager (see [workflow.md](../workflow.md#8-progress-log)).

```
date       | card   | PR / commit      | summary                                   | tests          | review
2026-11-17 | P1-T01 | initial commit   | scaffold, CLI stubs, CI, docs, ADR-001    | 23 passed, 98% | owner
2026-11-17 | P1-T02 | squash to develop | config loader + trading calendar, HOSE 2026 holidays | 97 passed, 98% | G2 round 2 request changes fixed; round 3 skipped by owner
2026-11-17 | chore  | PR #1 squash     | PO login (encrypted Pages data), plain env names, Pages deploy fix | 118 passed, 98% | G2 round 2 approve
2026-11-18 | ADR-007 | PR #13 squash    | ADR-007 Yahoo interim source, data pipeline design, gap register (14), cards P1-T36..T38 | 118 passed, 98% | owner (docs only)
2026-11-18 | P1-T36 | PR #15 squash    | DataSource protocol, DuckDB market store (raw snapshots, revisions, kind guard, atomic ingest), synthetic market, ingest CLI | 198 passed, 96.5% | G2 round 3 approve
2026-11-18 | tools  | PR #16 squash    | PO data: gap register and card due dates (build_status.py) | 213 passed | G2 round 3 point verified by manager
2026-11-18 | P1-T37 | PR #19 squash    | YahooSource (interim, optional [yahoo]); rescale refetch, per-ticker resume | 265 passed, 97.7% | G2 approve (round 3, after merge)
2026-11-18 | P1-T38 | PR #20 squash    | DQ checks v0, gap register, data status / data gaps | 363 passed, 97.0% | owner override; open: trailing synthetic suspension gap fails DQ on some days
2026-11-18 | docs   | PR #18 squash    | engine HTML diagrams, Phase 1 data constraints, CLAUDE.md no-watermark rule | docs | owner override after 4 G2 rounds
2026-11-18 | ADR-003 | PR #21 squash   | ADR-003 accepted in part; card P1-T11 | docs | owner override after 2 G2 rounds
2026-11-18 | P1-T11 | PR #23 squash    | simulator core (HOSE rules, ledger, order lifecycle, ideal/executable) | 456 passed | owner override; open: late-action entitlement, turnover denominator, pre-ex pending rescale (G2 request changes)
2026-11-19 | P1-T11b | PR #25 squash    | close P1-T11 G2 findings (late-action entitlement via bonus credits, turnover / previous-close equity, pre-ex pending rescale), synthetic declared suspensions in DQ, lazy CLI imports | 483 passed, 97.45% | G2 approve (round 3)
2026-11-19 | P1-T06 | PR #29 squash    | prices_adjusted (signals), prices_exec (exec_reconstructed), exec_exclusions; bad rows recomputed on rebuild; scale-discontinuity check; data rebuild --dry-run; pay/listing dates | 521 passed, 97.15% | G2 approve (round 2); open: [VERIFY] Yahoo dividend and volume scaling
2026-11-19 | P1-T12 | PR #28 squash    | risk layer (ATR sizing, max weight/positions, vol scaling, circuit breaker), lot-based ATR stops, cooldown from stop exit, ex-date ATR factor, rebalance threshold | 556 passed, 97.19% | G2 approve (round 2); open: late add_actions not in ATR series (follow-up), owner to confirm risk.stop_cooldown_sessions=null
2026-11-19 | P1-T12b | PR #32 squash    | ATR recomputed on late add_actions, exact lot/ledger sync, lots for bonus without entry, ex-date-open lot ATR basis | 571 passed | G2 approve (round 1); round-2 fixes merged without re-review (owner)
2026-11-19 | P1-T06b | PR #33 squash    | Yahoo outlier/step/pre-HOSE handling, split-adjusted dividends, owner decisions docs | 583 passed, 97.30% | owner override with G2 request changes open → issue #34
2026-11-21 | docs   | PR #35 squash    | tiered G2 review (light/full), delta rounds max 2, trust green CI | docs | light tier (owner decision)
2026-11-21 | P1-T06c | PR #36 squash   | step vs outlier (AC1 a+b), pre-HOSE cut at last out-of-band run, cash ex-date exempt, signal_ok, exec_exclusions.rows | 591 passed, 97.29% | G2 approve (round 2 delta); regression on real data (non-HOSE cut 25,094 rows) → P1-T06d; minor → #37
2026-11-21 | docs   | PR #38 squash    | real-data dry run before merging data-cleaning PRs | docs | light tier
2026-11-21 | P1-T06d | PR #39 squash   | non-HOSE cut only at clustered out-of-band sessions (250/10, owner-approved); real data prices_exec 6,223 -> 24,483 | 593 passed | G2 approve (round 1); minor -> #37
2026-11-21 | P1-T06e | PR #40 squash   | spike = one event, reset on clustered only, near-tolerance steps (LPB/SHB/VIB kept), duplicate_session, adjusted_is_rebuilt (ratio-v2); real data prices_exec 27,541, no excluded tickers | 604 passed | G2 approve (round 1); minor -> #41
2026-11-21 | docs   | PR #42 squash    | GAP-07 Tuesday duplicate pattern; progress log | docs | light tier
2026-11-21 | P1-T10 | PR #43 squash    | feature store v1 (6 groups, signal_ok = missing, rebuilt-store guard, feature_version, asof loader); real data 27,551 rows in 0.9 s | 664 passed, 97.2% | G2 approve (round 2 delta); membership by date -> #44
2026-11-21 | P1-T13 | PR #45 squash    | Strategy protocol, BaseStrategy (registry requires it), append-only trial_registry, trial_id incl. horizon, lab trials / lab register | 693 passed, 97.2% | G2 approve (round 2 delta); minor -> #46
2026-11-21 | P1-T14 | PR #47 squash    | S00 composite (4 blocks, owner 2026-11-21; trigger filter before top_n, owner-confirmed), S17 equal weight; packaged config 5 trials | 733 passed, 97.25% | G2 approve (round 1)
2026-11-21 | P1-T15 | PR #49 squash    | S01 weekly reversal, S02 breakout (close_20d_break, features-v2), S03 oversold in uptrend; 10 packaged trials | 833 passed, 97.3% | G2 approve (round 1); minor -> #46
2026-11-21 | P1-T16 | PR #50 squash    | S04 bank pairs (onset max_hold), S05 residual s-score, ret_1d (features-v3), lookback_sessions; 12 packaged trials | 907 passed, 97.4% | owner merge with CI green before G2 finished; G2 request changes (S04 re-entry across NaN) -> P1-T16b; no trials registered yet
2026-11-21 | P1-T16b | PR #52 squash   | S04 open_side carries the last observed z across missing sessions (no re-entry after a time stop) | targeted 76 passed, CI green | G2 approve (P1-T16 round 2 delta)
```
