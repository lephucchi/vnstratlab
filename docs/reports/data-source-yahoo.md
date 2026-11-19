# Data source review: Yahoo Finance via `yfinance`

Status: **reviewed** · owner decision: [ADR-007](../adr/ADR-007-yahoo-interim-source.md)
(interim Phase 1 source, accepted risk). Reviewed: 2026-11-18. Reviewer: manager + research
agent. This is a reading of public terms and a technical probe, not legal advice. The vendor's
own text is the binding version.

## 1. Summary

| Question (data-sources.md policy 4) | Answer |
|---|---|
| Library licence | `yfinance` is Apache-2.0 (code only; says nothing about Yahoo's data) |
| Affiliation | "yfinance is not affiliated, endorsed, or vetted by Yahoo, Inc." (README) |
| Terms of use for the data | Yahoo Terms of Service. §2(d) prohibits accessing or collecting data "using any automated means" without Yahoo's prior permission; no personal-use exception. §2(e): no commercial use. §2(h): no reproduction or distribution of content without written permission |
| Personal use | `yfinance` README: "the Yahoo! finance API is intended for personal use only" |
| Rate limits | Not published; Yahoo APIs "may be subject to rate limits at Yahoo's absolute and sole discretion" (Yahoo API terms) |
| Attribution | Yahoo API terms require following the Yahoo attribution policy *if* a product uses the Yahoo APIs; whether the endpoints used by `yfinance` count as "Yahoo APIs" is not stated |
| Account / key | None |
| Automated access / datacenter IPs | Prohibited by ToS §2(d) without permission; behaviour from cloud IPs untested. CI never calls it |
| Redistribution | Not allowed (ToS §2(h)); vnstratlab never redistributes data |
| Commercial use | Not allowed (ToS §2(e)); vnstratlab is non-commercial |

**Fit with vnstratlab:** acceptable only as an **optional, user-side adapter** whose use is the
user's decision and responsibility (ADR-007 §2), with a one-time notice, no data in the
repository, and no calls from CI. The owner accepts the ToS risk for their own use.

## 2. Technical probe (2026-11-18)

Run with `yfinance` 1.8.0 in a throwaway environment outside the repository. **No data was
kept in the repository**; findings are described qualitatively.

| Item | Finding | Gap |
|---|---|---|
| Universe coverage | All 13 banks + TPB available as `<TICKER>.VN` (HOSE), currency VND | — |
| History depth | From 2010 for VCB, CTG, STB; from 2014–2018 for BID, SHB, HDB, VPB, TPB, TCB; from 2020–2021 for ACB, LPB, VIB, SSB (their HOSE listing dates) | GAP-04 |
| Indices | `^VNINDEX` and VN30 not available. VN30 ETF `E1VFVN30.VN` exists | GAP-03 |
| HNX / UPCoM | `.HN` symbols not found | GAP-04 |
| Price basis | `Close` is split-adjusted: stock dividends and bonus shares appear as fractional "splits" and earlier prices are scaled (off the tick grid). `Adj Close` additionally adjusts cash dividends | GAP-01 |
| Reference / ceiling / floor | Not provided | GAP-02 |
| Holidays | Rows exist on market holidays (e.g. Tết 2026) with volume 0 and the previous close repeated | GAP-05 |
| Corporate actions | `splits` (incl. stock dividends) and cash `dividends` series; no rights issues, no record dates | GAP-06 |
| Quality | Occasional consecutive sessions with identical close (and once identical volume); large single-day moves on some corporate-action dates | GAP-07 |
| Revisions | A new split rescales all earlier prices | GAP-08 |

## 3. Adapter requirements (become acceptance criteria of P1-T37)

1. Optional extra `[yahoo]`; lazy import; the core install and CI work without `yfinance`.
2. Fetch function injectable; unit tests use a fake and `synthetic_yahoo_*` fixtures only.
3. Rows labelled `source = yahoo`, `price_basis = split_adjusted`; raw response snapshot per
   ingest run kept as Parquet under `<home>/data/raw/yahoo/`.
4. Drop filler rows (volume 0 and O = H = L = C = previous close) and log them; drop the current
   session's bar if it is not final.
5. One-time notice on first use (Vietnamese and English) naming Yahoo's terms and the user's
   responsibility; `--accept-source-terms` flag for unattended runs.
6. Polite rate limit (config `data.yahoo.max_requests_per_minute`, default 30) and retries with
   backoff.

## 4. Sources (read 2026-11-18)

- `yfinance` README and licence: <https://github.com/ranaroussi/yfinance>,
  <https://github.com/ranaroussi/yfinance/blob/main/LICENSE.txt>
- Yahoo Terms of Service (US): <https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html>
  (sections 1–11 read verbatim; regional terms in §14 not reviewed)
- Yahoo API Terms of Use: <https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html>

## 5. Open questions

1. Which Yahoo entity and regional terms apply to a user in Vietnam (ToS §13–14 not reviewed).
2. Whether trading volume is adjusted for splits the same way as prices. P1-T06 assumes it is and
   divides volume by `F(t)` in the execution series.
   Whether Yahoo's dividend amounts are split-adjusted is also open: the repository fixtures are
   hand-built and cannot answer it (P1-T06 finding), so amounts are used as stored and
   `vnstratlab.data.adjust.DIVIDENDS_SPLIT_ADJUSTED` (default False) is the one switch to flip once
   a real sample is compared against a raw source.
3. How Yahoo treats repeated requests from datacenter IPs (not tested; CI never calls it).
