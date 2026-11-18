"""Render docs/data-gaps.md from src/vnstratlab/data/gaps.yaml (ADR-007).

Usage:
  python tools/render_gaps.py           # write docs/data-gaps.md
  python tools/render_gaps.py --check   # exit 1 if docs/data-gaps.md is out of date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GAPS_YAML = ROOT / "src" / "vnstratlab" / "data" / "gaps.yaml"
GAPS_MD = ROOT / "docs" / "data-gaps.md"


def render(register: dict[str, Any]) -> str:
    """Return the Markdown page for a parsed gap register."""
    lines = [
        "# Data gaps",
        "",
        "> Generated from `src/vnstratlab/data/gaps.yaml` (single source of truth, "
        "[ADR-007](adr/ADR-007-yahoo-interim-source.md)).",
        "> Edit the YAML, then run `python tools/render_gaps.py`; a test fails if this page is "
        "out of date.",
        "",
        f"Interim price source: **{register['source']}**. Each gap is a known shortfall that is "
        "worked around now and closed later. `vnstratlab data status` prints the same list.",
        "",
        "| ID | Gap | Severity | Status | Affects |",
        "|---|---|---|---|---|",
    ]
    for gap in register["gaps"]:
        lines.append(
            f"| [{gap['id']}](#{gap['id'].lower()}) | {gap['title']} | {gap['severity']} "
            f"| {gap['status']} | {', '.join(gap['affects'])} |"
        )
    lines.append("")
    for gap in register["gaps"]:
        lines += [
            f"## {gap['id']}",
            "",
            f"**{gap['title']}** · *{gap['title_vi']}*",
            "",
            f"- Status: {gap['status']} · severity: {gap['severity']} · since {gap['since']}",
            f"- Missing: {gap['missing']}",
            f"- Affects: {', '.join(gap['affects'])}",
            f"- Workaround now: {gap['workaround']}",
            f"- Closed by: {gap['close_by']}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the page is out of date")
    args = parser.parse_args()
    register = yaml.safe_load(GAPS_YAML.read_text(encoding="utf-8"))
    page = render(register)
    if args.check:
        current = GAPS_MD.read_text(encoding="utf-8") if GAPS_MD.exists() else ""
        if current != page:
            print("docs/data-gaps.md is out of date; run python tools/render_gaps.py")
            return 1
        return 0
    GAPS_MD.write_text(page, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
