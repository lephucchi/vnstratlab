"""tools/build_status.py never writes plaintext PO data, whichever workflow runs it."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_status.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_status", TOOL)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_status"] = mod
    spec.loader.exec_module(mod)
    return mod


bs = _load()


@pytest.mark.parametrize("creds", [True, False])
def test_publish_po_never_plaintext(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, creds: bool
) -> None:
    for name in ("PO_USERNAME", "PO_PASSWORD"):
        if creds:
            monkeypatch.setenv(name, "Zx9-unique")
        else:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env
    po_dir = tmp_path / "po"
    po_dir.mkdir()
    (po_dir / "data.json").write_text("{}", encoding="utf-8")  # stale plaintext
    monkeypatch.setattr("encrypt_po.KDF_ITERATIONS", 1000, raising=False)
    bs.publish_po(b'{"cards": []}', po_dir)
    names = sorted(f.name for f in po_dir.iterdir())
    assert names == (["data.enc.json"] if creds else [])
