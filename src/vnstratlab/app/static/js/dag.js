// Task DAG as inline SVG: layered top-to-bottom layout, hover card per node, click to select.
import { hcRow, hoverCard } from "./ui.js";
import { STATUS_VI, fmtDur, h } from "./util.js";

const W = 156;
const H = 58;
const GAP_X = 18;
const GAP_Y = 24;
const PAD = 14;

function layers(tasks) {
  const level = {};
  const visit = (t) => {
    if (level[t.id] !== undefined) return level[t.id];
    level[t.id] = 0; // guards against a cycle; the API never sends one
    const ups = t.upstream.map((u) => tasks.find((x) => x.id === u)).filter(Boolean);
    level[t.id] = ups.length ? 1 + Math.max(...ups.map(visit)) : 0;
    return level[t.id];
  };
  tasks.forEach(visit);
  return level;
}

function wrap(label) {
  if (label.length <= 19) return [label];
  const words = label.split(" ");
  let best = [label];
  let diff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(" ");
    const b = words.slice(i).join(" ");
    if (Math.abs(a.length - b.length) < diff) {
      diff = Math.abs(a.length - b.length);
      best = [a, b];
    }
  }
  return best;
}

/** Draw the DAG. Returns {el, update(tasks), select(id)}; ``onSelect(taskId)`` fires on node click. */
export function createDag(tasks, onSelect) {
  // Vertical layout: one row per dependency level, parallel tasks side by side.
  const level = layers(tasks);
  const rowsOf = {};
  tasks.forEach((t) => (rowsOf[level[t.id]] = [...(rowsOf[level[t.id]] || []), t.id]));
  const nLevels = Math.max(...Object.keys(rowsOf).map(Number)) + 1;
  const nWide = Math.max(...Object.values(rowsOf).map((c) => c.length));
  const width = PAD * 2 + nWide * W + (nWide - 1) * GAP_X;
  const height = PAD * 2 + nLevels * H + (nLevels - 1) * GAP_Y;
  const pos = {};
  for (const [lv, ids] of Object.entries(rowsOf)) {
    const rowW = ids.length * W + (ids.length - 1) * GAP_X;
    ids.forEach((id, i) => {
      pos[id] = { x: PAD + (width - PAD * 2 - rowW) / 2 + i * (W + GAP_X), y: PAD + Number(lv) * (H + GAP_Y) };
    });
  }

  const edges = [];
  const edgeEls = [];
  tasks.forEach((t) =>
    t.upstream.forEach((u) => {
      if (!pos[u]) return;
      const a = pos[u];
      const b = pos[t.id];
      const x1 = a.x + W / 2;
      const y1 = a.y + H;
      const x2 = b.x + W / 2;
      const y2 = b.y;
      const my = (y1 + y2) / 2;
      edgeEls.push(h("path", { class: "edge", d: `M${x1} ${y1} C${x1} ${my} ${x2} ${my} ${x2} ${y2 - 4}` }));
      edges.push({ to: t.id, from: u });
    })
  );

  const latest = {};
  tasks.forEach((t) => (latest[t.id] = t));
  const nodeEls = {};
  const durEls = {};
  const nodes = tasks.map((t) => {
    const lines = wrap(t.label_vi);
    const text = h(
      "text",
      { class: "node-label", x: W / 2 + 3, "text-anchor": "middle" },
      lines.map((ln, i) => {
        const span = h("tspan", { x: W / 2 + 3, y: lines.length === 1 ? 24 : 20 + i * 14 });
        span.textContent = ln;
        return span;
      })
    );
    const dur = h("text", { class: "node-dur", x: W / 2 + 3, y: H - 9, "text-anchor": "middle" }, "");
    const g = h(
      "g",
      {
        class: "dag-node st-queued",
        transform: `translate(${pos[t.id].x} ${pos[t.id].y})`,
        tabindex: 0,
        role: "button",
        "aria-label": t.label_vi,
        onclick: () => onSelect && onSelect(t.id),
        onkeydown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect && onSelect(t.id);
          }
        },
      },
      h("rect", { class: "node-rect", width: W, height: H, rx: 10 }),
      h("rect", { class: "node-bar", x: 0, y: 8, width: 4, height: H - 16, rx: 2 }),
      text,
      dur
    );
    hoverCard(g, () => {
      const cur = latest[t.id];
      const first = cur.error ? String(cur.error).split("\n")[0] : null;
      return [
        h("b", null, cur.label_vi),
        hcRow("Trạng thái", STATUS_VI[cur.status] || cur.status || "—"),
        hcRow("Thời gian", fmtDur(cur.duration_s)),
        cur.upstream.length ? hcRow("Phụ thuộc", cur.upstream.join(", ")) : null,
        first ? h("div", { class: "err" }, first) : null,
        h("div", { class: "muted small" }, "Bấm để xem log"),
      ];
    });
    nodeEls[t.id] = g;
    durEls[t.id] = dur;
    return g;
  });

  const svg = h("svg", { class: "dag", viewBox: `0 0 ${width} ${height}`, width, height, role: "group", "aria-label": "Sơ đồ tác vụ" }, h("g", null, edgeEls), h("g", null, nodes));

  function update(current) {
    const status = {};
    current.forEach((t) => {
      status[t.id] = t.status;
      latest[t.id] = t;
      const g = nodeEls[t.id];
      if (!g) return;
      g.setAttribute("class", `dag-node st-${t.status}${g.classList.contains("selected") ? " selected" : ""}`);
      durEls[t.id].textContent = t.status === "running" ? "đang chạy…" : t.duration_s != null ? fmtDur(t.duration_s) : "";
    });
    edges.forEach((e, i) => {
      const s = status[e.to];
      edgeEls[i].setAttribute("class", `edge edge-${s === "running" ? "flow" : s === "success" || s === "failed" ? "done" : "idle"}`);
    });
  }
  const select = (id) => Object.entries(nodeEls).forEach(([k, g]) => g.classList.toggle("selected", k === id));

  return { el: h("div", { class: "dag-wrap" }, svg), update, select };
}
