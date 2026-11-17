"""Technical benchmarks (docs/benchmarks.md).

Run: pytest benchmarks --benchmark-only --no-cov
CI stores results and alerts when a PR is >20% slower than `develop`.
Real benchmarks (simulator, walk-forward, SPA/MCS bootstrap) are added by their cards;
they must use synthetic data only.
"""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from vnstratlab.cli import app


def test_bench_cli_help(benchmark: Any) -> None:
    runner = CliRunner()
    result = benchmark(runner.invoke, app, ["--help"])
    assert result.exit_code == 0
