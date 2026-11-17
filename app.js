"use strict";

const STATUS_LABEL = {
  "todo": "Chưa làm",
  "in-progress": "Đang làm",
  "in-review": "Đang review",
  "changes-requested": "Cần sửa",
  "blocked": "Bị chặn",
  "done": "Đã xong",
};
const TODO_LIMIT = 8;
const BOARD_COLUMNS = ["todo", "in-progress", "in-review", "blocked", "done"];
const ADR_LABEL = {
  "accepted": ["Đã chấp nhận", "ok"],
  "proposed": ["Chờ quyết", "warn"],
  "partly-accepted": ["Một phần chờ quyết", "warn"],
  "rejected": ["Bác bỏ", "bad"],
  "superseded": ["Thay thế", "info"],
};

const $ = (sel) => document.querySelector(sel);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function chip(text, tone = "") {
  return el("span", { class: `chip ${tone}` }, text);
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false });
}

function runTone(run) {
  if (run.status !== "completed") return ["đang chạy", "info"];
  if (run.conclusion === "success") return ["thành công", "ok"];
  if (run.conclusion === "failure") return ["lỗi", "bad"];
  return [run.conclusion || "—", "warn"];
}

function renderKpis(d) {
  const total = d.cards.length;
  const done = d.counts.done || 0;
  const active = (d.counts["in-progress"] || 0) + (d.counts["in-review"] || 0) + (d.counts["changes-requested"] || 0);
  const tests = d.quality.tests;
  const ci = (d.github.runs || []).find((r) => r.name === "CI" && r.branch === "develop");
  const kpis = [
    ["Card đã xong", `${done}/${total}`, `${Math.round((100 * done) / Math.max(total, 1))}% kế hoạch`],
    ["Đang làm / review", String(active), `${d.counts.blocked || 0} bị chặn`],
    ["Chờ bạn quyết", String(d.waiting_for_owner.length), "ADR + PR"],
    ["CI develop", ci ? runTone(ci)[0] : "—", ci ? `${ci.sha} · ${fmtTime(ci.created_at)}` : "chưa có dữ liệu"],
    ["Test", tests ? `${tests.passed}/${tests.tests}` : "—", tests && tests.failures + tests.errors > 0 ? "có test lỗi" : "trên develop"],
    ["Coverage", d.quality.coverage != null ? `${d.quality.coverage}%` : "—", "ngưỡng 80%"],
    ["Mục [VERIFY]", String(d.verify_items), "luật sàn / lịch nghỉ cần xác nhận"],
  ];
  $("#kpis").replaceChildren(
    ...kpis.map(([label, value, sub]) =>
      el("div", { class: "kpi" }, el("div", { class: "label" }, label), el("div", { class: "value" }, value), el("div", { class: "sub" }, sub))
    )
  );
}

function renderWaiting(d) {
  const items = d.waiting_for_owner;
  if (!items.length) {
    $("#waiting").replaceChildren(el("li", { class: "empty" }, "Không có gì đang chờ."));
    return;
  }
  $("#waiting").replaceChildren(
    ...items.map((w) => {
      const label = w.type === "adr" ? chip("ADR", "warn") : chip("PR", "info");
      const text = w.url ? el("a", { href: w.url }, w.text) : w.text;
      return el("li", {}, label, text);
    })
  );
}

