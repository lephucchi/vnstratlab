"""Shared fixtures: no test may open a network connection."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that calls ``socket.socket.connect`` (ADR-007: CI never reaches Yahoo)."""

    def refuse(self: socket.socket, address: object) -> None:
        raise AssertionError(f"network access attempted in a unit test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
