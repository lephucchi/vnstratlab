# Data gaps

> Generated from `src/vnstratlab/data/gaps.yaml` (single source of truth, [ADR-007](adr/ADR-007-yahoo-interim-source.md)).
> Edit the YAML, then run `python tools/render_gaps.py`; a test fails if this page is out of date.

Interim price source: **yahoo**. Each gap is a known shortfall that is worked around now and closed later. `vnstratlab data status` prints the same list.

| ID | Gap | Severity | Status | Affects |
|---|---|---|---|---|
| [GAP-01](#gap-01) | No raw (unadjusted) prices | high | open | prices_daily, prices_adjusted, P1-T06, P1-T08, P1-T11, exit-2 |
| [GAP-02](#gap-02) | No reference, ceiling and floor prices | medium | open | prices_daily.ref_price, prices_daily.ceiling, prices_daily.floor, P1-T08, P1-T11 |
| [GAP-03](#gap-03) | No VNINDEX / VN30 index series | medium | open | benchmarks.market_indices, P1-T10 market-context features, P1-T23, G3 benchmarks |
| [GAP-04](#gap-04) | HOSE only; history starts at HOSE listing | medium | open | prices_daily, universe, P1-T10, P1-T20, lab statistics |
| [GAP-05](#gap-05) | Historical holiday lists missing before 2026 | medium | open | calendar, P1-T37, P1-T11, decision days before 2026 |
| [GAP-06](#gap-06) | Incomplete corporate actions | medium | open | corporate_actions, P1-T06, P1-T11 cash-dividend accounting |
| [GAP-07](#gap-07) | Stale and duplicated sessions | low | open | prices_daily, P1-T08, P1-T38 |
| [GAP-08](#gap-08) | History is revised after each split | medium | mitigated | prices_daily, data/raw, reproducibility of past runs |
| [GAP-09](#gap-09) | Unofficial access, user-side terms risk | medium | open | P1-T37, nightly loop reliability |
| [GAP-10](#gap-10) | No foreign / proprietary flow data | low | open | S06, P1-T04 |
| [GAP-11](#gap-11) | No bank fundamentals | high | open | fundamentals_q, P1-T07, S10, S11, S12, S13, P1-T10 valuation features |
| [GAP-12](#gap-12) | No news source | low | open | news_raw, P1-T09, Phase 1 exit-7 |
| [GAP-13](#gap-13) | VN30 membership before 2026-08 | medium | open | universe_membership, P1-T05, survivorship bias |
| [GAP-14](#gap-14) | Exact price-board match not possible on adjusted history | high | open | exit-2, G3 |

## GAP-01

**No raw (unadjusted) prices** · *Không có giá gốc chưa điều chỉnh*

- Status: open · severity: high · since 2026-11-18
- Missing: Yahoo OHLC is split-adjusted (stock dividends and bonus shares are treated as splits), so prices before a corporate action are scaled and off the HOSE tick grid.
- Affects: prices_daily, prices_adjusted, P1-T06, P1-T08, P1-T11, exit-2
- Workaround now: Rows carry price_basis=split_adjusted; P1-T06 never re-adjusts them; limit and tick checks on such rows are warnings; the simulator applies limit/tick rules only approximately on adjusted history.
- Closed by: A raw-price source (CafeF unadjusted EOD files via a FileSource, or a broker API) — new card.

## GAP-02

**No reference, ceiling and floor prices** · *Không có giá tham chiếu, trần, sàn*

- Status: open · severity: medium · since 2026-11-18
- Missing: Yahoo does not publish the exchange reference price or the daily limits.
- Affects: prices_daily.ref_price, prices_daily.ceiling, prices_daily.floor, P1-T08, P1-T11
- Workaround now: ref_price = previous stored close, ceiling/floor derived with the configured HOSE limit and tick rules; flagged derived=true. Wrong on ex-dates.
- Closed by: Same raw source as GAP-01, or exchange publications.

## GAP-03

**No VNINDEX / VN30 index series** · *Không có chỉ số VNINDEX / VN30*

- Status: open · severity: medium · since 2026-11-18
- Missing: Index symbols are not available on Yahoo.
- Affects: benchmarks.market_indices, P1-T10 market-context features, P1-T23, G3 benchmarks
- Workaround now: Benchmarks use the equal-weight universe index computed from stored prices; the VN30 ETF (E1VFVN30) may be ingested as an optional proxy, labelled as such.
- Closed by: An index source (exchange publications or another adapter) — new card.

## GAP-04

**HOSE only; history starts at HOSE listing** · *Chỉ có sàn HOSE; lịch sử bắt đầu từ ngày lên HOSE*

- Status: open · severity: medium · since 2026-11-18
- Missing: No HNX/UPCoM symbols. ACB, LPB, VIB and SSB start in 2020-2021 (their HOSE listing), so a 2015 backfill gives a ragged panel.
- Affects: prices_daily, universe, P1-T10, P1-T20, lab statistics
- Workaround now: A ticker is tradable only from its first stored session; lab reports state the effective start per ticker and the number of tickers per period.
- Closed by: CafeF files (cover HNX/UPCoM history) or another source — new card.

## GAP-05

**Historical holiday lists missing before 2026** · *Thiếu lịch nghỉ lễ trước năm 2026*

- Status: open · severity: medium · since 2026-11-18
- Missing: config/markets/hose.yaml lists holidays for 2026 (complete) and 2027 (partial) only; Yahoo emits filler rows on holidays.
- Affects: calendar, P1-T37, P1-T11, decision days before 2026
- Workaround now: Filler rows (volume 0 and O=H=L=C=previous close) are dropped by rule and logged; history uses TradingCalendar.from_sessions on the cleaned sessions.
- Closed by: Add HOSE holidays 2015-2025 with sources ([VERIFY]) — new card.

## GAP-06

**Incomplete corporate actions** · *Thiếu sự kiện doanh nghiệp*

- Status: open · severity: medium · since 2026-11-18
- Missing: Only split factors (including stock dividends) and cash dividends; no rights issues, record dates or announcement dates; amounts unverified.
- Affects: corporate_actions, P1-T06, P1-T11 cash-dividend accounting
- Workaround now: Store what Yahoo gives with source=yahoo; no lookahead use of announcement dates.
- Closed by: Corporate-action source (company/exchange disclosures) — new card.

## GAP-07

**Stale and duplicated sessions** · *Phiên trùng lặp hoặc giá đứng yên bất thường*

- Status: open · severity: low · since 2026-11-18
- Missing: Occasional consecutive sessions with identical close/volume.
- Affects: prices_daily, P1-T08, P1-T38
- Workaround now: Quality checks flag them (warning); they are kept but marked.
- Closed by: Cross-check with a second source.

## GAP-08

**History is revised after each split** · *Lịch sử giá bị Yahoo tính lại sau mỗi lần chia tách*

- Status: mitigated · severity: medium · since 2026-11-18
- Missing: A new split rescales all earlier prices at the source.
- Affects: prices_daily, data/raw, reproducibility of past runs
- Workaround now: Each refresh re-reads the last data.yahoo.overlap_sessions stored sessions per ticker; if an overlapping close differs (relative 1e-6) or a new stock event appears, that ticker is re-fetched in full from project.backfill_start and upserted, so earlier rows get revisions (counted in ingest_runs). A raw snapshot per run is kept, so a past lab run can be reproduced from its snapshot.
- Closed by: Raw-price source (GAP-01).

## GAP-09

**Unofficial access, user-side terms risk** · *Truy cập không chính thức, người dùng tự chịu điều khoản*

- Status: open · severity: medium · since 2026-11-18
- Missing: Yahoo ToS §2(d) prohibits automated collection without permission; endpoints may change or block without notice.
- Affects: P1-T37, nightly loop reliability
- Workaround now: Optional extra, one-time notice, data only on the user's machine, never in CI; synthetic source keeps the lab usable if Yahoo stops.
- Closed by: A licence-clean free source — new ADR.

## GAP-10

**No foreign / proprietary flow data** · *Không có dữ liệu khối ngoại / tự doanh*

- Status: open · severity: low · since 2026-11-18
- Missing: No flow data from Yahoo.
- Affects: S06, P1-T04
- Workaround now: S06 stays disabled.
- Closed by: P1-T04.

## GAP-11

**No bank fundamentals** · *Không có báo cáo tài chính ngân hàng*

- Status: open · severity: high · since 2026-11-18
- Missing: No quarterly fundamentals with publish dates.
- Affects: fundamentals_q, P1-T07, S10, S11, S12, S13, P1-T10 valuation features
- Workaround now: Value/quality strategies run only on synthetic data until a source exists.
- Closed by: P1-T07 with a source decision.

## GAP-12

**No news source** · *Chưa có nguồn tin tức*

- Status: open · severity: low · since 2026-11-18
- Missing: Raw news collection has no source yet.
- Affects: news_raw, P1-T09, Phase 1 exit-7
- Workaround now: None; Phase 2 forward data starts when a source is chosen.
- Closed by: P1-T09 with a source decision.

## GAP-13

**VN30 membership before 2026-08** · *Thiếu lịch sử thành phần VN30 trước 08/2026*

- Status: open · severity: medium · since 2026-11-18
- Missing: Membership history before the 2026-08-03 review.
- Affects: universe_membership, P1-T05, survivorship bias
- Workaround now: Current 13 + TPB with survivorship_warning (plan §3.1).
- Closed by: P1-T05.

## GAP-14

**Exact price-board match not possible on adjusted history** · *Không đối chiếu khớp tuyệt đối với bảng giá trên lịch sử đã điều chỉnh*

- Status: open · severity: high · since 2026-11-18
- Missing: Exit criterion 2 (20 closes match a public board exactly) needs raw closes.
- Affects: exit-2, G3
- Workaround now: Spot-check only sessions after each ticker's last corporate action.
- Closed by: GAP-01.
