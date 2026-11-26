// Chiến lược: cards, param sets with enable/disable, add a set from `params_schema`, delete user sets, plug-ins.
// Contract: GET /api/strategies, POST .../param-sets, PATCH/DELETE .../param-sets/{index}.
import { confirmDialog, emptyState, pageHead, switchEl, toast } from "./ui.js";
import { api, del, errorBox, h, patch, post } from "./util.js";

const HORIZON_VI = { short: "ngắn hạn", medium: "trung hạn", long: "dài hạn" };
const DSR_WARNING = "Mỗi bộ tham số mới là một trial mới và làm ngưỡng Deflated Sharpe cao hơn.";
const fmtParams = (p) => Object.entries(p).map(([k, v]) => `${k}=${v}`).join(", ");

function paramField(sc) {
  const id = `p-${sc.name}`;
  let input;
  if (sc.allowed) {
    input = h("select", { id }, sc.allowed.map((a) => h("option", { value: String(a) }, String(a))));
  } else if (sc.type === "bool") {
    input = h("select", { id }, h("option", { value: "true" }, "Bật"), h("option", { value: "false" }, "Tắt"));
  } else if (sc.type === "int" || sc.type === "float") {
    input = h("input", { id, type: "number", inputmode: "decimal", min: sc.min ?? null, max: sc.max ?? null, step: sc.type === "int" ? 1 : "any", required: true });
  } else input = h("input", { id, type: "text", required: true });
  const read = () => {
    if (sc.allowed) {
      const raw = input.value;
      return sc.allowed.find((a) => String(a) === raw);
    }
    if (sc.type === "bool") return input.value === "true";
    if (sc.type === "int" || sc.type === "float") return input.value === "" ? NaN : Number(input.value);
    return input.value;
  };
  const range = !sc.allowed && sc.min !== undefined ? ` (từ ${sc.min} đến ${sc.max})` : "";
  const el = h("div", { class: "field" }, h("label", { class: "lbl", for: id }, sc.name, h("span", { class: "unit" }, `${sc.type}${range}`)), input, sc.help_vi ? h("div", { class: "hint" }, sc.help_vi) : null);
  return { el, name: sc.name, read, input };
}

