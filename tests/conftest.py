from __future__ import annotations

from pathlib import Path

import pytest

from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig


@pytest.fixture(scope="session")
def engine_cfg(tmp_path_factory: pytest.TempPathFactory) -> AppConfig:
    """Packaged defaults (no user config) for engine tests."""
    home: Path = tmp_path_factory.mktemp("engine_home")
    return load_config(home)
