// Built-in terminal: type `vnstratlab ...` commands; each becomes a run (pipeline "cli").
// Only vnstratlab subcommands are accepted by the API. Output is read from the run's log.
import { api, h, load, post, save } from "./util.js";
import { hooks } from "./ui.js";

const HISTORY_KEY = "vnstratlab-term-history";
const OPEN_KEY = "vnstratlab-term-open";
const HEIGHT_KEY = "vnstratlab-term-h";
const MAX_LINES = 1200;
const PROMPT = "vnstratlab ›";
const LOCAL = [
  { path: ["help"], help: "Liệt kê lệnh, hoặc `help <lệnh>` để xem một lệnh.", options: [], allowed: true, local: true },
  { path: ["clear"], help: "Xóa màn hình terminal.", options: [], allowed: true, local: true },
];

export function createTerminal(root, isMock = false) {
  let commands = null;
  let history = load(HISTORY_KEY, []);
  let hIndex = -1;
  let draft = "";
  let pending = null; // {command} while waiting for y/n on source terms
  let attached = null; // {runId, timer}
  let lastRunId = null;

  const out = h("div", { class: "term-out", role: "log", "aria-live": "off" });
  const input = h("input", { class: "term-input", type: "text", spellcheck: "false", autocomplete: "off", autocapitalize: "off", "aria-label": "Dòng lệnh vnstratlab", placeholder: "gõ lệnh, Tab để gợi ý, help để xem danh sách" });
  const hint = h("div", { class: "term-hint" });
  const grip = h("div", { class: "term-grip", role: "separator", "aria-orientation": "horizontal", "aria-label": "Kéo để đổi chiều cao", tabindex: 0 });
  const head = h(
    "div",
    { class: "term-head" },
    h("span", { class: "term-title" }, "Terminal"),
    h("span", { class: "term-sub" }, "chỉ lệnh vnstratlab · không phải shell"),
    h("span", { class: "grow" }),
    h("button", { class: "cli-btn", type: "button", onclick: () => clear() }, "Xóa"),
    h("button", { class: "cli-btn", type: "button", "aria-label": "Đóng terminal", onclick: () => setOpen(false) }, "Đóng (Ctrl+`)")
  );
  root.append(grip, head, out, h("div", { class: "term-line" }, h("span", { class: "term-prompt" }, PROMPT), input), hint);

  // ---------- panel ----------
  function setHeight(px) {
    const v = Math.min(Math.max(140, px), Math.round(window.innerHeight * 0.7));
    document.documentElement.style.setProperty("--term-h", `${v}px`);
    return v;
  }
  setHeight(load(HEIGHT_KEY, 260));
  grip.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    grip.setPointerCapture(e.pointerId);
    const move = (ev) => setHeight(window.innerHeight - ev.clientY);
    const up = () => {
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
      save(HEIGHT_KEY, parseInt(getComputedStyle(document.documentElement).getPropertyValue("--term-h"), 10));
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  });
  grip.addEventListener("keydown", (e) => {
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--term-h"), 10) || 260;
    if (e.key === "ArrowUp") save(HEIGHT_KEY, setHeight(cur + 30));
    if (e.key === "ArrowDown") save(HEIGHT_KEY, setHeight(cur - 30));
  });

  function isOpen() {
    return !root.hidden;
  }
  function setOpen(open) {
    root.hidden = !open;
    document.body.classList.toggle("term-open", open);
    save(OPEN_KEY, open);
    document.getElementById("term-toggle")?.setAttribute("aria-pressed", String(open));
    if (open) {
      ensureCommands();
      if (!out.children.length) welcome();
      setTimeout(() => input.focus(), 0);
    }
  }

  // ---------- output ----------
  function line(text, cls = "") {
    const el = h("div", { class: `tl ${cls}` }, text);
    out.append(el);
    while (out.children.length > MAX_LINES) out.firstChild.remove();
    out.scrollTop = out.scrollHeight;
    return el;
  }
  function logLine(text) {
    const m = /^\d\d:\d\d:\d\d (DEBUG|INFO|WARNING|ERROR|CRITICAL)\b/.exec(text);
    line(text, m && m[1] === "WARNING" ? "warn" : m && (m[1] === "ERROR" || m[1] === "CRITICAL") ? "err" : "");
  }
  function clear() {
    out.replaceChildren();
  }
  function welcome() {
    line("vnstratlab terminal. Gõ `help` để xem lệnh, Tab để gợi ý, ↑/↓ để xem lịch sử, Ctrl+C để hủy lần chạy.", "dim");
    line("Mỗi lệnh chạy thành một lần chạy (run) và hiện ở trang Runs. Chỉ khuyến nghị — không đặt lệnh.", "dim");
  }

  // ---------- commands / completion ----------
  async function ensureCommands() {
    if (commands) return commands;
    const res = await api("/cli/commands");
    commands = res.ok && res.body ? res.body.commands : [];
    if (!res.ok) line("Chưa tải được danh sách lệnh từ API (gợi ý Tab tạm tắt).", "dim");
    return commands;
  }
  const all = () => [...(commands || []), ...LOCAL];
  const strip = (s) => s.replace(/^\s*vnstratlab(\s+|$)/, "");

  function context(value) {
    const body = strip(value);
    const endsSpace = /\s$/.test(value);
    const parts = body.split(/\s+/).filter(Boolean);
    const partial = endsSpace || !parts.length ? "" : parts[parts.length - 1];
    const done = endsSpace || !parts.length ? parts : parts.slice(0, -1);
    return { done, partial };
  }
  function candidates(value) {
    const { done, partial } = context(value);
    const cmds = all();
    const exact = cmds.find((c) => c.path.length === done.filter((d) => !d.startsWith("-")).length && c.path.every((p, i) => p === done[i]));
    const out2 = new Map();
    // next path segment(s)
    const k = done.length;
    if (!done.some((d) => d.startsWith("-"))) {
      cmds.filter((c) => c.path.length > k && c.path.slice(0, k).every((p, i) => p === done[i])).forEach((c) => out2.set(c.path[k], { text: c.path[k], help: c.path.length === k + 1 ? c.help : "nhóm lệnh", cmd: c }));
    }
    if (exact && (partial.startsWith("-") || out2.size === 0)) {
      exact.options.forEach((o) => out2.set(o.name, { text: o.name, help: o.help + (o.choices ? ` (${o.choices.join("|")})` : ""), opt: o }));
    }
    return { list: [...out2.values()].filter((c) => c.text.startsWith(partial)), partial, exact };
  }
  function commonPrefix(list) {
    return list.reduce((a, b) => {
      let i = 0;
      while (i < a.length && a[i] === b[i]) i++;
      return a.slice(0, i);
    });
  }
  function complete() {
    const { list, partial } = candidates(input.value);
    if (!list.length) return;
    const names = list.map((c) => c.text);
    const common = commonPrefix(names);
    const base = input.value.slice(0, input.value.length - partial.length);
    if (names.length === 1) input.value = `${base}${names[0]} `;
    else {
      input.value = base + common;
      line(`${PROMPT} ${input.value}`, "cmd");
      line(list.map((c) => c.text).join("   "), "dim");
    }
    showHint();
  }
  function showHint() {
    const v = input.value;
    if (!v.trim()) return void (hint.textContent = "");
    const { list, partial, exact } = candidates(v);
    const one = list.find((c) => c.text === partial) || (list.length === 1 ? list[0] : null);
    if (one) hint.textContent = `${one.text}: ${one.help}`;
    else if (exact && !partial) hint.textContent = `${exact.path.join(" ")}: ${exact.help}${exact.allowed ? "" : " — không chạy được ở đây"}`;
    else if (list.length) hint.textContent = list.slice(0, 6).map((c) => c.text).join("  ") + (list.length > 6 ? " …" : "");
    else hint.textContent = "";
  }

  // ---------- running ----------
  function detach() {
    if (attached) clearInterval(attached.timer);
    attached = null;
  }
  function attach(runId) {
    detach();
    lastRunId = runId;
    let offset = 0;
    let busy = false;
    const tick = async () => {
      if (busy) return;
      busy = true;
      const lg = await api(`/runs/${encodeURIComponent(runId)}/tasks/cli/log?offset=${offset}`);
      if (lg.ok && lg.body) {
        offset = lg.body.offset;
        lg.body.text.split("\n").filter((l, i, a) => l !== "" || i < a.length - 1).forEach(logLine);
      }
      const run = await api(`/runs/${encodeURIComponent(runId)}`);
      busy = false;
      if (!run.ok || !attached || attached.runId !== runId) return;
      if (run.body.status === "success" || run.body.status === "failed") {
        const lg2 = await api(`/runs/${encodeURIComponent(runId)}/tasks/cli/log?offset=${offset}`);
        if (lg2.ok && lg2.body.text) lg2.body.text.split("\n").filter(Boolean).forEach(logLine);
        detach();
        const code = run.body.tasks[0] && run.body.tasks[0].summary ? run.body.tasks[0].summary.exit_code : null;
        if (run.body.reason === "cancelled") line("Đã hủy (^C). Tác vụ hiện tại kết thúc rồi dừng.", "warn");
        else line(`[exit ${code ?? (run.body.status === "success" ? 0 : 1)}]  ${run.body.status === "success" ? "xong" : "lỗi"} · `, run.body.status === "success" ? "ok" : "err").append(h("a", { href: `#/runs/${runId}` }, "xem run"));
        hooks.pokeTracker && hooks.pokeTracker();
      }
    };
    attached = { runId, timer: setInterval(tick, 450) };
    tick();
  }

  async function submit(raw) {
    const text = raw.trim();
    line(`${PROMPT} ${raw}`, "cmd");
    if (!text) return;
    if (history[history.length - 1] !== text) history.push(text);
    history = history.slice(-100);
    save(HISTORY_KEY, history);
    hIndex = -1;
    if (pending) {
      const p = pending;
      pending = null;
      if (/^(y|yes|c|có)$/i.test(text)) return send(p.command, true);
      return line("Đã hủy, chưa chấp nhận điều khoản.", "dim");
    }
    const bare = strip(text).trim();
    if (bare === "clear") return clear();
    if (bare === "help" || bare.startsWith("help ")) return help(bare.slice(4).trim());
    return send(text, false);
  }

  async function help(topic) {
    await ensureCommands();
    if (!topic) {
      line("Lệnh có thể dùng (Tab để hoàn tất; `help <lệnh>` để xem tùy chọn):");
      all().forEach((c) => line(`  ${c.path.join(" ").padEnd(16)} ${c.help}${c.allowed ? "" : "  [không chạy được ở đây]"}`, c.allowed ? "" : "dim"));
      line("Ctrl+C hủy lần chạy · Ctrl+` đóng/mở · ↑/↓ lịch sử · `clear` xóa màn hình.", "dim");
      return;
    }
    const parts = strip(topic).split(/\s+/);
    const c = all().find((x) => x.path.join(" ") === parts.join(" "));
    if (!c) return line(`Không có lệnh “${topic}”.`, "err");
    line(`${c.path.join(" ")}: ${c.help}`);
    if (!c.allowed) line(`Không chạy được ở đây: ${c.reason_vi || ""}`, "warn");
    c.options.forEach((o) => line(`  ${o.name.padEnd(22)} ${o.help}${o.choices ? ` (${o.choices.join("|")})` : ""}${o.required ? " [bắt buộc]" : ""}`));
  }

  async function send(command, acceptTerms) {
    const res = await post("/cli", acceptTerms ? { command, accept_terms: true } : { command });
    const b = res.body || {};
    if (res.status === 202) return attach(b.run_id);
    if (res.status === 409 && b.error === "terms_required") {
      line(`Điều khoản nguồn dữ liệu (${b.source}):`, "warn");
      String(b.notice || "").split("\n").forEach((l) => line(`  ${l}`, "dim"));
      line("Bạn đồng ý và muốn chạy tiếp? Gõ y rồi Enter (hoặc n để hủy).", "warn");
      pending = { command };
      return;
    }
    if (res.status === 409 && b.error === "busy") {
      line("Đang có lần chạy khác. Hãy chờ nó xong hoặc bấm Ctrl+C để hủy. ", "warn").append(h("a", { href: `#/runs/${b.active_run_id}` }, "xem lần chạy"));
      return;
    }
    if (b.error === "not_allowed") return line(`Không cho phép: ${b.reason_vi || b.message || ""}`, "err");
    if (b.error === "unknown_command") {
      line(`${b.message || "Lệnh không hợp lệ."}`, "err");
      (b.suggestions || []).forEach((s) => {
        const el = line(`  gợi ý: ${s}`, "sugg");
        el.addEventListener("click", () => {
          input.value = s;
          input.focus();
        });
      });
      return;
    }
    line(`Không chạy được (mã ${res.status}${b.error ? `: ${b.error}` : ""}).`, "err");
  }

  async function cancel() {
    const id = (attached && attached.runId) || hooks.activeRunId?.();
    if (!id) return false;
    line("^C", "dim");
    const res = await post(`/runs/${encodeURIComponent(id)}/cancel`, {});
    if (!res.ok) line("Không hủy được (lần chạy đã xong?).", "warn");
    return true;
  }

  input.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const v = input.value;
      input.value = "";
      hint.textContent = "";
      await submit(v);
    } else if (e.key === "Tab") {
      e.preventDefault();
      await ensureCommands();
      complete();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!history.length) return;
      if (hIndex === -1) draft = input.value;
      hIndex = Math.min(hIndex + 1, history.length - 1);
      input.value = history[history.length - 1 - hIndex];
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (hIndex === -1) return;
      hIndex -= 1;
      input.value = hIndex === -1 ? draft : history[history.length - 1 - hIndex];
    } else if (e.key === "c" && e.ctrlKey && !window.getSelection().toString()) {
      e.preventDefault();
      if (!(await cancel())) {
        line(`${PROMPT} ${input.value}^C`, "dim");
        input.value = "";
        pending = null;
      }
    } else if (e.key === "l" && e.ctrlKey) {
      e.preventDefault();
      clear();
    } else if (e.key === "Escape") {
      input.blur();
    }
  });
  input.addEventListener("input", showHint);
  root.addEventListener("click", (e) => {
    if (!window.getSelection().toString() && !e.target.closest("a,button")) input.focus();
  });

  const api2 = {
    isOpen,
    toggle: () => setOpen(!isOpen()),
    open: (command) => {
      setOpen(true);
      if (command !== undefined) {
        input.value = command;
        showHint();
      }
      setTimeout(() => input.focus(), 0);
    },
    cancel,
    get lastRunId() { return lastRunId; },
  };
  if (load(OPEN_KEY, false) && !isMock) setOpen(true);
  return api2;
}
