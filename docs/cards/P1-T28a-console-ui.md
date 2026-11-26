---
id: P1-T28a
title: Console UI — animated guide, Airflow-like runs (DAG, grid, logs), data and results
milestone: M1.4
release: v0.1.0
status: in-progress
branch: feat/P1-T28a-console-ui
due: 2026-11-29
---

### P1-T28a — Console UI on `vnstratlab serve`

- Depends on: P1-T27a (run registry and API, merged).
- Goal: when the user runs `vnstratlab serve`, the browser opens a simple local Console that
  (1) teaches how to use the tool with simple frame-by-frame motion and highlights what to
  watch, and (2) lets the user start pipelines and watch what the engine is doing — DAG, run
  history grid, live task logs — in the spirit of Apache Airflow.
- Owner decisions 2026-11-26: lean tests; UI text in **Vietnamese**; ships in v0.1.0.

#### Tech (keep it simple)

- Static files only in `src/vnstratlab/app/static/`: `index.html`, `css/console.css`,
  `js/*.js` (vanilla ES modules), SVG inline. **No build step, no CDN, no external fonts** —
  works offline. Hash-based routing: `#/huong-dan`, `#/runs`, `#/runs/<run_id>`, `#/du-lieu`,
  `#/ket-qua/<run_id>`.
- Motion: CSS keyframes / transitions and SVG (`stroke-dashoffset` for flowing edges).
  Respect `prefers-reduced-motion` (show static frames). Light and dark themes via CSS
  variables.
- POSTs send `X-Vnstratlab: 1`. Use the API exactly as shipped by P1-T27a (see
  `src/vnstratlab/app/server.py` and docs/cards/P1-T27a-runs-serve.md).

#### Page 1 — Hướng dẫn (guide, default page)

- A pipeline diagram `Ingest → Rebuild → Features → Strategies → Simulator → Báo cáo`; a
  "Phát" (play) button animates data flowing node by node; "Từng bước" (step) moves one frame at
  a time with Prev/Next; each frame highlights one node and shows a card: what it does (1–2
  lines), the command (`vnstratlab ...`, copy button), and **⚠ Cần để ý** items:
  - Ingest: synthetic vs real (Yahoo, interim, terms), partial bar before 16:00, DQ status.
  - Rebuild: adjusted vs execution series, excluded rows, gap register (GAP-xx).
  - Features: point-in-time only (no lookahead), `survivorship_warning` (GAP-13).
  - Strategies: frozen params, every trial counted, blocked strategies.
  - Simulator: T+ settlement, 100-share lots / odd lots, ceiling/floor, fees/tax `[VERIFY]`,
    ATR stop, circuit breaker.
  - Báo cáo: SYNTHETIC label, recommend-only (never places orders).
- A short "Bắt đầu nhanh" strip: 1) `vnstratlab init` 2) chạy demo 3) xem Runs 4) xem kết quả —
  with a button "Chạy demo ngay" that starts the `demo` pipeline and jumps to its run page.
- Static content lives in one JS data file (`js/guide-data.js`) so the PO page (next card) can
  reuse it.

#### Page 2 — Runs (Airflow-like)

- Top: pipeline buttons from `GET /api/pipelines` (labels in Vietnamese). Pipelines with
  `needs_source_terms` open a confirm dialog showing the returned `notice` text before resending
  with `accept_terms: true`. Busy → a clear message with a link to the active run.
- **Grid view** (`#/runs`): rows = task ids, columns = the last 20 runs (newest right), each cell
  a colored square by status (queued grey, running blue pulsing, success green, failed red,
  skipped light grey / striped); hover shows duration; click opens the run.
- **Run view** (`#/runs/<id>`): the DAG drawn as SVG from `tasks`/`edges` (simple layered
  left-to-right layout), node color by status, running node pulses, edges animate while the
  downstream task runs; durations under nodes; run header (pipeline, status, reason, start,
  duration). Live updates via `EventSource` on `/api/runs/<id>/events`; fall back to polling if
  SSE fails.
- **Logs panel**: task selector (defaults to the running or failed task), level filter
  (DEBUG/INFO/WARNING/ERROR), text search, auto-tail toggle, WARNING/ERROR lines highlighted,
  "Tải log" download link. Uses the `log` SSE events and `GET .../log?offset=` for history.
- A finished `demo` run shows a button "Xem kết quả".

#### Page 3 — Dữ liệu & Kết quả

- **Dữ liệu** (`#/du-lieu`): from `GET /api/data/status` — store cards (kind badge
  SYNTHETIC / THẬT), ticker table (first, last, rows), last ingest runs with status chips, last
  checks (errors/warnings count, first lines), open gaps by severity with title_vi.
- **Kết quả** (`#/ket-qua/<run_id>`): from `GET /api/results/<run_id>` — a red banner
  "DỮ LIỆU GIẢ LẬP — không nói gì về thị trường thật", the summary table (sortable; S17 rows
  tagged "benchmark"), and an equity chart as inline SVG (pick trials to overlay; S17 shown
  by default as reference).

#### Layout

Left nav (Hướng dẫn, Runs, Dữ liệu, Kết quả gần nhất), top bar with app version and a
permanent "Chỉ khuyến nghị — không đặt lệnh" tag. Must work at 1280 px and down to 390 px
width (nav collapses).

#### Tests (lean)

- `tests/test_console_static.py`: the static files are packaged and served (`GET /`,
  `/js/...`, `/css/...` → 200 via `TestClient`), `index.html` references only local assets (no
  `http://` / `https://` URLs in any static file), every route id used in nav exists, and
  `guide-data.js` contains the 6 pipeline steps.
- No browser tests in this card. Record a manual check in the handoff: run `vnstratlab serve`,
  start `demo`, and describe what each page showed (and attach 3–4 screenshots in the PR if
  you can produce them headlessly; optional).

#### Files

`src/vnstratlab/app/static/**`, `src/vnstratlab/app/server.py` (only if a static mount or
cache header needs a tweak — no API changes), `pyproject.toml` (package data for static files
if needed), `tests/test_console_static.py`, `docs/getting-started.md` (Console section with
the four pages), `CHANGELOG.md`, this card (`docs/cards/P1-T28a-console-ui.md`).

#### Acceptance criteria

1. `vnstratlab serve` opens the Console; the guide plays and steps through 6 frames, each with
   command and "Cần để ý" items; reduced motion shows static frames.
2. Starting `demo` from the Console shows the DAG live (statuses change, running node pulses),
   the grid gets a new column, logs stream with level filter and auto-tail.
3. A terms-required pipeline shows the notice and only starts after confirmation.
4. Data page shows the real store if present (kind badge) and the gaps; results page shows the
   synthetic banner, table and equity chart.
5. No external URLs in static files; no order-related UI; Vietnamese text throughout.
6. Static test file green; `ruff`, `mypy`, `pytest` green; guardrails unchanged.

#### Out of scope

API changes (raise them in the handoff instead), the PO dashboard (next card), scheduler,
backtest/lab pages.
