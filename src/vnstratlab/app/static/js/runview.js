// Run page: header (with the CLI command), Cancel / Rerun, DAG and logs in a resizable split.
import { createDag } from "./dag.js";
import { createLogs } from "./logs.js";
import { cliLine, confirmDialog, hooks, toast } from "./ui.js";
import { MOCK, api, cliOf, errorBox, fmtDur, fmtTime, h, isActive, isCancelled, post, statusChip } from "./util.js";

const POLL_MS = 1500;

function taskDetail(task) {
  if (!task) return null;
  const s = task.summary;
  const summary = s == null ? null : typeof s === "string" ? s : Object.entries(s).map(([k, v]) => `${k}: ${v}`).join(" · ");
  return h(
    "div",
    { class: "task-detail" },
    h("strong", null, task.label_vi),
    statusChip(task.status),
    h("span", { class: "muted" }, fmtDur(task.duration_s)),
    summary ? h("span", { class: "muted mono small" }, summary) : null,
    task.error ? h("div", { class: "err" }, task.error) : null
  );
}

function makeSplit(left, right) {
  const gutter = h("div", { class: "gutter", role: "separator", "aria-orientation": "vertical", "aria-label": "Kéo để đổi kích thước", tabindex: 0 });
  const el = h("div", { class: "split" }, h("div", { class: "pane" }, left), gutter, h("div", { class: "pane" }, right));
  const set = (pct) => el.style.setProperty("--split", `${Math.min(75, Math.max(20, pct))}%`);
  gutter.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    gutter.setPointerCapture(e.pointerId);
    gutter.classList.add("drag");
    const move = (ev) => {
      const r = el.getBoundingClientRect();
      set(((ev.clientX - r.left) / r.width) * 100);
    };
    const up = () => {
      gutter.classList.remove("drag");
      gutter.removeEventListener("pointermove", move);
      gutter.removeEventListener("pointerup", up);
    };
    gutter.addEventListener("pointermove", move);
    gutter.addEventListener("pointerup", up);
  });
  gutter.addEventListener("keydown", (e) => {
    const cur = parseFloat(el.style.getPropertyValue("--split")) || 42;
    if (e.key === "ArrowLeft") set(cur - 4);
    if (e.key === "ArrowRight") set(cur + 4);
  });
  return el;
}

