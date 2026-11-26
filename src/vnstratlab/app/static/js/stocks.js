// Cổ phiếu: pick a ticker, run the analysis (live progress), read numbers, signals and the recommendation;
// compare up to four tickers side by side. Recommend-only: nothing here places or routes an order.
import { lineChart, toMs } from "./charts.js";
import { HORIZON_LABEL, HORIZONS, dataLabel } from "./recs.js";
import { actionBadge, renderAnalysis } from "./stock-view.js";
import { cliLine, confirmDialog, emptyState, hooks, pageHead, segmented, toast } from "./ui.js";
import { STATUS_VI, api, errorBox, fmtClock, fmtPct, fmtVnd, fmtVndShort, h, isActive, load, post, save, statusChip } from "./util.js";

const RECENT_KEY = "vn-stock-recent";
const MAX_COMPARE = 4;
const POLL_MS = 800;
// Monochrome series: luminance + dash pattern (colour stays reserved for status).
const LOOKS = [{ stroke: "var(--fg)" }, { stroke: "var(--fg-2)", dash: "7 3" }, { stroke: "var(--muted)" }, { stroke: "var(--fg)", dash: "2 3" }];

const plain = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();
const changeText = (v) => (v === null || v === undefined ? "—" : `${v > 0 ? "▲" : v < 0 ? "▼" : ""} ${fmtPct(Math.abs(v), 1)}`);

/** Compare payload: the contract says "price and recommendation blocks side by side"; accept a list or a map. */
function compareItems(body) {
  const raw = body && (body.tickers || body.items || body.stocks || body.by_ticker);
  if (Array.isArray(raw)) return raw.map((x) => ({ ticker: x.ticker, price: x.price || {}, recommendation: x.recommendation || {} }));
  if (raw && typeof raw === "object") return Object.entries(raw).map(([ticker, x]) => ({ ticker, price: x.price || {}, recommendation: x.recommendation || {} }));
  return [];
}

// ---------- picker ----------
function createPicker(stocks, { onSingle, onToggle, isOn, mode }) {
  const state = { q: "" };
  const list = h("div", { class: "tk-grid stk-list", role: "listbox", "aria-label": "Danh sách mã" });
  const recent = h("div", { class: "recent" });
  const input = h("input", { type: "search", placeholder: "Tìm mã hoặc tên (VD: VCB, Techcombank)…", "aria-label": "Tìm mã cổ phiếu", autocomplete: "off", spellcheck: "false" });
  const shown = () => stocks.filter((s) => !state.q || plain(`${s.ticker} ${s.name || ""}`).includes(plain(state.q)));

  function pick(t) {
    if (mode() === "compare") onToggle(t);
    else onSingle(t);
    drawList();
  }
  function drawList() {
    const items = shown();
    list.replaceChildren(
      ...(items.length
        ? items.map((s) => {
            const on = isOn(s.ticker);
            const b = h(
              "button",
              { class: "tk", type: "button", role: "option", "aria-selected": String(on), "aria-pressed": String(on), "data-ticker": s.ticker, onclick: () => pick(s.ticker) },
              h("div", { class: "t" }, h("span", null, s.ticker), h("span", { class: "mono small" }, fmtVnd(s.last_close))),
              h("div", { class: "m" }, h("span", { class: "nm" }, s.name || s.group || ""), h("span", { class: "mono" }, changeText(s.change_1d))),
              s.signal_ok === false ? h("div", { class: "m" }, "thiếu tín hiệu") : null
            );
            return b;
          })
        : [h("p", { class: "muted small" }, "Không có mã nào khớp.")])
    );
  }
  function drawRecent() {
    const rec = load(RECENT_KEY, []).filter((t) => stocks.some((s) => s.ticker === t));
    recent.replaceChildren(...(rec.length ? [h("span", { class: "muted small" }, "Gần đây:"), ...rec.map((t) => h("button", { class: "chip btn-chip", type: "button", onclick: () => pick(t) }, t))] : []));
  }
  input.addEventListener("input", () => ((state.q = input.value.trim()), drawList()));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const exact = stocks.find((s) => s.ticker === input.value.trim().toUpperCase());
      const first = exact || shown()[0];
      if (first) (e.preventDefault(), pick(first.ticker));
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      list.querySelector("button")?.focus();
    }
  });
  list.addEventListener("keydown", (e) => {
    const btns = [...list.querySelectorAll("button")];
    const i = btns.indexOf(document.activeElement);
    if (i < 0) return;
    const next = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: btns.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    if (next < 0) input.focus();
    else btns[Math.min(next, btns.length - 1)].focus();
  });
  drawList();
  drawRecent();
  return { input, list, recent, redraw: () => (drawList(), drawRecent()) };
}

