// Inline SVG charts (no library): sparkline and a line chart with hover crosshair and tooltip.
import { h } from "./util.js";

export const isoDay = (ms) => new Date(ms).toISOString().slice(0, 10);
export const toMs = (d) => Date.parse(String(d).slice(0, 10) + "T00:00:00Z");

export function sparkline(values, w = 90, ht = 26) {
  const v = values.filter((x) => Number.isFinite(x));
  const svg = h("svg", { class: "spark", viewBox: `0 0 ${w} ${ht}`, "aria-hidden": "true" });
  if (v.length < 2) return svg;
  const lo = Math.min(...v);
  const hi = Math.max(...v);
  const span = hi - lo || 1;
  const pts = v.map((y, i) => `${((i / (v.length - 1)) * (w - 2) + 1).toFixed(1)},${(ht - 2 - ((y - lo) / span) * (ht - 4)).toFixed(1)}`);
  svg.append(h("polyline", { points: pts.join(" ") }));
  return svg;
}

function niceTicks(lo, hi, n = 4) {
  const span = hi - lo || 1;
  const raw = span / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(t);
  return out;
}

function nearest(xs, target) {
  let lo = 0;
  let hi = xs.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(xs[lo - 1] - target) <= Math.abs(xs[lo] - target)) return lo - 1;
  return lo;
}

/**
 * Line chart. ``set({series, bars, yFmt, area})``.
 * series: [{id, label, x: [ms], y: [number|null], stroke?, dash?, width?}]; bars: {x:[ms], y:[number]} drawn small at the bottom.
 */
