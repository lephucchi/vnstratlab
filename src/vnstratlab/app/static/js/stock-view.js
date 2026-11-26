// Rendering of one stock's analysis (GET /api/stocks/{ticker}/analysis). Pure view code: textContent only.
import { lineChart, toMs } from "./charts.js";
import { HORIZON_LABEL, HORIZONS, consensusChip, dataLabel, lotText, wbar } from "./recs.js";
import { cliLine, hcRow, hoverCard, segmented, table } from "./ui.js";
import { fmtDate, fmtInt, fmtNumVi, fmtPct, fmtTime, fmtVnd, fmtVndShort, h } from "./util.js";

const CHANGE_KEYS = [["1W", "1T"], ["1M", "1Th"], ["3M", "3Th"], ["6M", "6Th"], ["1Y", "1N"], ["YTD", "YTD"]];
const ACTION_NOTE = { MUA: "đang trong danh mục mục tiêu", "GIỮ": "có chiến lược giữ, danh mục kết hợp không có: chưa nên mua thêm", KHÔNG: "chưa có chiến lược chọn" };
const ACTION_DOT = { MUA: "st-success", "GIỮ": "st-warn", KHÔNG: "st-skipped" };
const RANGES = [["1T", 30], ["3T", 91], ["6T", 182], ["1N", 365], ["all", 0]];
const RANGE_LABEL = { "1T": "1T", "3T": "3T", "6T": "6T", "1N": "1N", all: "Tất cả" };

export const actionBadge = (action) => h("span", { class: `act act-${action}` }, h("span", { class: `dot ${ACTION_DOT[action] || ""}` }), action);

export function changeChips(change) {
  return h(
    "div",
    { class: "chg-row" },
    CHANGE_KEYS.map(([k, label]) => {
      const v = change ? change[k] : null;
      return h("span", { class: "chg-chip" }, h("span", { class: "muted" }, label), h("b", { class: "mono" }, v === null || v === undefined ? "—" : `${v > 0 ? "▲" : v < 0 ? "▼" : ""} ${fmtPct(Math.abs(v), 1)}`));
    })
  );
}

// ---------- header ----------
function header(a, onRerun) {
  const p = a.price || {};
  return h(
    "section",
    { class: "card stk-head" },
    h(
      "div",
      { class: "sh-top" },
      h("div", null, h("h2", { class: "sh-tk" }, a.ticker), h("span", { class: "muted small" }, `phiên ${fmtDate(a.asof)}`)),
      h("div", { class: "sh-px" }, h("div", { class: "value mono" }, fmtVnd(p.last_close)), h("span", { class: "muted small" }, "giá đóng cửa (VND)")),
      h("div", { class: "sh-meta" }, h("span", { class: `chip ${a.synthetic ? "soft" : "dashed"}` }, dataLabel(a)), h("button", { class: "btn ghost sm", type: "button", onclick: onRerun }, "Phân tích lại"))
    ),
    changeChips(p.change),
    a.label ? h("div", { class: "banner-synth", role: "note" }, a.label) : null,
    ...(a.warnings || []).map((w) => h("div", { class: "notice warn" }, w)),
    h("p", { class: "muted small mono" }, `Lần chạy ${a.run_id || "—"} · tạo lúc ${fmtTime(a.generated_at)}`),
    cliLine(`vnstratlab stock ${a.ticker}`)
  );
}

// ---------- recommendation ----------
function recommendationCard(a) {
  const rec = a.recommendation || {};
  const by = rec.by_horizon || {};
  const cols = HORIZONS.filter((hz) => by[hz]).map((hz) => {
    const r = by[hz];
    return h(
      "div",
      { class: `rec-col act-${r.action}` },
      h("div", { class: "rc-top" }, h("b", null, HORIZON_LABEL[hz]), actionBadge(r.action)),
      h("div", { class: "muted small" }, ACTION_NOTE[r.action] || ""),
      h("div", { class: "rc-meta" }, consensusChip(r.consensus, r.of), h("span", { class: "mono small" }, `tỷ trọng ${fmtPct(r.weight, 0)}`)),
      wbar(r.weight, 0.5),
      h("p", { class: "small" }, r.reason_vi || "")
    );
  });
  return h(
    "section",
    { class: "card stk-rec" },
    h("div", { class: "card-head" }, h("h2", null, "Khuyến nghị"), h("span", { class: "chip dashed" }, "Bản xem trước — chưa qua lab chọn lọc")),
    h("div", { class: "rec-cols" }, cols),
    rec.summary_vi ? h("p", { class: "summary" }, rec.summary_vi) : null,
    h("div", { class: "notice" }, rec.disclaimer_vi || "Chỉ là khuyến nghị tham khảo, không phải lời mời mua bán. Bạn tự quyết định và tự đặt lệnh.")
  );
}

