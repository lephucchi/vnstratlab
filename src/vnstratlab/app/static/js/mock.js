// Fixture mode (?mock=1): contract-shaped, SYNTHETIC data answered in the browser, no network.
// Runs progress in real time so the tracker, toasts, cancel, rerun, logs and the terminal can be tried.
// Shapes follow docs/cards/console-v2-api.md plus the existing /api endpoints.

import { createStockMock } from "./mock-stocks.js";

const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, body });
const clone = (v) => JSON.parse(JSON.stringify(v));

function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------- pipelines ----------------
const T = (id, label_vi, upstream = []) => ({ id, label_vi, upstream });
const DEMO_TASKS = [
  T("ingest", "Nạp dữ liệu giả lập"),
  T("rebuild", "Dựng lại chuỗi giá", ["ingest"]),
  T("features", "Tính đặc trưng", ["rebuild"]),
  T("strategies", "Tính danh mục mục tiêu", ["features"]),
  T("simulate", "Mô phỏng giao dịch", ["strategies"]),
  T("report", "Lập báo cáo", ["simulate"]),
];
const PIPELINES = [
  { id: "demo", label_vi: "Demo (dữ liệu giả lập)", needs_source_terms: false, cli: "vnstratlab demo", tasks: DEMO_TASKS },
  { id: "refresh", label_vi: "Làm mới dữ liệu", needs_source_terms: true, cli: "vnstratlab ingest && vnstratlab data rebuild && vnstratlab features build", tasks: [T("ingest", "Tải dữ liệu"), T("rebuild", "Dựng lại chuỗi giá", ["ingest"]), T("features", "Tính đặc trưng", ["rebuild"])] },
  { id: "ingest", label_vi: "Tải dữ liệu", needs_source_terms: true, cli: "vnstratlab ingest", tasks: [T("ingest", "Tải dữ liệu")] },
  { id: "backtest_all", label_vi: "Backtest toàn bộ chiến lược", needs_source_terms: false, cli: "vnstratlab backtest --all", tasks: [T("backtest", "Chạy backtest mọi trial"), T("aggregate", "Tổng hợp chỉ số", ["backtest"]), T("report", "Lập báo cáo", ["aggregate"])] },
  { id: "rebuild", label_vi: "Dựng lại chuỗi giá", needs_source_terms: false, cli: "vnstratlab data rebuild", tasks: [T("rebuild", "Dựng lại chuỗi giá")] },
  { id: "features", label_vi: "Tính đặc trưng", needs_source_terms: false, cli: "vnstratlab features build", tasks: [T("features", "Tính đặc trưng")] },
].map((p) => ({ ...p, edges: p.tasks.flatMap((t) => t.upstream.map((u) => [u, t.id])) }));
// Per-ticker analysis (docs/cards/stock-insight-api.md): started from the Cổ phiếu page, not listed in /pipelines.
const STOCK_PIPELINE = { id: "stock_analysis", label_vi: "Phân tích cổ phiếu", needs_source_terms: false, cli: "vnstratlab stock <TICKER>", tasks: [T("load", "Đọc giá và đặc trưng"), T("features", "Tính đặc trưng", ["load"]), T("signals", "Tín hiệu chiến lược", ["features"]), T("backtest", "Đối chiếu backtest", ["signals"]), T("report", "Lập báo cáo", ["backtest"])] };
STOCK_PIPELINE.edges = STOCK_PIPELINE.tasks.flatMap((t) => t.upstream.map((u) => [u, t.id]));

// ---------------- runs ----------------
const MIN = 60000;
const TASK_MS = 2200;
let seq = 0;
const runs = []; // newest first

function mkRun(pipelineId, { label, createdAgo = 0, sim = true, planMs, command = null, params = {} } = {}) {
  const p = [...PIPELINES, STOCK_PIPELINE].find((x) => x.id === pipelineId);
  const tasks = (p ? p.tasks : [T("cli", label || command || "cli")]).map((t) => ({ ...t, planMs: planMs ? planMs[t.id] || TASK_MS : pipelineId === "cli" ? 3600 : TASK_MS }));
  const created = Date.now() - createdAgo;
  const run = {
    run_id: `${new Date(created).toISOString().slice(0, 19).replace(/[-:T]/g, "").replace(/^(\d{8})(\d{6})$/, "$1-$2")}-${pipelineId}-${String(++seq).padStart(2, "0")}`,
    pipeline: pipelineId,
    label_vi: p ? p.label_vi : "Lệnh terminal",
    cli: p ? p.cli : command,
    created,
    tasks,
    sim: sim ? { start: created } : null,
    command,
    params,
    exit_code: 0,
  };
  runs.unshift(run);
  return run;
}

/** Derive the live view (statuses, durations) of a run from the clock. */
function view(run) {
  const now = Date.now();
  let t = run.sim ? run.sim.start : run.created;
  let stopped = false;
  const out = run.tasks.map((task, i) => {
    const base = { id: task.id, label_vi: task.label_vi, upstream: task.upstream, started_at: null, ended_at: null, duration_s: null, summary: {}, error: null };
    if (run.fixed && run.fixed[task.id]) return { ...base, ...run.fixed[task.id] };
    if (run.stopAfter !== undefined && i > run.stopAfter) return { ...base, status: now >= run.stopEnd ? "skipped" : "queued" };
    const s = t;
    const e = s + task.planMs;
    t = e;
    if (now >= e) {
      const failed = run.command && run.exit_code !== 0;
      const summary = run.command ? { command: run.command, exit_code: run.exit_code } : { rows: 1200 + i * 310, ms: task.planMs };
      return { ...base, status: failed ? "failed" : "success", started_at: new Date(s).toISOString(), ended_at: new Date(e).toISOString(), duration_s: task.planMs / 1000, summary, error: failed ? `exit ${run.exit_code}` : null };
    }
    if (now >= s && !stopped) {
      stopped = true;
      return { ...base, status: "running", started_at: new Date(s).toISOString(), duration_s: (now - s) / 1000 };
    }
    return { ...base, status: "queued" };
  });
  let status = "running";
  let reason = null;
  const last = run.stopAfter !== undefined ? run.stopAfter : out.length - 1;
  const endAt = run.stopAfter !== undefined ? run.stopEnd : t;
  if (run.fixed) status = out.some((x) => x.status === "failed") ? "failed" : "success";
  else if (now >= endAt) {
    status = run.stopAfter !== undefined || out.some((x) => x.status === "failed") ? "failed" : "success";
    if (run.stopAfter !== undefined) reason = "cancelled";
  } else if (!out.some((x) => x.status !== "queued")) status = "queued";
  if (run.fixed && run.reason) reason = run.reason;
  void last;
  const started = run.sim ? run.sim.start : run.created;
  const done = status === "success" || status === "failed";
  return {
    run_id: run.run_id,
    pipeline: run.pipeline,
    label_vi: run.label_vi,
    cli: run.cli,
    status,
    reason,
    created_at: new Date(run.created).toISOString(),
    started_at: new Date(started).toISOString(),
    ended_at: done ? new Date(Math.min(now, endAt || now)).toISOString() : null,
    duration_s: done ? (run.fixed ? out.reduce((a, x) => a + (x.duration_s || 0), 0) : Math.max(0, (Math.min(now, endAt) - started) / 1000)) : (now - started) / 1000,
    params: run.params || {},
    tasks: out,
  };
}

