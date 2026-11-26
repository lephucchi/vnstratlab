// Dữ liệu: tickers with sparklines, price + volume chart, DQ findings, expandable data gaps.
import { lineChart, sparkline, toMs } from "./charts.js";
import { emptyState, pageHead, segmented, table } from "./ui.js";
import { api, errorBox, fmtInt, h } from "./util.js";

const SEVERITY_VI = { high: "Cao", medium: "Trung bình", low: "Thấp" };
const RANGES = [["1T", 30], ["3T", 91], ["1N", 365], ["5N", 1826], ["all", 0]];
const RANGE_LABEL = { "1T": "1T", "3T": "3T", "1N": "1N", "5N": "5N", all: "Tất cả" };

const runChip = (status) => h("span", { class: `chip st-${["ok", "success", "done"].includes(status) ? "success" : ["failed", "error"].includes(status) ? "failed" : "queued"}` }, h("span", { class: "dot" }), status);

function priceDetail(kind) {
  const chart = lineChart({ height: 320 });
  const title = h("h2", null, "Giá và khối lượng");
  const holder = h("div", { class: "muted" }, "Chọn một mã ở trên để xem biểu đồ.");
  const sub = h("div", { class: "muted small mono" });
  const card = h("section", { class: "card", id: "price-detail" });
  let series = null;
  let range = "1N";
  function draw() {
    if (!series) return;
    const days = RANGES.find((r) => r[0] === range)[1];
    const last = series.dates.length - 1;
    let from = 0;
    if (days) {
      const cut = toMs(series.dates[last]) - days * 86400000;
      from = Math.max(0, series.dates.findIndex((d) => toMs(d) >= cut));
    }
    const x = series.dates.slice(from).map(toMs);
    chart.set({
      label: `Giá đóng cửa ${series.ticker}`,
      series: [{ id: series.ticker, label: `${series.ticker} đóng cửa`, x, y: series.close.slice(from) }],
      bars: { x, y: series.volume.slice(from) },
      yFmt: (v) => v.toLocaleString("vi-VN", { maximumFractionDigits: 2 }),
      barFmt: (v) => fmtInt(v),
      area: true,
    });
    const c = series.close.slice(from);
    const chg = c[c.length - 1] / c[0] - 1;
    sub.textContent = `${series.ticker} · ${series.kind === "real" ? "dữ liệu thật" : "SYNTHETIC"} · ${x.length} phiên · thay đổi ${(chg * 100).toFixed(1)}% trong khoảng chọn`;
  }
  const seg = segmented(RANGES.map((r) => [r[0], RANGE_LABEL[r[0]]]), range, (v) => ((range = v), draw()), "Khoảng thời gian");
  card.append(h("div", { class: "card-head" }, title, seg), sub, chart.el, holder);
  chart.el.hidden = true;
  seg.hidden = true;
  return {
    el: card,
    async show(ticker) {
      title.textContent = `Giá và khối lượng · ${ticker}`;
      holder.textContent = "Đang tải…";
      holder.hidden = false;
      chart.el.hidden = true;
      const res = await api(`/data/prices/${encodeURIComponent(ticker)}`);
      if (!res.ok) {
        holder.textContent = res.status === 404 ? "Chưa có giá của mã này (hoặc máy chủ chưa có /api/data/prices)." : "Không tải được giá của mã này.";
        return;
      }
      series = res.body;
      holder.hidden = true;
      chart.el.hidden = false;
      seg.hidden = false;
      draw();
    },
    kind,
  };
}

function tickerGrid(store, onPick) {
  const buttons = new Map();
  const last = store.tickers.map((t) => t.last).sort().pop();
  const from = last ? new Date(Date.parse(last) - 180 * 86400000).toISOString().slice(0, 10) : "";
  const grid = h("div", { class: "tk-grid" });
  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => entries.forEach((en) => en.isIntersecting && (io.unobserve(en.target), load(en.target.dataset.ticker))), { rootMargin: "200px" }) : null;
  async function load(t) {
    const res = await api(`/data/prices/${encodeURIComponent(t)}?from=${from}`);
    const slot = buttons.get(t).querySelector(".sp");
    if (res.ok && res.body.close.length > 1) {
      const c = res.body.close;
      slot.replaceChildren(sparkline(c));
      buttons.get(t).querySelector(".chg").textContent = `${((c[c.length - 1] / c[0] - 1) * 100).toFixed(1)}%`;
    }
  }
  store.tickers.forEach((t) => {
    const b = h(
      "button",
      { class: "tk", type: "button", "aria-pressed": "false", "data-ticker": t.ticker, onclick: () => (buttons.forEach((x) => x.setAttribute("aria-pressed", "false")), b.setAttribute("aria-pressed", "true"), onPick(t.ticker)) },
      h("div", { class: "t" }, h("span", null, t.ticker), h("span", { class: "chg muted small" }, "")),
      h("div", { class: "sp" }, h("div", { style: "height:26px" })),
      h("div", { class: "m" }, `${t.first} → ${t.last} · ${fmtInt(t.rows)}`)
    );
    buttons.set(t.ticker, b);
    grid.append(b);
    io ? io.observe(b) : load(t.ticker);
  });
  return { el: grid, pick: (t) => buttons.get(t) && buttons.get(t).click() };
}