// ---------- chart ----------
function chartCard(a) {
  const c = a.chart || { dates: [], close: [], volume: [], markers: [] };
  const chart = lineChart({ height: 340 });
  const horizonOf = {};
  (a.strategies || []).forEach((s) => (horizonOf[s.strategy_id] = [...(horizonOf[s.strategy_id] || []), s.horizon]));
  const buy = HORIZONS.find((hz) => a.recommendation && a.recommendation.by_horizon && a.recommendation.by_horizon[hz] && a.recommendation.by_horizon[hz].action === "MUA");
  const state = { range: "1N", marks: buy || "medium" };
  const note = h("p", { class: "muted small" });
  function draw() {
    const days = RANGES.find((r) => r[0] === state.range)[1];
    const last = c.dates.length - 1;
    let from = 0;
    if (days && last >= 0) {
      const cut = toMs(c.dates[last]) - days * 86400000;
      from = Math.max(0, c.dates.findIndex((d) => toMs(d) >= cut));
    }
    const x = c.dates.slice(from).map(toMs);
    const dateIdx = new Map(c.dates.map((d, i) => [d, i]));
    const marks = (c.markers || [])
      .filter((m) => dateIdx.has(m.date) && dateIdx.get(m.date) >= from && (state.marks === "all" || (horizonOf[m.strategy_id] || []).includes(state.marks)))
      .map((m) => ({ x: toMs(m.date), y: c.close[dateIdx.get(m.date)], side: m.side, label: m.strategy_id }));
    chart.set({
      label: `Giá đóng cửa ${a.ticker}`,
      series: [{ id: a.ticker, label: `${a.ticker} đóng cửa`, x, y: c.close.slice(from) }],
      bars: { x, y: c.volume.slice(from) },
      markers: marks,
      yFmt: (v) => fmtVnd(v),
      barFmt: (v) => fmtInt(v),
      area: true,
    });
    note.textContent = `${c.basis ? `Giá ${c.basis === "adjusted" ? "đã điều chỉnh" : c.basis}. ` : ""}${marks.length} điểm vào/ra của các chiến lược${state.marks === "all" ? "" : ` khung ${HORIZON_LABEL[state.marks].toLowerCase()}`}. ▲ = chiến lược bắt đầu giữ mã, ▽ = thôi giữ.`;
  }
  const range = segmented(RANGES.map((r) => [r[0], RANGE_LABEL[r[0]]]), state.range, (v) => ((state.range = v), draw()), "Khoảng thời gian");
  const marks = segmented([...HORIZONS.map((hz) => [hz, HORIZON_LABEL[hz]]), ["all", "Mọi khung"]], state.marks, (v) => ((state.marks = v), draw()), "Điểm vào/ra theo khung");
  const card = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Giá, khối lượng và điểm vào/ra"), range), h("div", { class: "toolbar" }, h("span", { class: "muted small" }, "Điểm vào/ra:"), marks), chart.el, note);
  requestAnimationFrame(draw);
  return card;
}

// ---------- stats ----------
function stat(label, value, sub) {
  return h("div", { class: "kpi" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value), sub ? h("div", { class: "sub" }, sub) : null);
}
function statsCard(a) {
  const p = a.price || {};
  const atrPct = p.last_close ? p.atr14 / p.last_close : null;
  return h(
    "section",
    { class: "card flat stk-stats" },
    h(
      "div",
      { class: "kpis stat-grid" },
      stat("Đỉnh 52 tuần", fmtVnd(p.high_52w), `${fmtPct(p.dist_high_52w, 1)} so với giá hiện tại`),
      stat("Đáy 52 tuần", fmtVnd(p.low_52w), `${fmtPct(p.dist_low_52w, 1, true)} so với đáy`),
      stat("Biến động 20 / 60 phiên", `${fmtPct(p.vol_20d_ann, 0)} / ${fmtPct(p.vol_60d_ann, 0)}`, "quy năm"),
      stat("Sụt giảm tối đa 1 năm", fmtPct(p.max_dd_1y, 1), "từ đỉnh xuống đáy"),
      stat("ATR 14 phiên", fmtVnd(p.atr14), atrPct === null ? null : `${fmtPct(atrPct, 1)} giá; cắt lỗ = 2 × ATR`),
      stat("GTGD TB 20 phiên", fmtVndShort(p.adv20_value_vnd), `phiên gần nhất = ${fmtNumVi(p.volume_vs_adv20, 2)} × TB`),
      stat("Trần / Sàn", `${fmtVnd(p.ceiling)} / ${fmtVnd(p.floor)}`, `lô giao dịch ${fmtVnd(p.lot_size)} cp`)
    )
  );
}

