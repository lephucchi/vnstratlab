from __future__ import annotations

from pathlib import Path

import pytest

from vnstratlab.paths import default_home, get_paths
from vnstratlab.settings import Settings, load_settings


def test_home_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    assert default_home() == tmp_path.resolve()


def test_default_home_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VNSTRATLAB_HOME", raising=False)
    assert "vnstratlab" in str(default_home()).lower()


def test_paths_layout(tmp_path: Path) -> None:
    paths = get_paths(tmp_path)
    assert paths.market_db == tmp_path / "data" / "market.duckdb"
    assert paths.lab_db.parent == paths.data_dir
    assert paths.journal_db.name == "journal.sqlite"
    assert paths.raw_dir.parent == paths.data_dir
    assert paths.config_file.name == "config.yaml"
    assert paths.env_file.name == ".env"
    assert paths.logs_dir.parent == tmp_path
    assert paths.backups_dir.parent == tmp_path
    assert paths.strategies_dir.parent == tmp_path
    assert not tmp_path.joinpath("data").exists()  # get_paths never touches disk


def test_secrets_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VNSTRATLAB_TELEGRAM_BOT_TOKEN", "synthetic-token")
    settings = Settings()
    assert "synthetic-token" not in repr(settings)
    assert settings.secret_status()["telegram_bot_token"] is True
    assert settings.secret_status()["llm_api_key"] is False


def test_load_settings_from_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VNSTRATLAB_LLM_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("VNSTRATLAB_LLM_API_KEY=synthetic-llm-key\n", encoding="utf-8")
    settings = load_settings(env_file)
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "synthetic-llm-key"
