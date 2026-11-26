// Logs panel: task selector, level filter, search, auto-tail, download.
import { h } from "./util.js";

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"];
const LINE = /^\d\d:\d\d:\d\d (DEBUG|INFO|WARNING|ERROR|CRITICAL)\b/;

function levelRank(level) {
  if (level === "CRITICAL") return 3;
  return Math.max(LEVELS.indexOf(level), 0);
}

/** ``tasks``: the run's task list. ``onTask(id)`` is called when the user picks another task. */
export function createLogs(runId, tasks, onTask) {
  const buffers = {}; // task -> [{text, level}]
  const pending = {}; // task -> partial last line
  let current = tasks[0] ? tasks[0].id : null;

  const select = h(
    "select",
    { "aria-label": "Tác vụ", onchange: () => setTask(select.value, true) },
    tasks.map((t) => h("option", { value: t.id }, t.label_vi))
  );
  const level = h(
    "select",
    { "aria-label": "Mức log", onchange: redraw },
    h("option", { value: "0" }, "Mọi mức"),
    LEVELS.slice(1).map((l, i) => h("option", { value: String(i + 1) }, `${l} trở lên`))
  );
  const search = h("input", { type: "search", placeholder: "Tìm trong log", "aria-label": "Tìm trong log", oninput: redraw });
  const tail = h("input", { type: "checkbox", checked: true, id: "tail" });
  const pre = h("pre", { class: "log", tabindex: 0 });
  const download = h("button", { class: "btn btn-small", type: "button", onclick: downloadLog }, "Tải log");

  function lineEl(entry) {
    const cls = entry.level === "WARNING" ? "warn" : entry.level === "ERROR" || entry.level === "CRITICAL" ? "err" : "";
    return h("div", { class: `ln ${cls}` }, entry.text || " ");
  }

  function visible(entry) {
    const q = search.value.trim().toLowerCase();
    return levelRank(entry.level) >= Number(level.value) && (!q || entry.text.toLowerCase().includes(q));
  }

  function scroll() {
    if (tail.checked) pre.scrollTop = pre.scrollHeight;
  }

  function redraw() {
    const entries = buffers[current] || [];
    const shown = entries.filter(visible);
    pre.replaceChildren(...(shown.length ? shown.map(lineEl) : [h("div", { class: "ln muted" }, "(chưa có dòng log nào)")]));
    scroll();
  }

  function downloadLog() {
    const text = (buffers[current] || []).map((e) => e.text).join("\n") + "\n";
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = h("a", { href: url, download: `${runId}-${current}.log` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function setTask(id, fromUser) {
    if (!id) return;
    current = id;
    select.value = id;
    redraw();
    if (fromUser && onTask) onTask(id);
  }

  /** Add log text for a task (whole chunks; a partial last line is kept until completed). */
  function append(task, text) {
    const buf = (buffers[task] = buffers[task] || []);
    const parts = ((pending[task] || "") + text).split("\n");
    pending[task] = parts.pop();
    const fresh = [];
    for (const line of parts) {
      const m = LINE.exec(line);
      const prev = buf.length ? buf[buf.length - 1].level : "INFO";
      const entry = { text: line, level: m ? m[1] : prev };
      buf.push(entry);
      fresh.push(entry);
    }
    if (task !== current) return;
    const rows = fresh.filter(visible);
    if (!rows.length) return;
    if (pre.querySelector(".muted")) pre.replaceChildren();
    pre.append(...rows.map(lineEl));
    scroll();
  }

  function reset(task) {
    buffers[task] = [];
    pending[task] = "";
    if (task === current) redraw();
  }

  function flush(task) {
    if (pending[task]) {
      append(task, "\n");
    }
  }

  const el = h(
    "section",
    { class: "card logs" },
    h("div", { class: "log-bar" }, select, level, search, h("label", { class: "check" }, tail, " Tự cuộn"), download),
    pre
  );
  setTask(current, false);
  return { el, append, flush, reset, setTask: (id) => setTask(id, false), get current() { return current; } };
}
