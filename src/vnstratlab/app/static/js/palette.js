// Command palette (Ctrl/Cmd+K or /) and the keyboard-shortcut overlay (?). Global shortcuts live here too.
import { startPipeline } from "./runs.js";
import { startTour } from "./tour.js";
import { hooks, toast } from "./ui.js";
import { api, h, post, toggleTheme } from "./util.js";

export const ROUTES = [
  ["tong-quan", "Tổng quan", "o"],
  ["huong-dan", "Hướng dẫn", "h"],
  ["runs", "Runs", "r"],
  ["du-lieu", "Dữ liệu", "d"],
  ["ket-qua", "Kết quả", "k"],
  ["chien-luoc", "Chiến lược", "s"],
  ["cau-hinh", "Cấu hình", "c"],
];

const plain = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();
function score(query, text) {
  const q = plain(query);
  const t = plain(text);
  if (!q) return 1;
  const at = t.indexOf(q);
  if (at >= 0) return 100 - at;
  let i = 0;
  for (const ch of t) if (ch === q[i]) i++;
  return i === q.length ? 10 : 0;
}

const SHORTCUTS = [
  ["Ctrl/⌘ + K  hoặc  /", "Mở bảng lệnh"],
  ["Ctrl + `", "Mở/đóng terminal"],
  ["?", "Xem phím tắt"],
  ["t", "Đổi giao diện sáng/tối"],
  ...ROUTES.map(([, label, k]) => [`g ${k}`, `Đi tới ${label}`]),
  ["Tab / ↑ ↓ (terminal)", "Gợi ý lệnh / lịch sử"],
  ["Ctrl + C (terminal)", "Hủy lần chạy đang chạy"],
  ["Esc", "Đóng hộp thoại"],
];

export function showShortcuts() {
  const dialog = h(
    "dialog",
    null,
    h("h2", null, "Phím tắt"),
    h("div", { class: "sc-grid" }, SHORTCUTS.map(([k, d]) => h("div", null, h("span", null, d), h("span", { class: "kbd" }, k)))),
    h("div", { class: "dialog-actions" }, h("button", { class: "btn ghost", type: "button", onclick: () => dialog.close() }, "Đóng"))
  );
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
}

async function buildItems() {
  const items = [];
  const go = (hash) => () => (location.hash = hash);
  ROUTES.forEach(([id, label, k]) => items.push({ group: "Trang", label, hint: `g ${k}`, run: go(`#/${id}`) }));
  items.push(
    { group: "Hành động", label: "Mở terminal", hint: "Ctrl+`", run: () => hooks.openTerminal && hooks.openTerminal() },
    { group: "Hành động", label: "Đổi giao diện sáng/tối", hint: "t", run: toggleTheme },
    { group: "Hành động", label: "Xem phím tắt", hint: "?", run: showShortcuts },
    { group: "Hành động", label: "Tham quan giao diện (Tour)", hint: "", run: () => startTour() }
  );
  const [pipes, runs, data, strat] = await Promise.all([api("/pipelines"), api("/runs?limit=8"), api("/data/status"), api("/strategies")]);
  if (pipes.ok) pipes.body.pipelines.forEach((p) => items.push({ group: "Chạy quy trình", label: `Chạy: ${p.label_vi}`, hint: p.cli || p.id, run: () => startPipeline(p.id) }));
  const act = runs.ok && runs.body.runs.find((r) => r.status === "running" || r.status === "queued");
  if (act) {
    items.push({
      group: "Hành động",
      label: `Hủy lần chạy đang chạy (${act.label_vi || act.pipeline})`,
      hint: "Ctrl+C",
      run: async () => {
        const r = await post(`/runs/${encodeURIComponent(act.run_id)}/cancel`, {});
        toast(r.ok ? "Đã gửi yêu cầu hủy" : r.status === 409 ? "Lần chạy đã xong" : "Không hủy được", { kind: r.ok ? "warn" : "err" });
      },
    });
  }
  if (runs.ok) runs.body.runs.forEach((r) => items.push({ group: "Lần chạy", label: `${r.label_vi || r.pipeline} · ${r.run_id}`, hint: r.status, run: go(`#/runs/${r.run_id}`) }));
  if (data.ok) {
    const seen = new Set();
    data.body.stores.forEach((s) => (s.tickers || []).forEach((t) => !seen.has(t.ticker) && (seen.add(t.ticker), items.push({ group: "Mã cổ phiếu", label: t.ticker, hint: "Dữ liệu", run: () => ((location.hash = "#/du-lieu"), setTimeout(() => document.querySelector(`[data-ticker="${t.ticker}"]`)?.click(), 600)) }))));
  }
  if (strat.ok) strat.body.strategies.forEach((s) => items.push({ group: "Chiến lược", label: `${s.id} · ${s.name_vi}`, hint: s.blocked ? "bị chặn" : "", run: go("#/chien-luoc") }));
  return items;
}

