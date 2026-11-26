// Hash router and shell: top bar (search, tracker, terminal, theme), drawer nav, terminal dock.
import { renderConfig } from "./config.js";
import { renderData } from "./data.js";
import { renderGuide } from "./guide.js";
import { installShortcuts, openPalette } from "./palette.js";
import { renderOverview } from "./overview.js";
import { renderResults } from "./results.js";
import { renderGrid } from "./runs.js";
import { renderRun } from "./runview.js";
import { renderStocks } from "./stocks.js";
import { renderStrategies } from "./strategies.js";
import { createTerminal } from "./terminal.js";
import { startTracker } from "./tracker.js";
import { hooks, hideHover } from "./ui.js";
import { MOCK, api, h, toggleTheme } from "./util.js";

const view = document.getElementById("view");
const nav = document.getElementById("nav");
const scrim = document.getElementById("scrim");
const toggle = document.getElementById("nav-toggle");
let cleanup = null;
let token = 0;

function setNavOpen(open) {
  nav.classList.toggle("open", open);
  scrim.classList.toggle("open", open);
  toggle.setAttribute("aria-expanded", String(open));
}
toggle.addEventListener("click", () => setNavOpen(!nav.classList.contains("open")));
scrim.addEventListener("click", () => setNavOpen(false));

const terminal = createTerminal(document.getElementById("term"), MOCK);
hooks.openTerminal = terminal.open;
document.getElementById("term-toggle").addEventListener("click", terminal.toggle);
document.getElementById("search-btn").addEventListener("click", openPalette);
document.getElementById("theme-btn").addEventListener("click", toggleTheme);
startTracker(document.getElementById("tracker"));
installShortcuts(terminal);
if (MOCK) document.getElementById("mock-tag").hidden = false;

async function latestResultsHref() {
  const { body } = await api("/runs?limit=20");
  const run = ((body && body.runs) || []).find((r) => r.pipeline === "demo" && r.status === "success");
  return run ? `#/ket-qua/${run.run_id}` : null;
}

async function route() {
  const mine = ++token;
  if (cleanup) {
    cleanup();
    cleanup = null;
  }
  hideHover();
  setNavOpen(false);
  const [page, arg] = (location.hash.replace(/^#\/?/, "") || "tong-quan").split("/");
  nav.querySelectorAll("a").forEach((a) => {
    const on = a.dataset.route === page;
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  const root = h("div", { class: "page" });
  view.replaceChildren(root);
  window.scrollTo(0, 0);
  let result;
  if (page === "tong-quan") result = renderOverview(root);
  else if (page === "huong-dan") result = renderGuide(root);
  else if (page === "runs") result = arg ? renderRun(root, arg) : renderGrid(root);
  else if (page === "du-lieu") result = renderData(root);
  else if (page === "ket-qua") result = renderResults(root, arg, latestResultsHref);
  else if (page === "co-phieu") result = renderStocks(root, arg);
  else if (page === "chien-luoc") result = renderStrategies(root);
  else if (page === "cau-hinh") result = renderConfig(root);
  else root.append(h("p", null, "Không tìm thấy trang. ", h("a", { href: "#/tong-quan" }, "Về Tổng quan")));
  let out;
  try {
    out = await result;
  } catch (err) {
    root.append(h("div", { class: "notice err", role: "alert" }, `Lỗi giao diện: ${err && err.message ? err.message : err}`));
    return;
  }
  if (typeof out !== "function") return;
  if (mine === token) cleanup = out;
  else out();
}

window.addEventListener("hashchange", route);
route();
