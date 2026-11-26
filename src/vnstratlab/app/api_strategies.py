"""Console v2: list strategies and add, switch off or delete parameter sets (card X-console-api).

Packaged parameter sets stay frozen: they can only be switched off or on (``disabled_params`` in
the user config). A user parameter set lives in ``strategies.<id>.user_params`` of the user
config; adding one registers its trials in the append-only ``TrialRegistry`` first (plan 6.4:
every trial is counted), and deleting one never removes a registered trial.
"""

from __future__ import annotations

import ast
import threading
from typing import Any

import duckdb
from fastapi import FastAPI
from pydantic import BaseModel

from vnstratlab import init_wizard as wiz
from vnstratlab.app import api_config as cfgapi
from vnstratlab.app.api_config import CONFIG_LOCK, json_error
from vnstratlab.config.loader import ConfigError, load_config
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.paths import AppPaths
from vnstratlab.strategies.base import HORIZONS
from vnstratlab.strategies.registry import (
    StrategyConfigError,
    canonical_params_json,
    entry_param_sets,
    get_strategy_class,
    load_strategies,
    make_trial_spec,
    registered_ids,
)
from vnstratlab.strategies.schemas import STRATEGY_INFO, params_schema

LAB_LOCK = threading.Lock()  # one lab.duckdb connection at a time inside this process
WARNING_VI = "Mỗi bộ tham số mới là một trial mới và làm ngưỡng Deflated Sharpe cao hơn."
KEPT_VI = "Các trial đã đăng ký vẫn nằm trong sổ đăng ký (chỉ ghi thêm, không xóa) và vẫn được đếm."


class ParamSetBody(BaseModel):
    params: dict[str, Any]
    horizons: list[str]


class EnabledBody(BaseModel):
    enabled: bool


def feature_version_of(paths: AppPaths, source: str) -> str | None:
    """The feature version in the store of ``source``, or None if there is no store or features."""
    from vnstratlab.data.protocol import SourceError
    from vnstratlab.data.store import MarketStore, kind_of_source
    from vnstratlab.lab.trials import TrialError, store_feature_version

    try:
        kind = kind_of_source(source)
        db = paths.market_db_for(kind)
        if not db.is_file():
            return None
        with MarketStore(db, kind, read_only=True) as store:
            return store_feature_version(store)
    except (SourceError, TrialError, duckdb.Error):
        return None


def registered_map(paths: AppPaths) -> dict[str, str]:
    """``trial_id -> registered_at`` for the trials already in the registry (read-only)."""
    from vnstratlab.lab.trials import TrialRegistry

    if not paths.lab_db.is_file():
        return {}
    with TrialRegistry(paths.lab_db, read_only=True) as registry:
        return {r.trial_id: r.registered_at.isoformat() for r in registry.list()}


def trial_total(paths: AppPaths) -> int:
    from vnstratlab.lab.trials import TrialRegistry

    if not paths.lab_db.is_file():
        return 0
    with TrialRegistry(paths.lab_db, read_only=True) as registry:
        return registry.count()


def _trial_entries(
    strategy_id: str,
    params: dict[str, Any],
    horizons: tuple[str, ...],
    fv: str | None,
    known: dict[str, str],
) -> list[dict[str, Any]]:
    if fv is None:
        return []
    cls = get_strategy_class(strategy_id)
    out: list[dict[str, Any]] = []
    for horizon in horizons:
        spec = make_trial_spec(cls(params, horizons), horizon, fv, ENGINE_VERSION)  # type: ignore[arg-type]
        entry: dict[str, Any] = {
            "horizon": horizon,
            "trial_id": spec.trial_id,
            "registered": spec.trial_id in known,
        }
        if spec.trial_id in known:
            entry["registered_at"] = known[spec.trial_id]
        out.append(entry)
    return out


def scan_plugins(paths: AppPaths) -> list[dict[str, Any]]:
    """User strategy files with the ids they declare, found by parsing only (nothing is run)."""
    plugins: list[dict[str, Any]] = []
    folder = paths.strategies_dir
    for file in sorted(folder.glob("*.py")) if folder.is_dir() else []:
        item: dict[str, Any] = {"file": file.name, "ids": []}
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for stmt in node.body:
                        if (
                            isinstance(stmt, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == "id" for t in stmt.targets)
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)
                        ):
                            item["ids"].append(stmt.value.value)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            item["error"] = f"cannot read: {type(exc).__name__}"
        else:
            item["error"] = "found but not loaded: plug-in loading is not available yet"
        plugins.append(item)
    return plugins


def _effective_entry(effective: dict[str, Any], strategy_id: str) -> dict[str, Any] | None:
    entry = (effective.get("strategies") or {}).get(strategy_id)
    return entry if isinstance(entry, dict) else None


