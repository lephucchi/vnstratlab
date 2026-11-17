"use strict";

const root = document.documentElement;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* storage unavailable */ } },
};

// ---------------------------------------------------------------- language
const langBtn = document.getElementById("lang");
function setLang(lang) {
  root.lang = lang;
  langBtn.textContent = lang === "vi" ? "EN" : "VI";
  langBtn.setAttribute("aria-label", lang === "vi" ? "English" : "Tiếng Việt");
  store.set("vnstratlab-lang", lang);
}
setLang(store.get("vnstratlab-lang") || "vi");
langBtn.addEventListener("click", () => { setLang(root.lang === "vi" ? "en" : "vi"); renderStatus(); renderStrategies(); });

// ---------------------------------------------------------------- theme
function isDark() {
  const t = root.dataset.theme;
  return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
}
const themeBtn = document.getElementById("theme");
const syncTheme = () => { themeBtn.setAttribute("aria-pressed", String(isDark())); window.dispatchEvent(new Event("themechange")); };
themeBtn.addEventListener("click", () => {
  root.dataset.theme = isDark() ? "light" : "dark";
  store.set("vnstratlab-theme", root.dataset.theme);
  syncTheme();
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncTheme);
themeBtn.setAttribute("aria-pressed", String(isDark()));

// ---------------------------------------------------------------- mobile menu
const menuBtn = document.getElementById("menu"), mobileNav = document.getElementById("mobile-nav");
menuBtn.addEventListener("click", () => {
  const open = mobileNav.hidden;
  mobileNav.hidden = !open;
  menuBtn.setAttribute("aria-expanded", String(open));
});
mobileNav.addEventListener("click", (e) => {
  if (e.target.closest("a")) { mobileNav.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); }
});

// ---------------------------------------------------------------- background: breathing dot grid
(function background() {
  const canvas = document.getElementById("bg");
  const ctx = canvas.getContext("2d");
  const GAP = 26;
  let w = 0, h = 0, dpr = 1, mx = -1e4, my = -1e4, raf = 0, t0 = performance.now();
  let rgb = "10,10,10"; // cached; refreshed on theme change, not every frame
  const readColor = () => { rgb = getComputedStyle(root).getPropertyValue("--dot").trim() || "10,10,10"; if (reduceMotion) draw(0); };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (reduceMotion) draw(0);
  }
  function draw(t) {
    ctx.clearRect(0, 0, w, h);
    const sy = window.scrollY * 0.15;
    for (let y = -(sy % GAP); y < h + GAP; y += GAP) {
      for (let x = (w % GAP) / 2; x < w; x += GAP) {
        const gy = y + sy;
        const wave = Math.sin(x * 0.012 + t * 0.0006) * Math.cos(gy * 0.014 - t * 0.0005);
        const d = Math.hypot(x - mx, y - my);
        const glow = Math.max(0, 1 - d / 180);
        const a = 0.07 + 0.07 * wave + 0.45 * glow * glow;
        const r = 0.9 + 0.5 * wave + 1.2 * glow;
        ctx.fillStyle = `rgba(${rgb},${Math.max(0.02, a).toFixed(3)})`;
        ctx.beginPath(); ctx.arc(x, y, Math.max(0.4, r), 0, 6.283); ctx.fill();
      }
    }
  }
  function loop(now) { draw(now - t0); raf = requestAnimationFrame(loop); }
  window.addEventListener("resize", resize);
  window.addEventListener("pointermove", (e) => { mx = e.clientX; my = e.clientY; }, { passive: true });
  document.addEventListener("pointerleave", () => { mx = my = -1e4; });
  window.addEventListener("themechange", readColor);
  readColor();
  resize();
  if (!reduceMotion) {
    raf = requestAnimationFrame(loop);
    document.addEventListener("visibilitychange", () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) raf = requestAnimationFrame(loop);
    });
  } else {
    window.addEventListener("scroll", () => draw(0), { passive: true });
  }
})();

