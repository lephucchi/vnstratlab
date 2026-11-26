// Kết quả: synthetic banner, sortable/filterable table, trial checkboxes drive the equity chart.
import { lineChart, toMs } from "./charts.js";
import { renderRecsPanel } from "./recs.js";
import { emptyState, pageHead, segmented } from "./ui.js";
import { api, errorBox, fmtNum, h } from "./util.js";

const PERCENT = new Set(["CAGR", "vol", "maxDD"]);
const COLUMN_LABEL = { trial: "Trial", horizon: "Khung", CAGR: "CAGR", vol: "Biến động", Sharpe: "Sharpe", maxDD: "Sụt giảm tối đa", turnover: "Vòng quay", trades: "Số lệnh" };
const SHOWN = ["trial", "horizon", "CAGR", "vol", "Sharpe", "maxDD", "turnover", "trades"];
const HORIZON_VI = { short: "ngắn", medium: "trung", long: "dài", all: "toàn bộ" };
// Monochrome series: luminance + dash pattern, so colour stays reserved for status.
const LOOKS = [
  { stroke: "var(--fg)" }, { stroke: "var(--fg-2)", dash: "7 3" }, { stroke: "var(--muted)" }, { stroke: "var(--fg)", dash: "2 3" },
  { stroke: "var(--faint)" }, { stroke: "var(--fg-2)", dash: "2 3" }, { stroke: "var(--muted)", dash: "7 3" }, { stroke: "var(--faint)", dash: "2 3" },
];
const BENCH_DASH = ["9 4", "3 3", "9 3 2 3"];

// A benchmark row has a trial_id starting with "benchmark_" or "benchmark" in its label.
// Packaged S17 trials are ordinary trials; they are only a fallback overlay when no benchmark rows exist.
const isBenchmark = (row) => String(row.trial_id).startsWith("benchmark_") || /benchmark/i.test(String(row.trial));
const isS17 = (row) => /^S17/.test(String(row.trial_id)) || /^S17/.test(String(row.trial));
function fmtCell(col, v) {
  if (v === null || v === undefined) return "n/a";
  if (PERCENT.has(col)) return `${fmtNum(v * 100, 1)}%`;
  if (col === "Sharpe") return fmtNum(v, 2);
  if (col === "turnover") return fmtNum(v, 3);
  if (col === "horizon") return HORIZON_VI[v] || v;
  return String(v);
}

function drawdown(values) {
  let peak = -Infinity;
  return values.map((v) => (v === null ? null : ((peak = Math.max(peak, v)), v / peak - 1)));
}