def build_listing(paths: AppPaths) -> dict[str, Any]:
    cfg = load_config(paths.home)
    effective = cfgapi.dump_config(cfg)
    defaults = cfgapi.defaults_dump()
    fv = feature_version_of(paths, cfg.data.source)
    with LAB_LOCK:
        try:
            known = registered_map(paths)
            total = trial_total(paths)
        except duckdb.Error:
            known, total = {}, 0
    strategies: list[dict[str, Any]] = []
    for sid in registered_ids():
        info = STRATEGY_INFO.get(sid, {})
        entry = _effective_entry(effective, sid)
        packaged = (defaults.get("strategies") or {}).get(sid) or {}
        allowed = [h for h in packaged.get("horizons", []) if h in HORIZONS]
        blocked, reason = False, None
        sets: list[dict[str, Any]] = []
        if entry is None:
            blocked, reason = True, "not in the strategies config"
        else:
            problems, items = entry_param_sets(sid, entry)
            if problems:
                blocked, reason = True, "; ".join(problems)
            level = entry.get("enabled", True) is not False
            for i, (params, horizons, enabled, origin) in enumerate(items):
                try:
                    trials = _trial_entries(sid, params, horizons, fv, known)
                except (ValueError, TypeError, KeyError):
                    trials = []
                sets.append(
                    {
                        "index": i,
                        "params": params,
                        "horizons": list(horizons),
                        "enabled": enabled and level,
                        "origin": origin,
                        "trial_ids": trials,
                    }
                )
        item: dict[str, Any] = {
            "id": sid,
            "name_vi": info.get("name_vi", sid),
            "description_vi": info.get("description_vi", ""),
            "basis": info.get("basis", ""),
            "horizons_allowed": allowed,
            "blocked": blocked,
            "params_schema": params_schema(sid),
            "param_sets": sets,
        }
        if reason:
            item["reason"] = reason
        strategies.append(item)
    return {
        "strategies": strategies,
        "trials_total": total,
        "plugins": scan_plugins(paths),
        "feature_version": fv,
    }


def _prune(user: dict[str, Any], sid: str) -> None:
    section = user.get("strategies")
    if isinstance(section, dict) and not section.get(sid):
        section.pop(sid, None)
    if isinstance(section, dict) and not section:
        user.pop("strategies", None)


def _strategy_entry(user: dict[str, Any], sid: str) -> dict[str, Any]:
    section = user.setdefault("strategies", {})
    entry: dict[str, Any] = section.setdefault(sid, {})
    return entry


def _check_candidate(user: dict[str, Any]) -> list[str]:
    """Problems of the user mapping as a whole: the loader and the strategies section."""
    try:
        cfg = wiz.load_candidate(user)
    except ConfigError as exc:
        return list(exc.problems)
    try:
        load_strategies(cfg)
    except StrategyConfigError as exc:
        return list(exc.problems)
    return []


