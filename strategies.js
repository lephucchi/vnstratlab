"use strict";
// Strategy catalogue shown on the intro site. Source of truth: docs/strategies.md on develop.
// Status is "design": parameters are proposals until the owner freezes them per card.
window.STRATEGIES = [
  {
    id: "S00", horizons: ["short"], card: "P1-T14", data: "prices, volume, fundamentals",
    name: { vi: "Điểm tổng hợp", en: "Composite score" },
    idea: {
      vi: "Chấm điểm mỗi mã trên 5 mặt cùng lúc rồi chỉ mua những mã điểm cao nhất mà đang có tín hiệu vào lệnh rõ ràng.",
      en: "Score every stock on five aspects at once, then buy only the top scorers that also show a clear entry trigger.",
    },
    rule: {
      vi: ["Xếp hạng 5 nhóm: xu hướng (giá so với MA20/MA50, lợi nhuận 60 phiên), sức mạnh so với trung vị nhóm, mức quá bán (−RSI14), khối lượng so với trung bình 20 phiên, định giá (chênh lệch P/B).", "Cộng có trọng số thành một điểm.", "Mua top_n mã điểm cao nhất có tín hiệu: vượt đỉnh 20 phiên, hoặc RSI14 < 35 khi giá vẫn trên MA50."],
      en: ["Rank five blocks: trend (close vs MA20/MA50, 60-day return), strength vs the group median, oversold (−RSI14), volume vs its 20-day average, valuation (P/B gap).", "Weighted sum gives one score.", "Buy the top_n scorers with a trigger: close above the 20-day high, or RSI14 < 35 while close is above MA50."],
    },
    params: ["{weights: equal, top_n: 3}", "{weights: trend_heavy, top_n: 3}"],
    basis: "Design doc (Layer 1)",
    risk: { vi: "Nhiều thành phần nên dễ bị \"chỉnh cho đẹp\": mỗi bộ trọng số là một trial, không tinh chỉnh thêm.", en: "Many moving parts invite tuning: each weight set is one trial, no further tuning." },
  },
  {
    id: "S01", horizons: ["short"], card: "P1-T15", data: "prices",
    name: { vi: "Đảo chiều tuần trong nhóm", en: "Weekly reversal within group" },
    idea: {
      vi: "Mã nào tuần trước giảm mạnh hơn cả nhóm thường hồi lại một phần trong tuần sau. Mua những mã \"tụt lại\" nhiều nhất.",
      en: "Stocks that fell more than their group last week tend to bounce back partly the next week. Buy the biggest laggards.",
    },
    rule: {
      vi: ["Lợi nhuận tuần trước của mỗi mã trừ trung vị của nhóm.", "Mua n mã thấp nhất, chia đều."],
      en: ["Last week's return of each stock minus the group median.", "Buy the n lowest, equal weight."],
    },
    params: ["{n: 2}", "{n: 3}"],
    basis: "Jegadeesh (1990), short-term reversal",
    risk: { vi: "Giao dịch nhiều nên nhạy với phí: phải sống sót qua stress test phí ×2.", en: "Trades often, so it is cost-sensitive: must survive the ×2 cost stress test." },
  },
  {
    id: "S02", horizons: ["short"], card: "P1-T15", data: "prices, volume",
    name: { vi: "Vượt đỉnh 20 phiên kèm khối lượng", en: "20-day breakout with volume" },
    idea: {
      vi: "Giá đóng cửa vượt đỉnh gần đây với khối lượng lớn bất thường thường báo hiệu một nhịp tăng mới.",
      en: "A close above the recent high on unusually heavy volume often marks the start of a new leg up.",
    },
    rule: {
      vi: ["Giá đóng cửa > giá đóng cửa cao nhất của lookback phiên trước.", "Và khối lượng > vol_mult × khối lượng trung bình 20 phiên.", "Chia đều cho các tín hiệu, tối đa max_n mã."],
      en: ["Close > highest close of the previous lookback sessions.", "And volume > vol_mult × 20-day average volume.", "Equal weight across signals, at most max_n stocks."],
    },
    params: ["{lookback: 20, vol_mult: 1.5, max_n: 3}"],
    basis: "Brock, Lakonishok & LeBaron (1992)",
    risk: { vi: "Mã vượt đỉnh hay mở cửa sát giá trần nên lệnh mua có thể không khớp; engine ghi lại các lệnh bị chặn.", en: "Breakouts often open near the ceiling, so buys may not fill; the engine logs every blocked order." },
  },
  {
    id: "S03", horizons: ["short"], card: "P1-T15", data: "prices",
    name: { vi: "Quá bán trong xu hướng tăng", en: "Oversold in uptrend" },
    idea: {
      vi: "Mua nhịp điều chỉnh ngắn của một mã vẫn đang trong xu hướng tăng dài hơn.",
      en: "Buy a short pullback in a stock that is still in a longer uptrend.",
    },
    rule: {
      vi: ["RSI(rsi_len) < rsi_max (quá bán).", "Và giá đóng cửa > MA(ma_len) (xu hướng còn tăng).", "Mua tối đa max_n mã có RSI thấp nhất."],
      en: ["RSI(rsi_len) < rsi_max (oversold).", "And close > MA(ma_len) (trend still up).", "Buy up to max_n stocks with the lowest RSI."],
    },
    params: ["{rsi_len: 2, rsi_max: 10, ma_len: 50, max_n: 3}", "{rsi_len: 14, rsi_max: 30, ma_len: 50, max_n: 3}"],
    basis: "Jegadeesh (1990); Moskowitz, Ooi & Pedersen (2012)",
  },
  {
    id: "S04", horizons: ["short"], card: "P1-T16", data: "prices",
    name: { vi: "Cặp ngân hàng (chỉ mua)", en: "Long-only bank pairs" },
    idea: {
      vi: "Hai ngân hàng thường đi cùng nhau. Khi một mã bị bỏ lại quá xa so với \"cặp\" của nó, mua mã bị tụt lại và chờ khoảng cách thu hẹp.",
      en: "Two banks usually move together. When one falls too far behind its pair, buy the laggard and wait for the gap to close.",
    },
    rule: {
      vi: ["Trong form phiên, chọn k cặp có tương quan lợi nhuận cao nhất.", "Spread = log tỷ lệ giá, chuẩn hóa z-score.", "Khi |z| > entry_z: mua mã tụt lại (không bán khống).", "Thoát khi z cắt 0 hoặc sau max_hold phiên."],
      en: ["Over form sessions, pick the k pairs with the highest return correlation.", "Spread = log price ratio, z-scored.", "When |z| > entry_z: buy the laggard (no short leg).", "Exit when z crosses 0 or after max_hold sessions."],
    },
    params: ["{form: 250, k: 5, entry_z: 2.0, max_hold: 10}"],
    basis: "Gatev, Goetzmann & Rouwenhorst (2006)",
    risk: { vi: "Không có chân bán khống nên thực chất gần với chiến lược đảo chiều; phải đọc kết quả theo cách đó.", en: "Without the short leg it behaves closer to a reversal strategy and must be read that way." },
  },
  {
    id: "S05", horizons: ["short"], card: "P1-T16", data: "prices",
    name: { vi: "Hồi quy phần dư", en: "Residual mean reversion" },
    idea: {
      vi: "Tách phần biến động riêng của mỗi mã khỏi biến động chung của cả nhóm ngân hàng. Mã nào giảm \"riêng\" quá mức thì mua.",
      en: "Separate each stock's own move from the move of the whole bank group. Buy stocks whose own move has dropped too far.",
    },
    rule: {
      vi: ["Hồi quy lợi nhuận ngày của mỗi mã theo lợi nhuận nhóm trong window phiên.", "Cộng dồn phần dư, chuẩn hóa z-score.", "Mua n mã âm nhất, dưới −entry_z."],
      en: ["Regress each stock's daily returns on the group return over window sessions.", "Cumulative residual, z-scored.", "Buy the n most negative below −entry_z."],
    },
    params: ["{window: 60, entry_z: 1.5, n: 2}"],
    basis: "Avellaneda & Lee (2010)",
  },
  {
    id: "S06", horizons: ["short"], card: "P1-T19", data: "foreign net buy/sell", blocked: true,
    name: { vi: "Dòng tiền khối ngoại", en: "Foreign flow" },
    idea: {
      vi: "Theo dấu nhà đầu tư nước ngoài: mua những mã họ mua ròng mạnh nhất gần đây.",
      en: "Follow foreign investors: buy the stocks they have been net buying the most.",
    },
    rule: {
      vi: ["Giá trị mua ròng khối ngoại 5 phiên / giá trị giao dịch.", "Mua top n."],
      en: ["5-day foreign net buy / traded value.", "Buy the top n."],
    },
    params: [],
    basis: "—",
    risk: { vi: "Đang tắt: chờ card P1-T04 tìm được nguồn dữ liệu khối ngoại miễn phí đạt yêu cầu.", en: "Disabled until card P1-T04 finds an acceptable free foreign-flow source." },
  },
  {
    id: "S08", horizons: ["medium"], card: "P1-T17", data: "prices",
    name: { vi: "Động lượng 6–12 tháng", en: "Cross-sectional momentum" },
    idea: {
      vi: "Mã tăng tốt nhất trong 6–12 tháng qua thường tiếp tục mạnh thêm một thời gian.",
      en: "Stocks that did best over the past 6–12 months tend to keep outperforming for a while.",
    },
    rule: {
      vi: ["Lợi nhuận từ t−L tháng đến t−1 tháng (bỏ tháng gần nhất).", "Mua top n."],
      en: ["Return from t−L months to t−1 month (skip the latest month).", "Buy the top n."],
    },
    params: ["{L_months: 6, n: 4}", "{L_months: 12, n: 4}"],
    basis: "Jegadeesh & Titman (1993)",
    risk: { vi: "13 ngân hàng rất tương quan nên chênh lệch giữa mã mạnh và yếu nhỏ; S09 kiểm tra giả thuyết ngược lại.", en: "13 highly correlated banks give small spreads; S09 tests the opposite." },
  },
  {
    id: "S09", horizons: ["medium"], card: "P1-T17", data: "prices",
    name: { vi: "Đảo chiều trung hạn", en: "Medium-term reversal" },
    idea: {
      vi: "Ngược với S08: mua mã yếu nhất, vì một số nghiên cứu về thị trường Việt Nam thấy hiệu ứng đảo chiều thay vì động lượng.",
      en: "The opposite of S08: buy the weakest, because several Vietnamese market studies find reversal rather than momentum.",
    },
    rule: {
      vi: ["Cùng cách xếp hạng như S08.", "Mua n mã đứng cuối."],
      en: ["Same ranking as S08.", "Buy the bottom n."],
    },
    params: ["{L_months: 6, n: 4}"],
    basis: { vi: "Các nghiên cứu thị trường Việt Nam; lab quyết định S08 hay S09 sống sót", en: "Vietnamese market studies; the lab decides whether S08 or S09 survives" },
  },
  {
    id: "S10", horizons: ["medium", "long"], card: "P1-T18", data: "equity, net income, prices",
    name: { vi: "P/B so với P/B hợp lý theo ROE", en: "P/B vs ROE-justified P/B" },
    idea: {
      vi: "Ngân hàng sinh lời cao (ROE cao) đáng được định giá P/B cao hơn. Mua những mã có P/B thấp nhất so với mức hợp lý theo ROE.",
      en: "A bank with high ROE deserves a higher P/B. Buy the ones trading furthest below their ROE-justified P/B.",
    },
    rule: {
      vi: ["P/B hợp lý = (ROE − g) / (r − g).", "Khoảng cách = (hợp lý − thực tế) / thực tế, dùng BCTC theo ngày công bố.", "Mua n mã có khoảng cách lớn nhất."],
      en: ["Justified P/B = (ROE − g) / (r − g).", "Gap = (justified − actual) / actual, using fundamentals by publish date.", "Buy the n largest gaps."],
    },
    params: ["{r: 0.14, g: 0.06, n: 3}"],
    basis: "Gordon (1959) growth model applied to banks",
    risk: { vi: "r và g là giả định, được ghi rõ trong báo cáo. Phụ thuộc chất lượng dữ liệu BCTC (P1-T07).", en: "r and g are stated assumptions. Depends on fundamentals data quality (P1-T07)." },
  },
  {
    id: "S11", horizons: ["medium", "long"], card: "P1-T18", data: "net income, prices",
    name: { vi: "Tỷ suất lợi nhuận (E/P)", en: "Earnings yield (E/P)" },
    idea: {
      vi: "Mã \"rẻ\" so với lợi nhuận nó tạo ra thường có lợi suất tốt hơn về dài hạn.",
      en: "Stocks that are cheap relative to their earnings tend to do better over time.",
    },
    rule: {
      vi: ["Lợi nhuận ròng 4 quý gần nhất / vốn hóa.", "Mua top n."],
      en: ["Trailing 4-quarter net income / market cap.", "Buy the top n."],
    },
    params: ["{n: 3}", "{n: 4}"],
    basis: "Value effect; Huang et al. (2023) for Vietnam",
  },
  {
    id: "S12", horizons: ["medium", "long"], card: "P1-T18", data: "ROE, NPL, NPL coverage",
    name: { vi: "Chất lượng tài sản và sinh lời", en: "Asset quality and profitability" },
    idea: {
      vi: "Chọn ngân hàng \"khỏe\": sinh lời cao, ít nợ xấu và trích lập dự phòng đầy đủ.",
      en: "Pick healthy banks: high profitability, low bad debt, well-covered by provisions.",
    },
    rule: {
      vi: ["Trung bình hạng của: ROE cao, tỷ lệ nợ xấu thấp, tỷ lệ bao phủ nợ xấu cao.", "Mua top n."],
      en: ["Average rank of high ROE, low NPL ratio, high NPL coverage.", "Buy the top n."],
    },
    params: ["{n: 3}"],
    basis: "Fama & French (2015), profitability",
    risk: { vi: "Dữ liệu nợ xấu từ nguồn miễn phí có thể thiếu hoặc trễ; chiến lược tự tắt nếu độ phủ < 90%.", en: "Free NPL data may be missing or late; the strategy turns off below 90% coverage." },
  },
  {
    id: "S13", horizons: ["medium"], card: "P1-T17", data: "S08 and S10 ranks",
    name: { vi: "Giá trị + động lượng", en: "Value + momentum" },
    idea: {
      vi: "Kết hợp \"rẻ\" (S10) và \"đang mạnh\" (S08): hai yếu tố này thường bù trừ nhau nên ổn định hơn từng cái riêng lẻ.",
      en: "Combine cheap (S10) and strong (S08): the two tend to offset each other, so the mix is steadier than either alone.",
    },
    rule: {
      vi: ["Trung bình hạng của S08 và S10.", "Mua top n."],
      en: ["Average of the S08 and S10 ranks.", "Buy the top n."],
    },
    params: ["{n: 4}"],
    basis: "Asness, Moskowitz & Pedersen (2013)",
  },
  {
    id: "S14", horizons: ["medium"], card: "P1-T19", data: "prices",
    name: { vi: "Biến động thấp", en: "Low volatility" },
    idea: {
      vi: "Mã ít biến động thường cho lợi nhuận điều chỉnh theo rủi ro tốt hơn kỳ vọng.",
      en: "Calmer stocks tend to deliver better risk-adjusted returns than expected.",
    },
    rule: {
      vi: ["Độ biến động window phiên.", "Mua n mã biến động thấp nhất, chia đều."],
      en: ["Volatility over window sessions.", "Buy the n lowest, equal weight."],
    },
    params: ["{window: 60, n: 4}"],
    basis: "Frazzini & Pedersen (2014)",
  },
  {
    id: "S15", horizons: ["medium"], card: "P1-T19", data: "prices",
    name: { vi: "Lọc xu hướng ngành", en: "Sector trend filter" },
    idea: {
      vi: "Chỉ nắm giữ khi cả nhóm ngân hàng đang trong xu hướng tăng; nếu không thì giữ tiền mặt.",
      en: "Hold the banks only while the whole group is trending up; otherwise stay in cash.",
    },
    rule: {
      vi: ["Nếu lợi nhuận lookback tháng của nhóm (chia đều) > 0: nắm giữ tất cả, chia đều.", "Ngược lại: giữ tiền mặt."],
      en: ["If the equal-weight group's lookback-month return > 0: hold all members equally.", "Otherwise: hold cash."],
    },
    params: ["{lookback_months: 12}", "{lookback_months: 6}"],
    basis: "Moskowitz, Ooi & Pedersen (2012), time-series momentum",
  },
  {
    id: "S17", horizons: ["short", "medium", "long"], card: "P1-T14", data: "membership",
    name: { vi: "Chia đều", en: "Equal weight" },
    idea: {
      vi: "Mua đều tất cả các mã trong danh sách. Đơn giản nhưng khó thắng, nên đây là thước đo mà mọi chiến lược khác phải vượt qua.",
      en: "Buy every stock in the universe in equal amounts. Simple but hard to beat, so it is the yardstick every other strategy must clear.",
    },
    rule: {
      vi: ["1/N cho mỗi mã đang thuộc danh sách.", "Bản thực thi dùng thêm lô lẻ để sát tỷ trọng."],
      en: ["1/N across current universe members.", "The executable version uses odd lots to stay close to the weights."],
    },
    params: [],
    basis: "DeMiguel, Garlappi & Uppal (2009)",
    risk: { vi: "Vừa là benchmark ở cổng 2, vừa là chiến lược được chọn. Khi không chiến lược nào qua cổng, khuyến nghị chính là S17 (hold_benchmark).", en: "Both the gate-2 benchmark and a selectable strategy. When nothing passes the gates, the recommendation is S17 (hold_benchmark)." },
  },
  {
    id: "S18", horizons: ["long"], card: "P1-T19", data: "returns",
    name: { vi: "Hierarchical Risk Parity", en: "Hierarchical Risk Parity" },
    idea: {
      vi: "Chia vốn sao cho mỗi nhóm mã có hành vi giống nhau gánh phần rủi ro tương đương, thay vì chia đều theo tiền.",
      en: "Split capital so that each cluster of similar stocks carries a similar share of risk, rather than an equal share of money.",
    },
    rule: {
      vi: ["Phân cụm các mã theo tương quan lợi nhuận ngày 1 năm.", "Phân bổ rủi ro theo cây phân cụm."],
      en: ["Cluster stocks by 1-year daily return correlation.", "Allocate risk down the cluster tree."],
    },
    params: [],
    basis: "López de Prado (2016)",
  },
];

window.HORIZON_NOTES = {
  short: { vi: "Quyết định mỗi tuần (thứ Sáu), giữ khoảng 1 tuần.", en: "Decides weekly (Friday), holds about 1 week." },
  medium: { vi: "Quyết định mỗi tháng, chia 3 phần vốn luân phiên, giữ 3–6 tháng.", en: "Decides monthly in 3 rotating tranches, holds 3–6 months." },
  long: { vi: "Quyết định mỗi tháng, 12 phần vốn luân phiên, giữ khoảng 1 năm. Ít kết quả độc lập nên mặc định chia đều giữa các chiến lược có cơ sở kinh tế; lab chủ yếu dùng để loại chiến lược hỏng.", en: "Decides monthly in 12 rotating tranches, holds about 1 year. Few independent outcomes, so it defaults to equal weight across economically grounded strategies; the lab mainly drops broken ones." },
};
