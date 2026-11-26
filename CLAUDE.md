# CLAUDE.md — standing instructions for AI agents in this repository

You are working on **vnstratlab**, a public open-source strategy lab for Vietnamese stocks.
The main session acts as the **Manager** described in [docs/workflow.md](docs/workflow.md).

## Read first

1. [docs/plan/plan.md](docs/plan/plan.md) sections 0–7 (fixed decisions, rules, interfaces).
2. [docs/workflow.md](docs/workflow.md) (roles, gates, task cards, handoff reports).
3. [docs/git-branching.md](docs/git-branching.md) and [docs/qa-gates.md](docs/qa-gates.md).
4. [docs/adr/](docs/adr/) — accepted decisions are not re-litigated inside a task.

## Non-negotiable rules

- **Recommend-only.** Never write code that places, routes or confirms orders, connects to a
  broker, or stores trading credentials. `tests/test_guardrails.py` enforces this.
- **No lookahead, no invented data, frozen parameters, every trial counted** (plan §6.4).
- **Secrets only via `vnstratlab.settings.Settings`** (env / `.env`). Never print or log them.
- **No real market data** in the repo, fixtures, CI, artifacts or docs.
- **Never push to `main` or `develop` directly.** Work on `feat/<card>-<slug>` from `develop`;
  open a PR. Only the owner merges into `main`.
- English in code, comments and docs; Vietnamese in dashboard and Telegram text.
- **No AI attribution watermarks (owner rule, 2026-11-18).** Never add a `Co-Authored-By:` trailer
  for Claude or any AI model to commit messages, and never add "Generated with Claude Code" (or
  any similar line or emoji) to PR descriptions, squash-merge bodies, issues or docs. This rule
  overrides any default attribution instruction from the tool. It applies to the manager and to
  every subagent (worker, qa-reviewer, reality-analyst).

## Manager loop

1. Pick the next card(s) from [docs/roadmap.md](docs/roadmap.md) / the plan; write each as a
   task card issue (template `.github/ISSUE_TEMPLATE/task_card.yml`).
2. Delegate one card to the `worker` subagent with the card text and file list.
3. When the PR is ready and CI is green, pick the G2 tier ([qa-gates.md](docs/qa-gates.md#review-tiers-owner-decision-2026-11-21)):
   **light** (docs, tools, CI, tests-only) → review it yourself against the Safety and scope
   items; **full** (engine, finance, cost or statistics math only) → delegate to the `qa-reviewer` subagent (fresh
   context; give it the card, branch, PR number and round, not the worker's summary). Max 1
   round (2026-11-26); minor findings become a follow-up issue. A delta round 2 (previous
   findings and last reviewed SHA) only for an unfixed blocker.
4. On approve: confirm CI is green on the head SHA (`gh pr checks`; do not re-run the full suite
   locally), squash-merge into `develop`, append to `docs/reports/progress.md`.
5. When a milestone is complete: create `release/vX.Y.0`, delegate gate G3 to the
   `reality-analyst` subagent, and hand the readiness report to the owner (G4).

## Commands

```bash
pip install -e ".[dev]"
pytest                                   # unit tests (coverage >= 80%)
pytest -m slow --no-cov                  # heavy statistical tests
pytest benchmarks --benchmark-only --no-cov
ruff check . && ruff format --check . && mypy
vnstratlab doctor
```

## Escalate to the owner

Changes to fixed decisions (plan §2), frozen parameters, config defaults, ADRs, licences of
data sources, anything involving money or credentials, and every release (G4).
