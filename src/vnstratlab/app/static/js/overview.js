// Tổng quan: data freshness, last runs, quick actions, gaps by severity, strategies/trials, VERIFY.
import { pipelineButton } from "./runs.js";
import { cliLine, emptyState, pageHead } from "./ui.js";
import { api, cliOf, errorBox, fmtAgo, fmtDur, fmtInt, h } from "./util.js";

/** Contract: GET /api/overview. Older backend: build the same shape from the existing endpoints. */
async function loadOverview() {
  const res = await api("/overview");
  if (res.ok) return res.body;
  const [runs, data] = await Promise.all([api("/runs?limit=5"), api("/data/status")]);
  if (!runs.ok) return null;
  const store = data.ok && data.body.stores[0];
  const counts = (data.ok && data.body.gaps.counts) || {};
  let staleDays = null;
  if (store && store.tickers && store.tickers.length) {
    const last = store.tickers.map((t) => t.last).sort().pop();
    staleDays = Math.max(0, Math.floor((Date.now() - Date.parse(last)) / 86400000));
  }
  return {
    version: null, home: data.ok ? data.body.home : null, source: store ? store.kind : null,
    store: store && !store.error ? { kind: store.kind, tickers: store.tickers.length, first: store.tickers.map((t) => t.first).sort()[0], last: store.tickers.map((t) => t.last).sort().pop(), rows: store.rows, stale_days: staleDays } : null,
    last_runs: runs.body.runs, active_run_id: (runs.body.runs.find((r) => r.status === "running" || r.status === "queued") || {}).run_id || null,
    gaps: { high: counts.high || 0, medium: counts.medium || 0, low: counts.low || 0 }, verify_count: null, strategies: null,
    fallback: true,
  };
}

/** Contract: store.tickers is a count; API v2 sends a list of strings plus ticker_count. */
function tickerCount(store) {
  if (!store) return null;
  if (typeof store.ticker_count === "number") return store.ticker_count;
  return Array.isArray(store.tickers) ? store.tickers.length : store.tickers;
}

function kpi(label, value, sub) {
  return h("div", { class: "kpi" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value), sub ? h("div", { class: "sub" }, sub) : null);
}

function freshness(store) {
  if (!store) {
    return h("section", { class: "card" }, h("h2", null, "Độ mới của dữ liệu"), emptyState("Chưa có dữ liệu", "Chạy demo (offline) hoặc nạp dữ liệu để bắt đầu.", h("a", { class: "btn sm", href: "#/runs" }, "Mở Runs")));
  }
  const stale = typeof store.stale_days === "number" && store.stale_days > 3;
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "Độ mới của dữ liệu"), h("span", { class: `chip ${store.kind === "real" ? "dashed" : "soft"}` }, store.kind === "real" ? "THẬT" : "SYNTHETIC")),
    h("div", { class: "fresh" }, h("div", { class: "value mono" }, store.last || "—"), h("div", { class: "muted small" }, "phiên mới nhất trong kho")),
    h("p", { class: "muted small" }, `${fmtInt(tickerCount(store))} mã · ${fmtInt(store.rows)} dòng · từ ${store.first || "—"}`),
    stale ? h("div", { class: "notice warn" }, `Dữ liệu đã cũ ${store.stale_days} ngày. Nên “Làm mới dữ liệu” trước khi đọc khuyến nghị.`) : h("div", { class: "notice ok" }, store.stale_days === 0 ? "Dữ liệu đến hôm nay." : `Dữ liệu cũ ${store.stale_days ?? "?"} ngày: còn trong ngưỡng.`)
  );
}