const activeRun = () => runs.map(view).find((r) => r.status === "running" || r.status === "queued") || null;

// seeded history: five finished runs, one failed with an error, one cancelled
function seedHistory() {
  const seeds = [
    ["demo", 6 * 60 * MIN, null],
    ["rebuild", 5 * 60 * MIN, null],
    ["features", 3 * 60 * MIN, "failed"],
    ["demo", 90 * MIN, null],
    ["refresh", 40 * MIN, "cancelled"],
    ["demo", 8 * MIN, null],
  ];
  for (const [pid, ago, kind] of seeds) {
    const r = mkRun(pid, { createdAgo: ago, sim: false });
    r.fixed = {};
    let first = true;
    r.tasks.forEach((task, i) => {
      const dur = 1.1 + ((i * 7 + ago / MIN) % 9) / 3;
      if (kind === "failed" && i === r.tasks.length - 1) r.fixed[task.id] = { status: "failed", duration_s: dur, error: "ValueError: features_daily: ticker VPB has 3 missing sessions", summary: {} };
      else if (kind === "cancelled" && i > 0) r.fixed[task.id] = { status: "skipped" };
      else r.fixed[task.id] = { status: "success", duration_s: dur, summary: { rows: 900 + i * 220 } };
      first = false;
    });
    void first;
    if (kind === "cancelled") {
      r.reason = "cancelled";
      r.fixed[r.tasks[0].id].status = "success";
    }
    if (kind === "failed") r.reason = "task_failed";
  }
}

const LOG = {
  ingest: ["bắt đầu nạp dữ liệu giả lập (seed=20261117)", "13 mã, 1300 phiên mỗi mã", "ghi 16.900 dòng vào market.synthetic.duckdb", "kiểm tra chất lượng: 0 lỗi, 2 cảnh báo"],
  rebuild: ["dựng giá điều chỉnh từ giá thô", "dựng chuỗi giá thực thi (lô 100, bước giá HOSE)", "loại 0 dòng khỏi chuỗi", "xong: adjusted 16.900 dòng, exec 16.900 dòng"],
  features: ["tính features_daily (point-in-time)", "cửa sổ 20/60/120 phiên", "survivorship_warning = true (GAP-13)", "ghi 16.900 dòng đặc trưng"],
  strategies: ["đăng ký 24 trial từ 8 chiến lược", "S06 bị chặn (GAP-04): bỏ qua", "tính danh mục mục tiêu cho 3 sổ", "mỗi trial được đếm trong registry"],
  simulate: ["mô phỏng khớp lệnh theo luật HOSE (T+2, lô 100)", "áp phí 0,15% và thuế 0,1% [VERIFY]", "cầu dao 10% không kích hoạt", "xong 24 trial, 1.804 lệnh mô phỏng"],
  report: ["tổng hợp bảng chỉ số", "vẽ đường vốn từng trial", "ghi summary.csv và equity/*.csv", "báo cáo SYNTHETIC: không nói gì về thị trường thật"],
  load: ["đọc giá điều chỉnh và giá thực thi của mã", "chỉ dùng dữ liệu đến phiên mới nhất (asof)", "13 mã trong vũ trụ để xếp hạng"],
  signals: ["tính xếp hạng của mã theo từng chiến lược đã đăng ký", "chỉ dùng dữ liệu <= asof (không nhìn trước)", "ghi tín hiệu và lịch sử chọn mã"],
  backtest: ["đối chiếu lịch sử chọn mã với lợi suất kỳ kế tiếp", "tính đóng góp theo chiến lược và buy & hold", "mỗi trial được đếm trong registry"],
  cli: ["vnstratlab: khởi động", "đọc cấu hình từ config.yaml", "thực hiện lệnh…", "xong"],
};
function logLines(run, task, v) {
  const base = LOG[task.id] || LOG.cli;
  const lines = base.map((m, i) => {
    const level = i === 2 && task.id === "ingest" ? "WARNING" : "INFO";
    return `10:12:${String(5 + i * 7).padStart(2, "0")} ${level} ${m}`;
  });
  if (run.command) lines.splice(1, 0, `10:12:06 INFO lệnh: ${run.command}`);
  if (v.status === "failed") lines.push("10:13:44 ERROR " + (v.error || "task failed"), "Traceback (most recent call last):", '  File "features.py", line 88, in build', "ValueError: features_daily: ticker VPB has 3 missing sessions");
  return lines;
}
function logText(runId, taskId) {
  const run = runs.find((r) => r.run_id === runId);
  const rv = run && view(run);
  const rec = rv && rv.tasks.find((t) => t.id === taskId);
  if (!rec) return null;
  const all = logLines(run, run.tasks.find((t) => t.id === taskId), rec);
  let n = all.length;
  if (rec.status === "running") n = Math.max(1, Math.min(all.length - 1, Math.floor(((rec.duration_s * 1000) / run.tasks.find((t) => t.id === taskId).planMs) * all.length)));
  if (rec.status === "queued" || rec.status === "skipped") n = 0;
  return { text: all.slice(0, n).map((l) => l + "\n").join(""), status: rec.status };
}

