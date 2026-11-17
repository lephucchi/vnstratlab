<!-- Title: Conventional Commits, e.g. "feat(engine): block buy fills on ceiling open" -->
<!-- Target: develop (features/fixes), main (release/* or hotfix/* only) -->

Closes #<issue>

## Handoff <card ID>
- Status: done | blocked | partial
- Files changed:
- Tests added / run: `<command>` → <result>
- Acceptance criteria: 1 ✅ 2 ✅ 3 ❌ (reason)
- Assumptions made:
- Open questions for manager:

## Author checklist
- [ ] Changes stay inside the card's file list
- [ ] Tests written first; no network in unit tests
- [ ] No lookahead (point-in-time data only)
- [ ] No frozen parameter changed; new params registered as trials
- [ ] No order placement / broker code (recommend-only)
- [ ] No secrets, no real market data; made-up fixtures are `synthetic_*`
- [ ] `--dry-run` works for anything that writes
- [ ] Docs and `CHANGELOG.md` (Unreleased) updated if behaviour/config changed

## For release / hotfix PRs into main
- [ ] Readiness report: `docs/reports/release-vX.Y.Z-readiness.md` → Ready
- [ ] TestPyPI rc installed and `vnstratlab demo` run in a clean venv
- [ ] Owner approval (G4)
