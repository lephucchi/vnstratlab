# ADR-007: Yahoo Finance as the interim Phase 1 price source; separate data pipeline; gap register

- Status: **accepted**
- Date: 2026-11-18
- Deciders: owner
- Amends: [ADR-006](ADR-006-synthetic-first.md) (decision 1 "no external source until the owner
  picks one") and plan decision **D6**
- Related: [data-source review: Yahoo](../reports/data-source-yahoo.md),
  [data-pipeline.md](../data-pipeline.md), [data-gaps.md](../data-gaps.md), cards P1-T36,
  P1-T37, P1-T38

## Context

ADR-006 put Phase 1 on synthetic data because `vnstock` stopped working on 2026-11-10 and every
remaining Vietnamese source needs a brokerage account (SSI FastConnect, TCBS, ...). The owner
cannot use SSI. To build and test the lab on real price history, the owner wants a free source
that needs no account, accepting known gaps that are filled later.

A probe on 2026-11-18 (results kept outside the repository; no data committed) found that Yahoo
Finance, read through the open-source `yfinance` library, has daily OHLCV for all 13 universe
banks and TPB on HOSE (`<TICKER>.VN`), in VND, with history from 2010 for some tickers and from
2020-2021 for others. It also showed the gaps listed in [data-gaps.md](../data-gaps.md):
prices are split-adjusted (no raw prices), no VNINDEX/VN30 index, no HNX/UPCoM, filler rows on
market holidays, occasional stale or duplicated rows.

Yahoo's Terms of Service (section 2(d)) prohibit collecting data "using any automated means"
without Yahoo's prior permission, with no personal-use exception; `yfinance` says Yahoo's API
"is intended for personal use only" and defers to Yahoo's terms. See the review.

## Decision

1. **Interim source.** Phase 1 uses Yahoo Finance daily prices through an optional
   `YahooSource` adapter (P1-T37), installed with `pip install "vnstratlab[yahoo]"`. It is
   labelled *interim* everywhere. ADR-006 decision 1 is amended accordingly; D6 now reads
   "synthetic data for tests/CI/demo; Yahoo Finance as interim user-side price source".
2. **User's choice, user's responsibility.** vnstratlab is a tool: it ships adapters, not data.
   Each user chooses a source, runs it on their own machine and is responsible for following
   that source's terms. The adapter shows a one-time notice that names Yahoo's terms and that
   the data is for the user's own research. vnstratlab never redistributes downloaded data.
   The owner accepts the ToS risk described above for their own use (accepted risk, not a legal
   opinion).
3. **Separate data pipeline.** Everything that touches a source lives in `vnstratlab.data`
   (sources → raw snapshot → normalise → quality checks → `market.duckdb`). Engine, features,
   strategies and lab read only the tables, never a source; an import-boundary test enforces this
   (P1-T36). Design: [data-pipeline.md](../data-pipeline.md).
4. **Gap register.** Every known shortfall of the interim source is a numbered gap (`GAP-xx`) in
   one machine-readable file, `src/vnstratlab/data/gaps.yaml`, rendered in
   [data-gaps.md](../data-gaps.md) and shown by `vnstratlab data status` (P1-T38). Each gap names
   the affected tables, cards and exit criteria, the workaround now, and how to close it.
5. **Price basis is explicit.** Every `prices_daily` row records `source` and `price_basis`
   (`raw` | `split_adjusted` | `synthetic`). Split factors are never re-applied to rows with
   `price_basis = split_adjusted` (P1-T06); cash-dividend adjustment for signals still applies.
   HOSE limit/tick checks on these rows are warnings, not failures (P1-T08 / P1-T38). For
   execution the engine reconstructs raw-like prices from the stock events
   ([engine.md §2](../engine.md#phase-1-data-constraints-adr-007), clarified 2026-11-18).
6. **Config.** New `data:` section in `defaults.yaml` (P1-T36): `data.source` (default
   `synthetic` in P1-T36, changed to `yahoo` by P1-T37 under this ADR), adapter options, rate
   limit. `project.backfill_start` stays 2015-01-01; tickers simply start when Yahoo history
   starts (GAP-04).
7. **Secrets.** Yahoo needs no key. `VNSTOCK_API_KEY` is removed from `Settings`,
   `.env.example` and `doctor` (P1-T37).
8. **Unchanged rules.** No real market data in the repo, fixtures, CI, artifacts or docs; CI never
   calls Yahoo (adapter tests use an injected fake fetcher and `synthetic_yahoo_*` fixtures);
   recommend-only.
9. **Scheduling.** The nightly loop scheduler stays inside `vnstratlab serve` (P1-T30) to avoid
   DuckDB cross-process locking. Until then users may run `vnstratlab ingest` from the OS
   scheduler (Task Scheduler / cron), documented in [data-pipeline.md](../data-pipeline.md).

## Consequences

- Real-data ingestion lands in v0.1 instead of after a source ADR. P1-T03 is replaced by P1-T36
  (protocol, store, synthetic) + P1-T37 (Yahoo); P1-T08 is partly delivered early as P1-T38
  (quality checks v0 + gap register).
- Phase 1 exit criterion 2 (closes match a public price board exactly) cannot be met on
  split-adjusted history (GAP-14); it is checked only on sessions after the last corporate action
  until a raw source closes GAP-01.
- Results on Yahoo data carry the source label and the open gaps in every lab report.
- If Yahoo blocks or changes its endpoints, the lab keeps working on synthetic data and on the
  data already stored; a new adapter replaces Yahoo without touching the engine.

## Alternatives considered

- **Stay synthetic only (ADR-006):** no real history to test the lab against. Kept for tests,
  CI and `demo`.
- **SSI FastConnect Data via own client:** free but needs an SSI account registered in person;
  not usable by the owner.
- **CafeF EOD files imported by the user (`FileSource`):** has raw and adjusted prices for
  HOSE/HNX/UPCoM, manual download only. Deferred; listed as the way to close GAP-01, GAP-04.
- **EODHD / Twelve Data:** paid for Vietnamese coverage; EODHD free tier has 1 year of history.
- **Unofficial broker web endpoints / community scrapers:** same fragility that ended `vnstock`.
