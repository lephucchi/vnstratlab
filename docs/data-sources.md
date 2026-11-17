# Data sources

## Policy

1. **Free first.** Phase 1 uses free sources so anyone can run the lab. Until a source is chosen,
   Phase 1 runs on a deterministic synthetic market (P1-T36, [ADR-006](adr/ADR-006-synthetic-first.md)).
2. **Adapter interface.** Every source implements the `DataSource` protocol (P1-T03), so a
   source can be replaced without touching the engine.
3. **No redistribution.** vnstratlab downloads data to the user's machine only. The repository,
   CI artifacts, caches, releases and docs never contain real market data.
4. **Licence check before integration.** Each source gets a short review in
   `docs/reports/data-source-<name>.md` before it becomes an install extra: terms of use,
   commercial/non-commercial limits, rate limits, attribution, whether automated access and
   datacenter IPs are allowed.
5. **Raw kept.** Raw responses are stored as Parquet in `<home>/data/raw/` for audit and
   re-processing.

## Candidates

| Source | Type | Status | Notes |
|---|---|---|---|
| Synthetic market (P1-T36) | Seeded generator: OHLCV, limits, ticks, lots, corporate actions | **Used in Phase 1** | Labelled synthetic everywhere; never evidence about the real market |
| `vnstock` 6 | Proprietary library (vendor index, not PyPI) | **Rejected as a dependency** | Pre-v6 releases stopped working on 2026-11-10; v6 has expiring releases and a remote switch-off. [Review](reports/data-source-vnstock.md) |
| `vnstock-oapi` + SSI FastConnect Data | Source-available adapter over the broker's Open API, user's own SSI account and keys | Candidate, decision deferred (ADR-006) | Free extensions allowed under conditions; raw vs. adjusted, fees, rate limits and IP policy unknown. [Review](reports/data-source-vnstock.md) |
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
