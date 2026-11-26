---
id: X-console-ui
title: Console v2 UI — intro-site/PO design system, richer interaction, config and strategy pages
milestone: M1.4
release: v0.1.0
status: in-review
branch: feat/X-console-ui-v2
due: 2026-11-29
---

### X-console-ui — Console v2 (design + interaction)

- Owner feedback 2026-11-26: the Console looks far from the intro site and the PO dashboard;
  interaction is weak; needs more UI and user-editable configuration (e.g. add strategies).
- Backend: card X-console-api (parallel) implements the contract in
  `docs/cards/console-v2-api.md` (copy it from the scratchpad path given in the brief). Build
  the UI against that contract; until the API branch lands, use a small fixture mode
  (`?mock=1` → `js/mock.js` returns contract-shaped data) so every page can be developed and
  shown. Remove nothing from the existing API usage.

#### 1. Design system — same as the intro site and PO dashboard

Source of truth: `git show origin/site:styles.css`, `origin/site:index.html`,
`origin/site:buffalo.svg`, `origin/po:styles.css`, `origin/po:index.html`.
- Port the **monochrome tokens** (`--bg --surface --fg --fg-2 --muted --faint --line --line-2
  --soft --radius`, light/dark via `prefers-color-scheme` + `data-theme` toggle like the PO),
  the dot-grid background, card/border/radius style, buttons (`.btn` filled fg, ghost), chips,
  tables, focus rings, `rise` entrance animation.
- **Fonts:** Geist / Geist Mono **bundled locally** (woff2 under `static/fonts/` with the OFL
  licence file next to them) — no Google Fonts link (offline, no external URLs). If bundling is
  not possible, fall back to the same system stack the sites use.
- **Mascot:** the buffalo symbol (from `origin/site:index.html` sprite / `buffalo.svg`) as
  brand mark in the top bar and favicon, and in empty states.
- Status colour is the only colour: success / running / failed / skipped as small accents
  (dot, left border, DAG node stroke) on the monochrome base — not full-colour blocks.
- Replace the current blue theme entirely. Keep Vietnamese text.

#### 2. Layout and navigation

Top bar (brand + mascot, global search/command button, active-run indicator with live
progress, theme toggle, "Chỉ khuyến nghị — không đặt lệnh" tag). Left nav:
**Tổng quan · Hướng dẫn · Runs · Dữ liệu · Kết quả · Chiến lược · Cấu hình**. Collapses to a
drawer under 760 px.

#### 3. Interaction (the main point)

- **Command palette** (Ctrl/⌘+K, also `/`): run a pipeline, jump to a page/run/ticker/strategy,
  toggle theme. Keyboard shortcuts listed in a `?` overlay (g o / g r / g d … style).
- **Toasts** for start/finish/fail/cancel/saved; non-blocking; click → go to the run.
- **Active-run tracker** in the top bar on every page (task i/n, elapsed, click → run).
- **Runs:** filters (pipeline, status), search; grid cells with hover cards (task, status,
  duration, error first line); run page with **Cancel** (while active) and **Chạy lại**
  (rerun); DAG nodes with hover card + click → logs; logs panel keeps level filter, search
  with match highlight + next/prev, auto-tail, copy line, download; resizable split between
  DAG and logs; compare two runs' durations (simple bar list).
- **Dữ liệu:** ticker list with sparkline per ticker (from `/api/data/prices`), click → a
  larger price + volume chart with hover crosshair and range buttons (1T/3T/1N/5N/Tất cả);
  DQ findings table with filters; gaps as expandable cards.
- **Kết quả:** sortable/filterable table, trial checkboxes drive the equity chart with hover
  crosshair and tooltip, normalised view toggle, drawdown mini-chart; "So với benchmark S17".
- **Tổng quan (new home):** data freshness card (last date, stale warning), last 5 runs,
  quick actions (Chạy demo, Làm mới dữ liệu, Backtest when available), gaps by severity,
  strategies/trials counts, VERIFY count.

#### 4. Config pages (user-editable, with guard rails)

- **Cấu hình:** forms generated from `editable` fields grouped (Vốn theo book, Chi phí, Rủi ro,
  Dữ liệu); show default vs current; `[VERIFY]` badge with help; live validation via
  `/api/config/validate` (debounced), a **diff preview** before saving, Save → toast with
  backup file name, "Khôi phục mặc định" per field. Banner: changes apply to your own runs;
  frozen-for-contributors note where present.
- **Chiến lược:** cards per strategy (name, description, basis, horizons, blocked reason),
  their param sets with enable/disable toggles and trial ids; **"Thêm bộ tham số"** opens a
  form built from `params_schema` (selects for allowed values, number inputs with bounds,
  horizon checkboxes), validates, shows the DSR warning, then creates it (trials registered).
  User-added sets can be deleted (with the "trial vẫn được giữ trong registry" note).
  Plug-ins discovered in the home `strategies/` folder are listed (read-only).

#### 5. Guide

Keep the 6-step motion guide, restyled to the monochrome system (flowing dashed edges,
frame counter, step cards), and add a short "Tour" mode that highlights real UI parts
(top bar tracker, Runs grid, Logs, Cấu hình) one by one with a spotlight overlay.

#### Tech

Static only (`src/vnstratlab/app/static/**`), vanilla ES modules, inline SVG charts (no chart
library), no build step, **no external URLs**, no `innerHTML` with data (textContent / DOM
APIs), POSTs with `X-Vnstratlab: 1`, `prefers-reduced-motion` respected.

#### Tests (lean)

Update `tests/test_console_static.py`: all assets served, no external URLs, fonts + licence
present (or documented fallback), every nav route exists, no `innerHTML` in JS, guide data has
6 steps. Manual check + screenshots of each page (light and dark) in the handoff/PR, using
Playwright if available (headless Chromium at 1280×800 and 390×844).

#### Files

`src/vnstratlab/app/static/**`, `tests/test_console_static.py`, `docs/getting-started.md`
(Console section), `CHANGELOG.md`, this card (`docs/cards/X-console-ui.md`) and the contract
(`docs/cards/console-v2-api.md`). **No Python changes** outside tests.

#### Acceptance criteria

1. Side by side with the intro site and the PO dashboard, the Console uses the same tokens,
   fonts, mascot, card and button styles, in light and dark.
2. Command palette, toasts, active-run tracker, cancel/rerun, log search, chart hovers work.
3. Config: edit → validate → diff → save → backup shown; reset to default works; invalid
   values show `problems` inline.
4. Strategies: add a param set from the schema form, toggle a set, delete a user set.
5. Works offline, no external URLs, 390 px usable.
6. Tests green; screenshots attached.