export async function renderOverview(root) {
  const ov = await loadOverview();
  if (!ov) {
    root.append(pageHead("Tổng quan"), errorBox("Không tải được tổng quan. Kiểm tra lại máy chủ `vnstratlab serve`."));
    return;
  }
  const pipes = await api("/pipelines");
  const list = pipes.ok ? pipes.body.pipelines : [];
  const byId = Object.fromEntries(list.map((p) => [p.id, p]));
  root.append(pageHead("Tổng quan", [ov.version ? `v${ov.version}` : null, ov.source ? `nguồn ${ov.source}` : null, ov.home].filter(Boolean).join(" · ")));
  if (ov.active_run_id) root.append(h("div", { class: "notice" }, h("span", { class: "dot st-running" }), " Đang có một lần chạy. ", h("a", { href: `#/runs/${ov.active_run_id}` }, "Xem tiến trình")));
  if (ov.fallback) root.append(h("div", { class: "notice warn" }, "Máy chủ chưa có /api/overview: số liệu chiến lược và VERIFY tạm ẩn."));

  const s = ov.strategies;
  root.append(
    h("div", { class: "kpis" },
      kpi("Mã trong kho", fmtInt(tickerCount(ov.store)), ov.store ? `${fmtInt(ov.store.rows)} dòng` : "chưa có dữ liệu"),
      kpi("Chiến lược", s ? `${s.enabled}/${s.registered}` : "—", "bộ tham số bật / chiến lược"),
      kpi("Trial đã đếm", s ? fmtInt(s.trials) : "—", "mọi lần thử đều được đếm"),
      kpi("Mục [VERIFY]", ov.verify_count === null ? "—" : fmtInt(ov.verify_count), "cần kiểm chứng"),
      kpi("Khoảng trống mở", fmtInt(ov.gaps.high + ov.gaps.medium + ov.gaps.low), `${ov.gaps.high} cao · ${ov.gaps.medium} TB · ${ov.gaps.low} thấp`)
    )
  );

  const actions = [
    byId.demo && [byId.demo, "Chạy demo", "Chạy thử toàn bộ quy trình trên dữ liệu giả lập, offline."],
    byId.refresh && [byId.refresh, "Làm mới dữ liệu", "Nạp dữ liệu mới, dựng lại giá và tính đặc trưng."],
    byId.backtest_all && [byId.backtest_all, "Backtest", "Chạy backtest cho mọi chiến lược đã bật (mỗi trial được đếm)."],
  ].filter(Boolean);
  const quick = h(
    "section",
    { class: "card" },
    h("h2", null, "Thao tác nhanh"),
    h("div", { class: "qa" }, actions.map(([p, label, text]) => h("div", { class: "qa-item" }, h("div", null, h("b", null, label), h("div", { class: "muted small" }, text)), pipelineButton(p, { label: "Chạy" }), cliLine(cliOf(p))))),
    byId.backtest_all ? null : h("div", { class: "qa-item" }, h("div", null, h("b", null, "Backtest"), h("div", { class: "muted small" }, "Sắp có: máy chủ chưa có quy trình backtest_all.")), h("button", { class: "btn ghost", type: "button", disabled: true }, "Chưa có"))
  );

  const runsCard = h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "5 lần chạy gần nhất"), h("a", { href: "#/runs" }, "Tất cả")),
    ov.last_runs.length
      ? h("div", { class: "run-list" }, ov.last_runs.map((r) => h("a", { class: "run-row", href: `#/runs/${r.run_id}` }, h("span", { class: `dot st-${r.status}` }), h("span", { class: "nm" }, r.label_vi || r.pipeline), h("span", { class: "when" }, fmtDur(r.duration_s)), h("span", { class: "when" }, fmtAgo(r.created_at)))))
      : emptyState("Chưa có lần chạy nào", "Bấm “Chạy demo” để có lần chạy đầu tiên.")
  );

  const gapsCard = h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "Khoảng trống theo mức độ"), h("a", { href: "#/du-lieu" }, "Chi tiết")),
    h("div", { class: "sevs" }, [["high", "Cao"], ["medium", "Trung bình"], ["low", "Thấp"]].map(([k, label]) => h("a", { class: "sevbox", href: "#/du-lieu" }, h("div", { class: "value mono" }, String(ov.gaps[k])), h("span", { class: `sev sev-${k}` }, label))))
  );

  root.append(h("div", { class: "grid-2" }, freshness(ov.store), quick), h("div", { class: "grid-2" }, runsCard, gapsCard));
}
