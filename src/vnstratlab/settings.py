"""Secrets and environment settings.

Rules (docs/configuration.md):
- Secrets come only from environment variables or a `.env` file. They are never
  committed, logged, printed, or sent to the browser.
- Non-secret parameters (strategy params, thresholds, costs) live in YAML config,
  not here.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "VNSTRATLAB_"


class Settings(BaseSettings):
    """Environment-driven settings. Every field maps to `VNSTRATLAB_<FIELD>`."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    home: Path | None = None
    log_level: str = "INFO"

    # Market data provider key, only if the chosen source requires one.
    data_api_key: SecretStr | None = None

    # Optional notifications.
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    # Phase 2 news scoring.
    llm_api_key: SecretStr | None = None

    # PO dashboard login (Pages build only): the dashboard data is encrypted with a key
    # derived from these two values; see tools/encrypt_po.py.
    po_user: str | None = None
    po_password: SecretStr | None = None

    def secret_status(self) -> dict[str, bool]:
        """Which secrets are configured. Returns booleans only, never values."""
        return {
            "data_api_key": self.data_api_key is not None,
            "telegram_bot_token": self.telegram_bot_token is not None,
            "telegram_chat_id": self.telegram_chat_id is not None,
            "llm_api_key": self.llm_api_key is not None,
            "po_user": self.po_user is not None,
            "po_password": self.po_password is not None,
        }


def load_settings(env_file: Path | None = None) -> Settings:
    """Load settings from the environment and an optional `.env` file."""
    if env_file is not None:
        return Settings(_env_file=env_file)
    return Settings()
