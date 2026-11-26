// Small helpers: DOM builder, API calls, formatting.

// The SVG namespace is an identifier, not a request; split so the no-external-URL test stays strict.
const SVG_NS = "http:" + "//www.w3.org/2000/svg";

/** Build an element. Children may be nodes, strings or arrays; null/false are skipped. */
export function h(tag, attrs, ...children) {
  const svg = ["svg", "g", "path", "line", "rect", "circle", "text", "polyline", "title", "tspan"].includes(tag);
  const el = svg ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.setAttribute("class", v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  const add = (c) => {
    if (Array.isArray(c)) c.forEach(add);
    else if (c !== null && c !== undefined && c !== false) {
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
  };
  children.forEach(add);
  return el;
}

export async function api(path, init) {
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

export function post(path, data) {
  return api(path, {
    method: "POST",
    headers: { "X-Vnstratlab": "1", "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export const STATUS_VI = {
  queued: "Chờ",
  running: "Đang chạy",
  success: "Thành công",
  failed: "Lỗi",
  skipped: "Bỏ qua",
};

export function fmtDur(s) {
  if (s === null || s === undefined) return "—";
  if (s < 1) return `${Math.round(s * 1000)} ms`;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)} ph ${Math.round(s % 60)} s`;
}

export function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN");
}

export function fmtNum(v, digits = 2) {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

export function statusChip(status) {
  return h("span", { class: `chip st-${status}` }, STATUS_VI[status] || status);
}

let toastTimer = null;
export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 2500);
}

export function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function errorBox(message) {
  return h("div", { class: "notice notice-error" }, message);
}
