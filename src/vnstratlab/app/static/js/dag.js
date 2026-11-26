// Task DAG as inline SVG: simple layered left-to-right layout.
import { STATUS_VI, fmtDur, h } from "./util.js";

const W = 150;
const H = 46;
const GAP_X = 56;
const GAP_Y = 26;
const PAD = 12;

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
  if (label.length <= 17) return [label];
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

/** Draw the DAG. Returns {el, update(tasks)}; ``onSelect(taskId)`` fires on node click. */
export function createDag(tasks, onSelect) {
  const level = layers(tasks);
  const cols = {};
  tasks.forEach((t) => (cols[level[t.id]] = [...(cols[level[t.id]] || []), t.id]));
  const nCols = Math.max(...Object.keys(cols).map(Number)) + 1;
  const nRows = Math.max(...Object.values(cols).map((c) => c.length));
  const width = PAD * 2 + nCols * W + (nCols - 1) * GAP_X;
  const height = PAD * 2 + nRows * (H + 16) + (nRows - 1) * GAP_Y;
  const pos = {};
  for (const [c, ids] of Object.entries(cols)) {
    const colH = ids.length * (H + 16) + (ids.length - 1) * GAP_Y;
    ids.forEach((id, i) => {
      pos[id] = {
        x: PAD + Number(c) * (W + GAP_X),
        y: PAD + (height - PAD * 2 - colH) / 2 + i * (H + 16 + GAP_Y),
      };
    });
  }

  const edges = [];
  const edgeEls = [];
  tasks.forEach((t) =>
    t.upstream.forEach((u) => {
      if (!pos[u]) return;
      const a = pos[u];
      const b = pos[t.id];
      const x1 = a.x + W;
      const y1 = a.y + H / 2;
      const x2 = b.x;
      const y2 = b.y + H / 2;
      const mx = (x1 + x2) / 2;
      const el = h("path", { class: "edge", d: `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2 - 6} ${y2}` });
      edges.push({ to: t.id, from: u });
      edgeEls.push(el);
    })
  );

  const nodeEls = {};
  const durEls = {};
  const nodes = tasks.map((t) => {
    const lines = wrap(t.label_vi);
    const rect = h("rect", { class: "node-rect", width: W, height: H, rx: 8 });
    const text = h(
      "text",
      { class: "node-label", x: W / 2, "text-anchor": "middle" },
      lines.map((ln, i) => {
        const span = h("tspan", { x: W / 2, y: lines.length === 1 ? H / 2 + 4 : H / 2 - 4 + i * 14 });
        span.textContent = ln;
        return span;
      })
    );
    const dur = h("text", { class: "node-dur", x: W / 2, y: H + 13, "text-anchor": "middle" }, "");
    const title = h("title", null, t.label_vi);
    const g = h(
      "g",
      {
        class: "dag-node st-queued",
        transform: `translate(${pos[t.id].x} ${pos[t.id].y})`,
        tabindex: 0,
        role: "button",
        onclick: () => onSelect && onSelect(t.id),
        onkeydown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect && onSelect(t.id);
          }
        },
      },
      title,
      rect,
      text,
      dur
    );
    nodeEls[t.id] = g;
    durEls[t.id] = dur;
    return g;
  });

  const svg = h(
    "svg",
    { class: "dag", viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": "Sơ đồ tác vụ" },
    h("g", null, edgeEls),
    h("g", null, nodes)
  );

  function update(current) {
    const status = {};
    current.forEach((t) => {
      status[t.id] = t.status;
      const g = nodeEls[t.id];
      if (!g) return;
      g.setAttribute("class", `dag-node st-${t.status}${g.classList.contains("selected") ? " selected" : ""}`);
      g.querySelector("title").textContent = `${t.label_vi}: ${STATUS_VI[t.status] || t.status}`;
      durEls[t.id].textContent = t.status === "running" ? "đang chạy…" : t.duration_s != null ? fmtDur(t.duration_s) : "";
    });
    edges.forEach((e, i) => {
      const s = status[e.to];
      const state = s === "running" ? "flow" : s === "success" || s === "failed" ? "done" : "idle";
      edgeEls[i].setAttribute("class", `edge edge-${state}`);
    });
  }

  function select(id) {
    Object.entries(nodeEls).forEach(([k, g]) => g.classList.toggle("selected", k === id));
  }

  return { el: h("div", { class: "dag-wrap" }, svg), update, select };
}
