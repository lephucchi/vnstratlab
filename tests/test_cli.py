from __future__ import annotations

import pytest
from typer.testing import CliRunner

from vnstratlab import __version__
from vnstratlab.cli import app

runner = CliRunner()

EXPECTED_COMMANDS = [
    "doctor",
    "demo",
    "init",
    "ingest",
    "backtest",
    "lab",
    "meta-backtest",
    "stress",
    "daily",
    "serve",
]


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in EXPECTED_COMMANDS:
        assert command in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize(
    ("args", "card"),
    [
        (["demo"], "P1-T32"),
        (["init"], "P1-T35"),
        (["backtest", "--strategy", "S02_breakout20"], "P1-T20"),
        (["lab", "--horizon", "short"], "P1-T22"),
        (["meta-backtest", "--horizon", "long"], "P1-T23"),
        (["stress", "--horizon", "medium"], "P1-T33"),
        (["daily", "--dry-run"], "P1-T26"),
        (["serve"], "P1-T27"),
    ],
)
def test_stubs_fail_loudly_and_name_their_card(args: list[str], card: str) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert card in result.output


def test_ingest_rejects_bad_date() -> None:
    result = runner.invoke(app, ["ingest", "--from", "2020-13-45"])
    assert result.exit_code != 0


def test_lab_rejects_unknown_horizon() -> None:
    result = runner.invoke(app, ["lab", "--horizon", "weekly"])
    assert result.exit_code == 2


def test_doctor_never_prints_secret_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    secret = "synthetic-secret-value-123"  # noqa: S105 - synthetic test value
    monkeypatch.chdir(str(tmp_path))  # a developer's own .env in the repo must not matter
    monkeypatch.setenv("APP_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert secret not in result.output
    assert "telegram_bot_token" in result.output
    assert "vnstock" not in result.output.lower()
    assert "set" in result.output
