// Shared UI pieces: toasts, hover cards, dialogs, CLI line, switches, empty states.
import { h, mascot } from "./util.js";

/** Filled in by main.js so pages can open the terminal without importing it (no cycles). */
export const hooks = { openTerminal: null, pokeTracker: null };

// ---------- toasts ----------
let toastHost = null;
/** kind: "ok" | "err" | "run" | "warn" | "" ; ``href`` makes the toast clickable. */
export function toast(message, opts = {}) {
  const { kind = "", sub = "", href = null, ms = 4500 } = opts;
  toastHost = toastHost || document.getElementById("toasts");
  const close = () => el.remove();
  const el = h(
    "div",
    {
      class: `toast ${kind}${href ? " clickable" : ""}`,
      role: "status",
      onclick: (e) => {
        if (e.target.closest(".x")) return;
        if (href) location.hash = href;
        close();
      },
    },
    h("div", { class: "t" }, message, sub ? h("small", null, sub) : null),
    h("button", { class: "x", type: "button", "aria-label": "Đóng", onclick: close }, "×")
  );
  toastHost.append(el);
  while (toastHost.children.length > 4) toastHost.firstChild.remove();
  setTimeout(close, ms);
  return el;
}

// ---------- hover cards ----------
let card = null;
export function hideHover() {
  if (card) card.remove();
  card = null;
}
function placeHover(x, y) {
  if (!card) return;
  const r = card.getBoundingClientRect();
  const left = Math.min(Math.max(8, x + 14), window.innerWidth - r.width - 8);
  const top = y + 18 + r.height > window.innerHeight ? y - r.height - 12 : y + 18;
  card.style.left = `${left}px`;
  card.style.top = `${Math.max(8, top)}px`;
}
/** Attach a hover card to ``el``; ``build()`` returns an array of nodes (or null to skip). */
export function hoverCard(el, build) {
  const show = (e) => {
    const nodes = build();
    if (!nodes) return;
    hideHover();
    card = h("div", { class: "hovercard", role: "tooltip" }, nodes);
    document.body.append(card);
    placeHover(e.clientX ?? el.getBoundingClientRect().left, e.clientY ?? el.getBoundingClientRect().bottom);
  };
  el.addEventListener("mouseenter", show);
  el.addEventListener("mousemove", (e) => placeHover(e.clientX, e.clientY));
  el.addEventListener("mouseleave", hideHover);
  el.addEventListener("focus", show);
  el.addEventListener("blur", hideHover);
}
export const hcRow = (k, v) => h("div", { class: "row" }, h("span", null, k), h("span", null, v));

// ---------- dialogs ----------
export function confirmDialog({ title, body, yes = "Đồng ý", no = "Hủy", danger = false }) {
  return new Promise((resolve) => {
    const dialog = h(
      "dialog",
      null,
      h("h2", null, title),
      body instanceof Node ? body : h("p", { class: "muted" }, body),
      h(
        "div",
        { class: "dialog-actions" },
        h("button", { class: "btn ghost", type: "button", onclick: () => dialog.close("no") }, no),
        h("button", { class: `btn${danger ? " danger" : ""}`, type: "button", onclick: () => dialog.close("yes") }, yes)
      )
    );
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "yes");
      dialog.remove();
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

// ---------- clipboard ----------
export async function copyText(text, okMessage = "Đã sao chép") {
  try {
    await navigator.clipboard.writeText(text);
    toast(okMessage, { kind: "ok", ms: 1800 });
  } catch {
    toast("Không sao chép được; hãy chọn và sao chép thủ công", { kind: "warn" });
  }
}

/** dbt-style line: the CLI command equivalent to a UI action, with copy and open-in-terminal. */
export function cliLine(command) {
  if (!command) return null;
  return h(
    "div",
    { class: "cli-line" },
    h("code", null, command),
    h("button", { class: "cli-btn", type: "button", onclick: () => copyText(command, "Đã sao chép lệnh") }, "Sao chép"),
    h("button", { class: "cli-btn", type: "button", onclick: () => hooks.openTerminal && hooks.openTerminal(command) }, "Mở trong terminal")
  );
}

// ---------- small widgets ----------
export function segmented(options, value, onChange, label) {
  const wrap = h("div", { class: "seg", role: "group", "aria-label": label || null });
  const draw = (v) =>
    wrap.replaceChildren(
      ...options.map(([val, text]) =>
        h("button", { type: "button", "aria-pressed": String(val === v), onclick: () => (draw(val), onChange(val)) }, text)
      )
    );
  draw(value);
  return wrap;
}

export function switchEl(checked, onChange, label) {
  const el = h("button", {
    class: "switch",
    type: "button",
    role: "switch",
    "aria-checked": String(checked),
    "aria-label": label || null,
    onclick: () => {
      const next = el.getAttribute("aria-checked") !== "true";
      el.setAttribute("aria-checked", String(next));
      onChange(next, el);
    },
  });
  return el;
}

export function emptyState(title, text, ...actions) {
  return h("div", { class: "empty" }, mascot("mark"), h("b", null, title), h("span", null, text), actions.length ? h("div", { class: "btn-row" }, actions) : null);
}

export function skeleton(n = 3) {
  return h("div", null, Array.from({ length: n }, () => h("div", { class: "skeleton" })));
}

export function pageHead(title, sub, ...actions) {
  return h(
    "div",
    { class: "head" },
    h("div", null, h("h1", null, title), sub ? h("p", { class: "muted small mono" }, sub) : null),
    actions.length ? h("div", { class: "head-actions" }, actions) : null
  );
}

export function table(headers, rows, { numeric = [] } = {}) {
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "tbl" },
      h("thead", null, h("tr", null, headers.map((x, i) => h("th", { class: numeric.includes(i) ? "num" : null }, x)))),
      h("tbody", null, rows.map((r) => h("tr", null, r.map((c, i) => h("td", { class: numeric.includes(i) ? "num" : null }, c)))))
    )
  );
}