export function lineChart({ height = 300 } = {}) {
  const svg = h("svg", { class: "chart", role: "img" });
  const tip = h("div", { class: "chart-tip", hidden: true });
  const el = h("div", { class: "chart-wrap" }, svg, tip);
  let state = { series: [], bars: null, yFmt: (v) => String(v), area: false, label: "Biểu đồ", barFmt: (v) => String(v) };
  let highlight = null;
  const M = { l: 62, r: 12, t: 10, b: 24 };
  let W = 800;
  let layout = null;

  function draw() {
    W = Math.max(240, el.clientWidth || 800);
    svg.setAttribute("viewBox", `0 0 ${W} ${height}`);
    svg.setAttribute("height", String(height));
    svg.setAttribute("aria-label", state.label);
    svg.replaceChildren();
    tip.hidden = true;
    const { series, bars } = state;
    const xs = series.flatMap((s) => s.x);
    const ys = series.flatMap((s) => s.y.filter((v) => v !== null && Number.isFinite(v)));
    if (!xs.length || !ys.length) {
      layout = null;
      svg.append(h("text", { class: "ax", x: W / 2, y: height / 2, "text-anchor": "middle" }, "Không có dữ liệu để vẽ"));
      return;
    }
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    let lo = Math.min(...ys);
    let hi = Math.max(...ys);
    if (lo === hi) {
      lo -= 1;
      hi += 1;
    }
    const pad = (hi - lo) * 0.06;
    lo -= pad;
    hi += pad;
    const volH = bars ? (height - M.t - M.b) * 0.2 : 0;
    const top = M.t;
    const bottom = height - M.b - (bars ? volH + 4 : 0);
    const X = (v) => M.l + ((v - x0) / (x1 - x0 || 1)) * (W - M.l - M.r);
    const Y = (v) => top + (1 - (v - lo) / (hi - lo)) * (bottom - top);
    layout = { X, Y, x0, x1 };
    for (const t of niceTicks(lo, hi)) {
      svg.append(h("line", { class: "gl", x1: M.l, x2: W - M.r, y1: Y(t), y2: Y(t) }), h("text", { class: "ax", x: M.l - 6, y: Y(t) + 3.5, "text-anchor": "end" }, state.yFmt(t)));
    }
    [0, 1 / 3, 2 / 3, 1].forEach((f, i, a) =>
      svg.append(h("text", { class: "ax", x: M.l + f * (W - M.l - M.r), y: height - 6, "text-anchor": i === 0 ? "start" : i === a.length - 1 ? "end" : "middle" }, isoDay(x0 + f * (x1 - x0))))
    );
    if (bars) {
      const vmax = Math.max(...bars.y, 1);
      const bw = Math.max(1, (W - M.l - M.r) / bars.x.length - 0.5);
      bars.x.forEach((bx, i) => {
        const bh = (bars.y[i] / vmax) * volH;
        svg.append(h("rect", { class: "vol", x: X(bx) - bw / 2, y: height - M.b - bh, width: bw, height: bh }));
      });
    }
    series.forEach((s, idx) => {
      const pts = [];
      s.x.forEach((xv, i) => s.y[i] !== null && Number.isFinite(s.y[i]) && pts.push(`${X(xv).toFixed(1)},${Y(s.y[i]).toFixed(1)}`));
      const dim = highlight && highlight !== s.id;
      if (state.area && idx === 0 && pts.length) {
        svg.append(h("polygon", { class: "area", points: `${pts[0].split(",")[0]},${bottom} ${pts.join(" ")} ${pts[pts.length - 1].split(",")[0]},${bottom}` }));
      }
      svg.append(
        h("polyline", {
          class: "ser",
          points: pts.join(" "),
          stroke: s.stroke || "var(--fg)",
          "stroke-width": highlight === s.id ? 2.6 : s.width || 1.6,
          "stroke-dasharray": s.dash || null,
          opacity: dim ? 0.22 : 1,
        })
      );
    });
    svg.append(h("g", { class: "hover" }));
  }

  function hover(e) {
    if (!layout) return;
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const target = layout.x0 + ((px - M.l) / (W - M.l - M.r)) * (layout.x1 - layout.x0);
    const lead = state.series.reduce((a, s) => (s.x.length > a.x.length ? s : a), state.series[0]);
    const xv = lead.x[nearest(lead.x, target)];
    const g = svg.querySelector(".hover");
    g.replaceChildren(h("line", { class: "xh", x1: layout.X(xv), x2: layout.X(xv), y1: M.t, y2: height - M.b }));
    const rows = [];
    for (const s of state.series) {
      const i = nearest(s.x, xv);
      if (Math.abs(s.x[i] - xv) > 5 * 86400000 || s.y[i] === null || !Number.isFinite(s.y[i])) continue;
      g.append(h("circle", { cx: layout.X(s.x[i]), cy: layout.Y(s.y[i]), r: 3.4, fill: s.stroke || "var(--fg)", stroke: "var(--surface)", "stroke-width": 1.5 }));
      rows.push([s, s.y[i]]);
    }
    rows.sort((a, b) => b[1] - a[1]);
    const lines = rows.slice(0, 8).map(([s, v]) =>
      h("div", { class: "r" }, h("span", null, h("i", { class: "sw", style: `border-top-color:${s.stroke || "var(--fg)"}${s.dash ? ";border-top-style:dashed" : ""}` }), s.label), h("span", null, state.yFmt(v)))
    );
    if (state.bars) {
      const bi = nearest(state.bars.x, xv);
      lines.push(h("div", { class: "r" }, h("span", null, "Khối lượng"), h("span", null, state.barFmt(state.bars.y[bi]))));
    }
    tip.replaceChildren(h("b", null, isoDay(xv)), ...lines);
    tip.hidden = false;
    const left = layout.X(xv) / W > 0.6 ? layout.X(xv) * (rect.width / W) - tip.offsetWidth - 12 : layout.X(xv) * (rect.width / W) + 12;
    tip.style.left = `${Math.max(4, left)}px`;
    tip.style.top = `${M.t + 6}px`;
  }
  svg.addEventListener("pointermove", hover);
  svg.addEventListener("pointerleave", () => {
    tip.hidden = true;
    svg.querySelector(".hover")?.replaceChildren();
  });
  if ("ResizeObserver" in window) {
    let last = 0;
    new ResizeObserver(() => {
      const w = el.clientWidth;
      if (w && Math.abs(w - last) > 2) {
        last = w;
        draw();
      }
    }).observe(el);
  }
  return {
    el,
    set(next) {
      state = { ...state, ...next };
      draw();
    },
    highlight(id) {
      highlight = id;
      draw();
    },
  };
}
