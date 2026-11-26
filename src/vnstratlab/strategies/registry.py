"""Strategy registry, trial identity and config loading (plan 5.4, engine.md section 12).

Pure: no database or file I/O beyond reading a strategy module's own source for its code hash
(enforced by tests/test_data_boundary.py). Persistence of trials lives in ``vnstratlab.lab.trials``.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from vnstratlab.strategies.base import HORIZONS, BaseStrategy, Horizon, Strategy

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

log = logging.getLogger(__name__)

_ENTRY_KEYS = frozenset(
    {"horizons", "params", "enabled", "reason", "user_params", "disabled_params"}
)
_USER_SET_KEYS = frozenset({"params", "horizons", "enabled"})
_REGISTRY: dict[str, type[BaseStrategy]] = {}

C = TypeVar("C", bound=type[BaseStrategy])


class StrategyConfigError(ValueError):
    """The ``strategies:`` config section is invalid; ``problems`` lists every issue."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("invalid strategies config:\n  " + "\n  ".join(problems))


# ------------------------------------------------------------------ registry


def register_strategy(cls: C) -> C:
    """Class decorator: make ``cls`` discoverable under ``cls.id``."""
    if not (isinstance(cls, type) and issubclass(cls, BaseStrategy)):
        raise TypeError(
            f"{cls!r} must subclass BaseStrategy so its weights go through asof_guard "
            "and validate_weights"
        )
    strategy_id = getattr(cls, "id", None)
    if not isinstance(strategy_id, str) or not strategy_id:
        raise TypeError(f"{cls.__name__} must define a non-empty string class attribute 'id'")
    existing = _REGISTRY.get(strategy_id)
    if existing is not None and existing is not cls:
        raise ValueError(f"strategy id {strategy_id!r} is already registered")
    _REGISTRY[strategy_id] = cls
    return cls


def unregister_strategy(strategy_id: str) -> None:
    """Remove a strategy class (used by tests that register local classes)."""
    _REGISTRY.pop(strategy_id, None)


def _load_builtins() -> None:
    importlib.import_module("vnstratlab.strategies.builtin")


def registered_ids() -> list[str]:
    _load_builtins()
    return sorted(_REGISTRY)


def get_strategy_class(strategy_id: str) -> type[BaseStrategy]:
    _load_builtins()
    try:
        return _REGISTRY[strategy_id]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "none registered"
        raise KeyError(f"unknown strategy id {strategy_id!r} (known: {known})") from None


# ------------------------------------------------------------------ trial identity


def strategy_code_hash(cls: type) -> str:
    """SHA-256 (hex) of the source of the module defining ``cls``, line endings normalised.

    Any edit to the module changes the hash and therefore the trial id (ADR-003 section 3).
    Code the module imports from elsewhere is not part of the hash; bump ``ENGINE_VERSION`` or
    the feature version for changes there.
    """
    module = sys.modules.get(cls.__module__)
    if module is None:
        raise ValueError(f"module {cls.__module__!r} of {cls.__name__} is not imported")
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError) as exc:
        raise ValueError(f"no source available for module {cls.__module__!r}: {exc}") from None
    normalised = source.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, set | frozenset):
        return sorted(value)
    raise TypeError(f"params value of type {type(value).__name__} is not JSON-serialisable")


def canonical_params_json(params: Mapping[str, Any]) -> str:
    """Canonical JSON of a parameter set: sorted keys, no whitespace, ASCII, no NaN.

    Note ``20`` and ``20.0`` are different parameter sets (different JSON text).
    """
    return json.dumps(
        params,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    )


