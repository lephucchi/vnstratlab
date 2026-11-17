"""Build public status data for the project websites (stdlib only).

Outputs
- <out>/po/data.json  : project-management data for the PO dashboard (branch `po`)
- <out>/data/status.json : measured facts for the intro site (branch `site`)

Sources (all public): repository files on develop and on feature branches, the progress log,
ADRs, task cards (YAML front matter), the plan, pytest/coverage results produced in the same
CI job, benchmark history from the `bench-data` branch, and the GitHub REST API (branches,
pull requests, workflow runs). No e-mail addresses or secrets are written.

Usage:
  python tools/build_status.py --repo . --out _site \
      [--coverage coverage.json] [--junit junit.xml] [--bench bench/data.js]
GITHUB_TOKEN / GITHUB_REPOSITORY are used for the API when present; without them the API
sections are empty and marked unavailable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CARD_STATUSES = ("todo", "in-progress", "in-review", "changes-requested", "blocked", "done")


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def scrub(value: Any) -> Any:
    """Remove anything that looks like an e-mail address, recursively."""
    if isinstance(value, str):
        return EMAIL_RE.sub("[email removed]", value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(  # noqa: S603 - fixed internal git arguments
            ["git", *args],  # noqa: S607 - git from PATH, as in CI
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


# ------------------------------------------------------------------ front matter


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a minimal `key: value` YAML front matter block."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        line = line.split("#", 1)[0].rstrip()
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, text[end + 4 :]


# ------------------------------------------------------------------ plan and cards


PLAN_MILESTONE_RE = re.compile(r"^### (M\d+\.\d+) — (.+)$")
PLAN_CARD_RE = re.compile(r"^\*\*(P\d-T\d+)(?: … (P\d-T\d+))? — (.+?)\*\*")
PLAN_PHASE_RE = re.compile(r"^## (\d+)\. Phase (\d) — (.+)$")


def parse_plan(text: str) -> list[dict[str, Any]]:
    """Every planned card from the plan, with its milestone and phase."""
    cards: list[dict[str, Any]] = []
    milestone, phase = "", ""
    for line in text.splitlines():
        if m := PLAN_PHASE_RE.match(line):
            phase, milestone = f"Phase {m.group(2)}", ""
        elif m := PLAN_MILESTONE_RE.match(line):
            milestone = f"{m.group(1)} {m.group(2)}"
        elif m := PLAN_CARD_RE.match(line):
            first, last, title = m.group(1), m.group(2), m.group(3)
            card_id = f"{first}…{last}" if last else first
            cards.append(
                {
                    "id": card_id,
                    "title": title,
                    "milestone": milestone,
                    "phase": phase,
                    "status": "todo",
                    "branch": None,
                    "source": "plan",
                }
            )
    return cards


ROADMAP_CARD_RE = re.compile(r"^\| (P\d-T\d+) \| (.+?) \| (v[\d.]+) \|")


def parse_roadmap_cards(text: str) -> list[dict[str, Any]]:
    """Cards added after the plan (roadmap table 'Cards added for the open-source version')."""
    cards = []
    for line in text.splitlines():
        if m := ROADMAP_CARD_RE.match(line):
            cards.append(
                {
                    "id": m.group(1),
                    "title": m.group(2),
                    "milestone": "",
                    "phase": "Phase 1",
                    "release": m.group(3),
                    "status": "todo",
                    "branch": None,
                    "source": "roadmap",
                }
            )
    return cards


def card_files(repo: Path) -> dict[str, dict[str, Any]]:
    """Task cards with front matter, from develop and from every remote feature branch.

    A card on a feature branch overrides the develop version (it is newer).
    """
    found: dict[str, dict[str, Any]] = {}

    def add(text: str, origin: str) -> None:
        meta, _ = parse_front_matter(text)
        if meta.get("id"):
            status = meta.get("status", "todo")
            found[meta["id"]] = {
                "id": meta["id"],
                "title": meta.get("title", ""),
                "milestone": meta.get("milestone", ""),
                "release": meta.get("release", ""),
                "status": status if status in CARD_STATUSES else "todo",
                "branch": meta.get("branch") or None,
                "source": origin,
            }

    for path in sorted((repo / "docs" / "cards").glob("*.md")):
        add(path.read_text(encoding="utf-8"), "develop")

    for ref in git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"
    ).split():
        branch = ref.removeprefix("origin/")
        if not branch.startswith(("feat/", "fix/")):
            continue
        for name in git(repo, "ls-tree", "--name-only", ref, "docs/cards/").split():
            if name.endswith(".md"):
                add(git(repo, "show", f"{ref}:{name}"), branch)
    return found


# ------------------------------------------------------------------ progress, ADRs


def parse_progress(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 6 and re.match(r"\d{4}-\d{2}-\d{2}", parts[0]):
            rows.append(
                {
                    "date": parts[0],
                    "card": parts[1],
                    "ref": parts[2],
                    "summary": parts[3],
                    "tests": parts[4],
                    "review": parts[5],
                }
            )
    return rows


ADR_STATUS_RE = re.compile(r"^- Status:\s*(.+)$", re.MULTILINE)


def parse_adrs(adr_dir: Path) -> list[dict[str, str]]:
    adrs = []
    for path in sorted(adr_dir.glob("ADR-*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        m = ADR_STATUS_RE.search(text)
        raw = re.sub(r"[*`]", "", m.group(1)).strip() if m else "unknown"
        low = re.sub(r"\([^)]*\)", "", raw).lower()  # ignore parenthetical notes
        status = (
            "proposed"
            if "proposed" in low and "accepted" not in low
            else "partly-accepted"
            if "proposed" in low
            else "accepted"
            if "accepted" in low
            else "rejected"
            if "rejected" in low
            else "superseded"
            if "superseded" in low
            else raw
        )
        adrs.append(
            {
                "id": path.stem.split("-", 2)[0] + "-" + path.stem.split("-")[1],
                "file": path.name,
                "title": title,
                "status": status,
                "status_text": raw,
            }
        )
    return adrs


def count_verify(repo: Path) -> int:
    total = 0
    for path in (repo / "src" / "vnstratlab" / "config").rglob("*.yaml"):
        total += len(
            re.findall(r"status:\s*(VERIFY|provisional)", path.read_text(encoding="utf-8"))
        )
    return total


# ------------------------------------------------------------------ test, coverage, bench


def read_coverage(path: Path | None) -> float | None:
    if not path or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    pct = data.get("totals", {}).get("percent_covered")
    return round(float(pct), 2) if pct is not None else None


def read_junit(path: Path | None) -> dict[str, int] | None:
    if not path or not path.exists():
        return None
    root = ET.parse(path).getroot()  # noqa: S314 - junit.xml written by our own pytest run
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for key in totals:
            totals[key] += int(s.get(key, 0))
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    return totals


def read_bench(path: Path | None) -> list[dict[str, Any]]:
    """Latest result per benchmark from github-action-benchmark's data.js."""
    if not path or not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    start = text.find("{")
    if start == -1:
        return []
    data = json.loads(text[start:].rstrip().rstrip(";"))
    out: list[dict[str, Any]] = []
    for _suite, entries in data.get("entries", {}).items():
        if not entries:
            continue
        last = entries[-1]
        for b in last.get("benches", []):
            out.append(
                {
                    "name": b.get("name"),
                    "value": b.get("value"),
                    "unit": b.get("unit"),
                    "commit": last.get("commit", {}).get("id", "")[:7],
                    "date": dt.datetime.fromtimestamp(last.get("date", 0) / 1000, dt.UTC)
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
    return out


# ------------------------------------------------------------------ GitHub API


def api(path: str) -> Any:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "vnstratlab-status"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed https host
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def github_data() -> dict[str, Any]:
    pulls = api("pulls?state=open&per_page=50")
    runs = api("actions/runs?per_page=30")
    branches = api("branches?per_page=100")
    return {
        "available": pulls is not None or runs is not None,
        "pulls": [
            {
                "number": p["number"],
                "title": p["title"],
                "head": p["head"]["ref"],
                "base": p["base"]["ref"],
                "user": p["user"]["login"],
                "draft": p.get("draft", False),
                "updated_at": p["updated_at"],
                "url": p["html_url"],
            }
            for p in (pulls or [])
        ],
        "runs": [
            {
                "name": r["name"],
                "branch": r["head_branch"],
                "sha": r["head_sha"][:7],
                "status": r["status"],
                "conclusion": r["conclusion"],
                "event": r["event"],
                "created_at": r["created_at"],
                "url": r["html_url"],
            }
            for r in ((runs or {}).get("workflow_runs") or [])
        ],
        "branches": sorted(b["name"] for b in (branches or [])),
    }


# ------------------------------------------------------------------ assemble


def build(
    repo: Path, out: Path, coverage: Path | None, junit: Path | None, bench: Path | None
) -> None:
    plan_text = (repo / "docs" / "plan" / "plan.md").read_text(encoding="utf-8")
    cards = parse_plan(plan_text)
    known = {c["id"] for c in cards}
    roadmap = repo / "docs" / "roadmap.md"
    if roadmap.exists():
        cards += [
            c
            for c in parse_roadmap_cards(roadmap.read_text(encoding="utf-8"))
            if c["id"] not in known
        ]
    overrides = card_files(repo)
    by_id = {c["id"]: c for c in cards}
    for cid, card in overrides.items():
        if cid in by_id:
            by_id[cid].update({k: v for k, v in card.items() if v not in ("", None)})
        else:
            cards.append(card)
            by_id[cid] = card

    progress_path = repo / "docs" / "reports" / "progress.md"
    progress = (
        parse_progress(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else []
    )
    for row in progress:  # anything merged per the progress log is done
        if row["card"] in by_id:
            by_id[row["card"]]["status"] = "done"

    adrs = parse_adrs(repo / "docs" / "adr")
    gh = github_data()
    tests = read_junit(junit)
    cov = read_coverage(coverage)
    benches = read_bench(bench)
    sha = git(repo, "rev-parse", "--short", "HEAD").strip()
    generated = now_iso()

    counts = {s: sum(1 for c in cards if c["status"] == s) for s in CARD_STATUSES}
    waiting = [
        {"type": "adr", "text": a["title"], "status": a["status"]}
        for a in adrs
        if a["status"] in ("proposed", "partly-accepted")
    ] + [
        {"type": "pr", "text": f"#{p['number']} {p['title']}", "url": p["url"]}
        for p in gh["pulls"]
        if not p["draft"]
    ]

    po = {
        "generated_at": generated,
        "commit": sha,
        "repository": os.environ.get("GITHUB_REPOSITORY", "lephucchi/vnstratlab"),
        "counts": counts,
        "cards": cards,
        "progress": progress,
        "adrs": adrs,
        "waiting_for_owner": waiting,
        "verify_items": count_verify(repo),
        "quality": {"tests": tests, "coverage": cov, "benchmarks": benches},
        "github": gh,
    }
    status = {
        "generated_at": generated,
        "commit": sha,
        "tests": tests,
        "coverage": cov,
        "benchmarks": benches,
        "last_ci": next(
            (r for r in gh["runs"] if r["name"] == "CI" and r["branch"] == "develop"), None
        ),
        "cards_done": counts["done"],
        "cards_total": len(cards),
    }

    for rel, payload in (("po/data.json", po), ("data/status.json", status)):
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(scrub(payload), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"wrote {target}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, default=Path())
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--coverage", type=Path)
    p.add_argument("--junit", type=Path)
    p.add_argument("--bench", type=Path)
    a = p.parse_args()
    build(a.repo.resolve(), a.out, a.coverage, a.junit, a.bench)


if __name__ == "__main__":
    main()