// ---------- run progress ----------
function runCard(ticker, cli) {
  const steps = h("ol", { class: "steps" });
  const label = h("span", { class: "muted small mono" });
  const status = h("span");
  const title = h("h2", null, `Đang phân tích ${ticker}`);
  const holder = h("div");
  const actions = h("div", { class: "btn-row" });
  const card = h("section", { class: "card stk-run", "aria-live": "polite" }, h("div", { class: "card-head" }, title, status), steps, label, actions, holder, cliLine(cli));
  function update(run, onCancel) {
    const tasks = run.tasks || [];
    const done = tasks.filter((t) => ["success", "failed", "skipped"].includes(t.status)).length;
    const elapsed = (Date.now() - new Date(run.started_at || run.created_at).getTime()) / 1000;
    status.replaceChildren(statusChip(run.status));
    steps.replaceChildren(
      ...tasks.map((t, i) => h("li", { class: `step st-${t.status}` }, h("span", { class: `dot st-${t.status}` }), h("span", { class: "sl" }, `${i + 1}. ${t.label_vi}`), h("span", { class: "muted small mono" }, STATUS_VI[t.status] || t.status)))
    );
    label.textContent = `Tác vụ ${Math.min(done + 1, tasks.length)}/${tasks.length} · ${fmtClock(elapsed)}`;
    actions.replaceChildren(
      h("a", { class: "btn ghost sm", href: `#/runs/${run.run_id}` }, "Xem log và sơ đồ"),
      isActive(run) ? h("button", { class: "btn danger sm", type: "button", onclick: onCancel }, "Hủy") : null
    );
  }
  return { el: card, update, setTitle: (t) => (title.textContent = t), setBody: (n) => holder.replaceChildren(n || "") };
}

// ---------- compare ----------
async function renderCompare(holder, tickers, token) {
  holder.replaceChildren(h("p", { class: "muted" }, "Đang tải so sánh…"));
  const res = await api(`/stocks/compare?tickers=${tickers.map(encodeURIComponent).join(",")}`);
  if (token.stale) return;
  if (!res.ok) return holder.replaceChildren(errorBox(res.status === 404 ? "Máy chủ chưa có /api/stocks/compare." : "Không tải được so sánh."));
  const items = compareItems(res.body);
  const label = dataLabel(res.body);
  // normalised price chart (= 100 at the start of the window) from the existing local prices endpoint
  const series = await Promise.all(items.map((it) => api(`/data/prices/${encodeURIComponent(it.ticker)}`)));
  if (token.stale) return;
  const chart = lineChart({ height: 300 });
  const lines = [];
  items.forEach((it, i) => {
    const r = series[i];
    if (!r.ok) return;
    const n = Math.min(260, r.body.close.length);
    const c = r.body.close.slice(-n);
    lines.push({ id: it.ticker, label: it.ticker, x: r.body.dates.slice(-n).map(toMs), y: c.map((v) => (v / c[0]) * 100), ...LOOKS[i % LOOKS.length] });
  });
  chart.set({ label: "So sánh giá chuẩn hóa", series: lines, yFmt: (v) => v.toFixed(0), area: false });
  const legend = h("div", { class: "legend-list" }, lines.map((l) => h("label", { class: "check small" }, h("i", { class: "sw", style: `border-top-color:${l.stroke};${l.dash ? "border-top-style:dashed" : ""}` }), l.label)));

  const cell = (v) => h("td", { class: "num" }, v);
  const row = (name, f) => h("tr", null, h("th", { scope: "row" }, name), items.map((it) => cell(f(it))));
  const keys = [["1W", "1T"], ["1M", "1Th"], ["3M", "3Th"], ["6M", "6Th"], ["1Y", "1N"], ["YTD", "YTD"]];
  const table = h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "tbl cmp" },
      h("thead", null, h("tr", null, h("th", null, ""), items.map((it) => h("th", { class: "num" }, h("a", { href: `#/co-phieu/${encodeURIComponent(it.ticker)}` }, it.ticker))))),
      h(
        "tbody",
        null,
        row("Giá đóng cửa (VND)", (it) => fmtVnd(it.price.last_close)),
        keys.map(([k, lb]) => row(`Thay đổi ${lb}`, (it) => changeText((it.price.change || {})[k]))),
        row("Cách đỉnh 52 tuần", (it) => fmtPct(it.price.dist_high_52w, 1)),
        row("Biến động 60 phiên", (it) => fmtPct(it.price.vol_60d_ann, 0)),
        row("Sụt giảm tối đa 1N", (it) => fmtPct(it.price.max_dd_1y, 1)),
        row("GTGD TB 20 phiên", (it) => fmtVndShort(it.price.adv20_value_vnd)),
        HORIZONS.map((hz) =>
          row(`Khuyến nghị ${HORIZON_LABEL[hz].toLowerCase()}`, (it) => {
            const r = (it.recommendation.by_horizon || {})[hz];
            return r ? h("div", { class: "cmp-rec" }, actionBadge(r.action), h("span", { class: "muted small mono" }, `${r.consensus}/${r.of} · ${fmtPct(r.weight, 0)}`)) : "—";
          })
        )
      )
    )
  );
  holder.replaceChildren(
    h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "So sánh giá (chuẩn hóa = 100)"), h("span", { class: "chip soft" }, label)), chart.el, legend),
    h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Số liệu và khuyến nghị cạnh nhau")), table, h("div", { class: "notice" }, "Chỉ khuyến nghị tham khảo — bạn tự quyết định và tự đặt lệnh."), ...items.map((it) => cliLine(`vnstratlab stock ${it.ticker}`)))
  );
}

