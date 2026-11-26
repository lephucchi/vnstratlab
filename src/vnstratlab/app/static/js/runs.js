// Page 2: Runs. Pipeline buttons, grid of recent runs, run view (DAG, header, logs).
import { createDag } from "./dag.js";
import { createLogs } from "./logs.js";
import { STATUS_VI, api, errorBox, fmtDur, fmtTime, h, post, statusChip } from "./util.js";

const GRID_RUNS = 20;
const GRID_REFRESH_MS = 3000;
const POLL_MS = 1500;

// ---------- starting a pipeline (shared with the guide page) ----------

function showBanner(...content) {
  const view = document.getElementById("view");
  view.querySelector(".banner")?.remove();
  view.prepend(h("div", { class: "notice banner", role: "alert" }, content));
}

function confirmTerms(info) {
  return new Promise((resolve) => {
    const dialog = h(
      "dialog",
      { class: "dialog" },
      h("h2", null, "Điều khoản nguồn dữ liệu"),
      h("p", { class: "muted" }, `Nguồn: ${info.source}`),
      h("pre", { class: "notice-text" }, info.notice),
      h(
        "div",
        { class: "dialog-actions" },
        h("button", { class: "btn", type: "button", onclick: () => dialog.close("no") }, "Hủy"),
        h("button", { class: "btn btn-primary", type: "button", onclick: () => dialog.close("yes") }, "Tôi đồng ý, bắt đầu chạy")
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

/** Start a pipeline; on success go to its run page. Returns the run id or null. */
export async function startPipeline(id, acceptTerms = false) {
  const res = await post("/runs", { pipeline: id, accept_terms: acceptTerms });
  const body = res.body || {};
  if (res.status === 202) {
    location.hash = `#/runs/${body.run_id}`;
    return body.run_id;
  }
  if (res.status === 409 && body.error === "terms_required") {
    return (await confirmTerms(body)) ? startPipeline(id, true) : null;
  }
  if (res.status === 409 && body.error === "busy") {
    showBanner("Đang có một lần chạy khác. Hãy chờ nó xong. ", h("a", { href: `#/runs/${body.active_run_id}` }, "Xem lần chạy đang chạy"));
  } else if (res.status === 422) {
    const detail = body.problems ? body.problems.join("; ") : body.message || "";
    showBanner(`Không bắt đầu được (${body.error === "config_invalid" ? "cấu hình chưa hợp lệ" : "lỗi nguồn dữ liệu"}). ${detail}`);
  } else {
    showBanner(`Không bắt đầu được (mã ${res.status}${body.error ? `: ${body.error}` : ""}).`);
  }
  return null;
}

// ---------- grid ----------

function pipelineBar(pipelines) {
  return h(
    "div",
    { class: "pipe-buttons" },
    pipelines.map((p) =>
      h(
        "button",
        {
          class: "btn",
          type: "button",
          title: p.needs_source_terms ? "Dùng dữ liệu thật; cần xác nhận điều khoản nguồn" : "",
          onclick: (e) => {
            e.currentTarget.disabled = true;
            startPipeline(p.id).finally(() => (e.currentTarget.disabled = false));
          },
        },
        `Chạy: ${p.label_vi}`
      )
    )
  );
}

function gridTable(runs, taskOrder) {
  const cols = runs.slice(0, GRID_RUNS).reverse(); // newest on the right
  if (!cols.length) return h("p", { class: "muted" }, "Chưa có lần chạy nào. Hãy bấm một nút ở trên hoặc “Chạy demo ngay” ở trang Hướng dẫn.");
  const rows = [...taskOrder];
  cols.forEach((r) => r.tasks.forEach((t) => !rows.includes(t.id) && rows.push(t.id)));
  const labels = {};
  cols.forEach((r) => r.tasks.forEach((t) => (labels[t.id] = t.label_vi)));
  return h(
    "div",
    { class: "grid-scroll" },
    h(
      "table",
      { class: "grid" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", null, "Tác vụ"),
          cols.map((r) =>
            h(
              "th",
              { class: "col-head", title: `${r.label_vi} — ${fmtTime(r.created_at)}` },
              h("a", { href: `#/runs/${r.run_id}` }, h("span", { class: `dot st-${r.status}` }), h("span", { class: "col-label" }, r.pipeline))
            )
          )
        )
      ),
      h(
        "tbody",
        null,
        rows.map((id) =>
          h(
            "tr",
            null,
            h("th", { scope: "row", title: id }, labels[id] || id),
            cols.map((r) => {
              const t = r.tasks.find((x) => x.id === id);
              if (!t) return h("td", null, h("span", { class: "cell empty" }));
              return h(
                "td",
                null,
                h("a", { href: `#/runs/${r.run_id}`, class: `cell st-${t.status}`, title: `${labels[id] || id}: ${STATUS_VI[t.status]} (${fmtDur(t.duration_s)})` })
              );
            })
          )
        )
      )
    ),
    legend()
  );
}

function legend() {
  return h(
    "div",
    { class: "legend" },
    ["queued", "running", "success", "failed", "skipped"].map((s) => h("span", null, h("span", { class: `cell st-${s}` }), STATUS_VI[s]))
  );
}

export async function renderGrid(root) {
  root.append(h("h1", null, "Runs"));
  const pipes = await api("/pipelines");
  if (!pipes.ok) {
    root.append(errorBox("Không tải được danh sách quy trình."));
    return;
  }
  const list = pipes.body.pipelines;
  const order = [];
  list.forEach((p) => p.tasks.forEach((t) => !order.includes(t.id) && order.push(t.id)));
  const holder = h("div");
  root.append(pipelineBar(list), holder);
  const load = async () => {
    const res = await api(`/runs?limit=${GRID_RUNS}`);
    if (!res.ok) return holder.replaceChildren(errorBox("Không tải được lịch sử lần chạy."));
    holder.replaceChildren(gridTable(res.body.runs, order));
  };
  await load();
  const timer = setInterval(() => !document.hidden && load(), GRID_REFRESH_MS);
  return () => clearInterval(timer);
}

// ---------- run view ----------

function taskDetail(task) {
  if (!task) return null;
  const summary = task.summary == null ? null : typeof task.summary === "string" ? task.summary : Object.entries(task.summary).map(([k, v]) => `${k}: ${v}`).join(", ");
  return h(
    "div",
    { class: "task-detail" },
    h("strong", null, task.label_vi),
    " ",
    statusChip(task.status),
    h("span", { class: "muted" }, ` ${fmtDur(task.duration_s)}`),
    summary ? h("div", { class: "muted" }, summary) : null,
    task.error ? h("div", { class: "notice notice-error" }, task.error) : null
  );
}

export async function renderRun(root, runId) {
  const first = await api(`/runs/${encodeURIComponent(runId)}`);
  if (!first.ok) {
    root.append(h("h1", null, "Runs"), errorBox(`Không tìm thấy lần chạy ${runId}.`), h("a", { href: "#/runs" }, "Về danh sách"));
    return;
  }
  let run = first.body;
  let userPicked = false;
  let source = null;
  let poller = null;
  let closed = false;
  const offsets = {};

  const head = h("div", { class: "run-head" });
  const resultBtn = h("div");
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

  const isLive = () => run.status === "queued" || run.status === "running";

  function pickDefault() {
    const t = run.tasks.find((x) => x.status === "running") || run.tasks.find((x) => x.status === "failed") || run.tasks[run.tasks.length - 1];
    return t ? t.id : null;
  }

  function drawHead() {
    head.replaceChildren(
      h("h1", null, run.label_vi || run.pipeline),
      h(
        "div",
        { class: "run-meta" },
        statusChip(run.status),
        h("span", null, `Quy trình: ${run.pipeline}`),
        h("span", null, `Bắt đầu: ${fmtTime(run.started_at || run.created_at)}`),
        h("span", null, `Thời gian: ${fmtDur(run.duration_s)}`),
        run.reason ? h("span", { class: "reason" }, `Lý do: ${run.reason}`) : null
      )
    );
    resultBtn.replaceChildren(
      run.pipeline === "demo" && run.status === "success" ? h("a", { class: "btn btn-primary", href: `#/ket-qua/${runId}` }, "Xem kết quả") : null
    );
  }

  function drawDetail() {
    detail.replaceChildren(taskDetail(run.tasks.find((t) => t.id === logs.current)));
  }

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
    // Finished runs (or the polling fallback): read the stored log; SSE supplies it for live runs.
    if (source) return;
    const res = await api(`/runs/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(task)}/log?offset=${offsets[task] || 0}`);
    if (!res.ok || closed) return;
    offsets[task] = res.body.offset;
    logs.append(task, res.body.text);
    if (res.body.status !== "running") logs.flush(task);
  }

  function startPolling() {
    poller = setInterval(async () => {
      await refresh();
      for (const t of run.tasks) if (t.status !== "queued" && t.status !== "skipped") await fetchHistory(t.id);
      if (!isLive()) stopLive();
    }, POLL_MS);
  }

  function stopLive() {
    if (source) source.close();
    source = null;
    if (poller) clearInterval(poller);
    poller = null;
  }

  function startLive() {
    if (!("EventSource" in window)) return startPolling();
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
      // SSE failed: fall back to polling (offsets start from what we have: nothing, so re-read).
      if (closed || !source) return;
      stopLive();
      run.tasks.forEach((t) => logs.reset(t.id));
      startPolling();
    };
  }

  root.append(
    h("p", null, h("a", { href: "#/runs" }, "‹ Tất cả lần chạy")),
    head,
    resultBtn,
    dag.el,
    detail,
    logs.el
  );
  apply(run);
  const initial = pickDefault();
  logs.setTask(initial);
  dag.select(initial);
  drawDetail();
  if (isLive()) startLive();
  else await fetchHistory(initial);

  return () => {
    closed = true;
    stopLive();
  };
}
