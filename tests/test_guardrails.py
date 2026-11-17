"""Project guardrails enforced by CI. See docs/adr/ADR-001 and docs/qa-gates.md (G2).

1. Recommend-only: no code that places orders with a broker.
2. Packaged config is valid YAML and contains no trading-automation keys.
3. HOSE [VERIFY] values carry a status so the release gate can list them.
"""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

SRC = Path(__file__).resolve().parents[1] / "src" / "vnstratlab"

FORBIDDEN_PATTERNS = [
    r"\bBrokerExecutor\b",
    r"\bplace_order\b",
    r"\bsubmit_order\b",
    r"\bcancel_order\b",
    r"\btrading_token\b",
    r"\bautomation_level\b",
    r"\bkill_switch\b",
    r"lightspeed",
    r"\bdnse\b",
]


def _load(resource: str) -> Any:
    text = files("vnstratlab.config").joinpath(resource).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_no_order_placement_code() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                offenders.append(f"{path.relative_to(SRC)}: {pattern}")
    assert not offenders, "Recommend-only rule violated:\n" + "\n".join(offenders)


def test_defaults_yaml_is_valid_and_recommend_only() -> None:
    cfg = _load("defaults.yaml")
    assert set(cfg["books"]) == {"short", "medium", "long"}
    assert cfg["news"]["use_in_signals"] is False
    flat = yaml.safe_dump(cfg)
    assert "automation_level" not in flat
    assert "kill_switch" not in flat


def test_hose_rules_have_status() -> None:
    market = _load("markets/hose.yaml")
    for name, rule in market["rules"].items():
        assert rule["status"] in {"VERIFY", "confirmed"}, name


def test_universe_has_membership() -> None:
    universe = _load("universes/vn30_banks.yaml")
    current = universe["membership"][0]
    assert len(current["tickers"]) == 13
    assert "TPB" not in current["tickers"]