// ---------- page ----------
export async function renderStocks(root, arg) {
  root.append(pageHead("Cổ phiếu", "Chọn mã, chạy phân tích và đọc số liệu, tín hiệu, khuyến nghị — chỉ để tham khảo"));
  const res = await api("/stocks");
  if (!res.ok) {
    root.append(errorBox(res.status === 404 ? "Máy chủ chưa có /api/stocks (cần bản cập nhật X-stock-api)." : "Không tải được danh sách mã."), cliLine("vnstratlab stock VCB"));
    return;
  }
  const stocks = res.body.tickers || [];
  const known = (t) => stocks.some((s) => s.ticker === t);
  const state = { mode: "single", ticker: arg && known(decodeURIComponent(arg).toUpperCase()) ? decodeURIComponent(arg).toUpperCase() : null, compare: [] };
  const token = { stale: false };
  let timer = null;
  const area = h("div", { class: "stk-area" });
  const cliHolder = h("div");
  const runBtn = h("button", { class: "btn", type: "button" }, "Phân tích");
  const hint = h("span", { class: "muted small" });

  const picker = createPicker(stocks, {
    mode: () => state.mode,
    isOn: (t) => (state.mode === "compare" ? state.compare.includes(t) : state.ticker === t),
    onSingle: (t) => select(t),
    onToggle: (t) => {
      state.compare = state.compare.includes(t) ? state.compare.filter((x) => x !== t) : state.compare.length < MAX_COMPARE ? [...state.compare, t] : (toast(`Chỉ so sánh tối đa ${MAX_COMPARE} mã`, { kind: "warn" }), state.compare);
      syncControls();
    },
  });

  function remember(t) {
    save(RECENT_KEY, [t, ...load(RECENT_KEY, []).filter((x) => x !== t)].slice(0, 6));
    picker.redraw();
  }
  function syncControls() {
    if (state.mode === "compare") {
      runBtn.textContent = `So sánh ${state.compare.length ? state.compare.join(", ") : ""}`.trim();
      runBtn.disabled = state.compare.length < 2;
      hint.textContent = `Chọn 2 đến ${MAX_COMPARE} mã (đã chọn ${state.compare.length}).`;
      cliHolder.replaceChildren(cliLine(state.compare.length ? `vnstratlab stock ${state.compare[0]}` : "vnstratlab recommend"));
    } else {
      runBtn.textContent = state.ticker ? `Phân tích ${state.ticker}` : "Phân tích";
      runBtn.disabled = !state.ticker;
      hint.textContent = state.ticker ? "" : "Chọn một mã trong danh sách.";
      cliHolder.replaceChildren(cliLine(state.ticker ? `vnstratlab stock ${state.ticker}` : "vnstratlab stock <MÃ>"));
    }
  }
  function stopPoll() {
    clearInterval(timer);
    timer = null;
  }

  async function showStored(t) {
    stopPoll();
    area.replaceChildren(h("div", { class: "skeleton" }), h("div", { class: "skeleton" }));
    const r = await api(`/stocks/${encodeURIComponent(t)}/analysis`);
    if (token.stale || state.ticker !== t || state.mode !== "single") return;
    if (r.ok) return area.replaceChildren(...renderAnalysis(r.body, () => start(t)));
    area.replaceChildren(
      r.status === 404
        ? h("section", { class: "card" }, emptyState(`Chưa có phân tích cho ${t}`, "Bấm “Phân tích” để chạy: đọc giá, tính đặc trưng, tín hiệu chiến lược rồi lập khuyến nghị.", h("button", { class: "btn", type: "button", onclick: () => start(t) }, `Phân tích ${t}`)))
        : errorBox("Không tải được phân tích của mã này.")
    );
  }
  function showEmpty() {
    area.replaceChildren(h("section", { class: "card" }, emptyState("Chọn mã và bấm Phân tích", "Bạn sẽ thấy số liệu giá, tín hiệu của từng chiến lược và khuyến nghị theo ba khung đầu tư.")));
  }
  function select(t) {
    state.ticker = t;
    remember(t);
    syncControls();
    history.replaceState(null, "", `#/co-phieu/${encodeURIComponent(t)}`);
    showStored(t);
  }

  async function track(runId, t, cli) {
    stopPoll();
    const card = runCard(t, cli);
    area.replaceChildren(card.el);
    const cancel = async () => {
      const r = await post(`/runs/${encodeURIComponent(runId)}/cancel`, {});
      toast(r.ok ? "Đã gửi yêu cầu hủy" : "Không hủy được: lần chạy đã xong", { kind: r.ok ? "warn" : "err" });
      hooks.pokeTracker && hooks.pokeTracker();
    };
    const tick = async () => {
      const r = await api(`/runs/${encodeURIComponent(runId)}`);
      if (token.stale || !r.ok) return true;
      card.update(r.body, cancel);
      if (isActive(r.body)) return false;
      stopPoll();
      hooks.pokeTracker && hooks.pokeTracker();
      if (r.body.status === "success" && state.ticker === t) return (showStored(t), true);
      const bad = r.body.tasks.find((x) => x.status === "failed");
      card.setTitle(r.body.reason === "cancelled" ? `Đã hủy phân tích ${t}` : `Phân tích ${t} gặp lỗi`);
      card.setBody(h("div", null, bad && bad.error ? h("div", { class: "notice err" }, String(bad.error).split("\n")[0]) : null, h("button", { class: "btn", type: "button", onclick: () => start(t) }, "Thử lại")));
      return true;
    };
    if (!(await tick())) timer = setInterval(tick, POLL_MS);
  }

  async function start(t, acceptTerms = false) {
    runBtn.disabled = true;
    const r = await post(`/stocks/${encodeURIComponent(t)}/analyze`, acceptTerms ? { accept_terms: true } : {});
    const b = r.body || {};
    syncControls();
    if (r.status === 202) {
      hooks.pokeTracker && hooks.pokeTracker();
      return track(b.run_id, t, b.cli || `vnstratlab stock ${t}`);
    }
    if (r.status === 409 && b.error === "terms_required") {
      const ok = await confirmDialog({ title: "Điều khoản nguồn dữ liệu", yes: "Tôi đồng ý, bắt đầu phân tích", body: h("pre", { class: "notice-text" }, b.notice || "") });
      return ok ? start(t, true) : null;
    }
    if (r.status === 409 && b.error === "busy") return toast("Đang có một lần chạy khác", { kind: "warn", href: `#/runs/${b.active_run_id}`, sub: "Bấm để xem lần chạy đang chạy" });
    toast(`Không bắt đầu được phân tích (mã ${r.status}${b.error ? `: ${b.error}` : ""})`, { kind: "err" });
  }

  runBtn.addEventListener("click", () => {
    if (state.mode === "compare") return state.compare.length >= 2 && renderCompare(area, state.compare, token);
    if (state.ticker) start(state.ticker);
  });
  const modeSeg = segmented([["single", "Phân tích một mã"], ["compare", "So sánh"]], state.mode, (m) => {
    state.mode = m;
    syncControls();
    picker.redraw();
    if (m === "compare") area.replaceChildren(h("section", { class: "card" }, emptyState("So sánh tối đa 4 mã", "Bấm các mã trong danh sách để thêm (2 đến 4), rồi bấm “So sánh”.")));
    else if (state.ticker) showStored(state.ticker);
    else showEmpty();
  }, "Chế độ");

  root.append(
    h(
      "section",
      { class: "card stk-picker" },
      h("div", { class: "card-head" }, h("h2", null, "Chọn mã"), modeSeg),
      h("div", { class: "toolbar" }, h("div", { class: "grow" }, picker.input), runBtn, hint),
      picker.recent,
      picker.list,
      cliHolder
    ),
    area
  );
  syncControls();
  if (state.ticker) {
    remember(state.ticker);
    // resume the live view when a run for this ticker is already going
    const runs = await api("/runs?limit=5");
    const live = runs.ok && runs.body.runs.find((r) => isActive(r) && r.pipeline === "stock_analysis" && r.params && r.params.ticker === state.ticker);
    if (live) track(live.run_id, state.ticker, live.cli || `vnstratlab stock ${state.ticker}`);
    else showStored(state.ticker);
  } else showEmpty();
  return () => {
    token.stale = true;
    stopPoll();
  };
}

