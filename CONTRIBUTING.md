# Contributing to vnstratlab

Thanks for helping. This file is the short version; the full process is in
[docs/workflow.md](docs/workflow.md), [docs/git-branching.md](docs/git-branching.md) and
[docs/qa-gates.md](docs/qa-gates.md).

## Ground rules

1. **Recommend-only.** No code that places, routes or confirms orders with a broker. PRs that
   add it are closed ([ADR-001](docs/adr/ADR-001-python-core-recommend-only.md)).
2. **No lookahead.** A value used at date `t` must have been knowable at the close of `t`.
3. **No invented data.** Fixtures with made-up numbers are named `synthetic_*`. Never commit
   real market data.
4. **Parameters are frozen.** Strategy params, gate thresholds and risk limits change only by
   owner decision. A new parameter set is a new trial, registered before it is backtested.
5. **Secrets only from env.** Never log, print or commit them.

## Setup

```bash
git clone https://github.com/lephucchi/vnstratlab.git
cd vnstratlab
git switch develop
python -m venv .venv && . .venv/Scripts/activate   # or: source .venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check . && ruff format --check . && mypy
```

## Making a change

1. Pick or open an issue. Larger work uses the **Task card** issue template.
2. Branch from `develop`: `feat/P1-T03-price-ingest`, `fix/42-tick-rounding`, `docs/...`.
3. Write tests first. Unit tests never hit the network.
4. Commit with [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(engine): block buy fills on ceiling open`.
5. Open a PR **into `develop`**, fill the template (handoff report + checklist).
6. CI (gate G1) must be green; an independent reviewer runs gate G2.
7. The PR is squash-merged.

## Definition of done

- Acceptance criteria of the card met and shown in the PR.
- `pytest` passes, coverage does not drop below 80%; `ruff check`, `ruff format --check`, `mypy` clean.
- Anything that writes supports `--dry-run`.
- No network in unit tests, no secrets, no real data in the diff.
- Docs updated when behaviour or config changes; `CHANGELOG.md` under *Unreleased*.

## Reporting security issues

See [SECURITY.md](SECURITY.md). Do not open public issues for vulnerabilities.