def compute_trial_id(
    strategy_id: str,
    params: Mapping[str, Any],
    horizon: Horizon,
    code_hash: str,
    feature_version: str,
    engine_version: str,
) -> str:
    """Deterministic trial id: first 16 hex chars of SHA-256 over the identity parts.

    The horizon is part of the identity (a horizon is a different rebalance period and a
    different return series, so it is a different trial for the DSR count).
    """
    identity = json.dumps(
        {
            "strategy_id": strategy_id,
            "params": canonical_params_json(params),
            "horizon": horizon,
            "strategy_code_hash": code_hash,
            "feature_version": feature_version,
            "engine_version": engine_version,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class TrialSpec:
    """Everything that identifies one trial."""

    trial_id: str
    strategy_id: str
    params_json: str
    horizon: Horizon
    strategy_code_hash: str
    feature_version: str
    engine_version: str


def make_trial_spec(
    strategy: Strategy,
    horizon: Horizon,
    feature_version: str,
    engine_version: str,
    code_hash: str | None = None,
) -> TrialSpec:
    """Trial identity of ``strategy`` on ``horizon`` (code hash from its class unless given)."""
    if horizon not in strategy.horizons:
        raise ValueError(f"{strategy.id} does not run on horizon {horizon!r}")
    code = code_hash if code_hash is not None else strategy_code_hash(type(strategy))
    return TrialSpec(
        trial_id=compute_trial_id(
            strategy.id, strategy.params, horizon, code, feature_version, engine_version
        ),
        strategy_id=strategy.id,
        params_json=canonical_params_json(strategy.params),
        horizon=horizon,
        strategy_code_hash=code,
        feature_version=feature_version,
        engine_version=engine_version,
    )


# ------------------------------------------------------------------ config loading


def _entry_problems(
    strategy_id: str, entry: object
) -> tuple[list[str], tuple[Horizon, ...], list[dict[str, Any]]]:
    where = f"strategies.{strategy_id}"
    if not isinstance(entry, Mapping):
        return [f"{where}: must be a mapping, got {type(entry).__name__}"], (), []
    problems: list[str] = []
    extra = sorted(set(entry) - _ENTRY_KEYS)
    if extra:
        problems.append(f"{where}: unknown key(s) {extra} (allowed: {sorted(_ENTRY_KEYS)})")
    horizons_raw = entry.get("horizons")
    horizons: list[Horizon] = []
    if not isinstance(horizons_raw, list | tuple) or not horizons_raw:
        problems.append(f"{where}.horizons: must be a non-empty list of {list(HORIZONS)}")
    else:
        for h in horizons_raw:
            if h not in HORIZONS:
                problems.append(f"{where}.horizons: {h!r} is not one of {list(HORIZONS)}")
            elif h in horizons:
                problems.append(f"{where}.horizons: duplicate {h!r}")
            else:
                horizons.append(h)
    params_raw = entry.get("params")
    param_sets: list[dict[str, Any]] = []
    if not isinstance(params_raw, list | tuple) or not params_raw:
        problems.append(f"{where}.params: must be a non-empty list of parameter mappings")
    else:
        seen: set[str] = set()
        for i, p in enumerate(params_raw):
            if not isinstance(p, Mapping) or not all(isinstance(k, str) for k in p):
                problems.append(f"{where}.params[{i}]: must be a mapping with string keys")
                continue
            try:
                key = canonical_params_json(p)
            except (TypeError, ValueError) as exc:
                problems.append(f"{where}.params[{i}]: {exc}")
                continue
            if key in seen:
                problems.append(f"{where}.params[{i}]: duplicate of an earlier parameter set")
                continue
            seen.add(key)
            param_sets.append(dict(p))
    return problems, tuple(horizons), param_sets


def entry_param_sets(
    strategy_id: str, entry: object
) -> tuple[list[str], list[tuple[dict[str, Any], tuple[Horizon, ...], bool, str]]]:
    """Every parameter set of a strategy entry in index order: the packaged ``params`` first, then
    the user's ``user_params``. Returns ``(problems, [(params, horizons, enabled, origin)])``.

    ``disabled_params`` lists packaged indices switched off; a user set carries its own
    ``enabled`` and ``horizons`` (a subset of the entry's). Strategy-level ``enabled`` is not
    applied here.
    """
    where = f"strategies.{strategy_id}"
    problems, horizons, packaged = _entry_problems(strategy_id, entry)
    if problems or not isinstance(entry, Mapping):
        return problems, []
    disabled_raw = entry.get("disabled_params", [])
    disabled: set[int] = set()
    if not isinstance(disabled_raw, list | tuple) or not all(
        isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(packaged)
        for i in disabled_raw
    ):
        problems.append(f"{where}.disabled_params: must be packaged parameter-set indices")
    else:
        disabled = set(disabled_raw)
    sets: list[tuple[dict[str, Any], tuple[Horizon, ...], bool, str]] = [
        (p, horizons, i not in disabled, "packaged") for i, p in enumerate(packaged)
    ]
    user_raw = entry.get("user_params", [])
    if not isinstance(user_raw, list | tuple):
        problems.append(f"{where}.user_params: must be a list")
        return problems, sets
    seen = {canonical_params_json(p) for p in packaged}
    for i, item in enumerate(user_raw):
        at = f"{where}.user_params[{i}]"
        if not isinstance(item, Mapping) or set(item) - _USER_SET_KEYS or "params" not in item:
            problems.append(f"{at}: must be a mapping with params, horizons and optional enabled")
            continue
        params = item["params"]
        if not isinstance(params, Mapping) or not all(isinstance(k, str) for k in params):
            problems.append(f"{at}.params: must be a mapping with string keys")
            continue
        user_h = item.get("horizons", list(horizons))
        if (
            not isinstance(user_h, list | tuple)
            or not user_h
            or any(h not in horizons for h in user_h)
            or len(set(user_h)) != len(user_h)
        ):
            problems.append(f"{at}.horizons: must be a non-empty subset of {list(horizons)}")
            continue
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            problems.append(f"{at}.enabled: must be true or false")
            continue
        try:
            key = canonical_params_json(params)
        except (TypeError, ValueError) as exc:
            problems.append(f"{at}.params: {exc}")
            continue
        if key in seen:
            problems.append(f"{at}.params: duplicate of an earlier parameter set")
            continue
        seen.add(key)
        sets.append((dict(params), tuple(user_h), enabled, "user"))
    return problems, sets


def load_strategies(cfg: AppConfig) -> list[Strategy]:
    """One strategy instance per (enabled strategy, parameter set), in config order.

    ``enabled: false`` entries are skipped and their ``reason`` logged. Unknown ids, malformed
    entries and parameter sets rejected by the strategy raise ``StrategyConfigError`` listing every
    problem. An empty ``strategies: {}`` returns ``[]``.
    """
    section: Mapping[str, Any] = cfg.strategies
    problems: list[str] = []
    instances: list[Strategy] = []
    for strategy_id, entry in section.items():
        if isinstance(entry, Mapping) and entry.get("enabled", True) is False:
            log.info(
                "strategy %s disabled: %s", strategy_id, entry.get("reason", "no reason given")
            )
            continue
        if isinstance(entry, Mapping) and not isinstance(entry.get("enabled", True), bool):
            problems.append(f"strategies.{strategy_id}.enabled: must be true or false")
            continue
        try:
            cls = get_strategy_class(strategy_id)
        except KeyError as exc:
            problems.append(f"strategies.{strategy_id}: {exc.args[0]}")
            continue
        entry_problems, sets = entry_param_sets(strategy_id, entry)
        problems.extend(entry_problems)
        if entry_problems:
            continue
        packaged_count = sum(1 for _p, _h, _e, origin in sets if origin == "packaged")
        for i, (params, horizons, enabled, origin) in enumerate(sets):
            if not enabled:
                continue
            try:
                instances.append(cls(params, horizons))
            except (ValueError, TypeError, KeyError) as exc:
                label = (
                    f"params[{i}]" if origin == "packaged" else f"user_params[{i - packaged_count}]"
                )
                problems.append(f"strategies.{strategy_id}.{label}: {exc}")
    if problems:
        raise StrategyConfigError(problems)
    return instances
