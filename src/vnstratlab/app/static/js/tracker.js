// Active-run tracker (top bar, every page) and run toasts (start / finish / fail / cancel).
import { api, fmtClock, h, isActive, isCancelled } from "./util.js";
import { hooks, toast } from "./ui.js";

const IDLE_MS = 3000;
const LIVE_MS = 1000;

export function startTracker(el) {
  const dot = h("span", { class: "dot" });
  const label = h("span", { class: "lbl" }, "Rảnh");
  const prog = h("span", { class: "prog" });
  prog.style.width = "0%";
  el.replaceChildren(dot, label, prog);
  let known = null; // run_id -> status seen on the previous poll
  let active = null;
  let timer = null;

  function paint() {
    if (!active) {
      el.classList.remove("live");
      label.textContent = "Rảnh";
      prog.style.width = "0%";
      el.title = "Không có lần chạy nào đang chạy";
      return;
    }
    const tasks = active.tasks || [];
    const done = tasks.filter((t) => t.status === "success" || t.status === "skipped" || t.status === "failed").length;
    const elapsed = (Date.now() - new Date(active.started_at || active.created_at).getTime()) / 1000;
    el.classList.add("live");
    label.textContent = `${active.label_vi || active.pipeline} · ${Math.min(done + 1, tasks.length)}/${tasks.length} · ${fmtClock(elapsed)}`;
    prog.style.width = `${tasks.length ? (done / tasks.length) * 100 : 0}%`;
    el.title = "Bấm để xem lần chạy đang chạy";
  }

  function announce(run, before) {
    const href = `#/runs/${run.run_id}`;
    const name = run.label_vi || run.pipeline;
    if (isActive(run) && before === undefined) toast(`Bắt đầu: ${name}`, { kind: "run", href, sub: "Bấm để xem tiến trình" });
    else if (isActive(run)) return;
    else if (!(before === undefined || before === "queued" || before === "running")) return;
    else if (run.status === "success") toast(`Hoàn tất: ${name}`, { kind: "ok", href });
    else if (isCancelled(run)) toast(`Đã hủy: ${name}`, { kind: "warn", href });
    else if (run.status === "failed") toast(`Lỗi: ${name}`, { kind: "err", href, sub: run.reason || "" });
  }

  async function poll() {
    const res = await api("/runs?limit=5");
    if (res.ok && res.body) {
      const list = res.body.runs || [];
      if (known !== null) {
        for (const run of [...list].reverse()) {
          const before = known[run.run_id];
          if (before === run.status) continue;
          // a run first seen already finished (very short) still gets its result toast
          announce(run, before);
        }
      }
      known = Object.fromEntries(list.map((r) => [r.run_id, r.status]));
      active = list.find(isActive) || null;
      document.dispatchEvent(new CustomEvent("vn:runs", { detail: list }));
    }
    paint();
    schedule();
  }
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(poll, active ? LIVE_MS : IDLE_MS);
  }
  setInterval(paint, 1000);
  el.addEventListener("click", () => {
    if (active) location.hash = `#/runs/${active.run_id}`;
    else location.hash = "#/runs";
  });
  hooks.activeRunId = () => (active ? active.run_id : null);
  hooks.pokeTracker = () => {
    clearTimeout(timer);
    return poll();
  };
  poll();
  return { get active() { return active; } };
}
