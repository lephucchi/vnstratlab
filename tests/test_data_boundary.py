"""Import boundary (ADR-007 section 3): downstream code reads tables, never a source."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "vnstratlab"
DOWNSTREAM = ("engine", "features", "strategies", "lab", "risk", "portfolio", "execution")
FORBIDDEN = ("vnstratlab.data.sources", "yfinance")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
            found.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _is_forbidden(name: str) -> bool:
    return any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN)


def test_downstream_packages_do_not_import_sources() -> None:
    offenders: list[str] = []
    for package in DOWNSTREAM:
        for path in (SRC / package).rglob("*.py"):
            offenders += [
                f"{path.relative_to(SRC)}: {name}" for name in _imports(path) if _is_forbidden(name)
            ]
    assert offenders == []


def test_boundary_checker_detects_a_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("from vnstratlab.data.sources import synthetic\nimport yfinance\n")
    names = [n for n in _imports(bad) if _is_forbidden(n)]
    assert "vnstratlab.data.sources.synthetic" in names
    assert "yfinance" in names


def test_importing_data_package_pulls_no_source_library() -> None:
    code = (
        "import sys, vnstratlab.data, vnstratlab.data.protocol, vnstratlab.data.store, "
        "vnstratlab.data.pipeline\n"
        "bad = [m for m in sys.modules\n"
        "       if m == 'yfinance' or m.startswith('vnstratlab.data.sources.')]\n"
        "assert not bad, bad\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