export async function openPalette() {
  if (document.querySelector("dialog.palette")) return;
  const input = h("input", { type: "text", placeholder: "Gõ để tìm trang, lệnh, lần chạy, mã, chiến lược…", "aria-label": "Bảng lệnh", autocomplete: "off", spellcheck: "false" });
  const list = h("ul", { class: "pal-list", role: "listbox" });
  const dialog = h(
    "dialog",
    { class: "palette", "aria-label": "Bảng lệnh" },
    h("div", { class: "pal-input" }, h("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round" }, h("circle", { cx: 11, cy: 11, r: 6.5 }), h("path", { d: "M16 16l4 4" })), input),
    list,
    h("div", { class: "pal-foot" }, h("span", null, "↑↓ chọn"), h("span", null, "Enter chạy"), h("span", null, "Esc đóng"))
  );
  let items = [];
  let shown = [];
  let sel = 0;
  function draw() {
    const q = input.value.trim();
    shown = items.map((it) => ({ it, s: score(q, `${it.label} ${it.group}`) })).filter((x) => x.s > 0).sort((a, b) => (q ? b.s - a.s : 0)).slice(0, 40).map((x) => x.it);
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    const nodes = [];
    let group = null;
    shown.forEach((it, idx) => {
      if (it.group !== group) {
        group = it.group;
        nodes.push(h("li", { class: "pal-group", role: "presentation" }, group));
      }
      nodes.push(h("li", { class: "pal-item", role: "option", "aria-selected": String(idx === sel), onclick: () => choose(idx), onmousemove: () => sel !== idx && ((sel = idx), mark()) }, h("span", null, it.label), it.hint ? h("span", { class: "hint" }, it.hint) : null));
    });
    list.replaceChildren(...(nodes.length ? nodes : [h("li", { class: "pal-group" }, "Không có kết quả")]));
  }
  function mark() {
    [...list.querySelectorAll(".pal-item")].forEach((el, i) => el.setAttribute("aria-selected", String(i === sel)));
    list.querySelectorAll(".pal-item")[sel]?.scrollIntoView({ block: "nearest" });
  }
  function choose(idx) {
    const it = shown[idx];
    if (!it) return;
    dialog.close();
    it.run();
  }
  input.addEventListener("input", () => ((sel = 0), draw()));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") (e.preventDefault(), (sel = Math.min(sel + 1, shown.length - 1)), mark());
    else if (e.key === "ArrowUp") (e.preventDefault(), (sel = Math.max(sel - 1, 0)), mark());
    else if (e.key === "Enter") (e.preventDefault(), choose(sel));
  });
  dialog.addEventListener("click", (e) => e.target === dialog && dialog.close());
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  input.focus();
  items = await buildItems();
  draw();
}

const typing = (e) => /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;

export function installShortcuts(terminal) {
  let g = 0;
  document.addEventListener("keydown", (e) => {
    if (document.querySelector("dialog[open], .tour-pop")) return;
    if (e.key === "`" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      return terminal.toggle();
    }
    if ((e.key === "k" || e.key === "K") && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      return openPalette();
    }
    if (typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "/") {
      e.preventDefault();
      return openPalette();
    }
    if (e.key === "?") return showShortcuts();
    if (e.key === "t") return toggleTheme();
    if (g && Date.now() - g < 1500) {
      const r = ROUTES.find((x) => x[2] === e.key);
      g = 0;
      if (r) location.hash = `#/${r[0]}`;
      return;
    }
    g = e.key === "g" ? Date.now() : 0;
  });
}
