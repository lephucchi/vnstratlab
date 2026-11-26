// Runs page: start a pipeline (with its CLI line), filters, grid with hover cards, compare two runs.
import { cliLine, confirmDialog, emptyState, hcRow, hooks, hoverCard, pageHead, segmented, toast } from "./ui.js";
import { STATUS_VI, api, cliOf, errorBox, fmtDur, fmtTime, h, post } from "./util.js";

const GRID_RUNS = 24;
const GRID_REFRESH_MS = 3000;

// ---------- starting a pipeline (shared by Overview, Guide, palette) ----------

function termsDialog(info) {
  return confirmDialog({
    title: "Điều khoản nguồn dữ liệu",
    yes: "Tôi đồng ý, bắt đầu chạy",
    body: h("div", null, h("p", { class: "muted" }, `Nguồn: ${info.source}`), h("pre", { class: "notice-text" }, info.notice)),
  });
}

function showBanner(text, link) {
  const view = document.getElementById("view");
  view.querySelector(".banner")?.remove();
  view.prepend(h("div", { class: "notice warn banner", role: "alert" }, text, link ? [" ", link] : null));
}

/** Start a pipeline; on success go to its run page. Returns the run id or null. */
export async function startPipeline(id, acceptTerms = false) {
  const res = await post("/runs", { pipeline: id, accept_terms: acceptTerms });
  const body = res.body || {};
  if (res.status === 202) {
    hooks.pokeTracker && hooks.pokeTracker();
    location.hash = `#/runs/${body.run_id}`;
    return body.run_id;
  }
  if (res.status === 409 && body.error === "terms_required") return (await termsDialog(body)) ? startPipeline(id, true) : null;
  if (res.status === 409 && body.error === "busy") {
    toast("Đang có một lần chạy khác", { kind: "warn", href: `#/runs/${body.active_run_id}`, sub: "Bấm để xem lần chạy đang chạy" });
    showBanner("Đang có một lần chạy khác. Hãy chờ nó xong. ", h("a", { href: `#/runs/${body.active_run_id}` }, "Xem lần chạy đang chạy"));
  } else if (res.status === 422) {
    showBanner(`Không bắt đầu được (${body.error === "config_invalid" ? "cấu hình chưa hợp lệ" : "lỗi nguồn dữ liệu"}). ${body.problems ? body.problems.join("; ") : body.message || ""}`);
  } else showBanner(`Không bắt đầu được (mã ${res.status}${body.error ? `: ${body.error}` : ""}).`);
  return null;
}

export function pipelineButton(p, { label, ghost = false, small = false } = {}) {
  const btn = h("button", { class: `btn${ghost ? " ghost" : ""}${small ? " sm" : ""}`, type: "button", title: p.needs_source_terms ? "Dùng dữ liệu thật; cần xác nhận điều khoản nguồn" : null }, label || `Chạy: ${p.label_vi}`);
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    await startPipeline(p.id);
    btn.disabled = false;
  });
  return btn;
}

function pipelineCard(p) {
  return h(
    "div",
    { class: "card hover pcard" },
    h("div", { class: "pc-top" }, h("b", null, p.label_vi), p.needs_source_terms ? h("span", { class: "chip dashed" }, "dữ liệu thật") : h("span", { class: "chip soft" }, "offline")),
    h("div", { class: "muted small" }, `${p.tasks.length} tác vụ: ${p.tasks.map((t) => t.label_vi).join(" → ")}`),
    h("div", { class: "pc-act" }, pipelineButton(p, { label: "Chạy" })),
    cliLine(cliOf(p))
  );
}

// ---------- grid ----------

function cellCard(r, t, label) {
  const first = t.error ? String(t.error).split("\n")[0] : null;
  return [
    h("b", null, label),
    hcRow("Trạng thái", STATUS_VI[t.status] || t.status),
    hcRow("Thời gian", fmtDur(t.duration_s)),
    hcRow("Lần chạy", r.pipeline),
    hcRow("Bắt đầu", fmtTime(r.started_at || r.created_at)),
    first ? h("div", { class: "err" }, first) : null,
  ];
}

function gridTable(runs, taskOrder) {
  const cols = runs.slice(0, GRID_RUNS).reverse(); // newest on the right
  if (!cols.length) return h("p", { class: "muted" }, "Không có lần chạy nào khớp bộ lọc.");
  const rows = [...taskOrder];
  cols.forEach((r) => r.tasks.forEach((t) => !rows.includes(t.id) && rows.push(t.id)));
  const labels = {};
  cols.forEach((r) => r.tasks.forEach((t) => (labels[t.id] = t.label_vi)));
  const table = h(
    "table",
    { class: "grid" },
    h(
      "thead",
      null,
      h(
        "tr",
        null,
        h("th", null, ""),
        cols.map((r) => {
          const a = h("a", { href: `#/runs/${r.run_id}` }, h("span", { class: `dot st-${r.status}` }), h("span", null, r.pipeline === "cli" ? "cli" : r.pipeline));
          hoverCard(a, () => [h("b", null, r.label_vi), hcRow("Trạng thái", STATUS_VI[r.status]), hcRow("Thời gian", fmtDur(r.duration_s)), hcRow("Bắt đầu", fmtTime(r.created_at)), r.reason ? hcRow("Lý do", r.reason) : null]);
          return h("th", { class: "col-head" }, a);
        })
      )
    ),
    h(
      "tbody",
      null,
      rows.map((id) =>
        h(
          "tr",
          null,
          h("th", { scope: "row" }, labels[id] || id),
          cols.map((r) => {
            const t = r.tasks.find((x) => x.id === id);
            if (!t) return h("td", null, h("span", { class: "cell none" }));
            const a = h("a", { href: `#/runs/${r.run_id}`, class: `cell st-${t.status}`, "aria-label": `${labels[id]}: ${STATUS_VI[t.status]}` });
            hoverCard(a, () => cellCard(r, t, labels[id] || id));
            return h("td", null, a);
          })
        )
      )
    )
  );
  return h(
    "div",
    null,
    h("div", { class: "grid-scroll" }, table),
    h("div", { class: "legend" }, ["queued", "running", "success", "failed", "skipped"].map((s) => h("span", null, h("span", { class: `cell st-${s}` }), STATUS_VI[s])))
  );
}

