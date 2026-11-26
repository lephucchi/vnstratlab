// Hash router and shell.
import { renderGuide } from "./guide.js";
import { renderGrid, renderRun } from "./runs.js";
import { renderData } from "./data.js";
import { renderResults } from "./results.js";
import { api, h } from "./util.js";

const view = document.getElementById("view");
const nav = document.getElementById("nav");
const toggle = document.getElementById("nav-toggle");
let cleanup = null;
let token = 0;

function setNavOpen(open) {
  nav.classList.toggle("open", open);
  toggle.setAttribute("aria-expanded", String(open));
}
toggle.addEventListener("click", () => setNavOpen(!nav.classList.contains("open")));

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
  setNavOpen(false);
  const parts = (location.hash.replace(/^#\/?/, "") || "huong-dan").split("/");
  const [page, arg] = parts;
  nav.querySelectorAll("a").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === page || (page === "runs" && a.dataset.route === "runs"));
  });
  const root = h("div");
  view.replaceChildren(root);
  window.scrollTo(0, 0);
  let result;
  if (page === "huong-dan") result = renderGuide(root);
  else if (page === "runs") result = arg ? renderRun(root, arg) : renderGrid(root);
  else if (page === "du-lieu") result = renderData(root);
  else if (page === "ket-qua") result = renderResults(root, arg, latestResultsHref);
  else root.append(h("p", null, "Không tìm thấy trang. ", h("a", { href: "#/huong-dan" }, "Về Hướng dẫn")));
  const out = await result;
  if (typeof out !== "function") return;
  if (mine === token) cleanup = out;
  else out();
}

window.addEventListener("hashchange", route);
route();
