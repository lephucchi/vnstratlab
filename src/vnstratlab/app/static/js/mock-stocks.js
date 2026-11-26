// Fixture data for the stock pages (?mock=1): contract-shaped (docs/cards/stock-insight-api.md), SYNTHETIC.
// Everything is computed from the mock price series with data <= the decision date only (no lookahead),
// so recommendations, signals, history and chart markers agree with each other.

const NAMES = {
  ACB: "Ngân hàng Á Châu", BID: "BIDV", CTG: "VietinBank", HDB: "HDBank", LPB: "LPBank", MBB: "MB Bank", SHB: "SHB",
  STB: "Sacombank", TCB: "Techcombank", TPB: "TPBank", VCB: "Vietcombank", VIB: "VIB", VPB: "VPBank",
};
const LABEL = "SYNTHETIC — dữ liệu giả lập, không nói gì về thị trường thật";
const NOTE_VI = "Chưa qua lab chọn lọc (P1-T22): trung bình đều các chiến lược đang bật.";
const DISCLAIMER_VI = "Chỉ là khuyến nghị tham khảo, không phải lời mời mua bán. Bạn tự quyết định và tự đặt lệnh.";
const HORIZONS = ["short", "medium", "long"];
const RISK = { max_positions: 4, max_weight: 0.35, atr_stop_multiple: 2.0 };
const COST = { fee: 0.0015, tax: 0.001, slip_round: 0.001, slip_odd: 0.003 };

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const sd = (a) => {
  if (a.length < 2) return null;
  const m = mean(a);
  return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / (a.length - 1));
};
const tickOf = (p) => (p < 10000 ? 10 : p < 50000 ? 50 : 100);
const roundTick = (p) => Math.round(p / tickOf(p)) * tickOf(p);
const floorTick = (p) => Math.floor(p / tickOf(p)) * tickOf(p);
const pctText = (v, d = 1) => `${(v * 100).toLocaleString("vi-VN", { minimumFractionDigits: d, maximumFractionDigits: d })}%`;

// Strategy definitions: ``score`` ranks tickers (higher = better), ``value`` is the signal shown to the user.
const SDEF = [
  { id: "S01", horizon: "short", index: 0, name_vi: "Đảo chiều theo tuần", params: { lookback_days: 5, top_n: 3, group: "bank" }, top: 3, signal: "ret_5d", score: (m) => (m.ret5 === null ? null : -m.ret5), value: (m) => m.ret5, why: "mã giảm mạnh nhất tuần qua (kỳ vọng hồi lại)" },
  { id: "S02", horizon: "short", index: 0, name_vi: "Phá vỡ 20 phiên", params: { window: 20, top_n: 3 }, top: 3, signal: "close_vs_high20", score: (m) => m.vsHigh20, value: (m) => m.vsHigh20, why: "giá đang sát đỉnh 20 phiên" },
  { id: "S03", horizon: "short", index: 0, name_vi: "Quá bán trong xu hướng tăng", params: { rsi_window: 14, trend_window: 100, top_n: 3 }, top: 3, signal: "rsi14", score: (m) => (m.trend100 !== null && m.trend100 > 0 ? -m.rsi14 : null), value: (m) => m.rsi14, why: "RSI thấp nhất trong các mã còn trên SMA100" },
  { id: "S08", horizon: "medium", index: 0, name_vi: "Động lượng 12-1", params: { formation_months: 12, skip_months: 1 }, top: 4, signal: "mom_12_1", score: (m) => m.mom121, value: (m) => m.mom121, why: "động lượng 12 tháng (bỏ 1 tháng gần nhất) thuộc nhóm dẫn đầu" },
  { id: "S09", horizon: "medium", index: 0, name_vi: "Đảo chiều trung hạn", params: { lookback_months: 3, top_n: 3 }, top: 3, signal: "ret_63d", score: (m) => (m.ret63 === null ? null : -m.ret63), value: (m) => m.ret63, why: "mã yếu nhất 3 tháng qua (kỳ vọng hồi lại)" },
  { id: "S15", horizon: "medium", index: 0, name_vi: "Xu hướng ngành", params: { window_days: 63, top_n: 4 }, top: 4, signal: "ret_63d", score: (m) => m.ret63, value: (m) => m.ret63, why: "lợi suất 3 tháng thuộc nhóm dẫn đầu" },
  { id: "S14", horizon: "long", index: 0, name_vi: "Biến động thấp", params: { window_days: 250, top_n: 4 }, top: 4, signal: "vol_250d", score: (m) => (m.vol250 === null ? null : -m.vol250), value: (m) => m.vol250, why: "biến động 250 phiên thấp nhất" },
  { id: "S18", horizon: "long", index: 0, name_vi: "Lợi suất trên rủi ro", params: { window_days: 250, top_n: 5 }, top: 5, signal: "ret_250_vol", score: (m) => (m.ret250 !== null && m.vol250 ? m.ret250 / m.vol250 : null), value: (m) => (m.ret250 !== null && m.vol250 ? m.ret250 / m.vol250 : null), why: "lợi suất điều chỉnh theo biến động 250 phiên cao nhất" },
  { id: "S04", horizon: "long", index: 0, name_vi: "Xu hướng dài hạn SMA200", params: { window_days: 200, top_n: 4 }, top: 4, signal: "close_vs_sma200", score: (m) => m.trend200, value: (m) => m.trend200, why: "giá cao hơn SMA200 nhiều nhất" },
];
const STEP = { short: 5, medium: 21, long: 63 };
const N_DECISIONS = { short: 104, medium: 36, long: 12 };
const trialId = (d) => `${d.id}-${d.index}-${d.horizon}`;
const SIGNAL_FMT = { ret_5d: "pct", close_vs_high20: "pct", rsi14: "num", mom_12_1: "pct", ret_63d: "pct", vol_250d: "pct", ret_250_vol: "num", close_vs_sma200: "pct" };
const signalText = (d, v) => (v === null || v === undefined ? "n/a" : SIGNAL_FMT[d.signal] === "pct" ? pctText(v) : v.toLocaleString("vi-VN", { maximumFractionDigits: 1 }));