// ---------- compare ----------

function compareCard(runs) {
  const holder = h("div", { class: "bars" });
  const opt = (r) => h("option", { value: r.run_id }, `${r.pipeline} · ${fmtTime(r.created_at)}`);
  const a = h("select", { "aria-label": "Lần chạy A", onchange: draw }, runs.map(opt));
  const b = h("select", { "aria-label": "Lần chạy B", onchange: draw }, runs.map(opt));
  if (runs.length > 1) b.selectedIndex = 1;
  function draw() {
    const ra = runs.find((r) => r.run_id === a.value);
    const rb = runs.find((r) => r.run_id === b.value);
    const ids = [...new Set([...ra.tasks, ...rb.tasks].map((t) => t.id))];
    const get = (r, id) => (r.tasks.find((t) => t.id === id) || {}).duration_s;
    const max = Math.max(0.1, ...ids.flatMap((id) => [get(ra, id) || 0, get(rb, id) || 0]));
    const label = (r, id) => (r.tasks.find((t) => t.id === id) || { label_vi: id }).label_vi;
    holder.replaceChildren(
      ...ids.flatMap((id) => [
        h("span", null, label(ra, id) === id ? label(rb, id) : label(ra, id)),
        h(
          "div",
          { class: "bar" },
          h("i", { style: `width:${((get(ra, id) || 0) / max) * 100}%` }),
          h("i", { class: "b", style: `width:${((get(rb, id) || 0) / max) * 100}%` }),
          h("em", null, `A ${fmtDur(get(ra, id))} · B ${fmtDur(get(rb, id))}`)
        ),
      ])
    );
  }
  if (!runs.length) return null;
  draw();
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "So sánh thời gian hai lần chạy"), h("div", { class: "btn-row" }, h("span", { class: "small muted" }, "A (thanh đậm)"), a, h("span", { class: "small muted" }, "B (thanh nhạt)"), b)),
    holder
  );
}

export async function renderGrid(root) {
  root.append(pageHead("Runs", "Chạy quy trình, xem lịch sử và so sánh các lần chạy"));
  const pipes = await api("/pipelines");
  if (!pipes.ok) {
    root.append(errorBox("Không tải được danh sách quy trình."));
    return;
  }
  const list = pipes.body.pipelines;
  const order = [];
  list.forEach((p) => p.tasks.forEach((t) => !order.includes(t.id) && order.push(t.id)));
  const state = { q: "", pipeline: "", status: "" };
  const gridHolder = h("div");
  const compareHolder = h("div");
  let all = [];

  const filtered = () =>
    all.filter((r) => (!state.pipeline || r.pipeline === state.pipeline) && (!state.status || r.status === state.status) && (!state.q || `${r.run_id} ${r.label_vi} ${r.pipeline}`.toLowerCase().includes(state.q)));
  function draw() {
    const runs = filtered();
    gridHolder.replaceChildren(
      all.length ? gridTable(runs, order) : emptyState("Chưa có lần chạy nào", "Bấm “Chạy” ở một quy trình phía trên, hoặc mở terminal bên dưới.", pipelineButton(list[0], { label: "Chạy demo" }))
    );
  }
  const pipeSel = h("select", { "aria-label": "Lọc theo quy trình", onchange: () => ((state.pipeline = pipeSel.value), draw()) }, h("option", { value: "" }, "Mọi quy trình"), [...list.map((p) => p.id), "cli"].map((id) => h("option", { value: id }, id)));
  const search = h("input", { type: "search", placeholder: "Tìm lần chạy…", "aria-label": "Tìm lần chạy", oninput: () => ((state.q = search.value.trim().toLowerCase()), draw()) });
  const seg = segmented([["", "Tất cả"], ["success", "Thành công"], ["failed", "Lỗi"], ["running", "Đang chạy"]], "", (v) => ((state.status = v), draw()), "Lọc theo trạng thái");

  root.append(
    h("div", { class: "pcards" }, list.map(pipelineCard)),
    h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Lịch sử (lần chạy mới nhất ở bên phải)")), h("div", { class: "toolbar" }, h("div", { class: "grow" }, search), pipeSel, seg), gridHolder),
    compareHolder
  );
  const load = async () => {
    const res = await api(`/runs?limit=${GRID_RUNS}`);
    if (!res.ok) return gridHolder.replaceChildren(errorBox("Không tải được lịch sử lần chạy."));
    all = res.body.runs;
    draw();
  };
  await load();
  const done = all.filter((r) => r.status !== "running" && r.status !== "queued");
  const cmp = compareCard(done);
  if (cmp) compareHolder.append(cmp);
  const timer = setInterval(() => !document.hidden && load(), GRID_REFRESH_MS);
  return () => clearInterval(timer);
}

