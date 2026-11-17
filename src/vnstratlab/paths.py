"""Filesystem locations for user data.

User data (market data, lab results, journal, logs, user config) never lives in
the repository. It lives in a per-user directory chosen by `platformdirs`, which
can be overridden with the `APP_HOME` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "vnstratlab"
HOME_ENV = "APP_HOME"


@dataclass(frozen=True)
class AppPaths:
    """All directories and files the app reads or writes."""

    home: Path

    @property
    def config_file(self) -> Path:
        return self.home / "config.yaml"

    @property
    def env_file(self) -> Path:
        return self.home / ".env"

    @property
    def data_dir(self) -> Path:
        return self.home / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def market_db(self) -> Path:
        return self.data_dir / "market.duckdb"

    @property
    def lab_db(self) -> Path:
        return self.data_dir / "lab.duckdb"

    @property
    def journal_db(self) -> Path:
        return self.data_dir / "journal.sqlite"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.home / "backups"

    @property
    def strategies_dir(self) -> Path:
        """User strategy plug-ins (one .py file per strategy)."""
        return self.home / "strategies"


def default_home() -> Path:
    """Return the app home: `$APP_HOME` if set, else the platform user-data dir."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_data_dir(APP_NAME, appauthor=False))


def get_paths(home: Path | None = None) -> AppPaths:
    """Build `AppPaths` without touching the disk."""
    return AppPaths(home=home if home is not None else default_home())