// ---------- strategy signals ----------
const fmtSignal = (name, v) => (v === null || v === undefined ? "n/a" : /ret|mom|vol|vs_|dist|trend/.test(name) ? fmtPct(v, 1) : fmtNumVi(v, 1));
function signalsCard(a) {
  const state = { hz: "" };
  const holder = h("div");
  function draw() {
    const rows = (a.strategies || []).filter((s) => !state.hz || s.horizon === state.hz);
    holder.replaceChildren(
      table(
        ["Chiến lược", "Khung", "Giữ?", "Tỷ trọng", "Hạng", "Tín hiệu", "Lý do", "Lịch sử chọn mã"],
        rows.map((s) => {
          const id = h("span", { class: "mono", tabindex: 0 }, s.strategy_id);
          hoverCard(id, () => [h("b", null, `${s.strategy_id} · ${s.trial_id || ""}`), ...Object.entries(s.params || {}).map(([k, v]) => hcRow(k, String(v)))]);
          const hist = s.history || {};
          return [
            id,
            HORIZON_LABEL[s.horizon] || s.horizon,
            s.holds ? h("span", { class: "chip solid" }, "Giữ") : h("span", { class: "chip" }, "Không"),
            s.holds ? fmtPct(s.weight, 0) : "—",
            s.rank != null && s.of != null ? `${s.rank}/${s.of}` : "—",
            h("span", { class: "mono small" }, s.signal && s.signal.name ? `${s.signal.name} = ${fmtSignal(s.signal.name, s.signal.value)}` : "—"),
            h("span", { class: "reason" }, s.reason_vi || ""),
            h("div", { class: "hist" }, wbar(hist.selected_share || 0, 1), h("span", { class: "muted small" }, `${fmtPct(hist.selected_share, 0)} / ${hist.n_decisions ?? "—"} kỳ`), h("span", { class: "muted small" }, hist.last_selected ? `gần nhất ${fmtDate(hist.last_selected)}` : "chưa từng chọn"))
          ];
        }),
        { numeric: [3, 4] }
      )
    );
  }
  draw();
  const excluded = (a.excluded_strategies || []).map((x) => h("div", { class: "notice warn" }, `${x.strategy_id}${x.horizon ? ` (${HORIZON_LABEL[x.horizon] || x.horizon})` : ""}: ${x.note_vi || "không tính cho mã này"}`));
  return h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", null, "Tín hiệu chiến lược"), segmented([["", "Mọi khung"], ...HORIZONS.map((hz) => [hz, HORIZON_LABEL[hz]])], "", (v) => ((state.hz = v), draw()), "Lọc theo khung")), holder, excluded);
}

// ---------- features ----------
const PCT_NAME = /(^|_)(ret|mom|vol(?!ume)|dist|dd|trend|pct|vs_)/;
function fmtFeature(f) {
  const v = f.value;
  if (v === null || v === undefined) return "—";
  if (f.unit === "pct") return fmtPct(v, 1);
  if (f.unit === "vnd") return fmtVndShort(v);
  if (f.unit === "ratio" || f.unit === "raw") return fmtNumVi(v, 2);
  if (/adv|value|vnd/.test(f.name)) return fmtVndShort(v);
  if (PCT_NAME.test(f.name) && Math.abs(v) < 20) return fmtPct(v, 1);
  return fmtNumVi(v, 2);
}
function featuresCard(a) {
  const rows = a.features || [];
  const pct = (v) => (v === null || v === undefined ? null : v > 1 ? v / 100 : v);
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "Đặc trưng"), h("span", { class: "muted small" }, "Thanh = vị trí của mã trong cả vũ trụ (phân vị)")),
    table(
      ["Đặc trưng", "Nhóm", "Giá trị", "Vị trí trong vũ trụ"],
      rows.map((f) => {
        const name = h("span", { class: "help", tabindex: 0 }, f.label_vi || f.name);
        if (f.help_vi) hoverCard(name, () => [h("b", null, f.label_vi || f.name), h("div", null, f.help_vi)]);
        const p = pct(f.pct_rank_universe);
        return [name, h("span", { class: "muted" }, f.group || ""), h("span", { class: "mono" }, fmtFeature(f)), p === null ? "—" : h("div", { class: "pr" }, wbar(p, 1), h("span", { class: "mono small" }, `${fmtPct(p, 0)}`))];
      }),
      { numeric: [2] }
    )
  );
}

