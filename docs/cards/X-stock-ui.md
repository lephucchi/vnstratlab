---
id: X-stock-ui
title: Console — recommendations on Kết quả, new per-stock analysis page
milestone: M1.5
release: v0.2.0
status: in-progress
branch: feat/X-stock-ui
due: 2026-11-28
---

### X-stock-ui — recommendations and per-stock analysis in the Console

- Owner request 2026-11-26: "trong console phần kết quả vẫn chưa thấy đề cử cổ phiếu nào" and
  "phân tích riêng lẻ từng cổ phiếu: chọn từng cổ phiếu để chạy, đưa ra số liệu để phân tích,
  khuyến nghị".
- Build against `docs/cards/stock-insight-api.md` (copy from the scratchpad path in the brief);
  extend the existing `?mock=1` mode with contract-shaped data so everything works before the
  API PR (X-stock-api) lands. Same design system, Vietnamese text, textContent only, no external
  URLs, the terminal/CLI line on every action.

#### 1. Kết quả → "Khuyến nghị hiện tại" (top of the page)

- Horizon tabs (Ngắn hạn / Trung hạn / Dài hạn) from `/api/recommendations/all`.
- A clear banner: status **"Bản xem trước — chưa qua lab chọn lọc"** + data label (SYNTHETIC /
  Yahoo tạm thời) + disclaimer "Chỉ khuyến nghị tham khảo — bạn tự quyết định và tự đặt lệnh".
- Target cards / table: mã, tỷ trọng (bar), đồng thuận (n/N chips with strategy names on hover),
  giá đóng cửa, vùng mua, số lô (+ lô lẻ), giá trị, giá cắt lỗ (and %), chi phí ước tính,
  trần/sàn; cash weight row; click a ticker → its analysis page.
- "Bằng chứng": trials counted, DSR/gate-1 per contributing strategy if present.
- Existing demo results stay below, retitled "Kết quả chạy thử (demo)".

#### 2. New page "Cổ phiếu" (`#/co-phieu`, `#/co-phieu/<TICKER>`), added to the nav and palette

- Ticker picker: searchable list from `/api/stocks` with last close and 1-day change; recent
  tickers; keyboard friendly.
- Button **"Phân tích"** → `POST /api/stocks/{ticker}/analyze`, live progress through the
  existing run tracker / DAG mini view; when done, render:
  - Header: ticker, last close, change chips (1T/1Th/3Th/6Th/1N/YTD), data label.
  - **Khuyến nghị** card per horizon: MUA / GIỮ / KHÔNG / BÁN as a calm monochrome badge (status
    accent only), consensus n/N, weight, reason; summary sentence; disclaimer.
  - Price chart with volume and **strategy in/out markers**, crosshair, range buttons.
  - Stat grid: 52w high/low + distance, vol 20/60d, max DD 1y, ATR14, ADV20 value, volume vs ADV.
  - **Tín hiệu chiến lược** table: strategy, horizon, holds?, weight, rank n/of, signal
    name/value, reason, history (selected share, last selected).
  - **Đặc trưng** table with percentile-in-universe bars and help tooltips.
  - **Backtest** block: buy & hold vs each strategy's contribution while holding.
  - **Rủi ro & quy mô** per book: lots, value, stop, risk VND, cost.
  - **Chất lượng dữ liệu**: gaps, exclusions, DQ findings, corporate actions.
- "So sánh" mode: add up to 4 tickers → side-by-side price and recommendation blocks
  (`/api/stocks/compare`).
- Empty state when no analysis yet: mascot + "Chọn mã và bấm Phân tích".

#### 3. Overview / palette / tour

Overview gets a "Khuyến nghị hiện tại" mini card (top 3 per horizon). Palette: "Phân tích mã …",
"Xem khuyến nghị". Tour: one step for each new section.

#### Tests and files

Update `tests/test_console_static.py` (new route exists, no innerHTML, no external URLs, no order
UI wording such as "đặt lệnh" buttons — the disclaimer text is allowed). Files:
`src/vnstratlab/app/static/**`, `tests/test_console_static.py`, `docs/getting-started.md`
(Console section), `CHANGELOG.md`, this card (`docs/cards/X-stock-ui.md`) and the contract.
Screenshots (light/dark, 1280 and 390) of Kết quả and Cổ phiếu in mock mode in the scratchpad.
