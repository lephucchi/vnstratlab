"""Import boundary (ADR-007 section 3): downstream code reads tables, never a source."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "vnstratlab"
DOWNSTREAM = ("engine", "features", "strategies", "lab", "risk", "portfolio", "execution")
FORBIDDEN = ("vnstratlab.data.sources", "yfinance")


def _package_of(path: Path, root: Path = SRC) -> list[str]:
    """Dotted package parts of the module at ``path``, e.g. engine/x.py -> [vnstratlab, engine]."""
    return ["vnstratlab", *path.relative_to(root).parts[:-1]]


def _imports(path: Path, root: Path = SRC) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = _package_of(path, root)
                base = package[: len(package) - (node.level - 1)]
                module = ".".join([*base, *([node.module] if node.module else [])])
            elif node.module:
                module = node.module
            else:
                continue
            found.append(module)
            found.extend(f"{module}.{alias.name}" for alias in node.names)
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


def test_boundary_checker_resolves_relative_imports(tmp_path: Path) -> None:
    pkg = tmp_path / "engine"
    pkg.mkdir()
    bad = pkg / "bad.py"
    bad.write_text(
        "from ..data.sources import synthetic\n"
        "from ..data import sources\n"
        "from ..data import protocol\n"
        "from . import sibling\n"
    )
    names = [n for n in _imports(bad, tmp_path) if _is_forbidden(n)]
    assert "vnstratlab.data.sources.synthetic" in names
    assert "vnstratlab.data.sources" in names
    assert "vnstratlab.data.protocol" in _imports(bad, tmp_path)  # resolved, then not flagged
    assert not any(n.endswith("protocol") for n in names)
    nested = pkg / "sub"
    nested.mkdir()
    deep = nested / "mod.py"
    deep.write_text("from .. import data\nfrom . import sibling\n")
    assert _imports(deep, tmp_path) == [
        "vnstratlab.engine",
        "vnstratlab.engine.data",
        "vnstratlab.engine.sub",
        "vnstratlab.engine.sub.sibling",
    ]


def test_downstream_scan_uses_the_relative_resolver() -> None:
    scanned = [p for package in DOWNSTREAM for p in (SRC / package).rglob("*.py")]
    assert scanned  # the downstream packages exist and are scanned
    assert all(_package_of(p)[1] in DOWNSTREAM for p in scanned)
    for path in scanned:
        assert [n for n in _imports(path) if _is_forbidden(n)] == []


def test_importing_data_package_pulls_no_source_library() -> None:
    code = (
        "import sys, vnstratlab.data, vnstratlab.data.protocol, vnstratlab.data.store, "
        "vnstratlab.data.pipeline\n"
        "bad = [m for m in sys.modules\n"
        "       if m == 'yfinance' or m == 'vnstratlab.data.sources'\n"
        "       or m.startswith('vnstratlab.data.sources.')]\n"
        "assert not bad, bad\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