export function createStockMock({ TICKERS, DATES, PRICES, capitalFor, trialsTotal }) {
  const L = DATES.length - 1;
  const cache = new Map();

  function metricsAt(tk, i) {
    const key = `${tk}:${i}`;
    if (cache.has(key)) return cache.get(key);
    const c = PRICES[tk].close;
    const v = PRICES[tk].volume;
    const ret = (n) => (i - n >= 0 ? c[i] / c[i - n] - 1 : null);
    const rets = (n) => {
      const out = [];
      for (let j = Math.max(1, i - n + 1); j <= i; j++) out.push(c[j] / c[j - 1] - 1);
      return out;
    };
    const win = (n) => c.slice(Math.max(0, i - n + 1), i + 1);
    const vol = (n) => (i >= n ? sd(rets(n)) * Math.sqrt(252) : null);
    const sma = (n) => (i >= n - 1 ? mean(win(n)) : null);
    const diffs = [];
    for (let j = i - 13; j <= i; j++) if (j > 0) diffs.push(c[j] - c[j - 1]);
    const gain = mean(diffs.map((x) => Math.max(x, 0)));
    const loss = mean(diffs.map((x) => Math.max(-x, 0)));
    const h20 = Math.max(...win(20));
    const h250 = Math.max(...win(252));
    const l250 = Math.min(...win(252));
    let peak = -Infinity;
    let dd = 0;
    win(252).forEach((p) => ((peak = Math.max(peak, p)), (dd = Math.min(dd, p / peak - 1))));
    const adv = mean(c.slice(i - 19, i + 1).map((p, k) => p * 1000 * v[i - 19 + k]));
    const volAvg = mean(v.slice(i - 19, i + 1));
    const s100 = sma(100);
    const s200 = sma(200);
    const m = {
      close: c[i],
      ret5: ret(5), ret21: ret(21), ret63: ret(63), ret126: ret(126), ret250: ret(250),
      mom121: i >= 252 ? c[i - 21] / c[i - 252] - 1 : null,
      vol20: vol(20), vol60: vol(60), vol250: vol(250),
      vsHigh20: c[i] / h20 - 1,
      trend100: s100 ? c[i] / s100 - 1 : null,
      trend200: s200 ? c[i] / s200 - 1 : null,
      rsi14: loss === 0 ? 100 : 100 - 100 / (1 + gain / loss),
      high52: h250, low52: l250, maxDD1y: dd,
      atr14: mean(diffs.map(Math.abs)) * 1.25, // close-only mock: the real pipeline uses high/low
      adv20: adv,
      volRatio: v[i] / volAvg,
    };
    cache.set(key, m);
    return m;
  }

  // ---- strategy selection at a decision index (data <= index only)
  function pick(def, i) {
    const rows = TICKERS.map((tk) => {
      const m = metricsAt(tk, i);
      return { tk, score: def.score(m), value: def.value(m) };
    });
    const ok = rows.filter((r) => r.score !== null && Number.isFinite(r.score)).sort((a, b) => b.score - a.score || (a.tk < b.tk ? -1 : 1));
    const rank = new Map(ok.map((r, k) => [r.tk, { rank: k + 1, value: r.value }]));
    const selected = new Set(ok.slice(0, def.top).map((r) => r.tk));
    return { rank, selected, of: ok.length };
  }
  const decisionCache = new Map();
  function decisions(def) {
    const key = trialId(def);
    if (!decisionCache.has(key)) {
      const out = [];
      for (let k = N_DECISIONS[def.horizon] - 1; k >= 0; k--) {
        const idx = L - k * STEP[def.horizon];
        if (idx >= 252) out.push({ idx, ...pick(def, idx) });
      }
      decisionCache.set(key, out);
    }
    return decisionCache.get(key);
  }

  // ---- sizing (engine.md §7/§9 in miniature)
  function sizing(tk, weight, capital) {
    const m = metricsAt(tk, L);
    const last = roundTick(m.close * 1000);
    const lot = 100;
    const ceiling = roundTick(last * 1.07);
    const floor = roundTick(last * 0.93);
    const atr14 = Math.round(m.atr14 * 1000);
    const stop = floorTick(last - RISK.atr_stop_multiple * atr14);
    const target = weight * capital;
    const lotQty = Math.floor(target / (last * lot));
    const rest = target - lotQty * lot * last;
    const oddQty = Math.min(lot - 1, Math.max(0, Math.floor(rest / last)));
    const qty = lotQty * lot + oddQty;
    const notional = qty * last;
    const cost = Math.round(lotQty * lot * last * (COST.fee + COST.slip_round) + oddQty * last * (COST.fee + COST.slip_odd));
    return {
      last_close: last, lot_size: lot, lot_qty: lotQty, odd_qty: oddQty, notional_vnd: notional,
      entry_zone: { low: last, high: Math.min(ceiling, roundTick(last * (1 + COST.slip_round))) }, ceiling, floor,
      atr14, stop_price: stop, stop_pct: stop / last - 1, est_cost_vnd: cost, risk_vnd: Math.round(qty * (last - stop)),
    };
  }

  const evidenceDsr = (def) => {
    const seed = [...trialId(def)].reduce((a, ch) => a + ch.charCodeAt(0), 0);
    return Math.round((0.28 + ((seed * 37) % 71) / 100) * 100) / 100;
  };

  function recommendation(horizon, capitalOverride) {
    const defs = SDEF.filter((d) => d.horizon === horizon);
    const capital = capitalOverride || capitalFor(horizon);
    const picks = defs.map((d) => ({ d, ...pick(d, L) }));
    const raw = {};
    picks.forEach(({ d, selected }) => selected.forEach((tk) => (raw[tk] = (raw[tk] || 0) + 1 / d.top / defs.length)));
    const top = Object.entries(raw).sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, RISK.max_positions);
    const targets = top.map(([tk, w]) => {
      const weight = Math.min(w, RISK.max_weight);
      return {
        ticker: tk, weight, consensus: picks.filter((p) => p.selected.has(tk)).length,
        strategies: picks.filter((p) => p.selected.has(tk)).map((p) => p.d.id), ...sizing(tk, weight, capital),
      };
    });
    const dsr = Object.fromEntries(defs.map((d) => [trialId(d), evidenceDsr(d)]));
    return {
      asof: DATES[L], source: "synthetic", synthetic: true, label: LABEL, status: "preview", note_vi: NOTE_VI,
      horizon, book_capital_vnd: capital,
      strategies: picks.map(({ d, selected }) => ({ strategy_id: d.id, params: d.params, trial_id: trialId(d), registered: true, weights: Object.fromEntries([...selected].map((tk) => [tk, 1 / d.top])) })),
      targets, cash_weight: Math.max(0, 1 - targets.reduce((a, t) => a + t.weight, 0)),
      evidence: { trials_counted: trialsTotal(), dsr_by_strategy: dsr, gate1_pass: Object.keys(dsr).filter((k) => dsr[k] >= 0.95) },
    };
  }
  const allRecommendations = () => ({ horizons: Object.fromEntries(HORIZONS.map((hz) => [hz, recommendation(hz)])) });

  function stocksList() {
    return {
      tickers: TICKERS.map((tk) => {
        const c = PRICES[tk].close;
        return { ticker: tk, name: NAMES[tk] || tk, group: "Ngân hàng", last: DATES[L], last_close: roundTick(c[L] * 1000), change_1d: c[L] / c[L - 1] - 1, in_universe: true, signal_ok: tk !== "LPB" };
      }),
    };
  }

  // ---- price block shared by the analysis and the compare endpoints
  function priceBlock(tk) {
    const m = metricsAt(tk, L);
    const ytdIdx = DATES.findIndex((d) => d >= `${DATES[L].slice(0, 4)}-01-01`);
    const s = sizing(tk, 0, 1);
    return {
      last_close: s.last_close,
      change: { "1W": m.ret5, "1M": m.ret21, "3M": m.ret63, "6M": m.ret126, "1Y": m.ret250, YTD: PRICES[tk].close[L] / PRICES[tk].close[Math.max(0, ytdIdx - 1)] - 1 },
      high_52w: roundTick(m.high52 * 1000), low_52w: roundTick(m.low52 * 1000),
      dist_high_52w: m.close / m.high52 - 1, dist_low_52w: m.close / m.low52 - 1,
      vol_20d_ann: m.vol20, vol_60d_ann: m.vol60, max_dd_1y: m.maxDD1y, atr14: s.atr14,
      adv20_value_vnd: Math.round(m.adv20), volume_vs_adv20: m.volRatio, ceiling: s.ceiling, floor: s.floor, lot_size: 100,
    };
  }

  function recommendationBlock(tk) {
    const by = {};
    HORIZONS.forEach((hz) => {
      const rec = recommendation(hz);
      const defs = SDEF.filter((d) => d.horizon === hz);
      const target = rec.targets.find((t) => t.ticker === tk);
      const holding = defs.filter((d) => pick(d, L).selected.has(tk)).length;
      // "BÁN": it was selected by some strategy at the previous decision but by none now
      const prev = defs.filter((d) => {
        const ds = decisions(d);
        return ds.length > 1 && ds[ds.length - 2].selected.has(tk);
      }).length;
      let action = "KHÔNG";
      let reason = "Không chiến lược nào của khung này đang chọn mã.";
      if (target) {
        action = "MUA";
        reason = `${target.consensus}/${defs.length} chiến lược đồng thuận; tỷ trọng đề xuất ${pctText(target.weight, 0)} sau lớp quản trị rủi ro.`;
      } else if (holding > 0) {
        action = "GIỮ";
        reason = `${holding}/${defs.length} chiến lược còn chọn mã nhưng chưa vào danh mục mục tiêu (giới hạn số vị thế hoặc tỷ trọng).`;
      } else if (prev > 0) {
        action = "BÁN";
        reason = `Phiên quyết định trước ${prev} chiến lược còn chọn mã, nay không còn chiến lược nào chọn.`;
      }
      by[hz] = { action, consensus: target ? target.consensus : holding, of: defs.length, weight: target ? target.weight : 0, reason_vi: reason };
    });
    return { by_horizon: by, summary_vi: "", disclaimer_vi: DISCLAIMER_VI };
  }

  function features(tk) {
    const defs = [
      ["ret_5d", "Lợi suất 5 phiên", "Động lượng", (m) => m.ret5, "Thay đổi giá đóng cửa so với 5 phiên trước. Âm sâu là tín hiệu cho chiến lược đảo chiều."],
      ["ret_21d", "Lợi suất 21 phiên", "Động lượng", (m) => m.ret21, "Thay đổi giá so với khoảng một tháng trước."],
      ["mom_12_1", "Động lượng 12-1", "Động lượng", (m) => m.mom121, "Lợi suất 12 tháng, bỏ 1 tháng gần nhất để tránh hiệu ứng đảo chiều ngắn hạn."],
      ["vol_20d", "Biến động 20 phiên (năm)", "Biến động", (m) => m.vol20, "Độ lệch chuẩn lợi suất ngày 20 phiên, quy năm. Cao nghĩa là giá dao động mạnh."],
      ["vol_60d", "Biến động 60 phiên (năm)", "Biến động", (m) => m.vol60, "Như trên nhưng cửa sổ 60 phiên, ổn định hơn."],
      ["rsi14", "RSI 14 phiên", "Xu hướng", (m) => m.rsi14, "Chỉ số sức mạnh tương đối: dưới 30 là quá bán, trên 70 là quá mua."],
      ["close_vs_sma200", "Giá so với SMA200", "Xu hướng", (m) => m.trend200, "Dương nghĩa là giá đang trên đường trung bình 200 phiên (xu hướng tăng dài hạn)."],
      ["dist_high_52w", "Cách đỉnh 52 tuần", "Xu hướng", (m) => m.close / m.high52 - 1, "Khoảng cách tới đỉnh 52 tuần; 0% là đang ở đỉnh."],
      ["volume_ratio", "Khối lượng / TB 20 phiên", "Thanh khoản", (m) => m.volRatio, "Trên 1 nghĩa là phiên gần nhất giao dịch sôi động hơn thường lệ."],
      ["adv20_value", "GTGD trung bình 20 phiên", "Thanh khoản", (m) => m.adv20, "Giá trị giao dịch trung bình mỗi phiên (VND): thước đo mức dễ mua bán."],
    ];
    return defs.map(([name, label_vi, group, f, help_vi]) => {
      const all = TICKERS.map((t) => f(metricsAt(t, L)));
      const own = f(metricsAt(tk, L));
      return { name, label_vi, group, value: own, pct_rank_universe: all.filter((x) => x <= own).length / all.length, help_vi };
    });
  }

  function strategyRows(tk) {
    return SDEF.map((d) => {
      const now = pick(d, L);
      const ds = decisions(d);
      const sel = ds.filter((x) => x.selected.has(tk));
      const rk = now.rank.get(tk);
      const holds = now.selected.has(tk);
      return {
        strategy_id: d.id, params: d.params, horizon: d.horizon, trial_id: trialId(d), holds, weight: holds ? 1 / d.top : 0,
        rank: rk ? rk.rank : null, of: now.of, signal: { name: d.signal, value: rk ? rk.value : null, name_vi: d.name_vi },
        reason_vi: rk
          ? holds
            ? `Xếp hạng ${rk.rank}/${now.of} theo ${d.signal} (${signalText(d, rk.value)}): ${d.why}; nằm trong top ${d.top} nên được chọn.`
            : `Xếp hạng ${rk.rank}/${now.of} theo ${d.signal} (${signalText(d, rk.value)}), ngoài top ${d.top} nên không được chọn.`
          : "Mã không đủ điều kiện của chiến lược này (không qua bộ lọc xu hướng).",
        history: { selected_share: sel.length / ds.length, last_selected: sel.length ? DATES[sel[sel.length - 1].idx] : null, n_decisions: ds.length },
      };
    });
  }

  function backtest(tk) {
    const c = PRICES[tk].close;
    const n = 520;
    const seg = c.slice(-n);
    const r = seg.slice(1).map((x, k) => x / seg[k] - 1);
    let peak = -Infinity;
    let dd = 0;
    seg.forEach((p) => ((peak = Math.max(peak, p)), (dd = Math.min(dd, p / peak - 1))));
    const by = SDEF.map((d) => {
      const ds = decisions(d);
      let contrib = 0;
      let wins = 0;
      let held = 0;
      const runs = [];
      let cur = 0;
      ds.forEach((x, k) => {
        const next = k + 1 < ds.length ? ds[k + 1].idx : L;
        if (x.selected.has(tk) && next > x.idx) {
          const pr = c[next] / c[x.idx] - 1;
          contrib += pr / d.top;
          held += 1;
          if (pr > 0) wins += 1;
          cur += 1;
        } else if (cur) (runs.push(cur), (cur = 0));
      });
      if (cur) runs.push(cur);
      return { strategy_id: d.id, horizon: d.horizon, periods_held: held, contribution_return: contrib, hit_rate: held ? wins / held : null, avg_hold_periods: runs.length ? mean(runs) : null };
    });
    return { buy_hold: { cagr: (seg[seg.length - 1] / seg[0]) ** (252 / seg.length) - 1, vol: sd(r) * Math.sqrt(252), sharpe: (mean(r) / sd(r)) * Math.sqrt(252), max_dd: dd }, by_strategy: by };
  }

  function chart(tk) {
    const n = 520;
    const from = DATES.length - n;
    const markers = [];
    SDEF.forEach((d) => {
      let was = false;
      decisions(d).forEach((x) => {
        const is = x.selected.has(tk);
        if (x.idx >= from && is !== was) markers.push({ date: DATES[x.idx], strategy_id: d.id, side: is ? "in" : "out" });
        was = is;
      });
    });
    markers.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    return { dates: DATES.slice(from), close: PRICES[tk].close.slice(from).map((p) => roundTick(p * 1000)), volume: PRICES[tk].volume.slice(from), markers };
  }

  function analysis(tk, { runId, generatedAt }) {
    const rec = recommendationBlock(tk);
    const price = priceBlock(tk);
    const book = {};
    HORIZONS.forEach((hz) => {
      const t = recommendation(hz).targets.find((x) => x.ticker === tk);
      const capital = capitalFor(hz);
      const s = sizing(tk, t ? t.weight : 0, capital);
      book[hz] = { capital_vnd: capital, weight: t ? t.weight : 0, lot_qty: s.lot_qty, odd_qty: s.odd_qty, notional_vnd: s.notional_vnd, stop_price: s.stop_price, stop_pct: s.stop_pct, risk_vnd: s.risk_vnd, est_cost_vnd: s.est_cost_vnd };
    });
    const buys = HORIZONS.filter((hz) => rec.by_horizon[hz].action === "MUA");
    const HZ = { short: "ngắn hạn", medium: "trung hạn", long: "dài hạn" };
    rec.summary_vi = `${tk}: ${buys.length ? `khuyến nghị MUA ở khung ${buys.map((hz) => `${HZ[hz]} (${rec.by_horizon[hz].consensus}/${rec.by_horizon[hz].of} chiến lược đồng thuận)`).join(", ")}` : "chưa có khung nào khuyến nghị mua"}. Giá cách đỉnh 52 tuần ${pctText(price.dist_high_52w)}, biến động 60 phiên ${pctText(price.vol_60d_ann, 0)}, sụt giảm tối đa 1 năm ${pctText(price.max_dd_1y)}.`;
    const gaps = tk === "VPB" ? ["VPB-2026-10-30"] : [];
    return {
      ticker: tk, asof: DATES[L], source: "synthetic", synthetic: true, label: LABEL, run_id: runId, generated_at: generatedAt,
      price, features: features(tk), strategies: strategyRows(tk), backtest: backtest(tk), risk: { book },
      quality: { gaps, exec_exclusions: tk === "TCB" ? 1 : 0, dq_findings_1y: tk === "VPB" ? 2 : tk === "SHB" ? 1 : 0, corporate_actions: tk === "HDB" ? [{ date: "2026-06-12", type: "cổ tức cổ phiếu", ratio: "30%" }] : [] },
      recommendation: rec, chart: chart(tk),
    };
  }

  function compare(tickers) {
    return { asof: DATES[L], source: "synthetic", synthetic: true, label: LABEL, tickers: tickers.map((tk) => ({ ticker: tk, price: priceBlock(tk), recommendation: recommendationBlock(tk) })) };
  }

  return { allRecommendations, recommendation, stocksList, analysis, compare, has: (tk) => TICKERS.includes(tk) };
}
