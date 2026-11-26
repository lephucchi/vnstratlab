// Khuyến nghị hiện tại: preview of today's targets per horizon (GET /api/recommendations/all).
// Shared by Kết quả (full panel) and Tổng quan (top-3 mini card). Recommend-only: no order UI.
import { cliLine, emptyState, hcRow, hoverCard, segmented } from "./ui.js";
import { api, fmtDate, fmtNumVi, fmtPct, fmtVnd, fmtVndShort, h, load, save } from "./util.js";

export const HORIZON_LABEL = { short: "Ngắn hạn", medium: "Trung hạn", long: "Dài hạn" };
export const HORIZONS = ["short", "medium", "long"];
export const DISCLAIMER = "Chỉ khuyến nghị tham khảo — bạn tự quyết định và tự đặt lệnh.";
const PREVIEW_STATUS = "Bản xem trước — chưa qua lab chọn lọc";

/** Fetch every horizon. Returns {horizons} or {error: "missing" | "failed"}. */
export async function loadRecommendations() {
  const res = await api("/recommendations/all");
  if (res.ok && res.body && res.body.horizons) return res.body;
  return { error: res.status === 404 || res.status === 0 ? "missing" : "failed" };
}

export const dataLabel = (rec) => (rec.synthetic ? "SYNTHETIC" : "Yahoo tạm thời");

/** A thin proportional bar: ``value`` is a fraction 0..1. */
export function wbar(value, max = 1) {
  const fill = h("i");
  fill.style.width = `${Math.max(0, Math.min(1, value / max)) * 100}%`;
  return h("span", { class: "wbar", role: "img", "aria-label": `Tỷ trọng ${fmtPct(value, 0)}` }, fill);
}

/** n/N consensus as filled dots + text; the hover card names the strategies. */
export function consensusChip(n, of, strategies) {
  const dots = Array.from({ length: of }, (_, i) => h("i", { class: i < n ? "on" : null }));
  const chip = h("span", { class: "chip cons", tabindex: 0, "aria-label": `Đồng thuận ${n} trên ${of} chiến lược` }, h("span", { class: "dots" }, dots), `${n}/${of}`);
  if (strategies && strategies.length) hoverCard(chip, () => [h("b", null, "Chiến lược đang chọn mã"), ...strategies.map((s) => h("div", null, s))]);
  return chip;
}

export function banner(rec) {
  return h(
    "div",
    { class: "rec-banner" },
    h("span", { class: "chip dashed" }, PREVIEW_STATUS),
    h("span", { class: "chip soft" }, dataLabel(rec)),
    rec.asof ? h("span", { class: "chip" }, `quyết định tại phiên ${fmtDate(rec.asof)}`) : null
  );
}

/** lot_qty = shares in round lots (multiple of lot_size); ``lots`` = number of round lots; odd_qty = odd-lot shares. */
export function lotText(t, lotSize) {
  const size = t.lot_size || lotSize || 100;
  const lots = t.lots ?? Math.floor((t.lot_qty || 0) / size);
  return `${fmtVnd(lots)} lô${lots ? ` (= ${fmtVnd(t.lot_qty)} cp)` : ""}${t.odd_qty ? ` + ${fmtVnd(t.odd_qty)} cp lẻ` : ""}`;
}

function kv(k, v) {
  return h("div", null, h("dt", null, k), h("dd", null, v));
}

