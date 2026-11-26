// Cấu hình: forms generated from the API's `editable` fields (contract: GET/PUT /api/config,
// POST /api/config/validate and /api/config/reset). Live validation, diff preview, save + backup, reset per field.
import { emptyState, pageHead, toast } from "./ui.js";
import { api, debounce, errorBox, fmtInt, h, post, put } from "./util.js";

const GROUPS = [["books", "Vốn theo book"], ["costs", "Chi phí"], ["risk", "Rủi ro"], ["data", "Dữ liệu"], ["engine", "Engine"]];
const getPath = (o, p) => p.split(".").reduce((a, k) => (a === undefined || a === null ? undefined : a[k]), o);
const round = (v) => Math.round(v * 1e8) / 1e8;

/** Display text of a stored value for a field (pct is stored as a fraction, shown in %). */
function show(f, v) {
  if (v === null || v === undefined) return "tắt";
  if (f.type === "pct") return `${+(v * 100).toFixed(4)}%`;
  if (f.type === "int" && f.unit === "VND") return `${fmtInt(v)} ₫`;
  return String(v);
}
const toInput = (f, v) => (v === null || v === undefined ? "" : f.type === "pct" ? String(+(v * 100).toFixed(4)) : String(v));
function fromInput(f, text) {
  if (f.type === "enum" || f.type === "date") return text;
  if (text.trim() === "") return f.nullable ? null : NaN; // nullable fields: null = off
  const n = Number(text);
  return f.type === "pct" ? round(n / 100) : n;
}

