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

Settings → Pages → Build and deployment → Source: **GitHub Actions**. Do this before the first
push: until Pages is enabled, the `deploy` job of `pages.yml` fails with
`HttpError: Not Found ... Ensure GitHub Pages has been enabled`.

Settings → Environments → `github-pages` → Deployment branches: allow **`main` and `develop`**.
`pages.yml` runs from `develop` (pushes and the `site`/`po` dispatches); with only `main`
allowed, its `deploy` job is rejected by the environment protection rule.

PO dashboard login: Settings → Secrets and variables → Actions → add `VNSTRATLAB_PO_USER` and
`VNSTRATLAB_PO_PASSWORD` (or `gh secret set VNSTRATLAB_PO_PASSWORD`). The build publishes the
dashboard data only as `po/data.enc.json`, AES-256-GCM with a PBKDF2 key derived from that
login; without the secrets nothing is published under `/po/`. Changing the password takes
effect on the next Pages build.

`pages.yml` is the only workflow that deploys Pages (on pushes to `develop`/`main`, daily, and
when the orphan `site`/`po` branches change). `docs.yml` only checks that the docs build.

## 6. Security

- Settings → Code security: enable **private vulnerability reporting**, Dependabot alerts and
  security updates, secret scanning and push protection.
- CI needs no repository secrets. The Pages build needs two: `VNSTRATLAB_PO_USER` and
  `VNSTRATLAB_PO_PASSWORD` (section 5).

## 7. Labels

Create: `task-card`, `phase-1`, `phase-2`, `phase-3`, `bug`, `qa:request-changes`,
`qa:blocked`, `release`, `verify-market-rule`, `good first issue`.