// ---------------------------------------------------------------- terminal (real commands, excerpt of real output)
const SCRIPT = [
  ["p", "git clone https://github.com/lephucchi/vnstratlab.git && cd vnstratlab"],
  ["o", "Cloning into 'vnstratlab'... done."],
  ["p", "python -m venv .venv && source .venv/bin/activate"],
  ["p", 'pip install -e ".[dev]"'],
  ["o", "Successfully installed vnstratlab-0.0.1"],
  ["p", "vnstratlab doctor"],
  ["h", "vnstratlab   0.0.1"],
  ["o", "python       3.12 (linux)\nhome         ~/.local/share/vnstratlab\nconfig: OK\n  holidays 2026: complete\n  holidays 2027: partial  WARNING: incomplete, check hose.yaml\nsecrets:\n  data_api_key         not set\n  telegram_bot_token   not set"],
  ["p", "git log --oneline --graph -5"],
  ["y", "* aa76fed feat(config): typed config loader and trading calendar (P1-T02)\n* 6b74990 style(tools): ruff-clean build_status.py\n* 7964b4c ci(pages): single Pages deploy for intro site, docs and PO dashboard\n* 2259e15 docs(engine): engine spec, strategy catalogue, end-to-end flow, ADR-003/004/005\n* 619cf7b chore: scaffold vnstratlab (P1-T01)"],
  ["p", "vnstratlab demo"],
  ["g", "# coming in v0.1 (P1-T32): synthetic data only, never real prices"],
];
const termBody = document.getElementById("term-body");
let termRun = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function playTerminal() {
  const run = ++termRun;
  termBody.replaceChildren();
  const caret = document.createElement("span"); caret.className = "caret";
  for (const [kind, text] of SCRIPT) {
    if (run !== termRun) return;
    const line = document.createElement("div"); line.className = kind;
    termBody.append(line);
    if (kind === "p" && !reduceMotion) {
      line.append(caret);
      for (let i = 1; i <= text.length; i++) {
        if (run !== termRun) return;
        line.firstChild && line.firstChild.nodeType === 3 ? (line.firstChild.nodeValue = text.slice(0, i)) : line.prepend(text.slice(0, i));
        await sleep(14 + Math.random() * 28);
      }
      await sleep(260);
      caret.remove();
    } else if (kind === "p") {
      line.textContent = text;
    } else {
      if (!reduceMotion) await sleep(120);
      // reveal multi-line output line by line
      const parts = text.split("\n");
      for (let i = 0; i < parts.length; i++) {
        if (run !== termRun) return;
        line.append(parts[i] + (i < parts.length - 1 ? "\n" : ""));
        termBody.scrollTop = termBody.scrollHeight;
        if (!reduceMotion) await sleep(55);
      }
      if (!reduceMotion) await sleep(380);
    }
    termBody.scrollTop = termBody.scrollHeight;
  }
  const last = document.createElement("div"); last.className = "p"; last.append(caret);
  termBody.append(last);
}
document.getElementById("term-replay").addEventListener("click", playTerminal);

// ---------------------------------------------------------------- reveal on scroll, graph, terminal start
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    e.target.classList.add("in");
    if (e.target.id === "term") playTerminal();
    io.unobserve(e.target);
  }
}, { threshold: 0.2 });
document.querySelectorAll(".sec-head, .features, .pipe, .funnel, .kpis, .timeline, .install, .mascot-sec")
  .forEach((el) => { el.classList.add("reveal"); io.observe(el); });
io.observe(document.getElementById("term"));

// ---------------------------------------------------------------- strategy tabs
const tabs = document.querySelectorAll('[role="tab"]');
function selectTab(tab, focus = false) {
  tabs.forEach((t) => { const on = t === tab; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
  document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== tab.dataset.tab; });
  if (focus) tab.focus();
}
tabs.forEach((tab, i) => {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (e) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    let next = step ? tabs[(i + step + tabs.length) % tabs.length] : null;
    if (e.key === "Home") next = tabs[0];
    if (e.key === "End") next = tabs[tabs.length - 1];
    if (next) { e.preventDefault(); selectTab(next, true); }
  });
});

// ---------------------------------------------------------------- copy buttons
async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); } catch (_) { return; }
  btn.classList.add("copied");
  setTimeout(() => btn.classList.remove("copied"), 1400);
}
document.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copy(b.dataset.copy, b)));
document.querySelectorAll("[data-copy-from]").forEach((b) => b.addEventListener("click", () => {
  const text = document.getElementById(b.dataset.copyFrom).innerText.split("\n").filter((l) => !l.startsWith("#")).join("\n");
  copy(text, b);
}));