// ---------------- data ----------------
const TICKERS = ["ACB", "BID", "CTG", "HDB", "LPB", "MBB", "SHB", "STB", "TCB", "TPB", "VCB", "VIB", "VPB"];
function sessions(n) {
  const out = [];
  const d = new Date(Date.UTC(2026, 10, 25));
  while (out.length < n) {
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return out.reverse();
}
const DATES = sessions(1300);
const PRICES = {};
TICKERS.forEach((tk, k) => {
  const r = rng(1000 + k * 37);
  let p = 20 + k * 6;
  const close = [];
  const volume = [];
  DATES.forEach(() => {
    p = Math.max(5, p * (1 + (r() - 0.485) * 0.032));
    close.push(Math.round(p * 100) / 100);
    volume.push(Math.round(800000 + r() * 6000000));
  });
  PRICES[tk] = { close, volume };
});

const GAPS = [
  { id: "GAP-04", title_vi: "Chưa có dòng vốn khối ngoại miễn phí", severity: "high", status: "open", missing: "Foreign net buy/sell", affects: ["S06"], workaround: "S06 bị chặn", close_by: "P1-T04" },
  { id: "GAP-11", title_vi: "Chưa có dữ liệu định giá (P/B, P/E)", severity: "high", status: "open", missing: "Valuation fields", affects: ["S00", "S10", "S13"], workaround: "Bỏ khối định giá khỏi S00", close_by: "P1-T07" },
  { id: "GAP-13", title_vi: "Danh sách mã hiện tại bỏ sót mã đã hủy niêm yết", severity: "medium", status: "open", missing: "Delisted tickers", affects: ["mọi chiến lược"], workaround: "Gắn cờ survivorship_warning", close_by: "P1-T07" },
  { id: "GAP-09", title_vi: "Lịch giá lịch sử Yahoo bắt đầu khác nhau theo mã", severity: "low", status: "open", missing: "Uniform history start", affects: ["backfill"], workaround: "Dùng ngày bắt đầu từng mã", close_by: "P1-T04" },
  { id: "GAP-12", title_vi: "Chưa có số liệu NPL của ngân hàng", severity: "medium", status: "open", missing: "NPL ratios", affects: ["S12"], workaround: "S12 ở trạng thái kế hoạch", close_by: "P1-T18" },
].map((g) => ({ ...g, title: g.title_vi, since: "2026-11-10" }));

function storeStatus() {
  return {
    file: "market.synthetic.duckdb",
    kind: "synthetic",
    rows: TICKERS.length * DATES.length,
    tickers: TICKERS.map((t) => ({ ticker: t, first: DATES[0], last: DATES[DATES.length - 1], rows: DATES.length })),
    runs: [
      { run_id: "ing-20261125-01", source: "synthetic", start: DATES[0], end: DATES[DATES.length - 1], rows_written: 16900, rows_changed: 0, rows_dropped: 0, status: "ok" },
      { run_id: "ing-20261124-01", source: "synthetic", start: DATES[0], end: DATES[DATES.length - 2], rows_written: 16887, rows_changed: 13, rows_dropped: 0, status: "ok" },
    ],
    last_run_checks: { run_id: "ing-20261125-01", errors: 0, warnings: 3, first_errors: [] },
  };
}
const DQ = [
  ["2026-11-25", "VPB", "volume_spike", "warning", "khối lượng gấp 6,1 lần trung bình 20 phiên"],
  ["2026-11-20", "SHB", "gap_open", "warning", "giá mở cửa lệch 4,8% so với đóng cửa trước"],
  ["2026-11-12", "HDB", "stale_price", "warning", "giá không đổi 3 phiên liên tiếp"],
  ["2026-10-30", "LPB", "missing_session", "error", "thiếu phiên 2026-10-30 trong chuỗi giá thô"],
  ["2026-10-02", "TCB", "ohlc_order", "error", "high < low (đã loại dòng)"],
  ["2026-09-18", "MBB", "volume_spike", "warning", "khối lượng gấp 5,2 lần trung bình 20 phiên"],
].map(([date, ticker, check, level, detail]) => ({ date, ticker, check, level, detail }));

// ---------------- results ----------------
const TRIALS = [
  ["benchmark_S17_equal_weight_short", "S17 Equal weight (benchmark, no risk layer)", "short"], ["benchmark_S17_equal_weight_medium", "S17 Equal weight (benchmark, no risk layer)", "medium"], ["S17-a", "S17 Equal weight (packaged)", "all"], ["S01-a", "S01 Weekly reversal a", "short"], ["S01-b", "S01 Weekly reversal b", "short"], ["S02-a", "S02 Breakout 20d", "short"],
  ["S03-a", "S03 Oversold in uptrend", "short"], ["S05-a", "S05 Residual mean reversion", "short"], ["S08-a", "S08 Momentum 6-12m", "medium"], ["S08-b", "S08 Momentum 12-1", "medium"],
  ["S09-a", "S09 Medium-term reversal", "medium"], ["S14-a", "S14 Low volatility", "medium"], ["S15-a", "S15 Sector trend", "medium"], ["S18-a", "S18 HRP", "long"],
];
function resultsFor(runId) {
  const dates = DATES.slice(-520);
  const equity = {};
  const rows = TRIALS.map(([id, name, hz], k) => {
    const r = rng(77 + k * 13);
    let v = 11000000;
    const curve = [];
    let peak = v;
    let dd = 0;
    dates.forEach(() => {
      v *= 1 + (r() - 0.488) * 0.016 + (id.startsWith("benchmark_") ? 0.0002 : 0);
      curve.push(Math.round(v));
      peak = Math.max(peak, v);
      dd = Math.min(dd, v / peak - 1);
    });
    equity[id] = { dates, equity: curve };
    const rets = curve.slice(1).map((c, i) => c / curve[i] - 1);
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length);
    return { trial_id: id, trial: name, horizon: hz, CAGR: (curve[curve.length - 1] / curve[0]) ** (252 / curve.length) - 1, vol: sd * Math.sqrt(252), Sharpe: (mean / sd) * Math.sqrt(252), maxDD: dd, turnover: 0.4 + r() * 2.4, trades: Math.round(40 + r() * 400) };
  });
  return { run_id: runId, synthetic: true, columns: Object.keys(rows[0]), rows, equity };
}

