// Page 3a: Dữ liệu. Stores, tickers, last ingest runs and checks, open gaps.
import { api, errorBox, h } from "./util.js";

const SEVERITY_VI = { high: "Cao", medium: "Trung bình", low: "Thấp" };

function runChip(status) {
  const cls = ["ok", "success", "done"].includes(status) ? "success" : ["failed", "error"].includes(status) ? "failed" : "queued";
  return h("span", { class: `chip st-${cls}` }, status);
}

function table(headers, rows) {
  return h(
    "div",
    { class: "table-scroll" },
    h("table", { class: "tbl" }, h("thead", null, h("tr", null, headers.map((x) => h("th", null, x)))), h("tbody", null, rows.map((r) => h("tr", null, r.map((c) => h("td", null, c))))))
  );
}

function storeCard(store) {
  const real = store.kind === "real";
  const badge = h("span", { class: `badge ${real ? "badge-real" : "badge-synth"}` }, real ? "THẬT" : "SYNTHETIC");
  const card = h("section", { class: "card" }, h("h2", null, store.file, " ", badge));
  if (store.error) {
    card.append(errorBox(`Không đọc được kho dữ liệu: ${store.error}`));
    return card;
  }
  card.append(h("p", { class: "muted" }, `${store.rows.toLocaleString("vi-VN")} dòng, ${store.tickers.length} mã`));
  card.append(
    h("details", { open: store.tickers.length <= 12 }, h("summary", null, "Các mã"), table(["Mã", "Từ ngày", "Đến ngày", "Số dòng"], store.tickers.map((t) => [t.ticker, t.first, t.last, t.rows])))
  );
  card.append(h("h3", null, "Các lần nạp gần nhất"));
  card.append(
    store.runs.length
      ? table(
          ["Mã lần chạy", "Nguồn", "Từ", "Đến", "Ghi", "Đổi", "Loại", "Trạng thái"],
          store.runs.map((r) => [r.run_id, r.source, r.start, r.end, r.rows_written, r.rows_changed, r.rows_dropped, runChip(r.status)])
        )
      : h("p", { class: "muted" }, "Chưa có lần nạp nào.")
  );
  const c = store.last_run_checks;
  if (c) {
    card.append(
      h("h3", null, "Kiểm tra chất lượng của lần nạp gần nhất"),
      h("p", null, h("span", { class: `chip st-${c.errors ? "failed" : "success"}` }, `${c.errors} lỗi`), " ", h("span", { class: `chip st-${c.warnings ? "running" : "success"}` }, `${c.warnings} cảnh báo`)),
      h("ul", { class: "watch" }, c.first_errors.map((e) => h("li", null, `${e.check} · ${e.ticker} · ${e.date}: ${e.detail}`)))
    );
  }
  return card;
}

function gapsCard(gaps) {
  const open = gaps.open || [];
  const card = h("section", { class: "card" }, h("h2", null, "Khoảng trống dữ liệu đang mở"));
  if (!open.length) {
    card.append(h("p", { class: "muted" }, "Không có khoảng trống nào đang mở."));
    return card;
  }
  for (const sev of ["high", "medium", "low"]) {
    const items = open.filter((g) => g.severity === sev);
    if (!items.length) continue;
    card.append(
      h("h3", null, h("span", { class: `sev sev-${sev}` }, SEVERITY_VI[sev]), ` (${items.length})`),
      h("ul", { class: "gaps" }, items.map((g) => h("li", null, h("code", null, g.id), " ", g.title_vi)))
    );
  }
  return card;
}

export async function renderData(root) {
  root.append(h("h1", null, "Dữ liệu"));
  const res = await api("/data/status");
  if (!res.ok) return root.append(errorBox("Không tải được tình trạng dữ liệu."));
  const { home, stores, gaps } = res.body;
  root.append(h("p", { class: "muted" }, `Thư mục dữ liệu: ${home}`));
  if (!stores.length) {
    root.append(
      h("section", { class: "card" }, h("p", null, "Chưa có dữ liệu. Chạy ", h("code", null, "vnstratlab ingest --source synthetic"), " (offline), hoặc ", h("code", null, "vnstratlab ingest"), " cho nguồn mặc định. Demo dùng thư mục tạm nên không ghi vào kho này."))
    );
  }
  stores.forEach((s) => root.append(storeCard(s)));
  root.append(gapsCard(gaps));
}