function view(rows, equity) {
  const ids = rows.map((r) => r.trial_id).filter((id) => equity[id]);
  const withCurve = rows.filter((r) => equity[r.trial_id]);
  const found = withCurve.filter(isBenchmark);
  const benches = found.length ? found : withCurve.filter(isS17).slice(0, 1);
  const benchIds = benches.map((r) => r.trial_id);
  const benchFor = (r) => benches.find((b) => b.horizon === r.horizon) || benches[0];
  const selected = new Set([...benchIds, ...ids.filter((i) => !benchIds.includes(i)).slice(0, 2)]);
  const look = (id) => (benchIds.includes(id) ? { stroke: "var(--fg)", dash: BENCH_DASH[benchIds.indexOf(id) % BENCH_DASH.length], width: 2.2 } : LOOKS[ids.indexOf(id) % LOOKS.length]);
  const label = Object.fromEntries(rows.map((r) => [r.trial_id, r.trial]));
  const state = { sortKey: null, dir: 1, horizon: "", q: "", norm: false };

  const chart = lineChart({ height: 330 });
  const ddChart = lineChart({ height: 150 });
  const legend = h("div", { class: "legend-list" });
  const cmpHolder = h("div");
  const body = h("tbody");
  const head = h("tr");

  function drawCharts() {
    const chosen = ids.filter((id) => selected.has(id));
    const mk = (id) => {
      const e = equity[id];
      const x = e.dates.map(toMs);
      const first = e.equity.find((v) => v !== null);
      return { id, label: label[id] || id, x, y: state.norm ? e.equity.map((v) => (v === null ? null : (v / first) * 100)) : e.equity, ...look(id) };
    };
    chart.set({ label: "Đường vốn", series: chosen.map(mk), yFmt: (v) => (state.norm ? v.toFixed(0) : `${(v / 1e6).toFixed(1)}tr`), area: false });
    ddChart.set({ label: "Mức sụt giảm", series: chosen.map((id) => ({ ...mk(id), y: drawdown(equity[id].equity) })), yFmt: (v) => `${(v * 100).toFixed(0)}%` });
    legend.replaceChildren(
      ...chosen.map((id) => {
        const l = look(id);
        const el = h("label", { class: "check small" }, h("i", { class: "sw", style: `border-top-color:${l.stroke};${l.dash ? "border-top-style:dashed" : ""}` }), label[id] || id);
        el.addEventListener("mouseenter", () => (chart.highlight(id), ddChart.highlight(id)));
        el.addEventListener("mouseleave", () => (chart.highlight(null), ddChart.highlight(null)));
        return el;
      })
    );
    compare(chosen);
  }

  function compare(chosen) {
    if (!benches.length) return void cmpHolder.replaceChildren();
    const others = chosen.filter((id) => !benchIds.includes(id)).map((id) => rows.find((r) => r.trial_id === id));
    const d = (v, w, pct) => (v === null || w === null ? "n/a" : `${v - w >= 0 ? "+" : ""}${pct ? `${((v - w) * 100).toFixed(1)} đpt` : (v - w).toFixed(2)}`);
    cmpHolder.replaceChildren(
      others.length
        ? h("div", { class: "table-wrap" }, h("table", { class: "tbl" }, h("thead", null, h("tr", null, ["Trial", "CAGR vs benchmark", "Sharpe vs benchmark", "Sụt giảm vs benchmark"].map((x, i) => h("th", { class: i ? "num" : null }, x)))), h("tbody", null, others.map((r) => h("tr", null, h("td", null, r.trial), h("td", { class: "num" }, d(r.CAGR, benchFor(r).CAGR, true)), h("td", { class: "num" }, d(r.Sharpe, benchFor(r).Sharpe, false)), h("td", { class: "num" }, d(r.maxDD, benchFor(r).maxDD, true)))))))
        : h("p", { class: "muted small" }, "Chọn thêm trial trong bảng để so với benchmark.")
    );
  }

  function drawTable() {
    let list = rows.filter((r) => (!state.horizon || r.horizon === state.horizon) && (!state.q || String(r.trial).toLowerCase().includes(state.q)));
    if (state.sortKey) {
      list = [...list].sort((a, b) => {
        const x = a[state.sortKey];
        const y = b[state.sortKey];
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (x > y ? 1 : -1) * state.dir;
      });
    }
    head.replaceChildren(
      h("th", null, h("span", { class: "sr-only" }, "Hiện trên biểu đồ")),
      ...SHOWN.map((c) =>
        h("th", { class: c === "trial" || c === "horizon" ? null : "num", "aria-sort": state.sortKey === c ? (state.dir === 1 ? "ascending" : "descending") : "none" },
          h("button", { class: "th-btn", type: "button", onclick: () => ((state.dir = state.sortKey === c ? -state.dir : 1), (state.sortKey = c), drawTable()) }, COLUMN_LABEL[c] || c, state.sortKey === c ? (state.dir === 1 ? " ▲" : " ▼") : ""))
      )
    );
    body.replaceChildren(
      ...list.map((r) => {
        const has = !!equity[r.trial_id];
        const box = h("input", { type: "checkbox", checked: selected.has(r.trial_id), disabled: !has, "aria-label": `Hiện ${r.trial} trên biểu đồ`, onchange: () => ((box.checked ? selected.add(r.trial_id) : selected.delete(r.trial_id)), drawCharts()) });
        return h("tr", { class: isBenchmark(r) ? "bench" : null }, h("td", null, box), SHOWN.map((c) => h("td", { class: c === "trial" || c === "horizon" ? "pad" : "num" }, fmtCell(c, r[c]), c === "trial" && isBenchmark(r) && !/benchmark/i.test(String(r.trial)) ? h("span", { class: "chip dashed" }, "benchmark") : null)));
      })
    );
  }

  const horizons = [...new Set(rows.map((r) => r.horizon))];
  const search = h("input", { type: "search", placeholder: "Lọc trial…", "aria-label": "Lọc trial", oninput: () => ((state.q = search.value.trim().toLowerCase()), drawTable()) });
  const table = h("div", { class: "table-wrap" }, h("table", { class: "tbl sortable" }, h("thead", null, head), body));
  drawTable();
  drawCharts();
  const normSeg = segmented([["abs", "Giá trị (VND)"], ["norm", "Chuẩn hóa = 100"]], "abs", (v) => ((state.norm = v === "norm"), drawCharts()), "Kiểu hiển thị");
  const hzSeg = segmented([["", "Mọi khung"], ...horizons.map((x) => [x, HORIZON_VI[x] || x])], "", (v) => ((state.horizon = v), drawTable()), "Lọc theo khung");

  return [
    h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Bảng tổng hợp"), h("span", { class: "small muted" }, "Tích ô đầu dòng để vẽ lên biểu đồ")), h("div", { class: "toolbar" }, h("div", { class: "grow" }, search), hzSeg), table),
    h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Đường vốn"), normSeg), chart.el, legend, h("h3", null, "Mức sụt giảm"), ddChart.el),
    h("section", { class: "card" }, h("h2", null, "So với benchmark"), cmpHolder),
  ];
}

export async function renderResults(root, runId, latest) {
  root.append(pageHead("Kết quả", "Khuyến nghị hiện tại và kết quả chạy thử"));
  root.append(await renderRecsPanel());
  root.append(h("h2", { class: "section-title" }, "Kết quả chạy thử (demo)"), h("p", { class: "muted small" }, "Bảng chỉ số và đường vốn của lần chạy demo trên dữ liệu giả lập: để xem phương pháp hoạt động, không phải khuyến nghị."));
  let id = runId;
  if (!id) {
    const href = await latest();
    id = href ? href.split("/").pop() : null;
  }
  if (!id) {
    root.append(h("div", { class: "card" }, emptyState("Chưa có kết quả", "Chạy demo để có kết quả đầu tiên.", h("a", { class: "btn sm", href: "#/" }, "Về Tổng quan"))));
    return;
  }
  const res = await api(`/results/${encodeURIComponent(id)}`);
  if (!res.ok) {
    root.append(errorBox(res.status === 404 ? `Lần chạy ${id} không có kết quả (chỉ demo thành công mới có).` : "Không tải được kết quả."), h("a", { href: "#/runs" }, "Về Runs"));
    return;
  }
  const data = res.body;
  root.append(
    h("div", { class: "banner-synth", role: "alert" }, "DỮ LIỆU GIẢ LẬP — không nói gì về thị trường thật"),
    h("p", { class: "muted small" }, "Lần chạy: ", h("a", { href: `#/runs/${id}` }, id)),
    ...view(data.rows, data.equity)
  );
}
