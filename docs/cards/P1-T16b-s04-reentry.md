---
id: P1-T16b
title: S04 no re-entry across missing sessions
milestone: M1.4 Strategies
release: v0.1.0
status: done
branch: fix/P1-T16b-s04-reentry
due: 2026-11-22
---

### P1-T16b — S04 onset test must carry the last observed z across missing sessions

- Found by G2 on P1-T16 (major): `open_side` compared with `z[t-1]` and treated NaN as "no z", so
  one missing session reset the band. `open_side([0, 2.5, 2.6, 2.7, 2.8, nan, 2.9], 2, 3)` re-entered
  (+1) but must return 0 like the gap-free sequence.
- Fix: compare with the last OBSERVED z; only the window start counts as no z. Docstrings and
  docs/strategies.md follow. Tests: the exact probe, and re-entry allowed when z returns inside the
  band across a gap and then breaks out.
- Minor: `features/core.py` docstring says `close_20d_break` was added in features-v2 (not v3).
- Files: `src/vnstratlab/strategies/builtin/s04_bank_pairs.py`, `src/vnstratlab/features/core.py`
  (docstring), `docs/strategies.md`, `tests/test_strategy_s04.py`.