function targetCard(t, rec) {
  const lots = lotText(t);
  const zone = t.entry_zone ? `${fmtVnd(t.entry_zone.low)} – ${fmtVnd(t.entry_zone.high)}` : "—";
  const of = (rec.strategies || []).length;
  const card = h(
    "article",
    { class: "rec-card" },
    h(
      "div",
      { class: "rec-top" },
      h("a", { class: "rec-tk", href: `#/co-phieu/${encodeURIComponent(t.ticker)}`, title: `Phân tích ${t.ticker}` }, t.ticker),
      h("span", { class: "rec-w mono" }, fmtPct(t.weight, 1))
    ),
    wbar(t.weight, 0.5),
    h("div", { class: "rec-cons" }, consensusChip(t.consensus, of || t.consensus, t.strategies), h("span", { class: "muted small" }, "chiến lược đồng thuận")),
    h(
      "dl",
      { class: "kv" },
      kv("Giá đóng cửa", fmtVnd(t.last_close)),
      kv("Vùng mua", zone),
      kv("Số lượng", lots),
      kv("Giá trị", `${fmtVnd(t.notional_vnd)} đ`),
      kv("Giá cắt lỗ", t.stop_price ? `${fmtVnd(t.stop_price)} (${fmtPct(t.stop_pct, 1)})` : "—"),
      kv("Chi phí ước tính", `${fmtVnd(t.est_cost_vnd)} đ`),
      kv("Trần / Sàn", `${fmtVnd(t.ceiling)} / ${fmtVnd(t.floor)}`)
    ),
    h("a", { class: "btn ghost sm", href: `#/co-phieu/${encodeURIComponent(t.ticker)}` }, `Phân tích ${t.ticker}`)
  );
  return card;
}

function evidence(rec) {
  const ev = rec.evidence || {};
  const dsr = ev.dsr_by_strategy || null;
  const pass = new Set(ev.gate1_pass || []);
  const rows = dsr ? Object.entries(dsr) : [];
  const head = h("div", { class: "ev-head" }, h("b", null, "Bằng chứng"), h("span", { class: "muted small" }, ` Đã đếm ${ev.trials_counted ?? "—"} trial (mọi lần thử đều được tính vào ngưỡng Deflated Sharpe)${ev.trials_contributing != null ? `; ${ev.trials_contributing} trial tham gia khuyến nghị này` : ""}.`));
  if (!rows.length) return h("div", { class: "rec-ev" }, head, h("p", { class: "muted small" }, "Chưa có chỉ số DSR / cổng 1 cho các chiến lược này."));
  return h(
    "div",
    { class: "rec-ev" },
    head,
    h(
      "div",
      { class: "ev-list" },
      rows.map(([k, v]) => h("div", { class: "ev-row" }, h("span", { class: "mono" }, k), h("span", { class: "mono" }, `DSR ${fmtNumVi(v, 2)}`), h("span", { class: `chip ${pass.has(k) ? "soft" : "dashed"}` }, pass.has(k) ? "qua cổng 1" : "chưa qua cổng 1")))
    )
  );
}

function horizonPanel(rec) {
  const targets = rec.targets || [];
  const info = h(
    "p",
    { class: "muted small" },
    `Sổ ${HORIZON_LABEL[rec.horizon].toLowerCase()} · vốn ${fmtVnd(rec.book_capital_vnd)} đ · ${targets.length} mã · tiền mặt ${fmtPct(rec.cash_weight, 0)}`
  );
  const strategies = h("p", { class: "muted small" }, `Chiến lược đang bật: ${(rec.strategies || []).map((s) => s.strategy_id).join(", ") || "chưa có"}. ${rec.note_vi || ""}`);
  const warns = (rec.warnings || []).map((w) => h("div", { class: "notice warn" }, w));
  if (!targets.length) {
    return h("div", null, info, warns, emptyState("Chưa có mã nào được đề xuất", "Cần dữ liệu và đặc trưng mới nhất: làm mới dữ liệu rồi tính đặc trưng.", cliLine("vnstratlab features build")), evidence(rec));
  }
  const cash = h("article", { class: "rec-card cash" }, h("div", { class: "rec-top" }, h("span", { class: "rec-tk" }, "Tiền mặt"), h("span", { class: "rec-w mono" }, fmtPct(rec.cash_weight, 1))), wbar(rec.cash_weight, 0.5), h("p", { class: "muted small" }, "Phần vốn chưa phân bổ do giới hạn số vị thế và tỷ trọng tối đa mỗi mã."));
  return h("div", null, info, strategies, warns, h("div", { class: "rec-grid" }, targets.map((t) => targetCard(t, rec)), cash), evidence(rec));
}

