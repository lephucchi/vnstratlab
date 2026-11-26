// Page 3b: Kết quả. Synthetic banner, sortable summary table, equity chart.
import { api, errorBox, fmtNum, h } from "./util.js";

const PERCENT = new Set(["CAGR", "vol", "maxDD"]);
const COLUMN_LABEL = { trial: "Trial", horizon: "Khung", CAGR: "CAGR", vol: "Biến động", Sharpe: "Sharpe", maxDD: "Sụt giảm tối đa", turnover: "Vòng quay", trades: "Số lệnh" };
const SHOWN = ["trial", "horizon", "CAGR", "vol", "Sharpe", "maxDD", "turnover", "trades"];

const isBenchmark = (row) => String(row.trial_id).startsWith("benchmark_") || String(row.trial).includes("(benchmark");

function fmtCell(col, v) {
  if (v === null || v === undefined) return "n/a";
  if (PERCENT.has(col)) return `${fmtNum(v * 100, 1)}%`;
  if (col === "Sharpe") return fmtNum(v, 2);
  if (col === "turnover") return fmtNum(v, 3);
  return String(v);
}

function summaryTable(rows) {
  let sortKey = null;
  let dir = 1;
  const body = h("tbody");
  const head = h("tr");
  function draw() {
    const sorted = [...rows];
    if (sortKey) {
      sorted.sort((a, b) => {
        const x = a[sortKey];
        const y = b[sortKey];
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (x > y ? 1 : -1) * dir;
      });
    }
    head.replaceChildren(
      ...SHOWN.map((c) =>
        h(
          "th",
          { "aria-sort": sortKey === c ? (dir === 1 ? "ascending" : "descending") : "none" },
          h(
            "button",
            {
              class: "th-btn",
              type: "button",
              onclick: () => {
                dir = sortKey === c ? -dir : 1;
                sortKey = c;
                draw();
              },
            },
            COLUMN_LABEL[c] || c,
            sortKey === c ? (dir === 1 ? " ▲" : " ▼") : ""
          )
        )
      )
    );
    body.replaceChildren(
      ...sorted.map((r) =>
        h(
          "tr",
          { class: isBenchmark(r) ? "bench" : null },
          SHOWN.map((c) => h("td", { class: c === "trial" || c === "horizon" ? null : "num" }, fmtCell(c, r[c]), c === "trial" && isBenchmark(r) && !String(r.trial).includes("(benchmark)") ? h("span", { class: "chip st-queued" }, "benchmark") : null))
        )
      )
    );
  }
  draw();
  return h("div", { class: "table-scroll" }, h("table", { class: "tbl sortable" }, h("thead", null, head), body));
}

function color(i) {
  return `hsl(${(i * 47) % 360} 65% 48%)`;
}

function equityChart(rows, equity) {
  const ids = rows.map((r) => r.trial_id).filter((id) => equity[id]);
  const bench = rows.find(isBenchmark);
  const selected = new Set(bench && equity[bench.trial_id] ? [bench.trial_id] : ids.slice(0, 1));
  const label = Object.fromEntries(rows.map((r) => [r.trial_id, r.trial]));
  const W = 820;
  const H = 320;
  const M = { l: 64, r: 12, t: 12, b: 28 };
  const svg = h("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Đường vốn" });
  const list = h("div", { class: "chart-legend" });

  function draw() {
    const chosen = ids.filter((id) => selected.has(id));
    const values = chosen.flatMap((id) => equity[id].equity.filter((v) => v !== null));
    svg.replaceChildren();
    if (!values.length) {
      svg.append(h("text", { x: W / 2, y: H / 2, "text-anchor": "middle", class: "axis" }, "Chọn ít nhất một trial"));
      return;
    }
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    if (lo === hi) {
      lo -= 1;
      hi += 1;
    }
    const pad = (hi - lo) * 0.05;
    lo -= pad;
    hi += pad;
    const y = (v) => M.t + (1 - (v - lo) / (hi - lo)) * (H - M.t - M.b);
    for (let i = 0; i <= 4; i++) {
      const v = lo + ((hi - lo) * i) / 4;
      svg.append(
        h("line", { class: "grid-line", x1: M.l, x2: W - M.r, y1: y(v), y2: y(v) }),
        h("text", { class: "axis", x: M.l - 6, y: y(v) + 4, "text-anchor": "end" }, Math.round(v).toLocaleString("vi-VN"))
      );
    }
    const dates = equity[chosen[0]].dates;
    [0, Math.floor((dates.length - 1) / 2), dates.length - 1].forEach((k, i) =>
      svg.append(h("text", { class: "axis", x: M.l + (k / Math.max(dates.length - 1, 1)) * (W - M.l - M.r), y: H - 8, "text-anchor": i === 0 ? "start" : i === 1 ? "middle" : "end" }, dates[k] || ""))
    );
    chosen.forEach((id) => {
      const { equity: e } = equity[id];
      const pts = e
        .map((v, k) => (v === null ? null : `${(M.l + (k / Math.max(e.length - 1, 1)) * (W - M.l - M.r)).toFixed(1)},${y(v).toFixed(1)}`))
        .filter(Boolean)
        .join(" ");
      const isB = bench && id === bench.trial_id;
      svg.append(h("polyline", { class: `series${isB ? " series-bench" : ""}`, points: pts, stroke: isB ? "var(--muted)" : color(ids.indexOf(id)) }));
    });
  }

  ids.forEach((id) => {
    const isB = bench && id === bench.trial_id;
    const box = h("input", {
      type: "checkbox",
      checked: selected.has(id),
      onchange: () => {
        box.checked ? selected.add(id) : selected.delete(id);
        draw();
      },
    });
    list.append(
      h(
        "label",
        { class: "check" },
        box,
        h("span", { class: "swatch", style: `background:${isB ? "var(--muted)" : color(ids.indexOf(id))}` }),
        label[id] || id
      )
    );
  });
  draw();
  return h("section", { class: "card" }, h("h2", null, "Đường vốn"), svg, list);
}

export async function renderResults(root, runId, latest) {
  root.append(h("h1", null, "Kết quả"));
  let id = runId;
  if (!id) {
    const href = await latest();
    id = href ? href.split("/").pop() : null;
  }
  if (!id) {
    root.append(h("div", { class: "card" }, h("p", null, "Chưa có kết quả. Chạy demo để có kết quả đầu tiên."), h("a", { class: "btn btn-primary", href: "#/huong-dan" }, "Về Hướng dẫn")));
    return;
  }
  const res = await api(`/results/${encodeURIComponent(id)}`);
  if (!res.ok) {
    root.append(errorBox(res.status === 404 ? `Lần chạy ${id} không có kết quả (chỉ demo thành công mới có).` : "Không tải được kết quả."), h("a", { href: "#/runs" }, "Về Runs"));
    return;
  }
  const data = res.body;
  root.append(
    h("div", { class: "banner-red", role: "alert" }, "DỮ LIỆU GIẢ LẬP — không nói gì về thị trường thật"),
    h("p", { class: "muted" }, "Lần chạy: ", h("a", { href: `#/runs/${id}` }, id)),
    h("section", { class: "card" }, h("h2", null, "Bảng tổng hợp"), summaryTable(data.rows)),
    equityChart(data.rows, data.equity)
  );
}