function addDialog(strat, onDone) {
  const fields = strat.params_schema.map(paramField);
  const checks = strat.horizons_allowed.map((hz) => ({ hz, box: h("input", { type: "checkbox", checked: strat.horizons_allowed.length === 1 }) }));
  const errors = h("ul", { class: "problems" });
  const submit = h("button", { class: "btn", type: "submit" }, "Thêm và đăng ký trial");
  const dialog = h(
    "dialog",
    null,
    h(
      "form",
      {
        method: "dialog",
        novalidate: true,
        onsubmit: async (e) => {
          e.preventDefault();
          const params = Object.fromEntries(fields.map((f) => [f.name, f.read()]));
          const horizons = checks.filter((c) => c.box.checked).map((c) => c.hz);
          const local = [];
          fields.forEach((f) => {
            const v = params[f.name];
            const sc = strat.params_schema.find((s) => s.name === f.name);
            if (v === undefined || (typeof v === "number" && Number.isNaN(v))) local.push(`params.${f.name}: chưa hợp lệ`);
            else if (typeof v === "number" && !sc.allowed && ((sc.min !== undefined && v < sc.min) || (sc.max !== undefined && v > sc.max))) local.push(`params.${f.name}: ngoài khoảng ${sc.min}–${sc.max}`);
          });
          if (!horizons.length) local.push("horizons: chọn ít nhất một khung");
          errors.replaceChildren(...local.map((p) => h("li", null, p)));
          if (local.length) return;
          submit.disabled = true;
          const r = await post(`/strategies/${encodeURIComponent(strat.id)}/param-sets`, { params, horizons });
          submit.disabled = false;
          if (r.ok) {
            dialog.close("ok");
            const b = r.body || {};
            toast(`Đã thêm bộ tham số${b.index !== undefined ? ` #${b.index}` : ""}`, { kind: "ok", sub: [b.warning_vi || DSR_WARNING, b.backup ? `Sao lưu: ${b.backup}` : null].filter(Boolean).join(" · ") });
            onDone();
          } else if (r.status === 409 && r.body && r.body.error === "features_required") {
            errors.replaceChildren(h("li", null, r.body.message_vi || r.body.message || "Cần tính đặc trưng trước khi thêm bộ tham số."), h("li", null, h("a", { href: "#/runs", onclick: () => dialog.close("no") }, "Mở Runs để chạy “Tính đặc trưng”, rồi thêm lại.")));
          } else errors.replaceChildren(...(((r.body && r.body.problems) || [(r.body && r.body.message) || `Không thêm được (mã ${r.status})`]).map((p) => h("li", null, p))));
        },
      },
      h("h2", null, `Thêm bộ tham số · ${strat.id}`),
      h("p", { class: "muted small" }, strat.name_vi),
      h("div", { class: "notice warn" }, DSR_WARNING),
      ...fields.map((f) => f.el),
      h("div", { class: "field" }, h("div", { class: "lbl" }, "Khung thời gian"), h("div", null, checks.map((c) => h("label", { class: "h-check" }, c.box, HORIZON_VI[c.hz] || c.hz)))),
      errors,
      h("div", { class: "dialog-actions" }, h("button", { class: "btn ghost", type: "button", onclick: () => dialog.close("no") }, "Hủy"), submit)
    )
  );
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
}

function setRow(strat, ps, reload) {
  const sw = switchEl(ps.enabled, async (next, el) => {
    el.disabled = true;
    const r = await patch(`/strategies/${encodeURIComponent(strat.id)}/param-sets/${ps.index}`, { enabled: next });
    el.disabled = false;
    if (r.ok) {
      row.classList.toggle("off", !next);
      toast(next ? "Đã bật bộ tham số" : "Đã tắt bộ tham số", { kind: "ok", ms: 2200 });
    } else {
      el.setAttribute("aria-checked", String(!next));
      toast("Không đổi được trạng thái", { kind: "err" });
    }
  }, `Bật bộ tham số ${ps.index}`);
  const user = ps.origin === "user";
  const row = h(
    "div",
    { class: `set${ps.enabled ? "" : " off"}` },
    h("div", { class: "params" }, h("b", null, `#${ps.index} `), fmtParams(ps.params), " ", ps.horizons.map((hz) => h("span", { class: "chip soft" }, HORIZON_VI[hz] || hz))),
    h("div", { class: "acts" }, h("span", { class: `chip ${user ? "dashed" : "soft"}` }, user ? "của bạn" : "gói sẵn"),
      user ? h("button", { class: "btn danger sm", type: "button", onclick: async () => {
        const ok = await confirmDialog({ title: "Xóa bộ tham số?", yes: "Xóa", danger: true, body: "Bộ tham số bị gỡ khỏi cấu hình của bạn. Trial vẫn được giữ trong registry (chỉ ghi thêm, không bao giờ xóa)." });
        if (!ok) return;
        const r = await del(`/strategies/${encodeURIComponent(strat.id)}/param-sets/${ps.index}`);
        if (r.ok) {
          toast("Đã xóa bộ tham số", { kind: "ok", sub: "Trial vẫn được giữ trong registry" });
          reload();
        } else if (r.status === 409 && r.body && r.body.error === "packaged_set") toast("Bộ tham số gói sẵn không xóa được", { kind: "warn", sub: "Bạn chỉ có thể tắt nó bằng công tắc" });
        else toast((r.body && (r.body.message_vi || r.body.message)) || `Không xóa được (mã ${r.status})`, { kind: "err" });
      } }, "Xóa") : null,
      sw),
    h("div", { class: "ids" }, ps.trial_ids.map((t) => h("span", { class: `chip ${t.registered ? "" : "dashed"}`, title: t.registered_at ? `Đăng ký ${t.registered_at}` : "Chưa đăng ký" }, `${t.trial_id}${t.registered ? "" : " (chưa)"}`)))
  );
  return row;
}

function card(strat, reload) {
  const blocked = strat.blocked;
  return h(
    "section",
    { class: `card st-card${blocked ? " blocked" : ""}` },
    h("div", { class: "card-head", style: "margin:0" }, h("h3", null, strat.name_vi), h("span", { class: "chip solid" }, strat.id)),
    h("div", { class: "muted" }, strat.description_vi),
    h("div", { class: "pillrow" }, h("span", { class: "chip soft" }, `cơ sở: ${strat.basis}`), strat.horizons_allowed.map((hz) => h("span", { class: "chip" }, HORIZON_VI[hz] || hz))),
    blocked ? h("div", { class: "notice warn", style: "margin:8px 0 0" }, strat.reason || "Bị chặn.") : null,
    strat.param_sets.length ? h("div", { class: "sets" }, strat.param_sets.map((ps) => setRow(strat, ps, reload))) : blocked ? null : h("p", { class: "muted small" }, "Chưa có bộ tham số nào."),
    blocked || !strat.params_schema.length ? null : h("div", { class: "btn-row", style: "margin-top:8px" }, h("button", { class: "btn ghost sm", type: "button", onclick: () => addDialog(strat, reload) }, "Thêm bộ tham số"))
  );
}

export async function renderStrategies(root) {
  root.append(pageHead("Chiến lược", "Bộ tham số là các trial: mọi lần thử đều được đếm"));
  const res = await api("/strategies");
  if (!res.ok) {
    root.append(res.status === 404 ? emptyState("Máy chủ chưa có /api/strategies", "Trang này cần API chiến lược (card X-console-api). Dùng ?mock=1 để xem giao diện với dữ liệu mẫu.") : errorBox("Không tải được danh sách chiến lược."));
    return;
  }
  const reload = async () => {
    root.replaceChildren();
    await renderStrategies(root);
  };
  const { strategies, trials_total, plugins } = res.body;
  root.append(
    h("div", { class: "notice" }, `Tổng cộng ${trials_total} trial đã đăng ký. ${DSR_WARNING} Tham số gói sẵn chỉ bật/tắt được, không sửa.`),
    h("div", { class: "st-grid" }, strategies.map((s) => card(s, reload))),
    h(
      "section",
      { class: "card", style: "margin-top:16px" },
      h("h2", null, "Plug-in trong thư mục strategies/ (chỉ đọc)"),
      plugins.length
        ? h("ul", { class: "list" }, plugins.map((p) => h("li", null, h("code", null, p.file), p.ids.length ? h("span", { class: "muted" }, p.ids.join(", ")) : null, p.error ? h("span", { class: "chip dashed" }, "lỗi") : h("span", { class: "chip st-success" }, h("span", { class: "dot" }), "đã nạp"), p.error ? h("div", { class: "small", style: "color:var(--st-failed);width:100%" }, p.error) : null)))
        : h("p", { class: "muted" }, "Không có plug-in nào. Đặt tệp .py vào thư mục strategies/ trong thư mục dữ liệu để thêm chiến lược của riêng bạn.")
    )
  );
}
