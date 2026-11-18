"""Shared fixtures: no test may open a network connection."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a socket connection (ADR-007: CI never reaches Yahoo).

    Blocks ``socket.socket.connect``, ``connect_ex`` and ``socket.create_connection``.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"network access attempted in a unit test: {args[1:]!r}")

    def refuse_create(address: object, *args: object, **kwargs: object) -> None:
        raise AssertionError(f"network access attempted in a unit test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse_create)


@pytest.fixture(scope="session")
def engine_cfg(tmp_path_factory: pytest.TempPathFactory) -> AppConfig:
    """Packaged defaults (no user config) for engine tests."""
    home: Path = tmp_path_factory.mktemp("engine_home")
    return load_config(home)