function renderRoadmap(d) {
  const byPhase = new Map();
  for (const c of d.cards) {
    const phase = c.phase || "Khác";
    const ms = c.milestone || (c.release ? `Thêm cho ${c.release}` : "Chưa xếp milestone");
    if (!byPhase.has(phase)) byPhase.set(phase, new Map());
    const m = byPhase.get(phase);
    if (!m.has(ms)) m.set(ms, []);
    m.get(ms).push(c);
  }
  const out = [];
  for (const [phase, milestones] of byPhase) {
    out.push(el("div", { class: "phase-title" }, phase));
    for (const [ms, cards] of milestones) {
      const done = cards.filter((c) => c.status === "done").length;
      const pct = Math.round((100 * done) / cards.length);
      out.push(
        el("div", { class: "ms" },
          el("div", { class: "ms-head" }, el("span", {}, ms), el("span", { class: "muted" }, `${done}/${cards.length}`)),
          el("div", { class: "bar", role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": ms },
            el("span", { style: `width:${pct}%` })
          )
        )
      );
    }
  }
  $("#roadmap").replaceChildren(...out);
}

function renderBoard(d) {
  const phase = $("#phase-filter").value;
  const cards = d.cards.filter((c) => phase === "all" || c.phase === phase);
  const cols = BOARD_COLUMNS.map((status) => {
    const inCol = cards.filter((c) => (status === "in-review" ? ["in-review", "changes-requested"].includes(c.status) : c.status === status));
    return el("div", { class: "col" },
      el("h3", {}, el("span", {}, STATUS_LABEL[status]), el("span", { class: "muted" }, String(inCol.length))),
      ...(status === "todo" && inCol.length > TODO_LIMIT ? inCol.slice(0, TODO_LIMIT) : inCol).map((c) =>
        el("div", { class: "task" },
          el("span", { class: "id" }, c.id), " ",
          c.status === "changes-requested" ? chip("cần sửa", "bad") : null,
          c.branch ? chip(c.branch, "info") : null,
          el("span", { class: "t" }, c.title)
        )
      ),
      status === "todo" && inCol.length > TODO_LIMIT
        ? el("p", { class: "muted small" }, `+ ${inCol.length - TODO_LIMIT} card khác`)
        : null
    );
  });
  $("#board").replaceChildren(...cols);
}

function renderAdrs(d) {
  const repo = d.repository;
  $("#adrs tbody").replaceChildren(
    ...d.adrs.map((a) => {
      const [label, tone] = ADR_LABEL[a.status] || [a.status, ""];
      return el("tr", {},
        el("td", {}, el("a", { href: `https://github.com/${repo}/blob/develop/docs/adr/${a.file}` }, a.title)),
        el("td", {}, chip(label, tone))
      );
    })
  );
}

function renderQuality(d) {
  const q = d.quality;
  const rows = [
    ["Test pass", q.tests ? `${q.tests.passed} / ${q.tests.tests}` : "—"],
    ["Test lỗi", q.tests ? String(q.tests.failures + q.tests.errors) : "—"],
    ["Coverage", q.coverage != null ? `${q.coverage}%` : "—"],
  ];
  const nodes = rows.map(([k, v]) => el("div", { class: "q-row" }, el("span", {}, k), el("span", { class: "v" }, v)));
  if (q.benchmarks && q.benchmarks.length) {
    nodes.push(el("div", { class: "phase-title" }, "Benchmark (mới nhất)"));
    for (const b of q.benchmarks) {
      nodes.push(el("div", { class: "q-row" }, el("span", {}, b.name), el("span", { class: "v" }, `${Number(b.value).toPrecision(4)} ${b.unit}`)));
    }
  } else {
    nodes.push(el("p", { class: "empty small" }, "Chưa có dữ liệu benchmark."));
  }
  $("#quality").replaceChildren(...nodes);
}

function renderPulls(d) {
  const pulls = d.github.pulls || [];
  if (!d.github.available) {
    $("#pulls").replaceChildren(el("li", { class: "empty" }, "Không lấy được dữ liệu GitHub."));
    return;
  }
  if (!pulls.length) {
    $("#pulls").replaceChildren(el("li", { class: "empty" }, "Không có PR đang mở."));
    return;
  }
  $("#pulls").replaceChildren(
    ...pulls.map((p) => el("li", {}, chip(`#${p.number}`, "info"), el("a", { href: p.url }, p.title), el("span", { class: "muted small" }, `${p.head} → ${p.base}`)))
  );
}

function renderRuns(d) {
  const runs = (d.github.runs || []).slice(0, 10);
  if (!runs.length) {
    $("#runs").replaceChildren(el("li", { class: "empty" }, "Chưa có dữ liệu CI."));
    return;
  }
  $("#runs").replaceChildren(
    ...runs.map((r) => {
      const [label, tone] = runTone(r);
      return el("li", {}, chip(label, tone), el("a", { href: r.url }, r.name), el("span", { class: "muted small" }, `${r.branch} · ${r.sha} · ${fmtTime(r.created_at)}`));
    })
  );
}

function renderProgress(d) {
  const rows = [...d.progress].reverse();
  if (!rows.length) {
    $("#progress tbody").replaceChildren(el("tr", {}, el("td", { colspan: "5", class: "empty" }, "Chưa có mục nào.")));
    return;
  }
  $("#progress tbody").replaceChildren(
    ...rows.map((r) => el("tr", {}, el("td", {}, r.date), el("td", {}, r.card), el("td", {}, r.summary), el("td", {}, r.tests), el("td", {}, r.review)))
  );
}

// ---------------------------------------------------------------- data access (encrypted)
// data.enc.json is an AES-256-GCM envelope produced by tools/encrypt_po.py in pages.yml.
// The key is PBKDF2-SHA256(user + "\n" + password, salt, iter); wrong credentials cannot decrypt.
// Both values are NFC-normalised and trimmed, exactly like tools/encrypt_po.py.
// Same set as Python's strip(" \t\r\n"): spaces, tabs, CR and LF at both ends.
const norm = (s) => s.normalize("NFC").replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, "");
const SESSION_KEY = "vnstratlab-po-key";
const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const toB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const session = {
  get() { try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); } catch (_) { return null; } },
  set(v) { try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(v)); } catch (_) { /* unavailable */ } },
  clear() { try { sessionStorage.removeItem(SESSION_KEY); } catch (_) { /* unavailable */ } },
};

