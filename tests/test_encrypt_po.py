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
    for name, value in (("PO_USERNAME", user), ("PO_PASSWORD", pw)):
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


# Fixed vector: also decrypted by the PO page's WebCrypto code (Node check in PR #1).
VECTOR = {
    "v": 1,
    "alg": "AES-256-GCM",
    "kdf": "PBKDF2-SHA256",
    "iter": 1000,
    "salt": "AAECAwQFBgcICQoLDA0ODw==",
    "iv": "AAECAwQFBgcICQoL",
    "data": "Z/HACvy/Qb8yOZqnDAogHlIfDZ2jzPQASJP+",
}


def test_known_vector() -> None:
    env = ep.encrypt(
        b'{"ok":true}', "po", "Zx9-tr\u00e2u", 1000, salt=bytes(range(16)), iv=bytes(range(12))
    )
    assert env == VECTOR


@pytest.mark.parametrize(
    ("user", "pw"),
    [
        ("po", "Zx9-tr\u00e2u"),
        (" po ", "Zx9-tr\u00e2u\n"),  # secret saved with a trailing newline
        ("po", "Zx9-tra\u0302u"),  # NFD form of the same password
    ],
)
def test_normalised_credentials_decrypt(user: str, pw: str) -> None:
    assert ep.decrypt(VECTOR, user, pw) == b'{"ok":true}'


def test_publish_never_writes_plaintext(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    po_dir = tmp_path / "po"
    assert ep.publish(b'{"cards": []}', po_dir, _settings(monkeypatch, "po", "Zx9-unique"), 1000)
    assert [f.name for f in po_dir.iterdir()] == ["data.enc.json"]


def test_publish_without_credentials_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ep.publish(b"{}", tmp_path, _settings(monkeypatch, None, None)) is False
    assert "::warning::" in capsys.readouterr().out
    assert not any(tmp_path.iterdir())


def test_po_login_not_in_doctor_and_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, "po", "Zx9-unique")
    assert "po_password" not in settings.secret_status()
    assert "Zx9-unique" not in repr(settings)