// ---------- backtest ----------
function backtestCard(a) {
  const bt = a.backtest || {};
  const bh = bt.buy_hold || {};
  const rows = bt.by_strategy || [];
  const maxAbs = Math.max(0.0001, ...rows.map((r) => Math.abs(r.contribution_return || 0)));
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "Backtest"), h("span", { class: "chip soft" }, dataLabel(a))),
    h("p", { class: "muted small" }, bt.note_vi || "So sánh mua và giữ với phần đóng góp của từng chiến lược trong những kỳ nó đang giữ mã này. Đây là đối chiếu lịch sử, không phải dự báo."),
    h("div", { class: "kpis stat-grid" }, stat("Mua & giữ · CAGR", fmtPct(bh.cagr, 1, true)), stat("Biến động", fmtPct(bh.vol, 1)), stat("Sharpe", fmtNumVi(bh.sharpe, 2)), stat("Sụt giảm tối đa", fmtPct(bh.max_dd, 1))),
    table(
      ["Chiến lược", "Khung", "Số kỳ giữ", "Đóng góp", "Tỷ lệ kỳ lãi", "Giữ TB (kỳ)"],
      rows.map((r) => [
        h("span", { class: "mono" }, r.strategy_id),
        HORIZON_LABEL[r.horizon] || r.horizon,
        fmtInt(r.periods_held),
        h("div", { class: "pr" }, wbar(Math.abs(r.contribution_return || 0), maxAbs), h("span", { class: "mono small" }, fmtPct(r.contribution_return, 1, true))),
        r.hit_rate === null || r.hit_rate === undefined ? "—" : fmtPct(r.hit_rate, 0),
        fmtNumVi(r.avg_hold_periods, 1)
      ]),
      { numeric: [2, 4, 5] }
    )
  );
}

// ---------- risk and sizing ----------
function riskCard(a) {
  const book = (a.risk && a.risk.book) || {};
  const rows = HORIZONS.filter((hz) => book[hz]);
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "Rủi ro & quy mô theo sổ")),
    table(
      ["Sổ", "Vốn", "Tỷ trọng", "Số lượng", "Giá trị", "Giá cắt lỗ", "Rủi ro nếu cắt lỗ", "Chi phí ước tính"],
      rows.map((hz) => {
        const b = book[hz];
        return [
          HORIZON_LABEL[hz],
          fmtVndShort(b.capital_vnd),
          fmtPct(b.weight, 0),
          lotText(b, (a.price || {}).lot_size),
          `${fmtVnd(b.notional_vnd)} đ`,
          b.stop_price ? `${fmtVnd(b.stop_price)} (${fmtPct(b.stop_pct, 1)})` : "—",
          `${fmtVnd(b.risk_vnd)} đ`,
          `${fmtVnd(b.est_cost_vnd)} đ`
        ];
      }),
      { numeric: [1, 2, 3, 4, 5, 6, 7] }
    ),
    h("p", { class: "muted small" }, "Số lượng làm tròn xuống theo lô giao dịch; phần lẻ là lô lẻ (trượt giá cao hơn). Rủi ro = số cổ phiếu × (giá vào − giá cắt lỗ).")
  );
}

// ---------- data quality ----------
function qualityCard(a) {
  const q = a.quality || {};
  const gaps = q.gaps || [];
  const actions = q.corporate_actions || [];
  const item = (k, v, bad) => h("li", null, h("span", { class: `dot ${bad ? "st-failed" : "st-success"}` }), h("span", { class: "grow" }, k), h("b", { class: "mono" }, v));
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("h2", null, "Chất lượng dữ liệu của mã")),
    h(
      "ul",
      { class: "list q-list" },
      item("Phiên thiếu trong chuỗi giá", gaps.length ? `${gaps.length} (${gaps.join(", ")})` : "0", gaps.length > 0),
      item("Dòng bị loại khỏi chuỗi thực thi", String(q.exec_exclusions ?? 0), (q.exec_exclusions || 0) > 0),
      item("Phát hiện DQ trong 1 năm", String(q.dq_findings_1y ?? 0), (q.dq_findings_1y || 0) > 0),
      item("Sự kiện doanh nghiệp (điều chỉnh giá)", String(actions.length), false)
    ),
    actions.length ? table(["Ngày", "Loại", "Chi tiết"], actions.map((x) => [fmtDate(x.date), x.type || "—", x.ratio || x.detail || "—"])) : null
  );
}

/** All sections of an analysis as an array of nodes. ``onRerun`` restarts the analysis. */
export function renderAnalysis(a, onRerun) {
  return [header(a, onRerun), recommendationCard(a), chartCard(a), statsCard(a), signalsCard(a), featuresCard(a), backtestCard(a), riskCard(a), qualityCard(a), h("p", { class: "muted small disclaimer" }, (a.recommendation && a.recommendation.disclaimer_vi) || "Chỉ là khuyến nghị tham khảo, không phải lời mời mua bán. Bạn tự quyết định và tự đặt lệnh.")];
}