function dqCard(fallbackRows) {
  const state = { level: "", q: "" };
  const holder = h("div");
  let rows = [];
  function draw() {
    const shown = rows.filter((r) => (!state.level || r.level === state.level) && (!state.q || `${r.ticker} ${r.check} ${r.detail}`.toLowerCase().includes(state.q)));
    holder.replaceChildren(shown.length ? table(["Ngày", "Mã", "Kiểm tra", "Mức", "Chi tiết"], shown.map((r) => [r.date, r.ticker, r.check, h("span", { class: `chip ${r.level === "error" ? "dashed" : "warn"}` }, r.level === "error" ? "lỗi" : "cảnh báo"), r.detail])) : h("p", { class: "muted" }, "Không có phát hiện nào khớp."));
  }
  const search = h("input", { type: "search", placeholder: "Lọc theo mã, kiểm tra…", "aria-label": "Lọc phát hiện chất lượng", oninput: () => ((state.q = search.value.trim().toLowerCase()), draw()) });
  const seg = segmented([["", "Tất cả"], ["error", "Lỗi"], ["warning", "Cảnh báo"]], "", (v) => ((state.level = v), draw()), "Mức");
  const card = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Phát hiện chất lượng dữ liệu (DQ)")), h("div", { class: "toolbar" }, h("div", { class: "grow" }, search), seg), holder);
  (async () => {
    const res = await api("/data/quality?limit=200");
    rows = res.ok ? res.body.rows : fallbackRows.map((e) => ({ date: e.date, ticker: e.ticker, check: e.check, level: "error", detail: e.detail }));
    if (!res.ok) card.prepend(h("div", { class: "notice warn" }, "Máy chủ chưa có /api/data/quality: chỉ hiện các lỗi của lần nạp gần nhất."));
    draw();
  })();
  return card;
}

function gapsCard(gaps) {
  const open = gaps.open || [];
  const state = { sev: "" };
  const holder = h("div");
  function draw() {
    const shown = open.filter((g) => !state.sev || g.severity === state.sev);
    holder.replaceChildren(
      ...(shown.length
        ? shown.map((g) =>
            h(
              "details",
              { class: "gap" },
              h("summary", null, h("code", null, g.id), h("span", { class: `sev sev-${g.severity}` }, SEVERITY_VI[g.severity] || g.severity), h("span", null, g.title_vi)),
              h("dl", null, h("dt", null, "Thiếu gì"), h("dd", null, g.missing), h("dt", null, "Ảnh hưởng"), h("dd", null, (g.affects || []).join(", ")), h("dt", null, "Cách xử lý tạm"), h("dd", null, g.workaround), h("dt", null, "Đóng bằng"), h("dd", null, g.close_by), h("dt", null, "Từ ngày"), h("dd", null, g.since))
            )
          )
        : [h("p", { class: "muted" }, "Không có khoảng trống nào đang mở.")])
    );
  }
  draw();
  return h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, `Khoảng trống dữ liệu đang mở (${open.length})`), segmented([["", "Tất cả"], ["high", "Cao"], ["medium", "Trung bình"], ["low", "Thấp"]], "", (v) => ((state.sev = v), draw()), "Mức độ")), holder);
}

export async function renderData(root) {
  root.append(pageHead("Dữ liệu", "Kho dữ liệu cục bộ — không rời khỏi máy của bạn"));
  const res = await api("/data/status");
  if (!res.ok) return root.append(errorBox("Không tải được tình trạng dữ liệu."));
  const { home, stores, gaps } = res.body;
  root.append(h("p", { class: "muted small mono" }, `Thư mục dữ liệu: ${home}`));
  if (!stores.length) {
    root.append(h("section", { class: "card" }, emptyState("Chưa có dữ liệu", "Chạy nạp dữ liệu giả lập (offline) hoặc nguồn mặc định. Demo dùng thư mục tạm nên không ghi vào kho này.", h("a", { class: "btn sm", href: "#/runs" }, "Mở Runs"))));
  }
  let fallbackErrors = [];
  for (const store of stores) {
    const real = store.kind === "real";
    const head = h("div", { class: "card-head" }, h("h2", null, store.file), h("span", { class: `chip ${real ? "dashed" : "soft"}` }, real ? "THẬT" : "SYNTHETIC"));
    if (store.error) {
      root.append(h("section", { class: "card" }, head, errorBox(`Không đọc được kho dữ liệu: ${store.error}`)));
      continue;
    }
    const detail = priceDetail(store.kind);
    const grid = tickerGrid(store, (t) => detail.show(t));
    root.append(
      h("section", { class: "card" }, head, h("p", { class: "muted small" }, `${fmtInt(store.rows)} dòng, ${store.tickers.length} mã. Bấm một mã để xem biểu đồ.`), grid.el),
      detail.el,
      h(
        "section",
        { class: "card" },
        h("h2", null, "Các lần nạp gần nhất"),
        store.runs.length ? table(["Mã lần chạy", "Nguồn", "Từ", "Đến", "Ghi", "Đổi", "Loại", "Trạng thái"], store.runs.map((r) => [r.run_id, r.source, r.start, r.end, r.rows_written, r.rows_changed, r.rows_dropped, runChip(r.status)]), { numeric: [4, 5, 6] }) : h("p", { class: "muted" }, "Chưa có lần nạp nào.")
      )
    );
    if (store.last_run_checks) fallbackErrors = store.last_run_checks.first_errors || [];
    if (store.tickers.length) grid.pick(store.tickers[0].ticker);
  }
  if (stores.length) root.append(dqCard(fallbackErrors));
  root.append(gapsCard(gaps));
}
