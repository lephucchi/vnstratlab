// Tour: highlights real parts of the Console one by one with a spotlight overlay.
import { hooks } from "./ui.js";
import { api, h } from "./util.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function find(selector, tries = 30) {
  for (let i = 0; i < tries; i++) {
    const el = document.querySelector(selector);
    if (el && el.getBoundingClientRect().width > 0) return el;
    await wait(100);
  }
  return null;
}

const STEPS = [
  { sel: "#tracker", title: "Theo dõi lần chạy", text: "Ở mọi trang, ô này cho biết lần chạy đang diễn ra: tác vụ thứ mấy, đã chạy bao lâu. Bấm để mở lần chạy đó." },
  { sel: "#search-btn", title: "Bảng lệnh (Ctrl+K)", text: "Chạy quy trình, nhảy tới trang, lần chạy, mã cổ phiếu hay chiến lược. Bấm ? để xem mọi phím tắt." },
  { sel: "#term", title: "Terminal tích hợp (Ctrl+`)", text: "Mọi thao tác trên giao diện đều có lệnh tương đương. Gõ lệnh vnstratlab tại đây, Tab để gợi ý, Ctrl+C để hủy.", before: () => hooks.openTerminal && hooks.openTerminal() },
  { sel: ".pcards", route: "#/runs", title: "Chạy quy trình", text: "Mỗi thẻ có nút chạy và dòng lệnh CLI tương đương để sao chép hoặc mở trong terminal." },
  { sel: ".grid", route: "#/runs", title: "Lưới các lần chạy", text: "Mỗi cột là một lần chạy, mỗi hàng là một tác vụ. Rê chuột vào ô để xem trạng thái, thời gian và lỗi." },
  { sel: ".logs", route: "latest-run", title: "Log của tác vụ", text: "Lọc theo mức, tìm kiếm có tô sáng và nhảy giữa các kết quả, tự cuộn, sao chép từng dòng hoặc tải về." },
  { sel: ".cfg-layout", route: "#/cau-hinh", title: "Cấu hình", text: "Sửa tham số của riêng bạn: có kiểm tra tức thì, xem trước khác biệt và sao lưu trước khi lưu." },
];

let active = false;

export async function startTour() {
  if (active) return;
  active = true;
  let i = 0;
  const block = h("div", { class: "tour-block" });
  const hole = h("div", { class: "tour-hole" });
  const pop = h("div", { class: "tour-pop", role: "dialog", "aria-label": "Tham quan giao diện" });
  document.body.append(block, hole, pop);

  const end = () => {
    active = false;
    block.remove();
    hole.remove();
    pop.remove();
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", place);
  };
  const onKey = (e) => {
    if (e.key === "Escape") end();
    else if (e.key === "ArrowRight") go(i + 1);
    else if (e.key === "ArrowLeft") go(i - 1);
  };
  document.addEventListener("keydown", onKey, true);

  let target = null;
  function place() {
    if (!target) return;
    const r = target.getBoundingClientRect();
    const pad = 6;
    Object.assign(hole.style, { left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` });
    const pw = pop.offsetWidth || 340;
    const ph = pop.offsetHeight || 160;
    const below = r.bottom + 14 + ph < window.innerHeight;
    const top = below ? r.bottom + 14 : Math.max(8, r.top - ph - 14);
    const small = window.innerWidth < 560;
    pop.style.left = `${small ? 12 : Math.min(Math.max(12, r.left), window.innerWidth - pw - 12)}px`;
    pop.style.top = `${small ? Math.max(8, window.innerHeight - ph - 12) : Math.max(8, top)}px`;
  }
  window.addEventListener("resize", place);

  async function go(n) {
    if (n < 0) return;
    if (n >= STEPS.length) return end();
    i = n;
    const step = STEPS[n];
    if (step.before) step.before();
    if (step.route === "latest-run") {
      const res = await api("/runs?limit=1");
      const run = res.ok && res.body.runs[0];
      if (!run) return go(n + 1);
      if (!location.hash.startsWith("#/runs/")) location.hash = `#/runs/${run.run_id}`;
    } else if (step.route && location.hash !== step.route) location.hash = step.route;
    target = await find(step.sel);
    if (!active) return;
    if (!target) return go(n + 1);
    target.scrollIntoView({ block: "center", behavior: "instant" });
    pop.replaceChildren(
      h("div", { class: "step" }, `Bước ${n + 1}/${STEPS.length}`),
      h("h3", null, step.title),
      h("p", { class: "muted" }, step.text),
      h("div", { class: "btn-row" }, h("button", { class: "btn ghost sm", type: "button", disabled: n === 0, onclick: () => go(n - 1) }, "‹ Trước"), h("button", { class: "btn sm", type: "button", onclick: () => go(n + 1) }, n === STEPS.length - 1 ? "Kết thúc" : "Tiếp ›"), h("button", { class: "btn ghost sm", type: "button", onclick: end }, "Thoát"))
    );
    place();
    requestAnimationFrame(place);
  }
  await go(0);
}
