---
id: P1-T12b
title: Risk follow-ups — ATR for late actions, exact lot shrink, bonus lots
milestone: M1.3 Engine
release: v0.1.0
status: in progress
branch: feat/P1-T12b-risk-followups
due: 2026-11-21
---

### P1-T12b — Risk follow-ups from the P1-T12 review

- Depends on: P1-T12 · issue #30
- Branch: `feat/P1-T12b-risk-followups`, from `develop`
- Goal: make the stop/ATR state independent of **when** a corporate action becomes known, so a
  paper book that receives a late Yahoo event and a replay that knows it up front produce the
  same digest (required by P1-T24).

#### Fixes
1. **ATR for late actions.** `Simulator.add_actions` must update the ex-date factors of the
   affected tickers and recompute their ATR series (`risk.atr.atr(..., ex_factor=)` stays pure).
   Only reads after the apply session use the new series (no lookahead: values for sessions
   before the apply session that were already used are not rewritten in outputs). Remove the
   limitation note in engine.md §7.
2. **Exact lot shrink.** `_reduce_entry` (loop.py) shrinks lots to the ledger's remaining shares
   (`left / total`), not `(total − sold) / total`, so lot totals never drift from the ledger after
   floored bonuses or late credits.
3. **Bonus shares without an entry.** A late bonus credited after the position was fully sold (or
   any share added with no lot) gets a lot: entry price = the ticker's last close before the apply
   session in the execution basis, ATR = current ATR; document the rule in engine.md §7.

#### Files to create / change
- `src/vnstratlab/engine/loop.py`, `src/vnstratlab/risk/atr.py` (only if a helper is needed)
- `tests/test_engine_loop.py`, `tests/test_risk_atr.py`
- `docs/engine.md` §7, `CHANGELOG.md`

#### Acceptance criteria (hand-computed; numbers in test comments)
1. Replay determinism: the same run with a 50 % stock event passed at construction vs added late
   via `add_actions` before its ex-date gives identical digests; added after the ex-date, ATR
   values from the apply session on equal the up-front run's (hand numbers from the P1-T12 probe:
   ATR at the ex-date 1,035.7, not 2,160.7).
2. Lot totals equal ledger shares after: partial sell, floored 15 % bonus, late bonus on sold
   shares (property test over ≥ 100 random sequences).
3. A late bonus on a fully sold position creates a lot with the stated entry and ATR; a stop can
   fire on it.
4. Existing P1-T11 / P1-T11b / P1-T12 tests pass; with no risk layer, digests unchanged.
5. `pytest && ruff check . && ruff format --check . && mypy` green; coverage ≥ 80 %; no network.

#### Out of scope
Data-side event repair (P1-T06b), strategies, paper books (P1-T24).
