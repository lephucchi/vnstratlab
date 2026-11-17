"""tools/encrypt_po.py: PO dashboard data is published only encrypted (or not at all)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.exceptions import InvalidTag

from vnstratlab.settings import Settings

TOOL = Path(__file__).resolve().parents[1] / "tools" / "encrypt_po.py"
FAST = 1_000  # PBKDF2 iterations for tests only


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("encrypt_po", TOOL)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["encrypt_po"] = mod
    spec.loader.exec_module(mod)
    return mod


ep = _load()


def _settings(monkeypatch: pytest.MonkeyPatch, user: str | None, pw: str | None) -> Settings:
    for name, value in (("VNSTRATLAB_PO_USER", user), ("VNSTRATLAB_PO_PASSWORD", pw)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_roundtrip() -> None:
    env = ep.encrypt(b'{"a": 1}', "po", "s3cret-pass", iterations=FAST)
    assert env["alg"] == "AES-256-GCM"
    assert env["iter"] == FAST
    assert ep.decrypt(env, "po", "s3cret-pass") == b'{"a": 1}'


@pytest.mark.parametrize(("user", "pw"), [("po", "wrong"), ("other", "s3cret-pass")])
def test_wrong_credentials_fail(user: str, pw: str) -> None:
    env = ep.encrypt(b"x", "po", "s3cret-pass", iterations=FAST)
    with pytest.raises(InvalidTag):
        ep.decrypt(env, user, pw)


def test_fresh_salt_and_iv() -> None:
    a = ep.encrypt(b"x", "po", "pw", iterations=FAST)
    b = ep.encrypt(b"x", "po", "pw", iterations=FAST)
    assert a["salt"] != b["salt"]
    assert a["iv"] != b["iv"]


def test_run_encrypts_and_removes_plaintext(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src, dst = tmp_path / "data.json", tmp_path / "data.enc.json"
    src.write_text('{"cards": []}', encoding="utf-8")
    settings = _settings(monkeypatch, "po", "s3cret-pass")
    assert ep.run(src, dst, settings, iterations=FAST) is True
    assert not src.exists()
    env = json.loads(dst.read_text(encoding="utf-8"))
    assert "cards" not in dst.read_text(encoding="utf-8")
    assert ep.decrypt(env, "po", "s3cret-pass") == b'{"cards": []}'
    out = capsys.readouterr().out
    assert "s3cret-pass" not in out


@pytest.mark.parametrize(("user", "pw"), [(None, None), ("po", None), (None, "pw"), ("po", "")])
def test_run_without_credentials_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, user: str | None, pw: str | None
) -> None:
    src, dst = tmp_path / "data.json", tmp_path / "data.enc.json"
    src.write_text("{}", encoding="utf-8")
    dst.write_text("stale", encoding="utf-8")
    assert ep.run(src, dst, _settings(monkeypatch, user, pw)) is False
    assert not src.exists()
    assert not dst.exists()


def test_main_missing_input(tmp_path: Path) -> None:
    assert ep.main(["--in", str(tmp_path / "nope.json"), "--out", str(tmp_path / "o")]) == 1


def test_secret_status_reports_po(monkeypatch: pytest.MonkeyPatch) -> None:
    status = _settings(monkeypatch, "po", "pw").secret_status()
    assert status["po_user"] is True
    assert status["po_password"] is True
    assert "pw" not in repr(_settings(monkeypatch, "po", "pw"))