export async function renderConfig(root) {
  root.append(pageHead("Cấu hình", "Chỉnh các tham số của riêng bạn, có kiểm tra và sao lưu"));
  const res = await api("/config");
  if (!res.ok) {
    root.append(res.status === 404 ? emptyState("Máy chủ chưa có /api/config", "Trang này cần API cấu hình (card X-console-api). Dùng ?mock=1 để xem giao diện với dữ liệu mẫu.") : errorBox("Không tải được cấu hình."));
    return;
  }
  const cfg = res.body;
  const edits = {}; // path -> new value
  const resets = new Set(); // path -> go back to default (removes the override)
  const inputs = {};
  const errEls = {};
  let problems = [];
  let diff = [];

  const side = h("aside", { class: "card cfg-side" });
  const banner = h("div", { class: "notice" }, "Thay đổi ở đây áp dụng cho các lần chạy của riêng bạn (ghi vào ", h("code", null, cfg.file), cfg.exists ? ")." : ", sẽ được tạo khi lưu).");

  const changedCount = () => Object.keys(edits).length + resets.size;
  const cur = (f) => getPath(cfg.effective, f.path);
  const def = (f) => getPath(cfg.defaults, f.path);

  function paintField(f) {
    const inp = inputs[f.path];
    const changed = f.path in edits || resets.has(f.path);
    inp.classList.toggle("changed", changed);
    const bad = problems.filter((p) => p.startsWith(`${f.path}:`));
    inp.classList.toggle("invalid", bad.length > 0);
    errEls[f.path].textContent = bad.map((p) => p.slice(f.path.length + 1).trim()).join("; ");
    const reset = inp.closest(".field").querySelector(".reset");
    reset.hidden = resets.has(f.path) || !(cur(f) !== def(f) || f.path in edits);
  }

  const validate = debounce(async () => {
    if (!Object.keys(edits).length) {
      problems = [];
      diff = [];
      paintAll();
      return paintSide();
    }
    const r = await post("/config/validate", { changes: edits });
    if (r.ok && r.body) {
      problems = r.body.problems || [];
      diff = r.body.diff || [];
    } else problems = [`Không kiểm tra được (mã ${r.status})`];
    paintAll();
    paintSide();
  }, 350);

  function paintAll() {
    cfg.editable.forEach(paintField);
  }

  function onEdit(f, value) {
    resets.delete(f.path);
    if (value === cur(f) || (value === null && cur(f) === undefined)) delete edits[f.path];
    else edits[f.path] = value;
    paintField(f);
    paintSide();
    validate();
  }

  function control(f) {
    const v = cur(f);
    let el;
    if (f.type === "enum") {
      el = h("select", { id: `f-${f.path}`, onchange: () => onEdit(f, el.value) }, (f.options || []).map((o) => h("option", { value: o }, String(o))));
      el.value = v;
    } else if (f.type === "bool") {
      el = h("select", { id: `f-${f.path}`, onchange: () => onEdit(f, el.value === "true") }, h("option", { value: "true" }, "Bật"), h("option", { value: "false" }, "Tắt"));
      el.value = String(v);
    } else if (f.type === "date") {
      el = h("input", { id: `f-${f.path}`, type: "date", value: v || "", oninput: () => onEdit(f, el.value) });
    } else {
      const k = f.type === "pct" ? 100 : 1;
      el = h("input", {
        id: `f-${f.path}`, type: "number", inputmode: "decimal", value: toInput(f, v),
        min: f.min !== undefined ? +(f.min * k).toFixed(6) : null, max: f.max !== undefined ? +(f.max * k).toFixed(6) : null, step: f.step !== undefined ? +(f.step * k).toFixed(6) : "any", placeholder: f.nullable ? "tắt (để trống)" : null, // min_exclusive/max_exclusive: enforced by the server, shown inline
       
        oninput: () => onEdit(f, fromInput(f, el.value)),
      });
    }
    inputs[f.path] = el;
    return el;
  }

  function setInput(f, value) {
    const el = inputs[f.path];
    if (f.type === "enum" || f.type === "date") el.value = value ?? "";
    else if (f.type === "bool") el.value = String(value);
    else el.value = toInput(f, value);
  }

  function field(f) {
    const reset = h("button", { class: "reset", type: "button", hidden: true, onclick: () => {
      delete edits[f.path];
      if (cur(f) !== def(f)) resets.add(f.path);
      else resets.delete(f.path);
      setInput(f, def(f));
      paintField(f);
      paintSide();
      validate();
    } }, "Khôi phục mặc định");
    const err = h("div", { class: "err" });
    errEls[f.path] = err;
    return h(
      "div",
      { class: "field" },
      h("label", { class: "lbl", for: `f-${f.path}` }, f.label_vi, f.nullable ? h("span", { class: "chip soft" }, "có thể tắt") : null, f.verify ? h("span", { class: "badge-verify", title: "Giá trị cần kiểm chứng với nguồn chính thức hoặc công ty chứng khoán của bạn" }, "[VERIFY]") : null),
      h("div", { class: "row" }, control(f), f.unit && f.type !== "pct" ? h("span", { class: "unit" }, f.unit) : f.type === "pct" ? h("span", { class: "unit" }, "%") : null),
      h("div", { class: "hint" }, f.help_vi, " ", h("span", { class: "cur" }, `Mặc định: ${show(f, def(f))} · hiện tại: ${show(f, cur(f))}`)),
      f.frozen_note_vi ? h("div", { class: "hint" }, `Khóa: ${f.frozen_note_vi}`) : null,
      err,
      reset
    );
  }

  function paintSide() {
    const n = changedCount();
    const lines = [
      ...diff.map((d) => [d.path, d.from, d.to]),
      ...[...resets].map((p) => {
        const f = cfg.editable.find((x) => x.path === p);
        return [p, cur(f), def(f), true];
      }),
    ];
    const fmt = (path, v) => {
      const f = cfg.editable.find((x) => x.path === path);
      return f ? show(f, v) : String(v);
    };
    const unmatched = problems.filter((p) => !cfg.editable.some((f) => p.startsWith(`${f.path}:`)));
    side.replaceChildren(
      ...[
      h("h2", null, "Xem trước thay đổi"),
      n === 0 ? h("p", { class: "muted small" }, "Chưa có thay đổi. Sửa một ô để xem khác biệt tại đây trước khi lưu.") : null,
      unmatched.length ? h("ul", { class: "problems" }, unmatched.map((p) => h("li", null, p))) : null,
      problems.length && !unmatched.length ? h("p", { class: "small", style: "color:var(--st-failed)" }, `${problems.length} giá trị chưa hợp lệ (xem ô bị đánh dấu).`) : null,
      lines.length ? h("div", { class: "diff" }, lines.map(([p, from, to, isReset]) => h("div", null, h("span", null, p, isReset ? " (về mặc định)" : ""), h("span", null, h("span", { class: "f" }, fmt(p, from)), " → ", h("span", { class: "t" }, fmt(p, to)))))) : null,
      h(
        "div",
        { class: "btn-row", style: "margin-top:14px" },
        h("button", { class: "btn", type: "button", disabled: n === 0 || problems.length > 0, onclick: save }, `Lưu${n ? ` (${n})` : ""}`),
        h("button", { class: "btn ghost", type: "button", disabled: n === 0, onclick: discard }, "Bỏ thay đổi")
      ),
      h("p", { class: "muted small", style: "margin-top:12px" }, "Mỗi lần lưu tạo một bản sao lưu config.yaml.bak-… trước khi ghi. Giá trị được kiểm tra bằng đúng bộ đọc cấu hình của chương trình.")
      ].filter(Boolean)
    );
  }

  function discard() {
    Object.keys(edits).forEach((p) => delete edits[p]);
    resets.clear();
    problems = [];
    diff = [];
    cfg.editable.forEach((f) => setInput(f, cur(f)));
    paintAll();
    paintSide();
  }

  async function save() {
    let backup = null;
    if (Object.keys(edits).length) {
      const r = await put("/config", { changes: edits });
      if (!r.ok) {
        problems = (r.body && r.body.problems) || [`Không lưu được (mã ${r.status})`];
        paintAll();
        paintSide();
        return toast("Không lưu được: có giá trị chưa hợp lệ", { kind: "err" });
      }
      backup = r.body.backup;
    }
    if (resets.size) {
      const r = await post("/config/reset", { paths: [...resets] });
      if (!r.ok) return toast(`Không khôi phục được (mã ${r.status})`, { kind: "err" });
      backup = r.body.backup || backup;
    }
    toast("Đã lưu cấu hình", { kind: "ok", sub: backup ? `Sao lưu: ${backup}` : "Chưa có tệp cũ nên không cần sao lưu" });
    root.replaceChildren();
    await renderConfig(root);
  }

  const forms = GROUPS.map(([id, title]) => {
    const fs = cfg.editable.filter((f) => f.group === id);
    return fs.length ? h("section", { class: "card" }, h("h2", null, title), h("div", { class: "fields" }, fs.map(field))) : null;
  }).filter(Boolean);
  root.append(banner, h("div", { class: "cfg-layout" }, h("div", null, forms), side));
  paintAll();
  paintSide();
}
