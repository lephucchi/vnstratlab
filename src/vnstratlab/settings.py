"""Secrets and environment settings.

Rules (docs/configuration.md):
- Secrets come only from environment variables or a `.env` file. They are never
  committed, logged, printed, or sent to the browser.
- Non-secret parameters (strategy params, thresholds, costs) live in YAML config,
  not here.
- Variable names are plain and conventional (no project prefix): each field maps to the
  upper-case field name, e.g. `telegram_bot_token` -> `TELEGRAM_BOT_TOKEN`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_NAMES = (
    "APP_HOME",
    "LOG_LEVEL",
    "VNSTOCK_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PO_USERNAME",
    "PO_PASSWORD",
)


class Settings(BaseSettings):
    """Environment-driven settings. Every field maps to the upper-case field name."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App home override (not `HOME`, which belongs to the operating system).
    app_home: Path | None = None
    log_level: str = "INFO"

    # vnstock key, only if the installed vnstock version asks for one (source review: P1-T03).
    vnstock_api_key: SecretStr | None = None

    # Optional Telegram report: the bot's token, and the id of the chat it posts to.
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    # PO dashboard login, used only by the Pages build (tools/encrypt_po.py).
    po_username: str | None = None
    po_password: SecretStr | None = None

    def secret_status(self) -> dict[str, bool]:
        """Which user-facing secrets are configured. Booleans only, never values.

        The PO login is maintainer-only (Pages build) and is not reported here.
        """
        return {
            "vnstock_api_key": self.vnstock_api_key is not None,
            "telegram_bot_token": self.telegram_bot_token is not None,
            "telegram_chat_id": self.telegram_chat_id is not None,
        }


def load_settings(env_file: Path | None = None) -> Settings:
    """Load settings from the environment and an optional `.env` file."""
    if env_file is not None:
        return Settings(_env_file=env_file)
    return Settings()
