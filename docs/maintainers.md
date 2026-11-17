# Maintainer setup

One-time GitHub configuration for the repository owner. Everything here is done in the GitHub
web UI (or with `gh`), not in code.

## 1. Branches

1. Default branch: **`develop`** (Settings → General → Default branch). PRs then target
   `develop` by default; `main` holds releases.
2. Settings → General → Pull Requests: allow **squash** and **merge commits**, disable rebase
   merging; enable "Automatically delete head branches".

## 2. Branch protection (Settings → Branches → Add rule, or Rulesets)

**`main`**
- Require a pull request before merging, 1 approval, dismiss stale approvals
- Require status checks: `lint`, all `test (...)` matrix jobs, `guardrails`, `secrets`, `pr-title`
- Require branches to be up to date; require conversation resolution
- Block force pushes and deletion; restrict pushes to the owner

**`develop`**
- Same as `main`, plus "Require linear history"

Status checks appear in the list only after the CI workflow has run once on a PR.

## 3. Environments (Settings → Environments)

| Environment | Protection |
|---|---|
| `pypi` | Required reviewer: owner; deployment branches/tags: tags `v*` |
| `testpypi` | Deployment tags: `v*rc*` |
| `github-pages` | Branch `main` |

## 4. PyPI Trusted Publishing (no tokens)

1. On pypi.org → Account → Publishing → "Add a pending publisher":
   project `vnstratlab`, owner `lephucchi`, repo `vnstratlab`, workflow `release.yml`,
   environment `pypi`.
2. Same on test.pypi.org with environment `testpypi`.

## 5. Pages

Settings → Pages → Source: **GitHub Actions**. The `docs.yml` workflow deploys on pushes to `main`.

## 6. Security

- Settings → Code security: enable **private vulnerability reporting**, Dependabot alerts and
  security updates, secret scanning and push protection.
- No repository secrets are needed for CI.

## 7. Labels

Create: `task-card`, `phase-1`, `phase-2`, `phase-3`, `bug`, `qa:request-changes`,
`qa:blocked`, `release`, `verify-market-rule`, `good first issue`.