/** Full panel for Kết quả. Returns a section element. */
export async function renderRecsPanel() {
  const card = h("section", { class: "card recs", id: "recs" });
  const data = await loadRecommendations();
  const head = h("div", { class: "card-head" }, h("h2", null, "Khuyến nghị hiện tại"));
  if (data.error) {
    card.append(head, h("div", { class: "notice warn", role: "alert" }, data.error === "missing" ? "Máy chủ chưa có /api/recommendations (cần bản cập nhật X-stock-api)." : "Không tải được khuyến nghị."), cliLine("vnstratlab recommend"));
    return card;
  }
  const hzs = HORIZONS.filter((hz) => data.horizons[hz]);
  let current = load("vn-rec-horizon", "short");
  if (!hzs.includes(current)) current = hzs[0];
  const body = h("div");
  const first = data.horizons[current];
  const stamp = h("div");
  const cli = h("div");
  function draw(hz) {
    current = hz;
    save("vn-rec-horizon", hz);
    const rec = data.horizons[hz];
    stamp.replaceChildren(banner(rec));
    body.replaceChildren(horizonPanel(rec));
    cli.replaceChildren(cliLine(`vnstratlab recommend --horizon ${hz}`));
  }
  const seg = segmented(hzs.map((hz) => [hz, `${HORIZON_LABEL[hz]} (${(data.horizons[hz].targets || []).length})`]), current, draw, "Khung đầu tư");
  head.append(seg);
  card.append(head, stamp, h("div", { class: "notice" }, h("b", null, "Chỉ khuyến nghị tham khảo — bạn tự quyết định và tự đặt lệnh. "), first.label || ""), body, cli);
  draw(current);
  return card;
}

/** Top-3-per-horizon mini card for Tổng quan. */
export async function renderRecsMini() {
  const card = h("section", { class: "card recs-mini" });
  const head = h("div", { class: "card-head" }, h("h2", null, "Khuyến nghị hiện tại"), h("a", { href: "#/ket-qua" }, "Xem đầy đủ"));
  const data = await loadRecommendations();
  if (data.error) {
    card.append(head, h("p", { class: "muted small" }, data.error === "missing" ? "Máy chủ chưa có /api/recommendations." : "Không tải được khuyến nghị."), cliLine("vnstratlab recommend"));
    return card;
  }
  const any = HORIZONS.map((hz) => data.horizons[hz]).find(Boolean);
  card.append(head, any ? banner(any) : null);
  card.append(
    h(
      "div",
      { class: "mini-cols" },
      HORIZONS.filter((hz) => data.horizons[hz]).map((hz) => {
        const rec = data.horizons[hz];
        const top = (rec.targets || []).slice(0, 3);
        return h(
          "div",
          { class: "mini-col" },
          h("b", null, HORIZON_LABEL[hz]),
          top.length
            ? top.map((t) => {
                const row = h("a", { class: "mini-row", href: `#/co-phieu/${encodeURIComponent(t.ticker)}` }, h("span", { class: "mono tk" }, t.ticker), wbar(t.weight, 0.5), h("span", { class: "mono w" }, fmtPct(t.weight, 0)), h("span", { class: "muted small" }, `${t.consensus}/${(rec.strategies || []).length || t.consensus}`));
                hoverCard(row, () => [h("b", null, `${t.ticker} · ${HORIZON_LABEL[hz]}`), hcRow("Giá đóng cửa", fmtVnd(t.last_close)), hcRow("Giá trị", fmtVndShort(t.notional_vnd)), hcRow("Cắt lỗ", fmtVnd(t.stop_price))]);
                return row;
              })
            : h("span", { class: "muted small" }, "Chưa có mã được đề xuất")
        );
      })
    ),
    h("p", { class: "muted small" }, DISCLAIMER),
    cliLine("vnstratlab recommend")
  );
  return card;
}
