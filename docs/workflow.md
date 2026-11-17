# Development workflow

How work moves from an idea to a release. It applies to human contributors and to the AI
agents that build most of the code. Branch mechanics are in [git-branching.md](git-branching.md);
gate checklists are in [qa-gates.md](qa-gates.md).

## 1. Roles

| Role | Who | Does | Must not |
|---|---|---|---|
| **Owner** | Maintainer (human) | Approves releases (G4), ADRs, any change to frozen parameters, config defaults or scope | — |
| **Manager** | AI agent (Opus), main session | Splits milestones into task cards, assigns them, runs integration tests, merges into `develop`, keeps `docs/reports/progress.md` | Review code it assigned to itself; skip a gate; merge without re-running tests |
| **Worker** | AI agent (Sonnet) or contributor | Implements exactly one task card on its own branch, tests first, opens a PR with a handoff report | Change files outside the card; edit frozen parameters; add network calls to unit tests |
| **QA Reviewer** | AI agent (Opus), fresh context | Independent code review of each PR (gate G2). Reads the diff and the card, **not** the worker's conclusions first | Edit code; approve with failing CI |
| **Reality Analyst** | AI agent (Opus) | Release readiness (gate G3): benchmarks, cross-engine comparison, stress tests, product comparison | Tune parameters to improve results; change code under test |

Agent definitions live in [`.claude/agents/`](../.claude/agents/); the manager's standing
instructions are in [`CLAUDE.md`](../CLAUDE.md).

**Independence rule.** The agent that wrote a change never reviews it. G2 and G3 always run
in a fresh context with only the card, the diff and the repository.

## 2. Pipeline

```
 Plan / issue
     │
     ▼
 G0  Task card ready ───────── manager writes card (issue template "Task card")
     │
     ▼
     Worker: feat/<card-id>-<slug> from develop → tests → code → PR into develop
     │
     ▼
 G1  CI green ──────────────── lint, types, tests (3 OS × 3 Python), guardrails,
     │                         secret scan, benchmark comparison
     ▼
 G2  QA code review ────────── QA Reviewer: approve / request changes / block
     │                         (request changes → back to worker)
     ▼
     Manager re-runs tests, squash-merges into develop, logs progress
     │
     ▼  (milestone complete)
     release/vX.Y.0 from develop  — feature freeze, fixes only
     │
     ▼
 G3  Release readiness ─────── Reality Analyst: benchmarks, cross-engine check,
     │                         stress tests, product comparison → readiness report
     ▼
 G4  Owner approval ────────── owner reads the report, approves the release PR
     │
     ▼
     merge into main → tag vX.Y.Z → PyPI + GitHub Release + docs (prod)
```

Nothing reaches `main` (production) without G1–G4.

## 3. Gate summary

| Gate | When | Who | Blocking? | Output |
|---|---|---|---|---|
| G0 | Before work starts | Manager | Yes | Task card issue with acceptance criteria |
| G1 | Every push to a PR | CI | Yes (required checks) | Green checks |
| G2 | Every PR into `develop`, `release/*`, `main` | QA Reviewer | Yes | Review with verdict + checklist |
| G3 | Every `release/*` branch | Reality Analyst | Yes for minor/major; reduced for patch | `docs/reports/release-vX.Y.Z-readiness.md` |
| G4 | Release PR into `main` | Owner | Yes | Approval on the PR |

Patch releases (`vX.Y.Z`, Z>0) run G3 in reduced form: stress tests and benchmarks only, unless
the fix touches the engine, lab or strategies, in which case the full G3 runs.

## 4. Task cards (G0)

A card is a GitHub issue created from the **Task card** template. It contains:

```markdown
### <ID> — <title>
- Depends on: <IDs>
- Goal: <one sentence>
- Files to create/change: <paths>
- Inputs: <tables, config keys, fixtures>
- Outputs: <tables, files, commands, endpoints>
- Acceptance criteria:
  1. <testable statement>
- Out of scope: <explicit exclusions>
- Notes: <plan sections, references>
```

IDs follow the plan: `P1-T03`, `P2-T04`, `P3-T02`. Cards not in the plan use `X-<issue number>`.
A card should take one working session. If it does not fit, the manager splits it.

## 5. Handoff report (worker → PR description)

```markdown
## Handoff <ID>
- Status: done | blocked | partial
- Files changed: ...
- Tests added / run: <command> → <result>
- Acceptance criteria: 1 ✅ 2 ✅ 3 ❌ (reason)
- Assumptions made: ...
- Open questions for manager: ...
```

The PR template contains this block; a PR without it is not reviewed.

## 6. Global engineering rules

These hold for every card (from the [plan](plan/plan.md), section 6.4):

1. **No lookahead.** Fundamentals use `published_at`; news after 14:45 counts for the next session.
2. **No invented data.** Only `synthetic_*` fixtures contain made-up numbers.
3. **Parameters are frozen.** New parameter set = new trial, registered before the backtest.
4. **Count every trial.** DSR uses the total trial count.
5. **Deterministic.** Seeds come from config.
6. **Tests.** pytest, no network in unit tests, hand-computed cases for every market rule.
7. **Dry-run first.** Every writing command supports `--dry-run`.
8. **Secrets.** Env or `.env` only; never logged, printed, committed or sent to the browser.
9. **Recommend-only.** No order placement anywhere (enforced by `tests/test_guardrails.py`).
10. **Style.** Type hints, `mypy --strict`, ruff, small functions, English in code and docs,
    Vietnamese in user-facing dashboard and Telegram text.
11. **Scope.** If a card needs a change to a fixed decision, stop and report to the manager.

## 7. Escalation

The worker stops and reports (handoff status `blocked`) when:

- the card contradicts the plan, an ADR or these rules;
- a market fact is uncertain (mark it `[VERIFY]` in config, never guess in code);
- data from a source looks wrong or its licence is unclear;
- a test can only pass by changing a frozen parameter.

The manager decides, or escalates to the owner for anything in the owner column of section 1.

## 8. Progress log

After each merge into `develop`, the manager appends one line to
[`docs/reports/progress.md`](reports/progress.md):

```
2026-11-18 | P1-T02 | merged #12 | config + calendar | tests 41 passed | G2 approve
```
