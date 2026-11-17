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
  store.set("vnstratlab-lang", lang);
}
setLang(store.get("vnstratlab-lang") || "vi");
langBtn.addEventListener("click", () => { setLang(root.lang === "vi" ? "en" : "vi"); renderStatus(); });

// ---------------------------------------------------------------- theme
function isDark() {
  const t = root.dataset.theme;
  return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
}
document.getElementById("theme").addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  root.dataset.theme = next;
  store.set("vnstratlab-theme", next);
});

// ---------------------------------------------------------------- background: breathing dot grid
(function background() {
  const canvas = document.getElementById("bg");
  const ctx = canvas.getContext("2d");
  const GAP = 26;
  let w = 0, h = 0, dpr = 1, mx = -1e4, my = -1e4, raf = 0, t0 = performance.now();

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (reduceMotion) draw(0);
  }
  function draw(t) {
    const rgb = getComputedStyle(root).getPropertyValue("--dot").trim() || "10,10,10";
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

// ---------------------------------------------------------------- terminal (real commands, real output)
const SCRIPT = [
  ["p", "git clone https://github.com/lephucchi/vnstratlab.git && cd vnstratlab"],
  ["o", "Cloning into 'vnstratlab'... done."],
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
document.querySelectorAll(".sec-head, .features, .pipe, .graph-wrap, .gate-grid, .kpis, .timeline, .install, .mascot-sec")
  .forEach((el) => { el.classList.add("reveal"); io.observe(el); });
io.observe(document.getElementById("graph"));
io.observe(document.getElementById("term"));

// ---------------------------------------------------------------- strategy tabs
const tabs = document.querySelectorAll('[role="tab"]');
tabs.forEach((tab) => tab.addEventListener("click", () => {
  tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
  document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== tab.dataset.tab; });
}));

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
