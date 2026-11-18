"""Gap register: typed loader for ``gaps.yaml`` (ADR-007).

The YAML file is the single source of truth for known data shortfalls. It is read by
``vnstratlab data status`` / ``data gaps`` and rendered into ``docs/data-gaps.md``.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

GAPS_FILE = Path(__file__).with_name("gaps.yaml")
GapStatus = Literal["open", "mitigated", "closed"]
GapSeverity = Literal["high", "medium", "low"]
SEVERITIES: tuple[GapSeverity, ...] = ("high", "medium", "low")
_ID = re.compile(r"^GAP-(\d{2})$")

Text = Annotated[str, Field(min_length=1)]


class GapError(ValueError):
    """The gap register is malformed."""


class Gap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(pattern=r"^GAP-\d{2}$")]
    title: Text
    title_vi: Text
    status: GapStatus
    severity: GapSeverity
    missing: Text
    affects: Annotated[tuple[Text, ...], Field(min_length=1)]
    workaround: Text
    close_by: Text
    since: date


class GapRegister(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    source: Text
    gaps: Annotated[tuple[Gap, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _ids_unique_and_sequential(self) -> GapRegister:
        duplicates = sorted(i for i, n in Counter(g.id for g in self.gaps).items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate gap ids: {', '.join(duplicates)}")
        numbers = []
        for gap in self.gaps:
            match = _ID.match(gap.id)
            numbers.append(int(match.group(1)) if match else -1)
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("gap ids must be sequential from GAP-01 in file order")
        return self

    def with_status(self, status: GapStatus | None) -> list[Gap]:
        return [g for g in self.gaps if status is None or g.status == status]

    def open_counts(self) -> dict[str, int]:
        """``{"open": N, "high": H, "medium": M, "low": L}`` over open gaps."""
        open_gaps = self.with_status("open")
        counts = Counter(g.severity for g in open_gaps)
        return {"open": len(open_gaps), **{s: counts.get(s, 0) for s in SEVERITIES}}


def load_gaps(path: Path | None = None) -> GapRegister:
    """Load and validate the register; raises ``GapError`` with a readable message."""
    target = path or GAPS_FILE
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GapError(f"cannot read {target}: {exc}") from exc
    try:
        return GapRegister.model_validate(data)
    except ValidationError as exc:
        raise GapError(f"{target}: {exc}") from exc


def gaps_summary_line(register: GapRegister) -> str:
    c = register.open_counts()
    return f"gaps: {c['open']} open (high {c['high']}, medium {c['medium']}, low {c['low']})"
