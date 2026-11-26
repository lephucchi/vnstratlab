// Logs panel: task selector, level filter, search with highlight + next/prev, auto-tail, copy line, download.
import { copyText } from "./ui.js";
import { h } from "./util.js";

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"];
const LINE = /^\d\d:\d\d:\d\d (DEBUG|INFO|WARNING|ERROR|CRITICAL)\b/;
const levelRank = (level) => (level === "CRITICAL" ? 3 : Math.max(LEVELS.indexOf(level), 0));

/** ``tasks``: the run's task list. ``onTask(id)`` is called when the user picks another task. */
export function createLogs(runId, tasks, onTask) {
  const buffers = {}; // task -> [{text, level}]
  const pending = {}; // task -> partial last line
  let current = tasks[0] ? tasks[0].id : null;
  let matchIdx = -1;

  const select = h("select", { "aria-label": "Tác vụ", onchange: () => setTask(select.value, true) }, tasks.map((t) => h("option", { value: t.id }, t.label_vi)));
  const level = h("select", { "aria-label": "Mức log", onchange: redraw }, h("option", { value: "0" }, "Mọi mức"), LEVELS.slice(1).map((l, i) => h("option", { value: String(i + 1) }, `${l} trở lên`)));
  const search = h("input", {
    type: "search",
    placeholder: "Tìm trong log (Enter: kết quả sau)",
    "aria-label": "Tìm trong log",
    oninput: () => ((matchIdx = -1), redraw(), step(1)),
    onkeydown: (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        step(e.shiftKey ? -1 : 1);
      }
    },
  });
  const count = h("span", { class: "count" }, "");
  const only = h("input", { type: "checkbox", onchange: redraw });
  const tail = h("input", { type: "checkbox", checked: true, id: "tail" });
  const pre = h("div", { class: "log", tabindex: 0, role: "log" });
  const q = () => search.value.trim().toLowerCase();

  function highlight(text) {
    const needle = q();
    if (!needle) return [text || " "];
    const out = [];
    const low = text.toLowerCase();
    let from = 0;
    let at;
    while ((at = low.indexOf(needle, from)) !== -1) {
      if (at > from) out.push(text.slice(from, at));
      out.push(h("mark", null, text.slice(at, at + needle.length)));
      from = at + needle.length;
    }
    out.push(text.slice(from) || (out.length ? "" : " "));
    return out;
  }

  function lineEl(entry) {
    const cls = entry.level === "WARNING" ? "warn" : entry.level === "ERROR" || entry.level === "CRITICAL" ? "err" : "";
    return h(
      "div",
      { class: `ln ${cls}` },
      h("span", { class: "tx" }, highlight(entry.text)),
      h("button", { class: "cp", type: "button", "aria-label": "Sao chép dòng này", onclick: () => copyText(entry.text, "Đã sao chép dòng log") }, "chép")
    );
  }

  function visible(entry) {
    if (levelRank(entry.level) < Number(level.value)) return false;
    return !(only.checked && q() && !entry.text.toLowerCase().includes(q()));
  }

  const scroll = () => tail.checked && (pre.scrollTop = pre.scrollHeight);

  function updateCount() {
    const marks = pre.querySelectorAll("mark");
    count.textContent = q() ? (marks.length ? `${matchIdx + 1}/${marks.length}` : "0") : "";
  }

  function step(dir) {
    const marks = [...pre.querySelectorAll("mark")];
    if (!q() || !marks.length) return updateCount();
    matchIdx = (matchIdx + dir + marks.length) % marks.length;
    marks.forEach((m, i) => m.classList.toggle("cur", i === matchIdx));
    tail.checked = false;
    marks[matchIdx].scrollIntoView({ block: "center" });
    updateCount();
  }

  function redraw() {
    const shown = (buffers[current] || []).filter(visible);
    pre.replaceChildren(...(shown.length ? shown.map(lineEl) : [h("div", { class: "ln muted" }, "(chưa có dòng log nào)")]));
    scroll();
    updateCount();
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
    matchIdx = -1;
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
    updateCount();
  }

  const reset = (task) => {
    buffers[task] = [];
    pending[task] = "";
    if (task === current) redraw();
  };
  const flush = (task) => pending[task] && append(task, "\n");

  const el = h(
    "section",
    { class: "card logs" },
    h(
      "div",
      { class: "log-bar" },
      h("div", { class: "log-grp" }, select, level),
      h("div", { class: "log-grp grow" }, h("div", { class: "grow" }, search), h("button", { class: "btn ghost sm", type: "button", "aria-label": "Kết quả trước", onclick: () => step(-1) }, "‹"), count, h("button", { class: "btn ghost sm", type: "button", "aria-label": "Kết quả sau", onclick: () => step(1) }, "›")),
      h("div", { class: "log-grp" }, h("label", { class: "check small" }, only, " Chỉ dòng khớp"), h("label", { class: "check small" }, tail, " Tự cuộn"), h("button", { class: "btn ghost sm", type: "button", onclick: downloadLog }, "Tải log"))
    ),
    pre
  );
  setTask(current, false);
  return { el, append, flush, reset, setTask: (id) => setTask(id, false), get current() { return current; } };
}
