// Page 1: Hướng dẫn. A six-step pipeline diagram you can play or step through.
import { QUICK_START, STEPS } from "./guide-data.js";
import { cliLine, pageHead } from "./ui.js";
import { h, reducedMotion } from "./util.js";
import { startPipeline } from "./runs.js";
import { startTour } from "./tour.js";

const FRAME_MS = 2600;

function connector(i, active) {
  // Arrow between node i-1 and node i: done (solid), flowing (animated) or idle.
  const state = i < active ? "done" : i === active ? "flowing" : "idle";
  return h(
    "svg",
    { class: `link link-${state}`, viewBox: "0 0 40 12", "aria-hidden": "true" },
    h("line", { x1: 2, y1: 6, x2: 32, y2: 6 }),
    h("path", { d: "M30 1 L38 6 L30 11" })
  );
}

export function renderGuide(root) {
  const reduced = reducedMotion();
  let active = 0;
  let timer = null;

  const diagram = h("div", { class: "pipe", role: "group", "aria-label": "Sơ đồ quy trình" });
  const card = h("section", { class: "card frame", "aria-live": "polite" });
  const playBtn = h("button", { class: "btn", type: "button" }, "Phát");
  const prevBtn = h("button", { class: "btn ghost", type: "button" }, "‹ Trước");
  const nextBtn = h("button", { class: "btn ghost", type: "button" }, "Sau ›");
  const counter = h("span", { class: "chip soft" });

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    playBtn.textContent = "Phát";
  }

  function draw() {
    diagram.replaceChildren(
      ...STEPS.flatMap((s, i) => [
        i > 0 ? connector(i, active) : null,
        h(
          "button",
          {
            class: `node${i === active ? " active" : ""}${i < active ? " done" : ""}`,
            type: "button",
            "aria-current": i === active ? "step" : null,
            onclick: () => {
              stop();
              go(i);
            },
          },
          h("span", { class: "n" }, String(i + 1)),
          s.name
        ),
      ]).filter(Boolean)
    );
    const s = STEPS[active];
    card.replaceChildren(
      h("span", { class: "counter" }, `Khung ${active + 1}/${STEPS.length}`),
      h("h2", null, `${active + 1}. ${s.name}`),
      h("p", null, s.what),
      cliLine(s.command),
      h("h3", { class: "watch-title" }, "Cần để ý"),
      h("ul", { class: "watch" }, s.watch.map((w) => h("li", null, w)))
    );
    card.classList.remove("enter");
    void card.offsetWidth; // restart the entrance animation
    card.classList.add("enter");
    counter.textContent = `Khung ${active + 1}/${STEPS.length}`;
    prevBtn.disabled = active === 0;
    nextBtn.disabled = active === STEPS.length - 1;
  }

  function go(i) {
    active = Math.min(Math.max(i, 0), STEPS.length - 1);
    draw();
  }

  playBtn.addEventListener("click", () => {
    if (timer) return stop();
    if (active === STEPS.length - 1) go(0);
    playBtn.textContent = "Dừng";
    timer = setInterval(() => {
      if (active >= STEPS.length - 1) return stop();
      go(active + 1);
    }, FRAME_MS);
  });
  prevBtn.addEventListener("click", () => {
    stop();
    go(active - 1);
  });
  nextBtn.addEventListener("click", () => {
    stop();
    go(active + 1);
  });

  const demoBtn = h("button", { class: "btn", type: "button" }, "Chạy demo ngay");
  const tourBtn = h("button", { class: "btn ghost", type: "button", onclick: () => startTour() }, "Tham quan giao diện (Tour)");
  demoBtn.addEventListener("click", async () => {
    demoBtn.disabled = true;
    await startPipeline("demo");
    demoBtn.disabled = false;
  });

  root.append(
    pageHead("Hướng dẫn", "Từ dữ liệu giá đến báo cáo: sáu bước, mỗi bước có lệnh và những điểm cần để ý", tourBtn),
    diagram,
    h(
      "div",
      { class: "controls" },
      reduced ? null : playBtn,
      prevBtn,
      nextBtn,
      counter,
      reduced ? h("span", { class: "muted small" }, "Giảm chuyển động đang bật: dùng nút Trước/Sau để xem từng khung.") : null
    ),
    card,
    h(
      "section",
      { class: "card quick" },
      h("h2", null, "Bắt đầu nhanh"),
      h("ol", { class: "quick-steps" }, QUICK_START.map((t) => h("li", null, t))),
      h("div", { class: "btn-row" }, demoBtn),
      cliLine("vnstratlab demo")
    )
  );
  draw();
  return stop;
}
