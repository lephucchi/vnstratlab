"""Console v2: read and edit the user's ``config.yaml`` (card X-console-api).

Only the whitelisted ``EDITABLE`` paths can be written. A change is applied to the user's override
mapping with the ``vnstratlab.init_wizard`` helpers, validated with the real loader in a scratch
home, backed up and written atomically. The packaged defaults are never touched. Nothing here
reads the settings object, so no secret can reach a response.
"""

from __future__ import annotations

import copy
import datetime as dt
import functools
import json
import math
import threading
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vnstratlab import init_wizard as wiz
from vnstratlab.config.loader import ConfigError, load_config
from vnstratlab.paths import AppPaths

CONFIG_LOCK = threading.Lock()  # one config writer at a time (config and strategy endpoints)

_FROZEN_RISK = (
    "Giá trị mặc định là tham số đóng băng của dự án. Bạn có thể đổi cho riêng mình; "
    "mọi lần chạy sau sẽ dùng giá trị mới."
)
_FROZEN_ENGINE = "Chính sách của bộ mô phỏng (ADR-003) do chủ dự án đóng băng; chỉ đổi khi hiểu rõ."
_VERIFY_COST = "Kiểm tra lại với công ty chứng khoán của bạn [VERIFY]."


def _f(
    path: str,
    label_vi: str,
    group: str,
    type_: str,
    help_vi: str,
    *,
    verify: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "path": path,
        "label_vi": label_vi,
        "group": group,
        "type": type_,
        "verify": verify,
        "help_vi": help_vi,
    }
    field.update(extra)
    return field


def _pct(path: str, label_vi: str, group: str, help_vi: str, **extra: Any) -> dict[str, Any]:
    # a pct value is the raw fraction in the config (0.0015 = 0.15 %); the UI shows it as %
    return _f(
        path, label_vi, group, "pct", help_vi, min=0, max=1, max_exclusive=True,
        step=0.0001, unit="%", **extra,
    )  # fmt: skip


EDITABLE: list[dict[str, Any]] = [
    _f("books.short.capital_vnd", "Vốn sổ ngắn hạn", "books", "int",
       "Vốn giả lập của sổ ngắn hạn (rebalance hằng tuần).", min=1, step=1_000_000, unit="VND"),
    _f("books.medium.capital_vnd", "Vốn sổ trung hạn", "books", "int",
       "Vốn giả lập của sổ trung hạn (rebalance hằng tháng).", min=1, step=1_000_000, unit="VND"),
    _f("books.long.capital_vnd", "Vốn sổ dài hạn", "books", "int",
       "Vốn giả lập của sổ dài hạn (rebalance hằng tháng).", min=1, step=1_000_000, unit="VND"),
    _f("books.medium.tranches", "Số đợt giải ngân (trung hạn)", "books", "int",
       "Chia vốn sổ trung hạn thành bấy nhiêu đợt.", min=1, step=1),
    _pct("costs.brokerage_fee_pct", "Phí môi giới", "costs", "Phí môi giới mỗi lệnh.",
         verify=True, frozen_note_vi=_VERIFY_COST),
    _pct("costs.sales_tax_pct", "Thuế bán", "costs", "Thuế trên giá trị bán.",
         verify=True, frozen_note_vi=_VERIFY_COST),
    _pct("costs.slippage_pct.round_lot", "Trượt giá lô chẵn", "costs",
         "Chênh lệch giá khớp giả định cho lô chẵn.", verify=True, frozen_note_vi=_VERIFY_COST),
    _pct("costs.slippage_pct.odd_lot", "Trượt giá lô lẻ", "costs",
         "Chênh lệch giá khớp giả định cho lô lẻ.", verify=True, frozen_note_vi=_VERIFY_COST),
    _pct("risk.risk_per_position_pct", "Rủi ro mỗi vị thế", "risk",
         "Tỷ lệ vốn chấp nhận mất nếu một vị thế chạm điểm dừng lỗ.", frozen_note_vi=_FROZEN_RISK),
    _f("risk.atr_stop_multiple", "Hệ số ATR cho điểm dừng lỗ", "risk", "float",
       "Điểm dừng lỗ cách giá vào bấy nhiêu lần ATR.", min=0, min_exclusive=True, step=0.1,
       frozen_note_vi=_FROZEN_RISK),
    _f("risk.max_positions", "Số vị thế tối đa", "risk", "int",
       "Số mã tối đa được giữ cùng lúc.", min=1, step=1, frozen_note_vi=_FROZEN_RISK),
    _pct("risk.max_weight_per_ticker", "Tỷ trọng tối đa mỗi mã", "risk",
         "Một mã không được vượt tỷ trọng này.", frozen_note_vi=_FROZEN_RISK),
    _pct("risk.circuit_breaker_drawdown_pct", "Ngưỡng sụt giảm ngắt mạch", "risk",
         "Sổ về tiền mặt khi sụt giảm từ đỉnh vượt ngưỡng này.", frozen_note_vi=_FROZEN_RISK),
    _pct("risk.rebalance_threshold_pct", "Ngưỡng cân bằng lại", "risk",
         "Chỉ cân bằng lại khi lệch tỷ trọng vượt ngưỡng này.", frozen_note_vi=_FROZEN_RISK),
    _f("risk.vol_target_annual", "Mục tiêu biến động năm", "risk", "float",
       "Để trống = tắt. Ví dụ 0.15 = nhắm biến động 15 %/năm.", min=0, min_exclusive=True,
       step=0.01, nullable=True, frozen_note_vi=_FROZEN_RISK),
    _f("risk.stop_cooldown_sessions", "Số phiên nghỉ sau dừng lỗ", "risk", "int",
       "Để trống = một kỳ quyết định của sổ.", min=1, step=1, unit="sessions", nullable=True,
       frozen_note_vi=_FROZEN_RISK),
    _f("engine.unfilled_buy", "Lệnh mua không khớp", "engine", "enum",
       "Hủy hay giữ lệnh mua chưa khớp sang phiên sau.", options=["cancel", "carry"],
       frozen_note_vi=_FROZEN_ENGINE),
    _f("engine.unfilled_sell", "Lệnh bán không khớp", "engine", "enum",
       "Hủy hay giữ lệnh bán chưa khớp sang phiên sau.", options=["carry", "cancel"],
       frozen_note_vi=_FROZEN_ENGINE),
    _f("engine.max_carry_sessions", "Số phiên giữ lệnh tối đa", "engine", "int",
       "Lệnh được chuyển sang phiên sau tối đa bấy nhiêu phiên.", min=0, step=1,
       unit="sessions", frozen_note_vi=_FROZEN_ENGINE),
    _f("data.source", "Nguồn dữ liệu", "data", "enum",
       "yahoo = dữ liệu thật (nguồn tạm thời, cần chấp nhận điều khoản); synthetic = giả lập.",
       options=list(wiz.SOURCES)),
    _f("project.backfill_start", "Ngày bắt đầu tải lịch sử", "data", "date",
       "Ngày đầu tiên khi tải lịch sử lần đầu (YYYY-MM-DD)."),
]  # fmt: skip

