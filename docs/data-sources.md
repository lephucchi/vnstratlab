# Data sources

## Policy

1. **Free first.** Phase 1 uses free sources so anyone can run the lab: Yahoo Finance as an
   **interim** price source (P1-T37, [ADR-007](adr/ADR-007-yahoo-interim-source.md)) and a
   deterministic synthetic market for tests, CI and `demo` (P1-T36). Known shortfalls:
   [data gaps](data-gaps.md).
2. **Your source, your terms.** vnstratlab ships adapters, not data. You choose the source, run
   it on your own machine and follow that source's terms.
3. **Adapter interface.** Every source implements the `DataSource` protocol (P1-T03), so a
   source can be replaced without touching the engine.
4. **No redistribution.** vnstratlab downloads data to the user's machine only. The repository,
   CI artifacts, caches, releases and docs never contain real market data.
5. **Licence check before integration.** Each source gets a short review in
   `docs/reports/data-source-<name>.md` before it becomes an install extra: terms of use,
   commercial/non-commercial limits, rate limits, attribution, whether automated access and
   datacenter IPs are allowed.
6. **Raw kept.** Raw responses are stored as Parquet in `<home>/data/raw/` for audit and
   re-processing.

## Candidates

| Source | Type | Status | Notes |
|---|---|---|---|
| Yahoo Finance via `yfinance` (P1-T37) | Optional adapter `[yahoo]`, no account | **Interim Phase 1 price source** (ADR-007) | Split-adjusted prices, HOSE only, no indices; ToS restricts automated access, user's own responsibility. [Review](reports/data-source-yahoo.md) · [gaps](data-gaps.md) |
| CafeF EOD files (user download) | Files imported by the user | Candidate to close GAP-01/GAP-04 | Raw and adjusted, HOSE/HNX/UPCoM; manual download; terms not yet reviewed |
| Synthetic market (P1-T36) | Seeded generator: OHLCV, limits, ticks, lots, corporate actions | **Used for tests, CI, `demo`** | Labelled synthetic everywhere; never evidence about the real market |
| `vnstock` 6 | Proprietary library (vendor index, not PyPI) | **Rejected as a dependency** | Pre-v6 releases stopped working on 2026-11-10; v6 has expiring releases and a remote switch-off. [Review](reports/data-source-vnstock.md) |
| `vnstock-oapi` + SSI FastConnect Data | Source-available adapter over the broker's Open API, user's own SSI account and keys | Candidate, not used (owner has no SSI access, ADR-007) | Free extensions allowed under conditions; raw vs. adjusted, fees, rate limits and IP policy unknown. [Review](reports/data-source-vnstock.md) |
| Exchange and index announcements (HOSE) | Public web pages | Used in P1-T05 | VN30 review announcements for `universe_membership` |
| Company financial statements | Public filings | P1-T07 | Must record `published_at` |
| Foreign / proprietary flow | Various | P1-T04 investigates | S06 disabled if no acceptable free source |

## Data quality checks (P1-T08)

Missing tickers for the day, close outside [floor, ceiling], zero volume on a trading day,
adjusted day-over-day change > 15%, duplicate rows, stale data. Any failure stops the nightly
loop and sends an alert.

## Known pitfalls

- **Double adjustment.** Some endpoints return prices already adjusted for dividends. P1-T06
  must confirm the source returns raw prices before computing `prices_adjusted`.
- **Survivorship.** Universe membership must be read by date; tickers that left the index stay
  in history.
- **Publish dates.** Fundamentals without a publish date get a flagged fallback
  (quarter end + 45 days), never the quarter end itself.
- **Datacenter IPs.** Some Vietnamese endpoints may throttle or block foreign cloud IPs, which
  matters if you run the loop on GitHub Actions or a foreign VPS. Test first.