// ---------------------------------------------------------------- measured status (data/status.json from pages.yml)
const T = {
  vi: { tests: "Test pass", cov: "Coverage", ci: "CI develop", cards: "Card hoàn thành", ok: "xanh", fail: "lỗi", running: "đang chạy",
        updated: "Cập nhật", commit: "commit", bench: "Benchmark", value: "Giá trị", nodata: "Chưa có số liệu đo." },
  en: { tests: "Tests passing", cov: "Coverage", ci: "CI develop", cards: "Cards done", ok: "green", fail: "failing", running: "running",
        updated: "Updated", commit: "commit", bench: "Benchmark", value: "Value", nodata: "No measurements yet." },
};
let status;
function kpi(label, value, tone = "") {
  const d = document.createElement("div"); d.className = "kpi";
  const l = document.createElement("div"); l.className = "label"; l.textContent = label;
  const v = document.createElement("div"); v.className = `value ${tone}`; v.textContent = value;
  d.append(l, v); return d;
}
function renderStatus() {
  if (status === undefined) return;
  const t = T[root.lang] || T.vi;
  const s = status;
  const kpis = document.getElementById("kpis");
  const meta = document.getElementById("status-meta");
  const bench = document.getElementById("bench");
  bench.replaceChildren();
  if (!s) {
    kpis.replaceChildren(kpi(t.tests, "—"), kpi(t.cov, "—"), kpi(t.ci, "—"), kpi(t.cards, "—"));
    meta.textContent = t.nodata;
    return;
  }
  const ci = s.last_ci;
  let ciText = "—", ciTone = "";
  if (ci) {
    if (ci.status !== "completed") ciText = t.running;
    else if (ci.conclusion === "success") { ciText = t.ok; ciTone = "ok"; }
    else { ciText = t.fail; ciTone = "bad"; }
  }
  const failed = s.tests ? s.tests.failures + s.tests.errors : 0;
  kpis.replaceChildren(
    kpi(t.tests, s.tests ? `${s.tests.passed}/${s.tests.tests}` : "—", s.tests ? (failed ? "bad" : "ok") : ""),
    kpi(t.cov, s.coverage != null ? `${s.coverage}%` : "—"),
    kpi(t.ci, ciText, ciTone),
    kpi(t.cards, `${s.cards_done}/${s.cards_total}`),
  );
  if (s.benchmarks && s.benchmarks.length) {
    const box = document.createElement("div"); box.className = "bench";
    const table = document.createElement("table");
    const head = document.createElement("tr");
    for (const h of [t.bench, t.value, t.commit]) { const th = document.createElement("th"); th.textContent = h; head.append(th); }
    table.append(head);
    for (const b of s.benchmarks) {
      const tr = document.createElement("tr");
      for (const c of [b.name, `${Number(b.value).toPrecision(4)} ${b.unit}`, b.commit]) { const td = document.createElement("td"); td.textContent = c; tr.append(td); }
      table.append(tr);
    }
    box.append(table); bench.append(box);
  }
  const when = new Date(s.generated_at).toLocaleString(root.lang === "vi" ? "vi-VN" : "en-GB", { timeZone: "Asia/Ho_Chi_Minh", hour12: false });
  meta.textContent = `${t.updated} ${when} · ${t.commit} ${s.commit || "—"}`;
}
fetch("data/status.json", { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : null))
  .then((s) => { status = s; renderStatus(); })
  .catch(() => { status = null; renderStatus(); });

// ---------------------------------------------------------------- strategy cards + detail dialog
const L = () => (root.lang === "en" ? "en" : "vi");
const tr = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v[L()] : v);
const UI = {
  vi: { more: "Xem chi tiết →", idea: "Ý tưởng", rule: "Quy tắc", params: "Tham số đề xuất (chưa đóng băng)", basis: "Cơ sở", risk: "Lưu ý", horizons: "Khung", data: "Dữ liệu", card: "Card", none: "Không có tham số", blocked: "đang tắt",
        h: { short: "ngắn", medium: "trung", long: "dài" } },
  en: { more: "Details →", idea: "Idea", rule: "Rule", params: "Proposed parameters (not frozen)", basis: "Basis", risk: "Note", horizons: "Horizons", data: "Data", card: "Card", none: "No parameters", blocked: "disabled",
        h: { short: "short", medium: "medium", long: "long" } },
};
function node(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

function renderStrategies() {
  const u = UI[L()];
  for (const panel of document.querySelectorAll("[data-panel]")) {
    const h = panel.dataset.panel;
    const grid = node("div", "strat-grid");
    for (const s of window.STRATEGIES.filter((x) => x.horizons.includes(h))) {
      const b = node("button", `strat-card${s.blocked ? " blocked" : ""}`);
      b.type = "button";
      b.dataset.id = s.id;
      const top = node("span", "top");
      top.append(node("span", "sid", s.id), node("span", "sname", tr(s.name)));
      b.append(top, node("span", "sidea", tr(s.idea)), node("span", "smore", s.blocked ? `${u.blocked} · ${u.more}` : u.more));
      b.addEventListener("click", () => openStrategy(s.id));
      grid.append(b);
    }
    panel.replaceChildren(node("p", "hnote", tr(window.HORIZON_NOTES[h])), grid);
  }
}

const dlg = document.getElementById("strat-dlg");
function openStrategy(id) {
  const s = window.STRATEGIES.find((x) => x.id === id);
  const u = UI[L()];
  document.getElementById("dlg-id").textContent = s.id;
  document.getElementById("dlg-title").textContent = tr(s.name);
  const body = document.getElementById("dlg-body");
  const out = [node("h4", null, u.idea), node("p", "lead-idea", tr(s.idea)), node("h4", null, u.rule)];
  const ol = node("ol");
  for (const r of tr(s.rule)) ol.append(node("li", null, r));
  out.push(ol, node("h4", null, u.params));
  const chips = node("div", "chips");
  if (s.params.length) for (const p of s.params) chips.append(node("span", null, p));
  else chips.append(node("span", null, u.none));
  out.push(chips, node("h4", null, u.basis), node("p", null, tr(s.basis)));
  if (s.risk) out.push(node("h4", null, u.risk), node("p", "warn", tr(s.risk)));
  const meta = node("div", "dlg-meta");
  for (const [k, v] of [[u.horizons, s.horizons.map((h) => u.h[h]).join(" · ")], [u.data, s.data], [u.card, s.card]]) {
    const d = node("div"); d.append(node("small", null, k), node("span", null, v)); meta.append(d);
  }
  out.push(meta);
  body.replaceChildren(...out);
  body.scrollTop = 0;
  if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
}
document.getElementById("dlg-close").addEventListener("click", () => dlg.close());
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); }); // click on the backdrop
renderStrategies();
