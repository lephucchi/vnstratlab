# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0, minor versions may break APIs.

## [Unreleased]

### Added
- Project scaffold (P1-T01): `src/` layout package, Typer CLI with `doctor` and stubs for all
  planned commands, per-user app home via `platformdirs` (`VNSTRATLAB_HOME` override),
  env-only secrets via `pydantic-settings`, packaged default config (HOSE rules, VN30 banks).
- Guardrail tests: recommend-only (no order-placement code), config validity.
- CI (lint, types, tests on Windows/macOS/Linux × Python 3.11–3.13, secret scan),
  benchmark, weekly statistical tests, docs and release workflows.
- Documentation: workflow, git branching, QA gates, benchmarks, architecture, configuration,
  data sources, writing strategies, roadmap; ADR-001.
- ADR-005: long horizon decides monthly (accepted); threshold conversions and 12 tranches proposed.
- ADR-004 (accepted): gated, weighted selection by default; pre-registered rule for `last_winner`.
- End-to-end flow with a worked example (`docs/end-to-end-flow.md`).
- Engine specification (`docs/engine.md`), strategy catalogue (`docs/strategies.md`),
  ADR-003 (proposed engine and architecture refinements).
- Implementation plan v1.1 (recommend-only, portfolio optimisation as Phase 3).
