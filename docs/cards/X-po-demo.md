---
id: X-po-demo
title: PO dashboard — product demo section (guide motion, demo run DAG/logs, results, Console screenshots)
milestone: M1.4
release: v0.1.0
status: done
branch: feat/X-po-demo
due: 2026-11-30
---

### X-po-demo — product demo on the PO dashboard

- Depends on: P1-T27a (runs, merged), P1-T28a (Console UI incl. `js/guide-data.js`).
- Goal: the PO (owner) sees on the PO dashboard, without installing anything, what the tool
  does and how it is used: the same animated guide as the Console, the latest demo run as a DAG
  with task durations and log excerpts, the synthetic results, and screenshots of each Console
  page — refreshed on every Pages build.
- Owner decisions 2026-11-26: lean tests; Vietnamese UI; everything synthetic is labelled.

#### 1. Pages build (`develop` branch: `.github/workflows/pages.yml`, `tools/build_status.py`)

- After the test step: run the `demo` pipeline through the runner into a temp `APP_HOME`
  (`vnstratlab demo --quiet` with `APP_HOME` set, then read the newest run folder). Time-box
  the step (`timeout-minutes: 5`); a failure must not fail the Pages build — the PO data then
  says `demo: unavailable` with the reason.
- `build_status.py --demo-home <dir>`: add to the **encrypted** PO data a `demo` object:
  `{run_id, generated_at, status, duration_s, tasks:[{id,label_vi,status,duration_s,summary}],
  edges, logs:{task: last 40 lines}, results:{columns, rows}, equity:{trial_id: {dates,
  equity}} for S17 + the top 3 trials by Sharpe (downsampled to ≤ 260 points)}`. Never in
  `status.json` (public).
- Screenshots: install Playwright Chromium in the workflow, start `vnstratlab serve --no-open`
  on that temp home, capture 4 PNGs (guide frame 3, runs grid, run DAG with logs, results) at
  1280×800, and publish them **inside the encrypted payload is not practical** — so publish
  them under `/po/shots/` only if they contain no data beyond the synthetic demo (they do not)
  and name them generically (`guide.png`, `runs.png`, `run.png`, `results.png`). Failure to
  capture must not fail the build.
- Copy the Console's `js/guide-data.js` (and the guide CSS/SVG module if separate) into
  `_site/po/guide/` during the build so the PO page renders the same motion from one source.

#### 2. PO page (`po` orphan branch: `index.html`, `app.js`, `styles.css`)

- New tab/section **"Demo sản phẩm"** with three parts:
  1. **Hướng dẫn**: the guide animation (play / step, the 6 frames with "Cần để ý") loaded
     from `guide/guide-data.js` — same content as the Console.
  2. **Run demo gần nhất**: SVG DAG (same status colours as the Console), durations,
     click a node → its log excerpt; header with run time and status; "DỮ LIỆU GIẢ LẬP" banner.
  3. **Kết quả**: summary table and an inline SVG equity chart (S17 + top 3), plus the four
     Console screenshots in a simple gallery with captions.
- Show "chưa có dữ liệu demo" gracefully when `demo` is missing/unavailable.
- Keep the existing login/encryption flow untouched.

#### Tests (lean)

`tests/test_build_status.py`: `demo` object built from a fake run folder (2 tasks, a log, a
summary.csv) and present only in the PO payload, not in `status.json`; missing folder →
`{"available": false, ...}`. No tests on the `po` branch (static page) — manual check in the
handoff.

#### Files

develop: `.github/workflows/pages.yml`, `tools/build_status.py`, `tests/test_build_status.py`,
`CHANGELOG.md`, this card (`docs/cards/X-po-demo.md`). po branch: `index.html`, `app.js`,
`styles.css` (and a small `demo.js` if cleaner). Two PRs: one into `develop`, one into `po`.

#### Acceptance criteria

1. A Pages run on develop produces `po/data.enc.json` with a `demo` object and `po/shots/*.png`
   (or a logged reason why not); the build stays green if the demo or screenshots fail.
2. The PO page shows the three demo parts after login, matching the Console guide content.
3. `status.json` has no demo fields; nothing unencrypted besides the generic screenshots.
4. `ruff`, `mypy`, `pytest` green.

#### Out of scope

Console changes (raise them instead), real-data runs in CI (never), the public intro site.