// ---------------- config ----------------
const DEFAULTS = {
  project: { backfill_start: "2018-01-01" },
  data: { source: "yahoo" },
  books: { short: { capital_vnd: 11000000 }, medium: { capital_vnd: 11000000, tranches: 3 }, long: { capital_vnd: 11000000 } },
  costs: { brokerage_fee_pct: 0.0015, sales_tax_pct: 0.001, slippage_pct: { round_lot: 0.001, odd_lot: 0.003 } },
  risk: { risk_per_position_pct: 0.01, atr_stop_multiple: 2.0, max_positions: 4, max_weight_per_ticker: 0.35, circuit_breaker_drawdown_pct: 0.1, rebalance_threshold_pct: 0.1, vol_target_annual: null, stop_cooldown_sessions: null },
};
let userCfg = { books: { short: { capital_vnd: 20000000 } } };
const F = (path, label_vi, group, type, extra = {}) => ({ path, label_vi, group, type, verify: false, help_vi: "", ...extra });
const EDITABLE = [
  F("books.short.capital_vnd", "Vốn sổ ngắn hạn", "books", "int", { min: 1000000, max: 10000000000, step: 100000, unit: "VND", help_vi: "Vốn giấy của sổ ngắn hạn. Chỉ ảnh hưởng đến lần chạy của bạn." }),
  F("books.medium.capital_vnd", "Vốn sổ trung hạn", "books", "int", { min: 1000000, max: 10000000000, step: 100000, unit: "VND", help_vi: "Vốn giấy của sổ trung hạn." }),
  F("books.long.capital_vnd", "Vốn sổ dài hạn", "books", "int", { min: 1000000, max: 10000000000, step: 100000, unit: "VND", help_vi: "Vốn giấy của sổ dài hạn." }),
  F("books.medium.tranches", "Số đợt giải ngân (trung hạn)", "books", "int", { min: 1, max: 12, step: 1, help_vi: "Chia vốn trung hạn thành các đợt." }),
  F("costs.brokerage_fee_pct", "Phí môi giới", "costs", "pct", { min: 0, max: 0.01, step: 0.0001, unit: "%", verify: true, help_vi: "Phí môi giới mỗi chiều. Cần kiểm chứng với công ty chứng khoán của bạn." }),
  F("costs.sales_tax_pct", "Thuế bán", "costs", "pct", { min: 0, max: 0.01, step: 0.0001, unit: "%", verify: true, help_vi: "Thuế thu nhập cá nhân khi bán, theo quy định hiện hành." }),
  F("costs.slippage_pct.round_lot", "Trượt giá (lô chẵn)", "costs", "pct", { min: 0, max: 0.05, step: 0.0005, unit: "%", help_vi: "Giả định trượt giá khi khớp lô 100." }),
  F("costs.slippage_pct.odd_lot", "Trượt giá (lô lẻ)", "costs", "pct", { min: 0, max: 0.05, step: 0.0005, unit: "%", help_vi: "Giả định trượt giá khi khớp lô lẻ." }),
  F("risk.risk_per_position_pct", "Rủi ro mỗi vị thế", "risk", "pct", { min: 0.001, max: 0.05, step: 0.001, unit: "%", frozen_note_vi: "Đóng băng đối với người đóng góp: thay đổi phải qua chủ dự án.", help_vi: "Phần vốn chấp nhận mất nếu chạm dừng lỗ." }),
  F("risk.atr_stop_multiple", "Bội số ATR dừng lỗ", "risk", "float", { min: 0.5, max: 6, step: 0.1, frozen_note_vi: "Đóng băng đối với người đóng góp.", help_vi: "Khoảng dừng lỗ = bội số × ATR." }),
  F("risk.max_positions", "Số vị thế tối đa", "risk", "int", { min: 1, max: 30, step: 1, frozen_note_vi: "Đóng băng đối với người đóng góp.", help_vi: "Số mã tối đa trong một sổ." }),
  F("risk.max_weight_per_ticker", "Tỷ trọng tối đa mỗi mã", "risk", "pct", { min: 0.05, max: 1, step: 0.01, unit: "%", frozen_note_vi: "Đóng băng đối với người đóng góp.", help_vi: "Trần tỷ trọng một mã." }),
  F("risk.circuit_breaker_drawdown_pct", "Cầu dao sụt giảm", "risk", "pct", { min: 0.02, max: 0.5, step: 0.01, unit: "%", frozen_note_vi: "Đóng băng đối với người đóng góp.", help_vi: "Chặn lệnh mới khi sụt giảm vượt ngưỡng này." }),
  F("risk.vol_target_annual", "Mục tiêu biến động năm", "risk", "pct", { min_exclusive: 0, max: 2, step: 0.01, unit: "%", nullable: true, help_vi: "Để trống = tắt. Co vị thế để biến động năm gần mục tiêu này." }),
  F("risk.stop_cooldown_sessions", "Số phiên nghỉ sau dừng lỗ", "risk", "int", { min: 1, max: 60, step: 1, unit: "sessions", nullable: true, help_vi: "Để trống = một kỳ quyết định của sổ." }),
  F("risk.rebalance_threshold_pct", "Ngưỡng cân bằng lại", "risk", "pct", { min: 0.01, max: 0.5, step: 0.01, unit: "%", help_vi: "Chỉ cân bằng lại khi lệch quá ngưỡng." }),
  F("data.source", "Nguồn dữ liệu", "data", "enum", { options: ["yahoo", "synthetic"], help_vi: "Yahoo là nguồn tạm thời (interim); synthetic chạy offline." }),
  F("project.backfill_start", "Ngày bắt đầu nạp lịch sử", "data", "date", { help_vi: "Ngày sớm nhất khi nạp lịch sử giá." }),
];
const getPath = (o, p) => p.split(".").reduce((a, k) => (a === undefined || a === null ? undefined : a[k]), o);
function setPath(o, p, v) {
  const ks = p.split(".");
  let cur = o;
  ks.slice(0, -1).forEach((k) => (cur = cur[k] = cur[k] || {}));
  cur[ks[ks.length - 1]] = v;
}
function delPath(o, p) {
  const ks = p.split(".");
  let cur = o;
  for (const k of ks.slice(0, -1)) {
    if (!cur[k]) return;
    cur = cur[k];
  }
  delete cur[ks[ks.length - 1]];
}
const effective = () => {
  const e = clone(DEFAULTS);
  EDITABLE.forEach((f) => {
    const u = getPath(userCfg, f.path);
    if (u !== undefined) setPath(e, f.path, u);
  });
  return e;
};
function checkChanges(changes) {
  const problems = [];
  const diff = [];
  const cur = effective();
  for (const [path, value] of Object.entries(changes || {})) {
    const f = EDITABLE.find((x) => x.path === path);
    if (!f) {
      problems.push(`${path}: không được phép sửa`);
      continue;
    }
    if (value === null && f.nullable) {
      /* null = off */
    } else if (["int", "float", "pct"].includes(f.type)) {
      if (typeof value !== "number" || !Number.isFinite(value)) problems.push(`${path}: phải là số`);
      else if (f.type === "int" && !Number.isInteger(value)) problems.push(`${path}: phải là số nguyên`);
      else if (f.min_exclusive !== undefined && value <= f.min_exclusive) problems.push(`${path}: phải lớn hơn ${f.min_exclusive}`);
      else if (f.max_exclusive !== undefined && value >= f.max_exclusive) problems.push(`${path}: phải nhỏ hơn ${f.max_exclusive}`);
      else if (f.min !== undefined && value < f.min) problems.push(`${path}: nhỏ hơn mức tối thiểu ${f.min}`);
      else if (f.max !== undefined && value > f.max) problems.push(`${path}: lớn hơn mức tối đa ${f.max}`);
    } else if (f.type === "enum" && !f.options.includes(value)) problems.push(`${path}: giá trị không hợp lệ`);
    else if (f.type === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(String(value))) problems.push(`${path}: ngày phải có dạng YYYY-MM-DD`);
    diff.push({ path, from: getPath(cur, path), to: value });
  }
  return { problems, diff: diff.filter((d) => d.from !== d.to) };
}
const stamp = () => new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "T");

