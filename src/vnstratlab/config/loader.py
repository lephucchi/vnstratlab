"""Load, merge and validate the configuration.

Sources, in increasing priority:
1. packaged ``defaults.yaml``, ``markets/<project.market>.yaml`` and
   ``universes/<project.universe>.yaml``
2. the user's ``<app home>/config.yaml``

Merge rule: dicts merge recursively; lists and scalars replace. Keys under ``market:`` and
``universe:`` in the user file are merged over the packaged market / universe files.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from vnstratlab.config.models import AppConfig, holiday_date_problem
from vnstratlab.paths import get_paths

_NAME = re.compile(r"^[a-z0-9_]+$")


class ConfigError(ValueError):
    """Invalid configuration. ``problems`` holds one ``dotted.path: reason`` line per problem."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(problems))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` with ``override`` merged in: dicts recurse, everything else replaces."""
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _parse_yaml(text: str, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([f"{label}: invalid YAML ({exc})"]) from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError([f"{label}: top level must be a mapping"])
    return data


def _packaged(resource: str) -> dict[str, Any]:
    text = files("vnstratlab.config").joinpath(resource).read_text(encoding="utf-8")
    return _parse_yaml(text, resource)


def _packaged_named(folder: str, name: object, path: str) -> dict[str, Any]:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ConfigError([f"{path}: must be a lowercase name (letters, digits, underscore)"])
    resource = files("vnstratlab.config").joinpath(folder, f"{name}.yaml")
    if not resource.is_file():
        raise ConfigError([f"{path}: no packaged file {folder}/{name}.yaml"])
    return _parse_yaml(resource.read_text(encoding="utf-8"), f"{folder}/{name}.yaml")


def _as_mapping(value: object, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError([f"{path}: must be a mapping"])
    return value


def _format_errors(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for err in exc.errors(include_url=False):
        loc = [str(part) for part in err["loc"] if part != "[key]"]
        message = str(err["msg"]).removeprefix("Value error, ")
        for line in message.split("\n"):
            if line.startswith("@") and "|" in line:
                suffix, reason = line[1:].split("|", 1)
                problems.append(f"{'.'.join([*loc, suffix])}: {reason}")
            else:
                problems.append(f"{'.'.join(loc)}: {line}")
    return problems


def _read_user(home: Path | None) -> dict[str, Any]:
    config_file = get_paths(home).config_file
    if not config_file.is_file():
        if config_file.exists():
            raise ConfigError([f"{config_file}: not a file"])
        return {}
    try:
        text = config_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError([f"{config_file}: cannot read ({exc})"]) from None
    return _parse_yaml(text, str(config_file))


def _normalise_holiday_years(market: dict[str, Any], path: str) -> dict[str, Any]:
    """Return ``market`` with holiday year keys as ints (a quoted "2026" becomes 2026).

    Done before merging so a quoted year cannot sit next to the packaged int year.
    """
    holidays = market.get("holidays")
    if holidays is None:
        return market
    if not isinstance(holidays, dict):
        raise ConfigError([f"{path}.holidays: must be a mapping of year to holidays"])
    years: dict[int, Any] = {}
    problems: list[str] = []
    for key, block in holidays.items():
        if isinstance(key, int) and not isinstance(key, bool):
            year = key
        elif isinstance(key, str) and key.strip().isdecimal():
            year = int(key)
        else:
            problems.append(f"{path}.holidays.{key}: year must be an integer")
            continue
        if year in years:
            problems.append(f"{path}.holidays.{year}: year is listed more than once")
            continue
        years[year] = block
    if problems:
        raise ConfigError(problems)
    return {**market, "holidays": years}


def _raw_holiday_problems(market: dict[str, Any]) -> list[str]:
    """Weekday / in-year problems found on raw data, independent of other field errors."""
    problems: list[str] = []
    holidays = market.get("holidays")
    if not isinstance(holidays, dict):
        return problems
    for year, block in holidays.items():
        days = block.get("days") if isinstance(block, dict) else None
        if not isinstance(days, list):
            continue
        for index, day in enumerate(days):
            raw = day.get("date") if isinstance(day, dict) else None
            if isinstance(raw, str):
                try:
                    raw = dt.date.fromisoformat(raw)
                except ValueError:
                    continue
            if isinstance(raw, dt.date) and (problem := holiday_date_problem(year, raw)):
                problems.append(f"market.holidays.{year}.days.{index}.date: {problem}")
    return problems


@dataclass(frozen=True)
class LoadedConfig:
    """A validated config plus facts about the user file that the config itself does not keep."""

    config: AppConfig
    user_holiday_years: tuple[int, ...]  # years whose holidays the user file supplies


def load_config_with_info(home: Path | None = None) -> LoadedConfig:
    """Like :func:`load_config`, also reporting which holiday years the user file overrides.

    Any year block in the user file counts, including an empty ``days`` list (which removes
    all holidays of that year).
    """
    user = _read_user(home)

    user_market = _normalise_holiday_years(
        _as_mapping(user.pop("market", None), "market"), "market"
    )
    user_universe = _as_mapping(user.pop("universe", None), "universe")

    merged = deep_merge(_packaged("defaults.yaml"), user)
    project = _as_mapping(merged.get("project"), "project")
    packaged_market = _normalise_holiday_years(
        _packaged_named("markets", project.get("market"), "project.market"), "market"
    )
    market = deep_merge(packaged_market, user_market)
    universe = deep_merge(
        _packaged_named("universes", project.get("universe"), "project.universe"), user_universe
    )
    override_years = tuple(sorted(user_market.get("holidays") or {}))

    problems: list[str] = []
    config: AppConfig | None = None
    try:
        config = AppConfig.model_validate({**merged, "market": market, "universe": universe})
    except ValidationError as exc:
        problems = _format_errors(exc)
    problems += [p for p in _raw_holiday_problems(market) if p not in problems]
    if problems or config is None:
        raise ConfigError(problems)
    return LoadedConfig(config=config, user_holiday_years=override_years)


def load_config(home: Path | None = None) -> AppConfig:
    """Build the validated, immutable :class:`AppConfig`.

    ``home`` is the app home (default: ``vnstratlab.paths.default_home()``); its
    ``config.yaml`` is optional. Raises :class:`ConfigError` listing every problem.
    """
    return load_config_with_info(home).config
