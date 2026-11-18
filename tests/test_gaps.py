"""Gap register model, rendered page and `vnstratlab data gaps` (P1-T38)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from vnstratlab.cli import app
from vnstratlab.data.gaps import GAPS_FILE, GapError, gaps_summary_line, load_gaps

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def render_module() -> Any:
    spec = importlib.util.spec_from_file_location("render_gaps", ROOT / "tools" / "render_gaps.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_gaps"] = module
    spec.loader.exec_module(module)
    return module


def valid_gap(number: int = 1, **changes: Any) -> dict[str, Any]:
    gap: dict[str, Any] = {
        "id": f"GAP-{number:02d}",
        "title": "A synthetic gap",
        "title_vi": "Một khoảng trống giả",
        "status": "open",
        "severity": "low",
        "missing": "something",
        "affects": ["prices_daily"],
        "workaround": "do this",
        "close_by": "a card",
        "since": "2026-11-18",
    }
    gap.update(changes)
    return gap


def write_register(tmp_path: Path, gaps: list[dict[str, Any]]) -> Path:
    path = tmp_path / "gaps.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "source": "synthetic", "gaps": gaps}), encoding="utf-8"
    )
    return path


# ------------------------------------------------------------------ the shipped register


def test_shipped_register_loads() -> None:
    register = load_gaps()
    assert register.source == "yahoo"
    assert len(register.gaps) >= 1


def test_ids_are_unique_formatted_and_sequential() -> None:
    ids = [g.id for g in load_gaps().gaps]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"GAP-\d{2}", i) for i in ids)
    assert ids == [f"GAP-{n:02d}" for n in range(1, len(ids) + 1)]


def test_every_field_is_present_and_enums_hold() -> None:
    raw = yaml.safe_load(GAPS_FILE.read_text(encoding="utf-8"))
    fields = set(valid_gap())
    for gap in raw["gaps"]:
        assert set(gap) == fields
    for gap in load_gaps().gaps:
        assert gap.severity in {"high", "medium", "low"}
        assert gap.status in {"open", "mitigated", "closed"}
        assert gap.title_vi


def test_open_counts_and_summary_line() -> None:
    register = load_gaps()
    counts = register.open_counts()
    assert counts["open"] == counts["high"] + counts["medium"] + counts["low"]
    line = gaps_summary_line(register)
    assert line == (
        f"gaps: {counts['open']} open "
        f"(high {counts['high']}, medium {counts['medium']}, low {counts['low']})"
    )


# ------------------------------------------------------------------ validation


def test_a_valid_register_loads(tmp_path: Path) -> None:
    register = load_gaps(write_register(tmp_path, [valid_gap(1), valid_gap(2, severity="high")]))
    assert register.open_counts() == {"open": 2, "high": 1, "medium": 0, "low": 1}


@pytest.mark.parametrize(
    "gaps",
    [
        [valid_gap(1), valid_gap(1)],  # duplicate id
        [valid_gap(1), valid_gap(3)],  # not sequential
        [valid_gap(2)],  # does not start at 01
        [valid_gap(1, id="GAP-1")],  # bad format
        [valid_gap(1, id="GAP-001")],
        [valid_gap(1, severity="critical")],
        [valid_gap(1, status="done")],
        [valid_gap(1, title_vi="")],
        [valid_gap(1, affects=[])],
        [{k: v for k, v in valid_gap(1).items() if k != "workaround"}],  # missing field
        [valid_gap(1, surprise="x")],  # unknown field
        [valid_gap(1, since="not a date")],
        [],
    ],
)
def test_invalid_registers_are_rejected(tmp_path: Path, gaps: list[dict[str, Any]]) -> None:
    with pytest.raises(GapError):
        load_gaps(write_register(tmp_path, gaps))


def test_a_missing_file_is_a_gap_error(tmp_path: Path) -> None:
    with pytest.raises(GapError):
        load_gaps(tmp_path / "absent.yaml")


def test_status_filter(tmp_path: Path) -> None:
    gaps = [valid_gap(1), valid_gap(2, status="closed"), valid_gap(3, status="mitigated")]
    register = load_gaps(write_register(tmp_path, gaps))
    assert [g.id for g in register.with_status("open")] == ["GAP-01"]
    assert [g.id for g in register.with_status("closed")] == ["GAP-02"]
    assert len(register.with_status(None)) == 3


# ------------------------------------------------------------------ docs/data-gaps.md


def test_rendered_page_is_in_sync_with_the_yaml() -> None:
    module = render_module()
    register = yaml.safe_load(GAPS_FILE.read_text(encoding="utf-8"))
    page = (ROOT / "docs" / "data-gaps.md").read_text(encoding="utf-8")
    assert page == module.render(register), "run: python tools/render_gaps.py"


def test_the_renderer_check_mode_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = render_module()
    monkeypatch.setattr(sys, "argv", ["render_gaps.py", "--check"])
    assert module.main() == 0


# ------------------------------------------------------------------ CLI


def test_data_gaps_lists_the_register() -> None:
    result = runner.invoke(app, ["data", "gaps"])
    assert result.exit_code == 0, result.output
    for gap in load_gaps().gaps:
        assert gap.id in result.output
        assert gap.title_vi in result.output


def test_data_gaps_json_and_status_filter() -> None:
    everything = json.loads(runner.invoke(app, ["data", "gaps", "--json"]).output)
    assert [g["id"] for g in everything] == [g.id for g in load_gaps().gaps]
    open_only = json.loads(
        runner.invoke(app, ["data", "gaps", "--status", "open", "--json"]).output
    )
    assert all(g["status"] == "open" for g in open_only)
    closed = runner.invoke(app, ["data", "gaps", "--status", "closed"])
    assert closed.exit_code == 0
    assert "no gaps" in closed.output


def test_data_gaps_rejects_an_unknown_status() -> None:
    assert runner.invoke(app, ["data", "gaps", "--status", "done"]).exit_code == 2
