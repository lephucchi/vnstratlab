# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0, minor versions may break APIs.

## [Unreleased]

### Changed
- **Data source (ADR-006):** plan decision D6 (`vnstock`) is superseded. Phase 1 runs on a
  synthetic market (new card P1-T36); real-data cards wait for the owner's source decision.
  Review: `docs/reports/data-source-vnstock.md`.
- **Breaking:** environment variables have no project prefix: `APP_HOME` (was
  `VNSTRATLAB_HOME`), `LOG_LEVEL`, `VNSTOCK_API_KEY` (was `VNSTRATLAB_DATA_API_KEY`),
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. The unused LLM key is removed until the Phase 2
  card that needs it. Rename the keys in your `.env`.
- Pages: PO dashboard data is published only encrypted (`po/data.enc.json`); the plaintext
  `po/data.json` is no longer written.

### Added
- PO dashboard login: `PO_USERNAME` / `PO_PASSWORD` (GitHub secrets for the Pages build),
  `tools/encrypt_po.py` (AES-256-GCM, PBKDF2-SHA256 600k, NFC-normalised credentials).
- Config loader and trading calendar (P1-T02): typed frozen config (`load_config`, `ConfigError`
  with `dotted.path: reason` messages), deep-merge of user `config.yaml`, `TradingCalendar`
  (config holidays or observed sessions), `decision_days` for short/medium/long horizons,
  `holiday_coverage`; `doctor` reports config status and holiday coverage; HOSE holidays for
  2026 (complete) and 2027 (partial); long book uses monthly decision days.
- Pages: single deployment (`pages.yml`) combining intro site (`site` branch), docs (from `main`) and PO dashboard (`po` branch); `tools/build_status.py` generates public status data; `docs.yml` is build-only.
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
