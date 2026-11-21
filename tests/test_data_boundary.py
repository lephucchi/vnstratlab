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


ENGINE_FORBIDDEN_IMPORTS = (
    "duckdb",
    "pyarrow",
    "vnstratlab.data",
    "vnstratlab.config.loader",
    "httpx",
    "requests",
    "socket",
    "urllib",
    "sqlite3",
    "pathlib",
    "os",
    "shutil",
    "tempfile",
    "io",
)
ENGINE_FORBIDDEN_CALLS = {
    "open",
    "read_csv",
    "read_parquet",
    "read_json",
    "read_sql",
    "read_pickle",
    "read_feather",
    "to_csv",
    "to_parquet",
    "to_json",
    "to_pickle",
    "to_sql",
    "to_feather",
    "read_text",
    "write_text",
}


def _engine_violations(path: Path, root: Path = SRC) -> list[str]:
    """Forbidden imports and file/DB/network helper calls in one engine module."""
    bad = [
        name
        for name in _imports(path, root)
        if any(name == f or name.startswith(f + ".") for f in ENGINE_FORBIDDEN_IMPORTS)
    ]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called in ENGINE_FORBIDDEN_CALLS:
                bad.append(f"call {called}()")
    return bad


def test_engine_stays_pure() -> None:
    files = list((SRC / "engine").rglob("*.py"))
    assert len(files) >= 6  # rules, costs, ledger, orders, loop, __init__
    offenders = [f"{p.name}: {v}" for p in files for v in _engine_violations(p)]
    assert offenders == []


def test_risk_stays_pure() -> None:
    files = list((SRC / "risk").rglob("*.py"))
    assert len(files) >= 3  # atr, layer, __init__
    offenders = [f"{p.name}: {v}" for p in files for v in _engine_violations(p)]
    assert offenders == []


def test_engine_purity_checker_detects_violations(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import duckdb\nimport socket\nfrom pathlib import Path\n"
        "from vnstratlab.data import store\nimport pandas as pd\n"
        "f = open('x')\npd.read_csv('x')\ndf.to_parquet('y')\n"
    )
    found = _engine_violations(bad, tmp_path)
    for expected in (
        "duckdb",
        "socket",
        "pathlib",
        "vnstratlab.data.store",
        "call open()",
        "call read_csv()",
        "call to_parquet()",
    ):
        assert expected in found


def test_features_core_stays_pure() -> None:
    """The feature computation (core, groups, package init) does no I/O; ``build`` is the store
    side and is the only features module that may import ``vnstratlab.data``."""
    files = [p for p in (SRC / "features").rglob("*.py") if p.name != "build.py"]
    assert {p.name for p in files} >= {"__init__.py", "core.py", "groups.py"}
    offenders = [f"{p.name}: {v}" for p in files for v in _engine_violations(p)]
    assert offenders == []
    init_imports = _imports(SRC / "features" / "__init__.py")
    # importing the package never pulls the store side in
    assert not [n for n in init_imports if n.startswith("vnstratlab.features.build")]
