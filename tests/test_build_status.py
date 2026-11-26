"""tools/build_status.py: PO data never in plaintext; gap register and card due dates."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

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


GAPS_YAML = """\
version: 1
source: synthetic
gaps:
  - id: GAP-01
    title: First gap
    title_vi: Khoảng trống một
    status: open
    severity: high
    missing: >-
      Something is missing.
    affects: [table_a, P1-T99]
    workaround: Use a fallback.
    close_by: A new card.
    since: 2026-01-02
  - id: GAP-02
    title: Second gap
    title_vi: Khoảng trống hai
    status: mitigated
    severity: low
    missing: Less.
    affects: [table_b]
    workaround: Wait.
    close_by: Later.
    since: 2026-01-03
  - id: GAP-03
    title: Third gap
    title_vi: Khoảng trống ba
    status: closed
    severity: high
    missing: Nothing now.
    affects: []
    workaround: None needed.
    close_by: Done.
    since: 2026-01-04
"""


def _write_gaps(repo: Path, text: str = GAPS_YAML) -> None:
    path = repo / "src" / "vnstratlab" / "data" / "gaps.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


def test_gap_register_from_checkout(tmp_path: Path) -> None:
    _write_gaps(tmp_path)
    gaps = bs.gap_register(tmp_path)
    assert gaps["available"] is True
    assert gaps["origin"] == "checkout"
    assert "fallback" not in gaps
    assert gaps["source"] == "synthetic"
    assert gaps["version"] == 1
    assert gaps["counts"] == {
        "open": 1,
        "mitigated": 1,
        "closed": 1,
        "high": 1,  # the closed high-severity gap is not counted
        "medium": 0,
        "low": 1,
    }
    assert gaps["items"][0] == {
        "id": "GAP-01",
        "title": "First gap",
        "title_vi": "Khoảng trống một",
        "status": "open",
        "severity": "high",
        "missing": "Something is missing.",
        "affects": ["table_a", "P1-T99"],
        "workaround": "Use a fallback.",
        "close_by": "A new card.",
        "since": "2026-01-02",  # YAML date coerced to text
    }
    json.dumps(gaps)  # serialisable


def test_gap_register_missing(tmp_path: Path) -> None:
    assert bs.gap_register(tmp_path) == {"available": False, "reason": "gaps.yaml not found"}


def test_gap_register_date_version_is_serialisable() -> None:
    gaps = bs.parse_gaps("version: 2026-11-18\ngaps: []\n", "develop")
    json.dumps(gaps)
    assert gaps["version"] == "2026-11-18"


def test_safe_gap_register_never_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bs, "gap_register", lambda repo: {"available": True, "x": object()})
    gaps = bs.safe_gap_register(tmp_path)
    assert gaps["available"] is False
    assert gaps["reason"]


def test_plan_and_roadmap_cards_have_due() -> None:
    plan = "## 9. Phase 1 — X\n### M1.1 — Data\n**P1-T01 — First card**\n"
    roadmap = "| P1-T50 | Added card | v0.1.0 |\n"
    assert bs.parse_plan(plan)[0]["due"] == ""
    assert bs.parse_roadmap_cards(roadmap)[0]["due"] == ""


def test_gap_register_without_pyyaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_gaps(tmp_path)
    monkeypatch.setitem(sys.modules, "yaml", None)  # import yaml -> ImportError
    assert bs.gap_register(tmp_path) == {"available": False, "reason": "PyYAML not installed"}


@pytest.mark.parametrize("text", ["gaps: [unclosed", "just text", "gaps: 3"])
def test_gap_register_bad_yaml(tmp_path: Path, text: str) -> None:
    _write_gaps(tmp_path, text)
    gaps = bs.gap_register(tmp_path)
    assert gaps["available"] is False
    assert gaps["reason"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2026-11-21", "2026-11-21"), ("", ""), ("2026-02-30", ""), ("next week", "")],
)
def test_parse_due(raw: str, expected: str) -> None:
    assert bs.parse_due(raw) == expected


def test_card_due_from_front_matter(tmp_path: Path) -> None:
    cards = tmp_path / "docs" / "cards"
    cards.mkdir(parents=True)
    (cards / "P1-T90-a.md").write_text(
        "---\nid: P1-T90\ntitle: A\nstatus: todo\ndue: 2026-11-21\n---\nbody\n", encoding="utf-8"
    )
    (cards / "P1-T91-b.md").write_text(
        "---\nid: P1-T91\ntitle: B\nstatus: done\ndue: soon\n---\nbody\n", encoding="utf-8"
    )
    found = bs.card_files(tmp_path)
    assert found["P1-T90"]["due"] == "2026-11-21"
    assert found["P1-T91"]["due"] == ""


def test_build_po_data_has_gaps_and_due(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs" / "cards").mkdir(parents=True)
    (repo / "docs" / "plan").mkdir()
    (repo / "docs" / "plan" / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "docs" / "cards" / "P1-T90-a.md").write_text(
        "---\nid: P1-T90\ntitle: A\nstatus: todo\ndue: 2026-11-21\n---\n", encoding="utf-8"
    )
    _write_gaps(repo)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)  # no network
    captured: dict[str, Any] = {}

    def fake_publish(plaintext: bytes, po_dir: Path) -> None:
        captured.update(json.loads(plaintext.decode("utf-8")))

    monkeypatch.setattr(bs, "publish_po", fake_publish)
    bs.build(repo, tmp_path / "out", None, None, None)
    assert captured["gaps"]["counts"]["open"] == 1
    assert captured["cards"][0]["due"] == "2026-11-21"
    status = json.loads((tmp_path / "out" / "data" / "status.json").read_text(encoding="utf-8"))
    assert "gaps" not in status  # public status.json carries measured facts only


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("in review", "in-review"),
        ("In Progress", "in-progress"),
        ("changes_requested", "changes-requested"),
        ("done", "done"),
        ("superseded", "superseded"),
        ("someday", "todo"),
        ("", "todo"),
    ],
)
def test_normalise_status(raw: str, expected: str) -> None:
    assert bs.normalise_status(raw) == expected


@pytest.mark.parametrize(
    ("range_id", "ids", "expected"),
    [
        ("P1-T14…P1-T19", {"P1-T15"}, True),
        ("P1-T14…P1-T19", {"P1-T13", "P1-T20", "P1-T16b"}, False),
        ("P1-T14…P1-T19", set(), False),
        ("P1-T14", {"P1-T14"}, False),
    ],
)
def test_covered_by_range(range_id: str, ids: set[str], expected: bool) -> None:
    assert bs.covered_by_range(range_id, ids) is expected


def test_build_drops_covered_range_and_superseded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    cards = repo / "docs" / "cards"
    cards.mkdir(parents=True)
    (repo / "docs" / "plan").mkdir()
    (repo / "docs" / "plan" / "plan.md").write_text(
        "## 4. Phase 1 — Core\n### M1.1 — Data\n**P1-T03 — Old source**\n"
        "**P1-T14 … P1-T16 — Strategies**\n**P1-T20 … P1-T21 — Lab**\n",
        encoding="utf-8",
    )
    (cards / "P1-T03-a.md").write_text(
        "---\nid: P1-T03\ntitle: Old source\nstatus: superseded\n---\n", encoding="utf-8"
    )
    (cards / "P1-T15-b.md").write_text(
        "---\nid: P1-T15\ntitle: S\nstatus: in review\n---\n", encoding="utf-8"
    )
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        bs, "publish_po", lambda plaintext, po_dir: captured.update(json.loads(plaintext))
    )
    bs.build(repo, tmp_path / "out", None, None, None)
    ids = {c["id"]: c["status"] for c in captured["cards"]}
    assert "P1-T14…P1-T16" not in ids  # a member has its own card
    assert "P1-T20…P1-T21" in ids  # no member card yet
    assert "P1-T03" not in ids
    assert captured["superseded"] == [{"id": "P1-T03", "title": "Old source"}]
    assert ids["P1-T15"] == "in-review"
    status = json.loads((tmp_path / "out" / "data" / "status.json").read_text(encoding="utf-8"))
    assert status["cards_total"] == len(captured["cards"])


# ------------------------------------------------------------------ demo run (PO data only)


def _fake_demo_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    run_id = "20261126T103350-demo-8686"
    run_dir = home / "logs" / "runs" / run_id
    (run_dir / "demo" / "equity").mkdir(parents=True)
    run = {
        "run_id": run_id,
        "status": "success",
        "created_at": "2026-11-26T10:33:50+00:00",
        "ended_at": "2026-11-26T10:34:34+00:00",
        "duration_s": 44.0,
        "tasks": [
            {"id": "a", "label_vi": "Một", "status": "success", "duration_s": 1.5, "upstream": []},
            {
                "id": "b",
                "label_vi": "Hai",
                "status": "success",
                "duration_s": 2.0,
                "upstream": ["a"],
                "summary": {"rows": 3},
            },
        ],
    }
    (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (run_dir / "a.log").write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    (run_dir / "demo" / "summary.csv").write_text(
        "trial_id,trial,horizon,Sharpe\n"
        "t1,S01 x,short,0.5\nt2,S02 y,short,1.5\nb1,S17_equal_weight (benchmark),short,0.1\n",
        encoding="utf-8",
    )
    for tid in ("t1", "t2", "b1"):
        rows = "".join(f"2020-01-{d:02d},{100 + d}\n" for d in range(1, 29))
        (run_dir / "demo" / "equity" / f"{tid}.csv").write_text(
            "date,equity\n" + rows * 20, encoding="utf-8"
        )
    return home


def test_build_demo_from_run_folder(tmp_path: Path) -> None:
    demo = bs.build_demo(_fake_demo_home(tmp_path))
    assert demo["available"] is True
    assert demo["run_id"] == "20261126T103350-demo-8686"
    assert [t["id"] for t in demo["tasks"]] == ["a", "b"]
    assert demo["edges"] == [{"from": "a", "to": "b"}]
    assert demo["logs"]["a"] == [f"line {i}" for i in range(60, 100)]  # last 40 lines
    assert demo["logs"]["b"] == []
    assert demo["results"]["columns"] == ["trial_id", "trial", "horizon", "Sharpe"]
    assert set(demo["equity"]) == {"b1", "t1", "t2"}  # benchmark + top trials
    assert len(demo["equity"]["t1"]["dates"]) == 260  # 560 points downsampled
    assert demo["equity"]["t1"]["dates"][-1] == "2020-01-28"


@pytest.mark.parametrize("missing", [True, False])
def test_build_demo_unavailable(tmp_path: Path, missing: bool) -> None:
    demo = bs.build_demo(None if missing else tmp_path / "empty")
    assert demo["available"] is False
    assert demo["reason"]


def test_demo_only_in_po_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs" / "plan").mkdir(parents=True)
    (repo / "docs" / "plan" / "plan.md").write_text("# Plan\n", encoding="utf-8")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)  # no network
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        bs, "publish_po", lambda plain, po_dir: captured.update(json.loads(plain.decode("utf-8")))
    )
    bs.build(repo, tmp_path / "out", None, None, None, _fake_demo_home(tmp_path))
    assert captured["demo"]["available"] is True
    status_text = (tmp_path / "out" / "data" / "status.json").read_text(encoding="utf-8")
    assert "demo" not in status_text
    assert "20261126T103350" not in status_text
