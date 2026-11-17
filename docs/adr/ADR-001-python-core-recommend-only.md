# ADR-001: Python core, recommend-only, GitHub Actions for CI only

- Status: accepted
- Date: 2026-11-17
- Deciders: owner

## Context

The project began as a personal plan with a Phase 3 that placed live orders through a broker
API. It is now a public open-source tool that anyone can install. Three questions came up:
which language to build in, whether the tool should trade, and how to use GitHub's free compute.

## Decision

1. **Python 3.11+ for the whole core.** Data volumes are small (tens of tickers × ~3,000
   sessions); numpy, DuckDB and pandas already run native code. The key libraries
   (`arch` for SPA/MCS, scipy, LightGBM, data adapters, LLM SDKs) are Python. A pure-Python
   wheel keeps installation to one command on every OS. Hot paths are optimised in this order:
   vectorise → cache → `numba` → optional compiled extension with a pure-Python fallback.
2. **Recommend-only.** vnstratlab never places, routes or confirms orders. There is no broker
   executor, trading credential, automation level or kill switch. The final output is a
   recommendation the user acts on manually. The former Phase 3 (live trading) is replaced by
   portfolio optimisation. A guardrail test fails CI if order-placement code appears.
3. **GitHub Actions for development only.** CI, benchmarks, statistical tests, docs and
   releases run on Actions with synthetic data. Real market data never enters this public
   repository or its artifacts, caches or releases.

## Consequences

- Lower legal and financial risk for the project and its users; simpler security model.
- Users who want automation must build it outside vnstratlab; the project will not accept it.
- Go/Rust skills are not needed; contributors can work in one language.
- Nightly real-data runs happen on the user's machine (or their own private infrastructure).

## Alternatives considered

- **Go or Rust core:** faster, but no quant ecosystem (Go) or re-implementing statistical tests
  (Rust), and per-platform builds that complicate installation. Rejected.
- **Live trading as an optional plugin:** still distributes order-placement code under the
  project's name. Rejected.
- **Nightly real-data pipeline on public Actions:** would publish data through artifacts and
  depends on unreliable cron and on Vietnamese endpoints accepting foreign datacenter IPs. Rejected.