export async function renderRun(root, runId) {
  const first = await api(`/runs/${encodeURIComponent(runId)}`);
  if (!first.ok) {
    root.append(h("div", { class: "head" }, h("h1", null, "Runs")), errorBox(`Không tìm thấy lần chạy ${runId}.`), h("a", { href: "#/runs" }, "Về danh sách"));
    return;
  }
  let run = first.body;
  let userPicked = false;
  let source = null;
  let poller = null;
  let closed = false;
  const offsets = {};

  const head = h("div", { class: "head" });
  const cliHolder = h("div");
  const detail = h("div");
  const dag = createDag(run.tasks, (id) => {
    userPicked = true;
    logs.setTask(id);
    dag.select(id);
    fetchHistory(id);
    drawDetail();
  });
  const logs = createLogs(runId, run.tasks, (id) => {
    userPicked = true;
    dag.select(id);
    fetchHistory(id);
    drawDetail();
  });
  const live = () => isActive(run);

  function pickDefault() {
    const t = run.tasks.find((x) => x.status === "running") || run.tasks.find((x) => x.status === "failed") || run.tasks[run.tasks.length - 1];
    return t ? t.id : null;
  }

  async function cancel() {
    const res = await post(`/runs/${encodeURIComponent(runId)}/cancel`, {});
    if (res.status === 202) toast("Đã gửi yêu cầu hủy", { kind: "warn", sub: "Tác vụ hiện tại sẽ kết thúc, các tác vụ còn lại bị bỏ qua" });
    else if (res.status === 409) toast("Không hủy được: lần chạy đã xong", { kind: "warn" });
    else toast(`Không hủy được (mã ${res.status})`, { kind: "err" });
    hooks.pokeTracker && hooks.pokeTracker();
  }
  async function rerun() {
    let res = await post(`/runs/${encodeURIComponent(runId)}/rerun`, {});
    if (res.status === 404 && run.pipeline !== "cli") res = await post("/runs", { pipeline: run.pipeline, accept_terms: false });
    const b = res.body || {};
    if (res.status === 202) {
      toast("Đã chạy lại", { kind: "run" });
      hooks.pokeTracker && hooks.pokeTracker();
      location.hash = `#/runs/${b.run_id}`;
    } else if (res.status === 409 && b.error === "not_active") toast("Lần chạy này còn đang chạy, chưa thể chạy lại", { kind: "warn" });
    else if (res.status === 422 && b.error === "not_rerunnable") toast("Quy trình này không chạy lại được", { kind: "warn", sub: "Hãy chạy mới từ trang Runs" });
    else if (res.status === 409 && b.error === "busy") toast("Đang có một lần chạy khác", { kind: "warn", href: `#/runs/${b.active_run_id}` });
    else if (res.status === 409 && b.error === "terms_required") {
      const ok = await confirmDialog({ title: "Điều khoản nguồn dữ liệu", yes: "Tôi đồng ý, chạy lại", body: h("pre", { class: "notice-text" }, b.notice || "") });
      if (ok) {
        const r2 = await post("/runs", { pipeline: run.pipeline, accept_terms: true });
        if (r2.status === 202) location.hash = `#/runs/${r2.body.run_id}`;
      }
    } else toast(`Không chạy lại được (mã ${res.status})`, { kind: "err" });
  }

  function drawHead() {
    const cmd = run.cli || (run.pipeline === "cli" && run.tasks[0] && run.tasks[0].summary && run.tasks[0].summary.command) || cliOf({ id: run.pipeline });
    head.replaceChildren(
      h(
        "div",
        null,
        h("h1", null, run.label_vi || run.pipeline),
        h("div", { class: "run-meta" }, statusChip(run.status), h("span", { class: "mono" }, run.run_id), h("span", null, `Bắt đầu: ${fmtTime(run.started_at || run.created_at)}`), h("span", null, `Thời gian: ${fmtDur(run.duration_s)}`), run.reason ? h("span", null, `Lý do: ${isCancelled(run) ? "đã hủy" : run.reason}`) : null)
      ),
      h(
        "div",
        { class: "head-actions" },
        live() ? h("button", { class: "btn danger", type: "button", onclick: cancel }, "Hủy lần chạy") : null,
        !live() ? h("button", { class: "btn ghost", type: "button", onclick: rerun }, "Chạy lại") : null,
        run.pipeline === "demo" && run.status === "success" ? h("a", { class: "btn", href: `#/ket-qua/${runId}` }, "Xem kết quả") : null
      )
    );
    cliHolder.replaceChildren(cliLine(cmd) || "");
  }
  const drawDetail = () => detail.replaceChildren(taskDetail(run.tasks.find((t) => t.id === logs.current)) || "");

  function apply(next) {
    run = next;
    dag.update(run.tasks);
    drawHead();
    drawDetail();
  }
  async function refresh() {
    const res = await api(`/runs/${encodeURIComponent(runId)}`);
    if (res.ok && !closed) apply(res.body);
  }

  async function fetchHistory(task) {
    if (source) return; // SSE supplies the log of a live run
    const res = await api(`/runs/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(task)}/log?offset=${offsets[task] || 0}`);
    if (!res.ok || closed) return;
    offsets[task] = res.body.offset;
    logs.append(task, res.body.text);
    if (res.body.status !== "running") logs.flush(task);
  }
  function startPolling() {
    poller = setInterval(async () => {
      await refresh();
      if (!userPicked) {
        const running = run.tasks.find((t) => t.status === "running");
        if (running && running.id !== logs.current) {
          logs.setTask(running.id);
          dag.select(running.id);
        }
      }
      for (const t of run.tasks) if (t.status !== "queued" && t.status !== "skipped") await fetchHistory(t.id);
      if (!live()) stopLive();
    }, POLL_MS);
  }
  function stopLive() {
    if (source) source.close();
    source = null;
    if (poller) clearInterval(poller);
    poller = null;
  }
  function startLive() {
    if (MOCK || !("EventSource" in window)) return startPolling();
    source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
    source.addEventListener("task", (e) => {
      const { task, status } = JSON.parse(e.data);
      if (status === "running" && !userPicked) {
        logs.setTask(task);
        dag.select(task);
      }
      refresh();
    });
    source.addEventListener("log", (e) => {
      const { task, text } = JSON.parse(e.data);
      logs.append(task, text);
    });
    source.addEventListener("end", async () => {
      stopLive();
      run.tasks.forEach((t) => logs.flush(t.id));
      await refresh();
    });
    source.onerror = () => {
      if (closed || !source) return;
      stopLive();
      run.tasks.forEach((t) => logs.reset(t.id));
      startPolling();
    };
  }

  root.append(h("div", { class: "crumb" }, h("a", { href: "#/runs" }, "‹ Tất cả lần chạy")), head, cliHolder, detail, makeSplit(dag.el, logs.el));
  apply(run);
  const initial = pickDefault();
  logs.setTask(initial);
  dag.select(initial);
  drawDetail();
  if (live()) {
    startLive();
    if (poller) fetchHistory(initial);
  } else await fetchHistory(initial);

  return () => {
    closed = true;
    stopLive();
  };
}