async function deriveKey(user, password, env) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(`${norm(user)}\n${norm(password)}`), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: b64(env.salt), iterations: env.iter, hash: "SHA-256" },
    base, { name: "AES-GCM", length: 256 }, true, ["decrypt"]
  );
}
async function decryptWith(key, env) {
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(env.iv) }, key, b64(env.data));
  return JSON.parse(new TextDecoder().decode(plain));
}

const gate = $("#gate"), app = $("#app"), msg = $("#gate-msg"), form = $("#login"), btn = $("#login-btn");
function say(text, err = false) { msg.textContent = text; msg.classList.toggle("err", err); }
function busy(on) {
  btn.disabled = on;
  btn.replaceChildren(...(on ? [el("span", { class: "spin", "aria-hidden": "true" }), "Đang giải mã…"] : ["Đăng nhập"]));
}

async function loadEnvelope() {
  const res = await fetch("data.enc.json", { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const env = await res.json();
  if (env.v !== 1 || env.alg !== "AES-256-GCM" || env.kdf !== "PBKDF2-SHA256" || !(env.iter >= 100000)) {
    throw new Error("định dạng dữ liệu không hỗ trợ");
  }
  return env;
}

function show(data) {
  gate.hidden = true;
  app.hidden = false;
  $("#meta").textContent = `Cập nhật ${fmtTime(data.generated_at)} · commit ${data.commit || "—"}`;
  $("#repo-link").href = `https://github.com/${data.repository}`;
  renderKpis(data);
  renderWaiting(data);
  renderRoadmap(data);
  renderBoard(data);
  renderAdrs(data);
  renderQuality(data);
  renderPulls(data);
  renderRuns(data);
  renderProgress(data);
  $("#phase-filter").onchange = () => renderBoard(data);
}

async function main() {
  if (!window.crypto || !crypto.subtle) {
    say("Trình duyệt không hỗ trợ WebCrypto (cần HTTPS).", true);
    form.querySelectorAll("input, button").forEach((x) => { x.disabled = true; });
    return;
  }
  let env;
  try {
    env = await loadEnvelope();
  } catch (err) {
    say(`Không tải được dữ liệu (${err.message}).`, true);
    return;
  }
  if (!env) {
    say("Dashboard chưa được cấu hình: thiếu secret PO_USERNAME / PO_PASSWORD.", true);
    form.querySelectorAll("input, button").forEach((x) => { x.disabled = true; });
    return;
  }

  // resume the session: the derived key is kept only for this tab and only for this build
  const saved = session.get();
  if (saved && saved.salt === env.salt) {
    try {
      const key = await crypto.subtle.importKey("raw", b64(saved.key), "AES-GCM", false, ["decrypt"]);
      show(await decryptWith(key, env));
      return;
    } catch (_) { session.clear(); }
  }
  $("#user").focus();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const user = norm($("#user").value), pass = norm($("#pass").value);
    if (!user || !pass) { say("Nhập tài khoản và mật khẩu.", true); return; }
    busy(true); say("");
    try {
      const key = await deriveKey(user, pass, env);
      const data = await decryptWith(key, env);
      session.set({ salt: env.salt, key: toB64(await crypto.subtle.exportKey("raw", key)) });
      $("#pass").value = "";
      show(data);
    } catch (_) {
      say("Sai tài khoản hoặc mật khẩu.", true);
      form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
      $("#pass").select();
    } finally {
      busy(false);
    }
  });
}

$("#logout").addEventListener("click", () => {
  session.clear();
  location.reload();
});
$("#theme").addEventListener("click", () => {
  const t = document.documentElement.dataset.theme;
  const dark = t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("vnstratlab-theme", next); } catch (_) { /* unavailable */ }
});

main();
