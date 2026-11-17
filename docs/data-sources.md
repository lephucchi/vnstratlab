# Data sources

## Policy

1. **Free first.** Phase 1 uses free sources so anyone can run the lab.
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
| `vnstock` | Python library over public Vietnamese market endpoints | To review in P1-T03 | Recent versions use their own licence terms; review before making it a dependency. Check the installed API, not old docs |
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
