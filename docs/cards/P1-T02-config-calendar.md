---
id: P1-T02
title: Config loader and trading calendar
milestone: M1.0 Scaffold
release: v0.1.0
status: done
branch: feat/P1-T02-config-calendar
---

### P1-T02 — Config loader and trading calendar

- Depends on: P1-T01 (merged)
- Branch: `feat/P1-T02-config-calendar` (from `develop`)
- Goal: one validated, typed configuration object built from the packaged YAML plus the user's
  override, and a trading calendar that answers "is this a session, which is the next one, and
  which sessions are decision days".

#### Files to create / change
- `src/vnstratlab/config/models.py` (new): pydantic v2 models.
- `src/vnstratlab/config/loader.py` (new): loading, merging, validation, `ConfigError`.
- `src/vnstratlab/calendar.py` (new): `TradingCalendar`, `decision_days`.
- `src/vnstratlab/config/defaults.yaml`: `books.long.decision_day` becomes
  `last_trading_day_of_month` (owner decision; see item 7).
- `src/vnstratlab/config/markets/hose.yaml`: **already prepared by the manager** (holidays 2026
  complete, 2027 partial). Do not add, remove or change any date.
- `src/vnstratlab/cli.py`: `doctor` also prints config status and holiday coverage.
- `tests/test_config.py`, `tests/test_calendar.py` (new), fixtures under
  `tests/fixtures/` named `synthetic_*`.
- `docs/configuration.md` (merge rules), `CHANGELOG.md` (Unreleased).

#### Inputs
- Packaged files via `importlib.resources`: `defaults.yaml`, `markets/<project.market>.yaml`,
  `universes/<project.universe>.yaml`.
- Optional user override `<app home>/config.yaml` (path from `vnstratlab.paths`).

#### Outputs / behaviour
1. `load_config(home: Path | None = None) -> AppConfig` (immutable / frozen models), containing
   `defaults` sections (project, books, costs, risk, lab, benchmarks, stress, strategies, news,
   notify), the `market` (rules with `value`/`status`/`source`/`note`; holidays per year with
   `coverage` and `days`) and the `universe`.
2. Merge: user override is deep-merged over packaged defaults. Dicts merge recursively; lists and
   scalars **replace**. The user may override market rules and add holidays for a year via
   `market:` in their `config.yaml`.
3. Validation: unknown keys are errors (`extra="forbid"`). Invalid values raise `ConfigError`
   whose message lists every problem as `dotted.path: reason` (e.g.
   `costs.sales_tax_pct: Input should be greater than or equal to 0`). No raw stack traces in
   the CLI: `doctor` prints `config: INVALID` plus the messages and exits 1.
4. Sensible bounds: percentages in [0, 1); capital > 0; `max_positions` ≥ 1; horizons limited to
   `short|medium|long`; holiday dates must fall inside their year and on weekdays; holiday
   `status` in {`VERIFY`, `confirmed`, `provisional`}; `coverage` in {`complete`, `partial`}.
5. `TradingCalendar(holidays: Iterable[date])`, Mon–Fri sessions minus holidays:
   - `is_trading_day(d)`, `next_trading_day(d, n=1)`, `previous_trading_day(d, n=1)`,
     `trading_days(start, end)` (inclusive), `sessions_between(a, b)` (count).
   - `TradingCalendar.from_config(cfg)` uses config holidays.
   - `TradingCalendar.from_sessions(sessions)` builds a calendar from observed session dates
     (used later by P1-T03 for history, where trading days come from price data, not config).
6. `decision_days(calendar, horizon, start, end) -> list[date]`:
   - short: last trading day of each ISO week;
   - medium: last trading day of each calendar month;
   - long: last trading day of each calendar month (owner decision: long uses monthly decision
     days, same as medium).
   On a `from_sessions` calendar, a week/month cut off by the start or end of the data yields no
   decision day. `horizon` is typed with the `Horizon` Literal.
7. Long-horizon decision day: `defaults.yaml` `books.long.decision_day: last_trading_day_of_month`;
   there are no `decision_anchors`.
8. Coverage: `holiday_coverage(cfg, year) -> Literal["complete", "partial", "missing"]`.
   `doctor` prints coverage for the current and next year; `partial`/`missing` is a warning, not
   an error.

#### Acceptance criteria
1. `load_config()` on the packaged files returns a valid `AppConfig`; values round-trip
   (e.g. `cfg.costs.sales_tax_pct == 0.001`, `len(cfg.universe.membership[0].tickers) == 13`).
2. A user override changes one nested key and leaves its siblings intact (deep merge); a list in
   the override replaces the default list.
3. Each invalid fixture (`synthetic_bad_*.yaml`: unknown key, negative cost, bad horizon,
   holiday on a Saturday, holiday outside its year) raises `ConfigError` whose message contains the
   dotted path.
4. `doctor` with an invalid user config exits 1 and prints the dotted path; with no user config it
   prints `config: OK` and holiday coverage.
5. Calendar on a `synthetic_` holiday fixture: weekend and holiday are not trading days;
   `next_trading_day` skips a holiday spanning a weekend; `previous_trading_day` mirrors it;
   `trading_days` is inclusive; `n=3` works.
6. `decision_days` on fixtures: short returns the Thursday when Friday is a holiday; medium returns
   the last session of each month when the month ends on a weekend or holiday; long behaves like
   medium; a week/month truncated by the end of a `from_sessions` calendar yields nothing.
7. **Packaged holidays:** a test asserts the packaged `hose.yaml` has a **non-empty** `days` list
   for `date.today().year` (this test is meant to fail when a new year starts without data), and
   that every listed holiday is a weekday inside its year with a `source`.
8. With the packaged 2026 holidays: `is_trading_day(2026-02-18)` is False;
   `next_trading_day(2026-02-13) == 2026-02-23`; `is_trading_day(2026-08-22)` is False
   (Saturday make-up day not traded).
9. No new runtime dependencies; no network; `pytest`, `ruff check`, `ruff format --check`,
   `mypy --strict` all clean; coverage ≥ 80%.

#### Out of scope
- `vnstratlab init` wizard (P1-T35), databases, data ingestion, historical holidays before 2026
  (history uses `from_sessions` in P1-T03), market sessions/timezone logic beyond dates.

#### Notes
- Plan §3.2, Appendix A; `docs/configuration.md`; `docs/engine.md` §3 (two clocks).
- Never invent holiday dates or market facts. If something seems missing, report it in the handoff.
