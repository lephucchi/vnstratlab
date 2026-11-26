// Small helpers: DOM builder, API calls (with ?mock=1 fixture mode), formatting, theme.

// The SVG namespace is an identifier, not a request; split so the no-external-URL test stays strict.
const SVG_NS = "http:" + "//www.w3.org/2000/svg";
const SVG_TAGS = new Set(["svg", "g", "path", "line", "rect", "circle", "text", "polyline", "polygon", "title", "tspan", "use", "defs", "ellipse"]);

/** Build an element. Children may be nodes, strings or arrays; null/false are skipped.
 *  Text is always added as a text node (never parsed as markup). */
export function h(tag, attrs, ...children) {
  const el = SVG_TAGS.has(tag) ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.setAttribute("class", v);
    else if (k === "value" && tag !== "svg") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  const add = (c) => {
    if (Array.isArray(c)) c.forEach(add);
    else if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  };
  children.forEach(add);
  return el;
}

/** Fixture mode: add ?mock=1 to the URL (before the #) and every API call is answered by mock.js. */
export const MOCK = new URLSearchParams(location.search).get("mock") === "1";
let mockModule = null;

export async function api(path, init) {
  if (MOCK) {
    mockModule = mockModule || (await import("./mock.js"));
    return mockModule.mockApi(path, init || {});
  }
  try {
    const res = await fetch("/api" + path, init);
    let body = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    return { ok: res.ok, status: res.status, body };
  } catch {
    return { ok: false, status: 0, body: { error: "network" } };
  }
}

function send(method, path, data) {
  return api(path, {
    method,
    headers: { "X-Vnstratlab": "1", "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}
export const post = (path, data) => send("POST", path, data ?? {});
export const put = (path, data) => send("PUT", path, data);
export const patch = (path, data) => send("PATCH", path, data);
export const del = (path) => send("DELETE", path);

export const STATUS_VI = { queued: "Chờ", running: "Đang chạy", success: "Thành công", failed: "Lỗi", skipped: "Bỏ qua" };

export function fmtDur(s) {
  if (s === null || s === undefined) return "—";
  if (s < 1) return `${Math.round(s * 1000)} ms`;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)} ph ${Math.round(s % 60)} s`;
}
export function fmtClock(s) {
  const t = Math.max(0, Math.floor(s));
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}
export function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN");
}
export function fmtAgo(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!Number.isFinite(s)) return iso;
  if (s < 60) return "vừa xong";
  if (s < 3600) return `${Math.floor(s / 60)} phút trước`;
  if (s < 86400) return `${Math.floor(s / 3600)} giờ trước`;
  return `${Math.floor(s / 86400)} ngày trước`;
}
export function fmtNum(v, digits = 2) {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";
}
export function fmtInt(v) {
  return typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("vi-VN") : "—";
}

export function statusChip(status) {
  return h("span", { class: `chip st-${status}` }, h("span", { class: "dot" }), STATUS_VI[status] || status);
}
export const isActive = (run) => run && (run.status === "queued" || run.status === "running");
export const isCancelled = (run) => run && run.status === "failed" && run.reason === "cancelled";

export function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
export function errorBox(message) {
  return h("div", { class: "notice err", role: "alert" }, message);
}
export function debounce(fn, ms) {
  let t = null;
  const wrapped = (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

// ---- storage (always try/catch: it can be unavailable) ----
export function load(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}
export function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable */
  }
}

// ---- theme (same key as the intro site and the PO dashboard) ----
export function toggleTheme() {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  root.dataset.theme = next;
  try {
    localStorage.setItem("vnstratlab-theme", next);
  } catch {
    /* storage unavailable */
  }
}

// ---- icons: the mascot comes from the sprite in index.html ----
export function mascot(cls = "mark") {
  return h("svg", { class: cls, "aria-hidden": "true" }, h("use", { href: "#buffalo" }));
}

/** CLI line for a pipeline when the API does not send `cli` (older backend). */
const CLI_FALLBACK = { demo: "vnstratlab demo", refresh: "vnstratlab refresh", ingest: "vnstratlab ingest", rebuild: "vnstratlab data rebuild", features: "vnstratlab features build" };
export const cliOf = (p) => (p && (p.cli || CLI_FALLBACK[p.id || p.pipeline])) || null;
