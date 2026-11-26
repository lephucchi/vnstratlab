"use strict";
// "Demo sản phẩm": guide animation, latest synthetic demo run (DAG + logs), results and screenshots.
// Everything shown here is synthetic. Data comes from the decrypted PO payload (`demo`); the guide
// content is the Console's own guide-data.js, copied next to this page by the Pages build.

(function () {
  const SVG = "http://www.w3.org/2000/svg";
  const STATUS_VI = { queued: "Chờ", running: "Đang chạy", success: "Thành công", failed: "Lỗi", skipped: "Bỏ qua" };
  const SHOTS = [
    ["guide.png", "Hướng dẫn: sơ đồ sáu bước, lệnh và những điểm cần để ý."],
    ["runs.png", "Runs: lưới các lần chạy gần đây, mỗi ô là một tác vụ."],
    ["run.png", "Một lần chạy: sơ đồ tác vụ, thời gian từng bước và log."],
    ["results.png", "Kết quả: bảng chỉ số và đường vốn của demo giả lập."],
  ];
  const COLUMN_LABEL = { trial: "Trial", horizon: "Khung", CAGR: "CAGR", vol: "Biến động", Sharpe: "Sharpe", maxDD: "Sụt giảm tối đa", turnover: "Vòng quay", trades: "Số lệnh" };
  const PERCENT = new Set(["CAGR", "vol", "maxDD"]);
  const SHOWN = ["trial", "horizon", "CAGR", "vol", "Sharpe", "maxDD", "turnover", "trades"];

  const $ = (sel) => document.querySelector(sel);
  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "style") n.style.cssText = v; // CSSOM: allowed by the page CSP
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return n;
  }
  function s(tag, attrs, ...kids) {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v));
    for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return n;
  }
  const num = (v, d) => Number(v).toLocaleString("vi-VN", { minimumFractionDigits: d, maximumFractionDigits: d });
  function fmtDur(sec) {
    if (sec === null || sec === undefined) return "";
    return sec < 1 ? `${Math.round(sec * 1000)} ms` : sec < 60 ? `${num(sec, 1)} s` : `${Math.floor(sec / 60)} phút ${Math.round(sec % 60)} s`;
  }
  function fmtTime(iso) {
    return iso ? new Date(iso).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false }) : "—";
  }
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------------- 1. guide
  async function renderGuide(root) {
    let data;
    try {
      data = await import("./guide/guide-data.js");
    } catch (_) {
      root.replaceChildren(h("p", { class: "empty" }, "Chưa có nội dung hướng dẫn (thiếu guide/guide-data.js trong bản build)."));
      return;
    }
    const STEPS = data.STEPS;
    let active = 0;
    let timer = null;
    const pipe = h("div", { class: "pipe", role: "group", "aria-label": "Sơ đồ quy trình" });
    const card = h("div", { class: "frame", "aria-live": "polite" });
    const play = h("button", { class: "btn-s primary", type: "button" }, "Phát");
    const prev = h("button", { class: "btn-s", type: "button" }, "‹ Trước");
    const next = h("button", { class: "btn-s", type: "button" }, "Sau ›");
    const counter = h("span", { class: "muted small" });
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
      play.textContent = "Phát";
    };
    function draw() {
      pipe.replaceChildren(
        ...STEPS.flatMap((st, i) => [
          i > 0 ? h("span", { class: `link${i < active ? " done" : i === active ? " flow" : ""}`, "aria-hidden": "true" }) : null,
          h("button", { class: `pnode${i === active ? " active" : ""}${i < active ? " done" : ""}`, type: "button", "aria-current": i === active ? "step" : null,
            onclick: () => { stop(); go(i); } }, h("span", { class: "pn" }, String(i + 1)), st.name),
        ]).filter(Boolean)
      );
      const st = STEPS[active];
      card.replaceChildren(
        h("h3", {}, `${active + 1}. ${st.name}`),
        h("p", {}, st.what),
        h("p", {}, h("code", {}, st.command)),
        h("p", { class: "watch-t" }, "⚠ Cần để ý"),
        h("ul", { class: "watch" }, st.watch.map((w) => h("li", {}, w)))
      );
      counter.textContent = `Khung ${active + 1}/${STEPS.length}`;
      prev.disabled = active === 0;
      next.disabled = active === STEPS.length - 1;
    }
    function go(i) { active = Math.min(Math.max(i, 0), STEPS.length - 1); draw(); }
    play.addEventListener("click", () => {
      if (timer) return stop();
      if (active === STEPS.length - 1) go(0);
      play.textContent = "Dừng";
      timer = setInterval(() => { if (active >= STEPS.length - 1) stop(); else go(active + 1); }, 2600);
    });
    prev.addEventListener("click", () => { stop(); go(active - 1); });
    next.addEventListener("click", () => { stop(); go(active + 1); });
    root.replaceChildren(
      h("p", { class: "muted small" }, "Cùng nội dung với trang Hướng dẫn của Console: sáu bước từ dữ liệu giá đến báo cáo."),
      pipe,
      h("div", { class: "controls" }, reduced() ? null : play, prev, next, counter),
      card
    );
    draw();
  }

  // ---------------------------------------------------------------- 2. run DAG
  function layout(tasks, edges) {
    const ups = {};
    tasks.forEach((t) => (ups[t.id] = []));
    edges.forEach((e) => ups[e.to] && ups[e.to].push(e.from));
    const level = {};
    const visit = (id) => {
      if (level[id] !== undefined) return level[id];
      level[id] = 0;
      level[id] = ups[id].length ? 1 + Math.max(...ups[id].map(visit)) : 0;
      return level[id];
    };
    tasks.forEach((t) => visit(t.id));
    return level;
  }
  function wrap(label) {
    if (label.length <= 17) return [label];
    const w = label.split(" ");
    let best = [label];
    let diff = Infinity;
    for (let i = 1; i < w.length; i++) {
      const a = w.slice(0, i).join(" ");
      const b = w.slice(i).join(" ");
      if (Math.abs(a.length - b.length) < diff) { diff = Math.abs(a.length - b.length); best = [a, b]; }
    }
    return best;
  }
  function dag(demo, onSelect) {
    const W = 150, H = 46, GX = 56, GY = 26, PAD = 12;
    const level = layout(demo.tasks, demo.edges);
    const cols = {};
    demo.tasks.forEach((t) => (cols[level[t.id]] = [...(cols[level[t.id]] || []), t.id]));
    const nCols = Math.max(...Object.keys(cols).map(Number)) + 1;
    const nRows = Math.max(...Object.values(cols).map((c) => c.length));
    const width = PAD * 2 + nCols * W + (nCols - 1) * GX;
    const height = PAD * 2 + nRows * (H + 16) + (nRows - 1) * GY;
    const pos = {};
    for (const [c, ids] of Object.entries(cols)) {
      const colH = ids.length * (H + 16) + (ids.length - 1) * GY;
      ids.forEach((id, i) => { pos[id] = { x: PAD + Number(c) * (W + GX), y: PAD + (height - PAD * 2 - colH) / 2 + i * (H + 16 + GY) }; });
    }
    const status = Object.fromEntries(demo.tasks.map((t) => [t.id, t.status]));
    const edgeEls = demo.edges.filter((e) => pos[e.from] && pos[e.to]).map((e) => {
      const a = pos[e.from], b = pos[e.to];
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
      const ok = status[e.to] === "success" || status[e.to] === "failed";
      return s("path", { class: `edge${ok ? " done" : ""}`, d: `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2 - 6} ${y2}` });
    });
    const nodes = {};
    const els = demo.tasks.map((t) => {
      const lines = wrap(t.label_vi);
      const g = s("g", { class: `dnode st-${t.status}`, transform: `translate(${pos[t.id].x} ${pos[t.id].y})`, tabindex: 0, role: "button" },
        s("title", {}, `${t.label_vi}: ${STATUS_VI[t.status] || t.status}`),
        s("rect", { class: "nrect", width: W, height: H, rx: 8 }),
        s("text", { class: "nlabel", "text-anchor": "middle" }, lines.map((ln, i) => s("tspan", { x: W / 2, y: lines.length === 1 ? H / 2 + 4 : H / 2 - 4 + i * 14 }, ln))),
        s("text", { class: "ndur", x: W / 2, y: H + 13, "text-anchor": "middle" }, fmtDur(t.duration_s))
      );
      g.addEventListener("click", () => onSelect(t.id));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(t.id); } });
      nodes[t.id] = g;
      return g;
    });
    const svg = s("svg", { class: "dag", viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": "Sơ đồ tác vụ" }, s("g", {}, edgeEls), s("g", {}, els));
    return { el: h("div", { class: "dag-wrap" }, svg), select: (id) => Object.entries(nodes).forEach(([k, g]) => g.classList.toggle("selected", k === id)) };
  }

  function renderRun(root, demo) {
    if (!demo || !demo.available) { root.replaceChildren(unavailable(demo)); return; }
    const logBox = h("pre", { class: "log", tabindex: "0" });
    const detail = h("p", { class: "muted small" });
    const picker = dag(demo, select);
    function select(id) {
      const t = demo.tasks.find((x) => x.id === id);
      picker.select(id);
      const sum = Object.entries(t.summary || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
      detail.replaceChildren(h("strong", {}, t.label_vi), " ", h("span", { class: `chip st-${t.status}` }, STATUS_VI[t.status] || t.status), ` ${fmtDur(t.duration_s)}`, sum ? ` · ${sum}` : "");
      const lines = demo.logs[id] || [];
      logBox.replaceChildren(...(lines.length ? lines : ["(không có log)"]).map((ln) =>
        h("div", { class: /ERROR|Traceback/.test(ln) ? "ln err" : /WARNING/.test(ln) ? "ln warn" : "ln" }, ln)));
    }
    root.replaceChildren(
      h("div", { class: "run-meta" },
        h("span", { class: `chip st-${demo.status}` }, STATUS_VI[demo.status] || demo.status),
        h("span", { class: "muted small mono" }, demo.run_id),
        h("span", { class: "muted small" }, `Kết thúc ${fmtTime(demo.generated_at)}`),
        h("span", { class: "muted small" }, `Thời gian ${fmtDur(demo.duration_s)}`)),
      picker.el,
      h("p", { class: "muted small" }, "Bấm vào một tác vụ để xem 40 dòng log cuối của nó."),
      detail,
      logBox
    );
    select(demo.tasks[demo.tasks.length - 1].id);
  }

  // ---------------------------------------------------------------- 3. results
  const fmtCell = (c, v) => (v === null || v === undefined ? "n/a" : PERCENT.has(c) ? `${num(v * 100, 1)}%` : c === "Sharpe" ? num(v, 2) : c === "turnover" ? num(v, 3) : String(v));
  const isBench = (r) => String(r.trial).startsWith("S17") || String(r.trial).includes("(benchmark)");

  function equityChart(demo) {
    const ids = Object.keys(demo.equity || {});
    if (!ids.length) return null;
    const label = Object.fromEntries(demo.results.rows.map((r) => [r.trial_id, r.trial]));
    const series = ids.map((id, i) => {
      const e = demo.equity[id];
      const base = e.equity.find((v) => v !== null);
      return { id, bench: isBench(demo.results.rows.find((r) => r.trial_id === id) || {}), color: `hsl(${(i * 67 + 20) % 360} 60% 45%)`,
        pts: e.dates.map((d, k) => [Date.parse(d), e.equity[k] === null ? null : (100 * e.equity[k]) / base]).filter((p) => p[1] !== null) };
    }).filter((x) => x.pts.length > 1);
    if (!series.length) return null;
    const all = series.flatMap((x) => x.pts);
    const x0 = Math.min(...all.map((p) => p[0])), x1 = Math.max(...all.map((p) => p[0]));
    let y0 = Math.min(...all.map((p) => p[1])), y1 = Math.max(...all.map((p) => p[1]));
    const pad = (y1 - y0) * 0.06 || 1;
    y0 -= pad; y1 += pad;
    const Wd = 820, Ht = 300, L = 46, R = 12, T = 12, B = 26;
    const X = (v) => L + ((v - x0) / (x1 - x0 || 1)) * (Wd - L - R);
    const Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (Ht - T - B);
    const grid = [0, 1, 2, 3, 4].map((i) => {
      const v = y0 + ((y1 - y0) * i) / 4;
      return [s("line", { class: "gl", x1: L, x2: Wd - R, y1: Y(v), y2: Y(v) }), s("text", { class: "ax", x: L - 6, y: Y(v) + 4, "text-anchor": "end" }, num(v, 0))];
    });
    const years = [];
    for (let y = new Date(x0).getUTCFullYear(); y <= new Date(x1).getUTCFullYear(); y++) {
      const t = Date.UTC(y, 0, 1);
      if (t >= x0) years.push(s("text", { class: "ax", x: X(t), y: Ht - 8, "text-anchor": "middle" }, String(y)));
    }
    const lines = series.map((x) => s("polyline", { class: `eq${x.bench ? " bench" : ""}`, fill: "none", stroke: x.bench ? "currentColor" : x.color, "stroke-width": 1.8, points: x.pts.map((p) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ") }));
    const legend = h("div", { class: "legend" }, series.map((x) =>
      h("span", {}, h("i", { class: `sw${x.bench ? " bench" : ""}`, style: x.bench ? "" : `background:${x.color}` }), label[x.id] || x.id)));
    return h("div", {}, h("div", { class: "dag-wrap" }, s("svg", { class: "chart", viewBox: `0 0 ${Wd} ${Ht}`, role: "img", "aria-label": "Đường vốn quy về 100 của benchmark S17 và ba trial có Sharpe cao nhất" }, grid, years, lines)),
      legend, h("p", { class: "muted small" }, "Đường vốn quy về 100 tại ngày đầu; benchmark S17 và ba trial có Sharpe cao nhất. Dữ liệu giả lập."));
  }

  function table(demo) {
    const rows = demo.results.rows;
    if (!rows.length) return null;
    return h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, SHOWN.map((c) => h("th", { scope: "col" }, COLUMN_LABEL[c] || c)))),
      h("tbody", {}, rows.map((r) => h("tr", { class: isBench(r) ? "benchrow" : null }, SHOWN.map((c) => h("td", { class: c === "trial" || c === "horizon" ? null : "r" }, fmtCell(c, r[c]))))))));
  }

  function gallery() {
    const figs = SHOTS.map(([file, caption]) => {
      const img = h("img", { src: `shots/${file}`, alt: caption, loading: "lazy", width: "1280", height: "800" });
      const fig = h("figure", { class: "shot" }, h("a", { href: `shots/${file}`, target: "_blank", rel: "noopener" }, img), h("figcaption", { class: "small muted" }, caption));
      img.addEventListener("error", () => fig.remove());
      return fig;
    });
    return h("div", { class: "gallery" }, figs);
  }

  function renderResults(root, demo) {
    const parts = [];
    if (demo && demo.available) {
      parts.push(table(demo), equityChart(demo));
    } else {
      parts.push(unavailable(demo));
    }
    parts.push(h("h3", { class: "sub-h" }, "Ảnh chụp Console"), gallery());
    root.replaceChildren(...parts.filter(Boolean));
  }

  function unavailable(demo) {
    return h("p", { class: "empty" }, "Chưa có dữ liệu demo", demo && demo.reason ? h("span", {}, " (lý do kỹ thuật: ", h("span", { lang: "en" }, demo.reason), ")") : null, ". Lần build Pages tiếp theo sẽ thử lại.");
  }

  window.renderDemo = function (demo) {
    renderGuide($("#demo-guide"));
    renderRun($("#demo-run"), demo);
    renderResults($("#demo-results"), demo);
  };
})();