// ---------------- strategies ----------------
const STRATS = [
  {
    id: "S01", name_vi: "Đảo chiều theo tuần trong nhóm", description_vi: "Mua mã giảm mạnh nhất tuần trước trong cùng nhóm, kỳ vọng hồi lại.", basis: "giá", horizons_allowed: ["short"], blocked: false,
    params_schema: [
      { name: "lookback_days", type: "int", min: 3, max: 10, help_vi: "Số phiên nhìn lại để xác định mã giảm mạnh." },
      { name: "top_n", type: "int", min: 1, max: 6, help_vi: "Số mã được chọn." },
      { name: "group", type: "str", allowed: ["bank", "sector", "all"], help_vi: "Nhóm so sánh." },
    ],
    param_sets: [
      { index: 0, params: { lookback_days: 5, top_n: 3, group: "bank" }, horizons: ["short"], enabled: true, origin: "packaged", ids: ["short"] },
      { index: 1, params: { lookback_days: 5, top_n: 2, group: "bank" }, horizons: ["short"], enabled: true, origin: "packaged", ids: ["short"] },
    ],
  },
  {
    id: "S08", name_vi: "Động lượng cắt ngang 6–12 tháng", description_vi: "Xếp hạng theo lợi suất 6–12 tháng, giữ nhóm dẫn đầu.", basis: "giá", horizons_allowed: ["medium", "long"], blocked: false,
    params_schema: [
      { name: "formation_months", type: "int", allowed: [6, 9, 12], help_vi: "Độ dài giai đoạn hình thành." },
      { name: "skip_months", type: "int", min: 0, max: 2, help_vi: "Bỏ qua các tháng gần nhất." },
    ],
    param_sets: [
      { index: 0, params: { formation_months: 12, skip_months: 1 }, horizons: ["medium"], enabled: true, origin: "packaged", ids: ["medium"] },
      { index: 1, params: { formation_months: 6, skip_months: 0 }, horizons: ["medium"], enabled: false, origin: "packaged", ids: ["medium"] },
    ],
  },
  {
    id: "S14", name_vi: "Biến động thấp", description_vi: "Ưu tiên các mã có biến động thấp nhất trong cửa sổ gần đây.", basis: "giá", horizons_allowed: ["medium"], blocked: false,
    params_schema: [{ name: "window_days", type: "int", allowed: [60, 120, 250], help_vi: "Cửa sổ đo biến động." }],
    param_sets: [{ index: 0, params: { window_days: 120 }, horizons: ["medium"], enabled: true, origin: "packaged", ids: ["medium"] }],
  },
  {
    id: "S06", name_vi: "Dòng vốn khối ngoại", description_vi: "Theo dõi mua/bán ròng của khối ngoại.", basis: "dòng vốn ngoại", horizons_allowed: ["short"], blocked: true, reason: "Bị chặn: chưa có nguồn dữ liệu miễn phí (GAP-04).",
    params_schema: [], param_sets: [],
  },
];
STRATS.forEach((s) => s.param_sets.forEach((p) => (p.trial_ids = p.ids.map((hz) => ({ horizon: hz, trial_id: `${s.id}-${p.index}-${hz}`, registered: true, registered_at: "2026-11-17T09:00:00Z" })))));
const PLUGINS = [{ file: "strategies/my_breakout.py", ids: ["X01"] }, { file: "strategies/broken.py", ids: [], error: "ImportError: không tìm thấy module 'ta'" }];
const trialsTotal = () => STRATS.reduce((a, s) => a + s.param_sets.reduce((b, p) => b + p.trial_ids.length, 0), 0) + 14;