_BY_PATH = {f["path"]: f for f in EDITABLE}


def json_error(status: int, code: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": code, **extra}, status_code=status)


def json_safe(value: Any) -> Any:
    """``value`` as plain JSON data (dates become ISO strings)."""
    return json.loads(json.dumps(value, default=str))


def read_user(paths: AppPaths) -> dict[str, Any]:
    """The raw user mapping from ``config.yaml`` ({} if absent). Raises ``ConfigError``."""
    file = paths.config_file
    if not file.is_file():
        return {}
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigError([f"{file.name}: cannot read ({type(exc).__name__})"]) from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError([f"{file.name}: top level must be a mapping"])
    return data


def dump_config(cfg: Any) -> dict[str, Any]:
    dumped: dict[str, Any] = json_safe(cfg.model_dump(mode="json", by_alias=True))
    return dumped


@functools.cache
def _defaults_json() -> str:
    return json.dumps(dump_config(wiz.packaged_config()))


def defaults_dump() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(_defaults_json())
    return loaded


def at_path(tree: Any, path: str) -> Any:
    return wiz.get_path(tree, tuple(path.split(".")))


def _bounds(field: dict[str, Any], value: float) -> str | None:
    low, high = field.get("min"), field.get("max")
    if low is not None and (value < low or (field.get("min_exclusive") and value <= low)):
        return f"must be greater than {low}" if field.get("min_exclusive") else f"must be >= {low}"
    if high is not None and (value > high or (field.get("max_exclusive") and value >= high)):
        return f"must be below {high}" if field.get("max_exclusive") else f"must be <= {high}"
    return None


def coerce(field: dict[str, Any], value: Any) -> tuple[Any, str | None]:
    """The value as the config expects it, or a reason it is not acceptable."""
    kind = field["type"]
    if value is None:
        return (None, None) if field.get("nullable") else (None, "a value is required")
    if kind == "enum":
        ok = isinstance(value, str) and value in field["options"]
        return (value, None) if ok else (None, f"must be one of: {', '.join(field['options'])}")
    if kind == "bool":
        return (value, None) if isinstance(value, bool) else (None, "must be true or false")
    if kind == "date":
        try:
            if not isinstance(value, str):
                raise ValueError
            return dt.date.fromisoformat(value), None
        except ValueError:
            return None, "must be a date YYYY-MM-DD"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, "must be a number"
    if isinstance(value, float) and not math.isfinite(value):
        return None, "must be a finite number"
    if kind == "int":
        if isinstance(value, float) and not value.is_integer():
            return None, "must be a whole number"
        number: int | float = int(value)
    else:
        number = float(value)
    problem = _bounds(field, number)
    return (None, problem) if problem else (number, None)


class ChangesBody(BaseModel):
    changes: dict[str, Any]


class ResetBody(BaseModel):
    paths: list[str]


class Plan:
    """Outcome of a requested edit: problems, or the new override mapping and the diff."""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.diff: list[dict[str, Any]] = []
        self.overrides: dict[str, Any] = {}
        self.existing: dict[str, Any] = {}


def plan_edit(
    paths: AppPaths,
    *,
    changes: dict[str, Any] | None = None,
    reset: list[str] | None = None,
) -> Plan:
    plan = Plan()
    requested: dict[str, Any] = {}
    for path in [*(changes or {}), *(reset or [])]:
        if path not in _BY_PATH:
            plan.problems.append(f"{path}: not editable")
    for path, raw in (changes or {}).items():
        if path in _BY_PATH:
            value, problem = coerce(_BY_PATH[path], raw)
            if problem:
                plan.problems.append(f"{path}: {problem}")
            requested[path] = value
    if plan.problems:
        return plan
    try:
        plan.existing = read_user(paths)
        before = dump_config(load_config(paths.home))
    except ConfigError as exc:
        plan.problems = list(exc.problems)
        return plan
    split = {tuple(p.split(".")): v for p, v in requested.items()}
    overrides = wiz.apply_changes(plan.existing, split)
    overrides = wiz.reset_paths(overrides, [tuple(p.split(".")) for p in reset or []])
    plan.overrides = overrides
    try:
        after = dump_config(wiz.load_candidate(overrides))
    except ConfigError as exc:
        plan.problems = list(exc.problems)
        return plan
    for path in [*requested, *(reset or [])]:
        old, new = at_path(before, path), at_path(after, path)
        if old != new:
            plan.diff.append({"path": path, "from": old, "to": new})
    return plan


def commit_overrides(
    paths: AppPaths, overrides: dict[str, Any], existing: dict[str, Any]
) -> str | None:
    """Write ``overrides`` atomically with a ``.bak-<stamp>`` copy of the old file; returns the
    backup path, or None if nothing changed or there was no file."""
    if overrides == existing and paths.config_file.exists():
        return None
    now = dt.datetime.now(dt.UTC)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    file = paths.config_file
    n = 1
    while file.with_name(f"{file.name}.bak-{stamp}").exists():
        n += 1
        stamp = f"{now.strftime('%Y%m%dT%H%M%S')}-{n}"
    backup = wiz.write_config(
        file,
        wiz.render_config(overrides, now.date()),
        backup_stamp=stamp if file.exists() else None,
    )
    return str(backup) if backup else None


def register(app: FastAPI, paths: AppPaths) -> None:
    @app.get("/api/config", response_model=None)
    def get_config() -> Any:
        try:
            user = read_user(paths)
            effective = dump_config(load_config(paths.home))
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))
        return {
            "effective": effective,
            "defaults": defaults_dump(),
            "user": json_safe(user),
            "editable": copy.deepcopy(EDITABLE),
            "file": str(paths.config_file),
            "exists": paths.config_file.is_file(),
        }

    @app.post("/api/config/validate")
    def validate(body: ChangesBody) -> dict[str, Any]:
        plan = plan_edit(paths, changes=body.changes)
        return {"ok": not plan.problems, "problems": plan.problems, "diff": plan.diff}

    @app.put("/api/config", response_model=None)
    def put_config(body: ChangesBody) -> Any:
        with CONFIG_LOCK:
            plan = plan_edit(paths, changes=body.changes)
            if plan.problems:
                return json_error(422, "config_invalid", ok=False, problems=plan.problems)
            backup = commit_overrides(paths, plan.overrides, plan.existing) if plan.diff else None
        return {"ok": True, "backup": backup, "diff": plan.diff}

    @app.post("/api/config/reset", response_model=None)
    def reset_config(body: ResetBody) -> Any:
        with CONFIG_LOCK:
            plan = plan_edit(paths, reset=body.paths)
            if plan.problems:
                return json_error(422, "config_invalid", ok=False, problems=plan.problems)
            backup = commit_overrides(paths, plan.overrides, plan.existing) if plan.diff else None
        return {"ok": True, "backup": backup, "diff": plan.diff}


def home_of(paths: AppPaths) -> Path:
    return paths.home