def register(app: FastAPI, paths: AppPaths) -> None:
    @app.get("/api/strategies", response_model=None)
    def list_strategies() -> Any:
        try:
            return build_listing(paths)
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))

    def _locate(sid: str) -> tuple[Any, dict[str, Any], list[str]] | Any:
        if sid not in registered_ids():
            return json_error(404, "unknown_strategy", strategy=sid)
        try:
            cfg = load_config(paths.home)
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))
        packaged = (cfgapi.defaults_dump().get("strategies") or {}).get(sid)
        if not isinstance(packaged, dict):
            return json_error(409, "not_configured", strategy=sid)
        return cfg, packaged, [h for h in packaged.get("horizons", []) if h in HORIZONS]

    @app.post("/api/strategies/{sid}/param-sets", response_model=None)
    def add_param_set(sid: str, body: ParamSetBody) -> Any:
        found = _locate(sid)
        if not isinstance(found, tuple):
            return found
        cfg, _packaged, allowed = found
        problems: list[str] = []
        if not body.horizons or len(set(body.horizons)) != len(body.horizons):
            problems.append("horizons: must be a non-empty list without duplicates")
        problems += [
            f"horizons: {h!r} is not allowed for {sid} (allowed: {allowed})"
            for h in body.horizons
            if h not in allowed
        ]
        cls = get_strategy_class(sid)
        try:
            cls.validate_params(body.params)
            canonical_params_json(body.params)
        except (ValueError, TypeError, KeyError) as exc:
            problems.append(f"params: {exc}")
        if problems:
            return json_error(422, "invalid_param_set", ok=False, problems=problems)
        horizons = tuple(body.horizons)
        try:
            cls(body.params, horizons)  # type: ignore[arg-type]
        except (ValueError, TypeError, KeyError) as exc:
            return json_error(422, "invalid_param_set", ok=False, problems=[f"params: {exc}"])
        fv = feature_version_of(paths, cfg.data.source)
        if fv is None:
            return json_error(
                409,
                "features_required",
                message="no features in the local store: run `vnstratlab features build` first "
                "(a trial id includes the feature version)",
            )
        with CONFIG_LOCK:
            try:
                user = cfgapi.read_user(paths)
            except ConfigError as exc:
                return json_error(422, "config_invalid", problems=list(exc.problems))
            existing = wiz_copy(user)
            entry = _strategy_entry(user, sid)
            entry.setdefault("user_params", []).append(
                {"params": dict(body.params), "horizons": list(horizons)}
            )
            problems = _check_candidate(user)
            if problems:
                return json_error(422, "invalid_param_set", ok=False, problems=problems)
            index = _count_sets(wiz.load_candidate(user), sid) - 1
            try:
                trial_ids = _register_trials(paths, sid, dict(body.params), horizons, fv)
            except duckdb.Error as exc:
                return json_error(503, "lab_busy", message=f"cannot use lab.duckdb: {exc}")
            backup = cfgapi.commit_overrides(paths, user, existing)
        return {
            "ok": True,
            "index": index,
            "trial_ids": trial_ids,
            "warning_vi": WARNING_VI,
            "backup": backup,
        }

    @app.patch("/api/strategies/{sid}/param-sets/{index}", response_model=None)
    def toggle_param_set(sid: str, index: int, body: EnabledBody) -> Any:
        found = _locate(sid)
        if not isinstance(found, tuple):
            return found
        cfg, _packaged, _allowed = found
        with CONFIG_LOCK:
            try:
                user = cfgapi.read_user(paths)
            except ConfigError as exc:
                return json_error(422, "config_invalid", problems=list(exc.problems))
            effective_entry = cfg.strategies.get(sid)
            problems, items = entry_param_sets(sid, _thaw(effective_entry))
            if problems or not 0 <= index < len(items):
                return json_error(404, "not_found", strategy=sid, index=index)
            existing = wiz_copy(user)
            packaged_n = sum(1 for it in items if it[3] == "packaged")
            entry = _strategy_entry(user, sid)
            if index < packaged_n:
                off = {int(i) for i in entry.get("disabled_params", [])}
                (off.discard if body.enabled else off.add)(index)
                if off:
                    entry["disabled_params"] = sorted(off)
                else:
                    entry.pop("disabled_params", None)
            else:
                user_list = entry.get("user_params", [])
                user_list[index - packaged_n]["enabled"] = body.enabled
                if body.enabled:
                    user_list[index - packaged_n].pop("enabled")
            _prune(user, sid)
            problems = _check_candidate(user)
            if problems:
                return json_error(422, "invalid_param_set", ok=False, problems=problems)
            backup = cfgapi.commit_overrides(paths, user, existing)
        return {"ok": True, "index": index, "enabled": body.enabled, "backup": backup}

    @app.delete("/api/strategies/{sid}/param-sets/{index}", response_model=None)
    def delete_param_set(sid: str, index: int) -> Any:
        found = _locate(sid)
        if not isinstance(found, tuple):
            return found
        cfg, _packaged, _allowed = found
        with CONFIG_LOCK:
            try:
                user = cfgapi.read_user(paths)
            except ConfigError as exc:
                return json_error(422, "config_invalid", problems=list(exc.problems))
            problems, items = entry_param_sets(sid, _thaw(cfg.strategies.get(sid)))
            if problems or not 0 <= index < len(items):
                return json_error(404, "not_found", strategy=sid, index=index)
            if items[index][3] != "user":
                return json_error(
                    409, "packaged_set", message="packaged parameter sets cannot be deleted"
                )
            packaged_n = sum(1 for it in items if it[3] == "packaged")
            existing = wiz_copy(user)
            entry = _strategy_entry(user, sid)
            entry["user_params"].pop(index - packaged_n)
            if not entry["user_params"]:
                entry.pop("user_params")
            _prune(user, sid)
            problems = _check_candidate(user)
            if problems:
                return json_error(422, "invalid_param_set", ok=False, problems=problems)
            backup = cfgapi.commit_overrides(paths, user, existing)
        return {
            "ok": True,
            "index": index,
            "trials_kept": True,
            "message_vi": KEPT_VI,
            "backup": backup,
        }


def wiz_copy(user: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(user)


def _thaw(value: Any) -> Any:
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw(v) for v in value]
    return value


def _count_sets(cfg: Any, sid: str) -> int:
    return len(entry_param_sets(sid, _thaw(cfg.strategies.get(sid)))[1])


def _register_trials(
    paths: AppPaths, sid: str, params: dict[str, Any], horizons: tuple[str, ...], fv: str
) -> list[dict[str, Any]]:
    """Register every (params, horizon) trial; this must succeed before the config is written."""
    from vnstratlab.lab.trials import TrialRegistry

    cls = get_strategy_class(sid)
    instance = cls(params, horizons)  # type: ignore[arg-type]
    out: list[dict[str, Any]] = []
    with LAB_LOCK, TrialRegistry(paths.lab_db) as registry:
        for horizon in horizons:
            spec = make_trial_spec(instance, horizon, fv, ENGINE_VERSION)  # type: ignore[arg-type]
            result = registry.register(spec, "console: user parameter set")
            entry: dict[str, Any] = {
                "horizon": horizon,
                "trial_id": spec.trial_id,
                "registered": True,
            }
            if result.registered_at is not None:
                entry["registered_at"] = result.registered_at.isoformat()
            out.append(entry)
    return out