function validateParamSet(strat, body) {
  const problems = [];
  const params = body.params || {};
  for (const sc of strat.params_schema) {
    const v = params[sc.name];
    if (v === undefined || v === "") problems.push(`params.${sc.name}: bắt buộc`);
    else if (sc.allowed && !sc.allowed.includes(v)) problems.push(`params.${sc.name}: chỉ nhận ${sc.allowed.join(", ")}`);
    else if (sc.type === "int" && !sc.allowed && (!Number.isInteger(v) || v < sc.min || v > sc.max)) problems.push(`params.${sc.name}: số nguyên trong [${sc.min}, ${sc.max}]`);
  }
  if (!body.horizons || !body.horizons.length) problems.push("horizons: chọn ít nhất một khung");
  else if (body.horizons.some((x) => !strat.horizons_allowed.includes(x))) problems.push(`horizons: chỉ nhận ${strat.horizons_allowed.join(", ")}`);
  if (strat.param_sets.some((p) => JSON.stringify(p.params) === JSON.stringify(params))) problems.push("params: bộ tham số này đã tồn tại");
  return problems;
}

// ---------------- terminal ----------------
const O = (name, type = "bool", help = "", extra = {}) => ({ name, type, help, required: false, ...extra });
const COMMANDS = [
  { path: ["demo"], help: "Chạy demo offline trên dữ liệu giả lập.", options: [O("--out", "str", "Thư mục xuất báo cáo"), O("--quiet", "bool", "Ít log")], allowed: true },
  { path: ["ingest"], help: "Nạp giá thô vào kho dữ liệu cục bộ.", options: [O("--source", "choice", "Nguồn dữ liệu", { choices: ["yahoo", "synthetic"] }), O("--accept-source-terms", "bool", "Chấp nhận điều khoản nguồn")], allowed: true },
  { path: ["data", "status"], help: "Xem kho dữ liệu, lần nạp gần nhất và khoảng trống.", options: [O("--json", "bool", "In JSON")], allowed: true },
  { path: ["data", "rebuild"], help: "Dựng lại giá điều chỉnh và giá thực thi.", options: [O("--source", "choice", "Nguồn dữ liệu", { choices: ["yahoo", "synthetic"] }), O("--dry-run", "bool", "Chạy thử, không ghi")], allowed: true },
  { path: ["features", "build"], help: "Tính features_daily.", options: [O("--dry-run", "bool", "Chạy thử, không ghi")], allowed: true },
  { path: ["lab", "trials"], help: "Liệt kê các trial đã đăng ký.", options: [O("--json", "bool", "In JSON")], allowed: true },
  { path: ["runs", "list"], help: "Liệt kê các lần chạy gần nhất.", options: [], allowed: true },
  { path: ["runs", "show"], help: "Xem chi tiết một lần chạy.", options: [O("--json", "bool", "In JSON")], allowed: true },
  { path: ["doctor"], help: "Kiểm tra môi trường và cấu hình.", options: [], allowed: true },
  { path: ["init"], help: "Tạo cấu hình ban đầu (cần --yes).", options: [O("--yes", "bool", "Không hỏi lại"), O("--force", "bool", "Ghi đè, có sao lưu")], allowed: true },
  { path: ["serve"], help: "Mở Console (đang chạy sẵn).", options: [O("--port", "int", "Cổng")], allowed: false, reason_vi: "Không chạy được từ terminal trong Console (đệ quy)." },
];
let termsAccepted = false;
let featuresReady = false; // S14 needs features_daily first (API: 409 features_required)
function tokens(line) {
  const out = line.match(/"[^"]*"|'[^']*'|\S+/g) || [];
  return out.map((t) => t.replace(/^["']|["']$/g, ""));
}
function postCli(body) {
  const line = String(body.command || "");
  if (/[\n\r]/.test(line)) return reply(422, { error: "unknown_command", message: "Không nhận lệnh nhiều dòng", suggestions: [] });
  let toks = tokens(line);
  if (toks[0] === "vnstratlab") toks = toks.slice(1);
  if (!toks.length) return reply(422, { error: "unknown_command", message: "Lệnh trống", suggestions: [] });
  const cmd = COMMANDS.filter((c) => c.path.every((p, i) => toks[i] === p)).sort((a, b) => b.path.length - a.path.length)[0];
  if (!cmd) {
    const sugg = COMMANDS.filter((c) => c.path[0][0] === toks[0][0] || c.path[0].includes(toks[0])).map((c) => `vnstratlab ${c.path.join(" ")}`);
    return reply(422, { error: "unknown_command", message: `Không có lệnh “${toks.join(" ")}”`, suggestions: sugg.slice(0, 4) });
  }
  if (!cmd.allowed) return reply(422, { error: "not_allowed", reason_vi: cmd.reason_vi });
  if (cmd.path[0] === "init" && !toks.includes("--yes")) return reply(422, { error: "not_allowed", reason_vi: "`init` cần `--yes` vì Console không có bàn phím để hỏi lại." });
  const needsTerms = cmd.path[0] === "ingest" && !toks.includes("synthetic") && !toks.includes("--accept-source-terms");
  if (needsTerms && !termsAccepted && !body.accept_terms) return reply(409, { error: "terms_required", source: "yahoo", notice: "Dữ liệu Yahoo Finance là nguồn tạm thời (interim).\nBạn chịu trách nhiệm tuân thủ điều khoản sử dụng của nguồn.\nKhông phân phối lại dữ liệu." });
  if (needsTerms && body.accept_terms) termsAccepted = true;
  const act = activeRun();
  if (act) return reply(409, { error: "busy", active_run_id: act.run_id });
  const command = `vnstratlab ${toks.join(" ")}`;
  const run = mkRun("cli", { label: command, command });
  run.label_vi = command;
  return reply(202, { run_id: run.run_id, argv: ["vnstratlab", ...toks] });
}

// ---------------- stock pages ----------------
let stockApi = null;
const stock = () => (stockApi = stockApi || createStockMock({ TICKERS, DATES, PRICES, capitalFor: (hz) => effective().books[hz].capital_vnd, trialsTotal }));
const SEEDED_ANALYSES = new Set(["VCB", "LPB", "BID"]); // analyses "already stored" when the Console opens
const STOCK_PLAN = { load: 1100, features: 900, signals: 1300, backtest: 1100, report: 800 };
function startStockRun(ticker, body) {
  const run = mkRun("stock_analysis", { planMs: STOCK_PLAN, params: { ticker, source: body.source || "synthetic", horizons: body.horizons || ["short", "medium", "long"] } });
  run.label_vi = `Phân tích ${ticker}`;
  run.cli = `vnstratlab stock ${ticker}`;
  return run;
}
function storedAnalysis(ticker) {
  const done = runs.find((r) => r.pipeline === "stock_analysis" && r.params.ticker === ticker && view(r).status === "success");
  if (done) return { runId: done.run_id, generatedAt: view(done).ended_at };
  if (SEEDED_ANALYSES.has(ticker)) return { runId: `seed-stock-${ticker}`, generatedAt: new Date(Date.now() - 3 * 60 * MIN).toISOString() };
  return null;
}

// ---------------- router ----------------
export function mockApi(path, init) {
  const method = (init.method || "GET").toUpperCase();
  const [pathname, query = ""] = path.split("?");
  const q = new URLSearchParams(query);
  const body = init.body ? JSON.parse(init.body) : {};
  const seg = pathname.split("/").filter(Boolean);
  const m = (pattern) => {
    const ps = pattern.split("/").filter(Boolean);
    if (ps.length !== seg.length) return null;
    const out = [];
    for (let i = 0; i < ps.length; i++) {
      if (ps[i] === "*") out.push(decodeURIComponent(seg[i]));
      else if (ps[i] !== seg[i]) return null;
    }
    return out;
  };
  let x;
  const R = (status, b) => Promise.resolve(reply(status, b));

  if (!runs.length) seedHistory();
  if (method === "GET") {
    if (m("overview")) {
      const last = DATES[DATES.length - 1];
      const act = activeRun();
      return R(200, {
        version: "0.1.0-mock", home: "~/vnstratlab (fixture)", source: "synthetic",
        store: { kind: "synthetic", tickers: [...TICKERS], ticker_count: TICKERS.length, first: DATES[0], last, rows: TICKERS.length * DATES.length, stale_days: 1 },
        last_runs: runs.slice(0, 5).map(view), active_run_id: act ? act.run_id : null,
        gaps: { high: GAPS.filter((g) => g.severity === "high").length, medium: GAPS.filter((g) => g.severity === "medium").length, low: GAPS.filter((g) => g.severity === "low").length },
        verify_count: 4, strategies: { registered: STRATS.filter((s) => !s.blocked).length, enabled: STRATS.reduce((a, s) => a + s.param_sets.filter((p) => p.enabled).length, 0), trials: trialsTotal() },
      });
    }
    if (m("recommendations/all")) return R(200, stock().allRecommendations());
    if (m("recommendations")) {
      const hz = q.get("horizon") || "short";
      return ["short", "medium", "long"].includes(hz) ? R(200, stock().recommendation(hz)) : R(422, { error: "invalid_horizon", message: "horizon phải là short, medium hoặc long" });
    }
    if (m("stocks")) return R(200, stock().stocksList());
    if (m("stocks/compare")) {
      const tks = (q.get("tickers") || "").split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
      if (!tks.length || tks.length > 4 || tks.some((t) => !stock().has(t))) return R(422, { error: "invalid_tickers", message: "Chọn từ 1 đến 4 mã trong vũ trụ" });
      return R(200, stock().compare(tks));
    }
    if ((x = m("stocks/*/analysis"))) {
      const tk = x[0].toUpperCase();
      if (!stock().has(tk)) return R(404, { error: "unknown_ticker", ticker: tk });
      const st = storedAnalysis(tk);
      return st ? R(200, stock().analysis(tk, st)) : R(404, { error: "no_analysis", ticker: tk });
    }
    if (m("pipelines")) return R(200, { pipelines: clone(PIPELINES) });
    if (m("runs")) return R(200, { runs: runs.slice(0, Number(q.get("limit") || 20)).map(view) });
    if ((x = m("runs/*"))) {
      const r = runs.find((y) => y.run_id === x[0]);
      return r ? R(200, view(r)) : R(404, { error: "not_found", run_id: x[0] });
    }
    if ((x = m("runs/*/tasks/*/log"))) {
      const lg = logText(x[0], x[1]);
      if (!lg) return R(404, { error: "not_found" });
      const off = Number(q.get("offset") || 0);
      return R(200, { text: lg.text.slice(off), offset: lg.text.length, status: lg.status });
    }
    if (m("data/status")) return R(200, { home: "~/vnstratlab (fixture)", stores: [storeStatus()], gaps: { counts: { high: 2, medium: 2, low: 1 }, open: clone(GAPS) } });
    if (m("data/gaps")) return R(200, { counts: { high: 2, medium: 2, low: 1 }, gaps: clone(GAPS) });
    if ((x = m("data/prices/*"))) {
      const p = PRICES[x[0]];
      if (!p) return R(404, { error: "not_found", ticker: x[0] });
      const from = q.get("from") || "0000";
      const to = q.get("to") || "9999";
      const idx = DATES.map((d, i) => (d >= from && d <= to ? i : -1)).filter((i) => i >= 0);
      return R(200, { ticker: x[0], kind: "synthetic", dates: idx.map((i) => DATES[i]), close: idx.map((i) => p.close[i]), volume: idx.map((i) => p.volume[i]) });
    }
    if (m("data/quality")) return R(200, { rows: DQ.slice(0, Number(q.get("limit") || 50)) });
    if ((x = m("results/*"))) {
      const r = runs.find((y) => y.run_id === x[0]);
      if (!r) return R(404, { error: "not_found" });
      if (r.pipeline !== "demo" || view(r).status !== "success") return R(404, { error: "no_results", run_id: x[0] });
      return R(200, resultsFor(x[0]));
    }
    if (m("config")) return R(200, { effective: effective(), defaults: clone(DEFAULTS), user: clone(userCfg), editable: clone(EDITABLE), file: "~/vnstratlab/config.yaml", exists: Object.keys(userCfg).length > 0 });
    if (m("strategies")) return R(200, { strategies: clone(STRATS).map(({ param_sets, ...s }) => ({ ...s, param_sets: param_sets.map(({ ids, ...p }) => p) })), trials_total: trialsTotal(), plugins: clone(PLUGINS) });
    if (m("cli/commands")) return R(200, { commands: clone(COMMANDS) });
  }
  if (method === "POST") {
    if (m("runs")) {
      const p = PIPELINES.find((y) => y.id === body.pipeline);
      if (p && ["demo", "features", "refresh"].includes(p.id)) featuresReady = true;
      if (!p) return R(404, { error: "unknown_pipeline", pipeline: body.pipeline, available: PIPELINES.map((y) => y.id) });
      if (p.needs_source_terms && !termsAccepted && !body.accept_terms) return R(409, { error: "terms_required", source: "yahoo", notice: "Dữ liệu Yahoo Finance là nguồn tạm thời (interim).\nBạn chịu trách nhiệm tuân thủ điều khoản sử dụng của nguồn.\nKhông phân phối lại dữ liệu." });
      const act = activeRun();
      if (act) return R(409, { error: "busy", active_run_id: act.run_id });
      if (p.needs_source_terms) termsAccepted = true;
      const run = mkRun(p.id);
      return R(202, { run_id: run.run_id, pipeline: p.id, cli: p.cli });
    }
    if ((x = m("runs/*/cancel"))) {
      const r = runs.find((y) => y.run_id === x[0]);
      const v = r && view(r);
      if (!v || (v.status !== "running" && v.status !== "queued")) return R(409, { error: "not_active", run_id: x[0] });
      const i = Math.max(0, v.tasks.findIndex((t) => t.status === "running"));
      r.stopAfter = i;
      let end = r.sim.start;
      for (let k = 0; k <= i; k++) end += r.tasks[k].planMs;
      r.stopEnd = end;
      return R(202, { run_id: x[0] });
    }
    if ((x = m("runs/*/rerun"))) {
      const r = runs.find((y) => y.run_id === x[0]);
      if (!r) return R(404, { error: "not_found" });
      if (view(r).status === "running" || view(r).status === "queued") return R(409, { error: "not_active", run_id: x[0] });
      if (r.pipeline !== "cli" && r.pipeline !== "stock_analysis" && !PIPELINES.some((y) => y.id === r.pipeline)) return R(422, { error: "not_rerunnable" });
      const act = activeRun();
      if (act) return R(409, { error: "busy", active_run_id: act.run_id });
      const n = r.command ? mkRun("cli", { command: r.command }) : r.pipeline === "stock_analysis" ? startStockRun(r.params.ticker, r.params) : mkRun(r.pipeline);
      n.label_vi = r.label_vi;
      return R(202, { run_id: n.run_id, pipeline: n.pipeline, cli: n.cli });
    }
    if ((x = m("stocks/*/analyze"))) {
      const tk = x[0].toUpperCase();
      if (!stock().has(tk)) return R(404, { error: "unknown_ticker", ticker: tk });
      const act = activeRun();
      if (act) return R(409, { error: "busy", active_run_id: act.run_id });
      const run = startStockRun(tk, body);
      return R(202, { run_id: run.run_id, cli: run.cli });
    }
    if (m("cli")) return Promise.resolve(postCli(body));
    if (m("config/validate")) {
      const { problems, diff } = checkChanges(body.changes);
      return R(200, { ok: !problems.length, problems, diff });
    }
    if (m("config/reset")) {
      const stamp1 = `config.yaml.bak-${stamp()}`;
      const before = effective();
      (body.paths || []).forEach((p) => delPath(userCfg, p));
      const after = effective();
      return R(200, { ok: true, backup: stamp1, diff: (body.paths || []).map((p) => ({ path: p, from: getPath(before, p), to: getPath(after, p) })) });
    }
    if ((x = m("strategies/*/param-sets"))) {
      const s = STRATS.find((y) => y.id === x[0]);
      if (!s) return R(404, { error: "not_found" });
      const problems = validateParamSet(s, body);
      if (problems.length) return R(422, { error: "invalid", problems });
      if (s.id === "S14" && !featuresReady) return R(409, { error: "features_required", message_vi: "Cần tính đặc trưng (features_daily) trước khi thêm bộ tham số cho chiến lược này." });
      const index = Math.max(-1, ...s.param_sets.map((p) => p.index)) + 1;
      const trial_ids = body.horizons.map((hz) => ({ horizon: hz, trial_id: `${s.id}-u${index}-${hz}`, registered: true, registered_at: new Date().toISOString() }));
      s.param_sets.push({ index, params: body.params, horizons: body.horizons, enabled: true, origin: "user", trial_ids, ids: [] });
      return R(200, { ok: true, index, backup: `config.yaml.bak-${stamp()}`, trial_ids, warning_vi: "Mỗi bộ tham số mới là một trial mới và làm ngưỡng Deflated Sharpe cao hơn." });
    }
  }
  if (method === "PUT" && m("config")) {
    const { problems, diff } = checkChanges(body.changes);
    if (problems.length) return R(422, { error: "invalid", problems });
    Object.entries(body.changes).forEach(([p, v]) => setPath(userCfg, p, v));
    return R(200, { ok: true, backup: Object.keys(userCfg).length ? `config.yaml.bak-${stamp()}` : null, diff });
  }
  if (method === "PATCH" && (x = m("strategies/*/param-sets/*"))) {
    const s = STRATS.find((y) => y.id === x[0]);
    const p = s && s.param_sets.find((y) => String(y.index) === x[1]);
    if (!p) return R(404, { error: "not_found" });
    p.enabled = !!body.enabled;
    return R(200, { ok: true });
  }
  if (method === "DELETE" && (x = m("strategies/*/param-sets/*"))) {
    const s = STRATS.find((y) => y.id === x[0]);
    const i = s ? s.param_sets.findIndex((y) => String(y.index) === x[1]) : -1;
    if (i < 0) return R(404, { error: "not_found" });
    if (s.param_sets[i].origin !== "user") return R(409, { error: "packaged_set", message_vi: "Chỉ xóa được bộ tham số do bạn thêm." });
    s.param_sets.splice(i, 1);
    return R(200, { ok: true, kept_trials: true, message_vi: "Trial vẫn được giữ trong registry (chỉ ghi thêm, không xóa)." });
  }
  return R(404, { error: "not_found", path });
}
