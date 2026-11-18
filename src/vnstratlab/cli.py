"""Command-line interface: `vnstratlab <command>` or `python -m vnstratlab <command>`.

Most commands are stubs until their task card lands (see docs/roadmap.md).
A stub prints which card implements it and exits with code 1, so scripts never
mistake a stub for success.
"""

from __future__ import annotations

import platform
import sys
from datetime import date
from enum import StrEnum
from typing import Annotated

import typer

from vnstratlab import __version__
from vnstratlab.calendar import holiday_coverage
from vnstratlab.config.loader import ConfigError, load_config, load_config_with_info
from vnstratlab.data.pipeline import IngestReport, default_start
from vnstratlab.data.pipeline import ingest as ingest_data
from vnstratlab.data.protocol import SourceError, get_source, source_names
from vnstratlab.paths import get_paths
from vnstratlab.settings import load_settings

app = typer.Typer(
    name="vnstratlab",
    help="Strategy lab for Vietnamese stocks. Recommendations only; it never places orders.",
    no_args_is_help=True,
    add_completion=False,
)


class Horizon(StrEnum):
    short = "short"
    medium = "medium"
    long = "long"


DryRun = Annotated[
    bool, typer.Option("--dry-run", help="Print what would be written; write nothing.")
]


def _not_implemented(card: str) -> None:
    typer.echo(f"Not implemented yet. Planned in task card {card} (see docs/roadmap.md).", err=True)
    raise typer.Exit(code=1)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"vnstratlab {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    """vnstratlab command-line interface."""


def _echo_config_status() -> bool:
    """Print config validity and holiday coverage. Returns False if the config is invalid."""
    try:
        loaded = load_config_with_info()
    except ConfigError as exc:
        typer.echo("config: INVALID")
        for problem in exc.problems:
            typer.echo(f"  {problem}")
        return False
    cfg = loaded.config
    typer.echo("config: OK")
    this_year = date.today().year
    for year in (this_year, this_year + 1):
        coverage = holiday_coverage(cfg, year)
        warning = "" if coverage == "complete" else "  WARNING: incomplete, check hose.yaml"
        typer.echo(f"  holidays {year}: {coverage}{warning}")
    for year in loaded.user_holiday_years:
        typer.echo(f"  holidays {year}: user override")
    return True


@app.command()
def doctor() -> None:
    """Check the installation: version, paths and which secrets are set (never their values)."""
    paths = get_paths()
    settings = load_settings()
    typer.echo(f"vnstratlab   {__version__}")
    typer.echo(f"python       {platform.python_version()} ({sys.platform})")
    typer.echo(f"home         {paths.home}  (exists: {paths.home.exists()})")
    typer.echo(f"config       {paths.config_file}  (exists: {paths.config_file.exists()})")
    typer.echo(f"data         {paths.data_dir}")
    config_ok = _echo_config_status()
    typer.echo("secrets:")
    for name, is_set in settings.secret_status().items():
        typer.echo(f"  {name:<20} {'set' if is_set else 'not set'}")
    if not config_ok:
        raise typer.Exit(code=1)


@app.command()
def demo() -> None:
    """Run the whole pipeline offline on bundled synthetic data."""
    _not_implemented("P1-T32")


@app.command()
def init() -> None:
    """Interactive setup: universe, capital, data directory, optional notifications."""
    _not_implemented("P1-T35")


def _parse_date(value: str | None, option: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"{value!r} is not a YYYY-MM-DD date", param_hint=option) from None


def _echo_ingest_report(report: IngestReport) -> None:
    typer.echo(f"run {report.run_id}  source {report.source}  {report.start} .. {report.end}")
    typer.echo(
        f"rows in {report.rows_in}, written {report.rows_written}, "
        f"changed {report.rows_changed}, dropped {report.rows_dropped}"
    )
    if report.dry_run:
        typer.echo("dry run: nothing was written")
        for name, frame in report.preview.items():
            typer.echo(f"{name} (first 5 of {len(frame)} rows):")
            typer.echo(frame.head(5).to_string(index=False))
    else:
        typer.echo(f"store {report.db_path}")
        typer.echo(f"raw   {report.raw_path}")


@app.command()
def ingest(
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    from_date: Annotated[
        str | None,
        typer.Option("--from", help="Start date YYYY-MM-DD; default: day after the latest stored."),
    ] = None,
    to_date: Annotated[
        str | None, typer.Option("--to", help="End date YYYY-MM-DD; default: today.")
    ] = None,
    dry_run: DryRun = False,
) -> None:
    """Download or refresh market data into the local data directory."""
    start = _parse_date(from_date, "--from")
    end = _parse_date(to_date, "--to") or date.today()
    if start is not None and start > end:
        raise typer.BadParameter(f"--from {start} is after --to {end}")
    paths = get_paths()
    try:
        cfg = load_config(paths.home)
    except ConfigError as exc:
        typer.echo("config: INVALID", err=True)
        for problem in exc.problems:
            typer.echo(f"  {problem}", err=True)
        raise typer.Exit(code=1) from None
    name = source or cfg.data.source
    try:
        adapter = get_source(name, cfg)
        start = start or default_start(cfg, paths, adapter)
        if start > end:
            typer.echo(f"{name}: up to date (latest stored session is on or after {end})")
            return
        report = ingest_data(cfg, paths, adapter, start, end, dry_run=dry_run)
    except SourceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2 if name not in source_names() else 1) from None
    _echo_ingest_report(report)


@app.command()
def backtest(
    strategy: Annotated[str, typer.Option("--strategy", help="Registered strategy id.")],
) -> None:
    """Walk-forward backtest of one registered strategy."""
    _not_implemented("P1-T20")


@app.command()
def lab(
    horizon: Annotated[Horizon, typer.Option("--horizon")],
    asof: Annotated[str | None, typer.Option("--asof", help="YYYY-MM-DD")] = None,
    dry_run: DryRun = False,
) -> None:
    """Run one strategy-selection cycle (gates, MCS, weights) for a horizon."""
    _not_implemented("P1-T22")


@app.command("meta-backtest")
def meta_backtest(horizon: Annotated[Horizon, typer.Option("--horizon")]) -> None:
    """Backtest the lab itself against equal weight and 'pick last winner'."""
    _not_implemented("P1-T23")


@app.command()
def stress(horizon: Annotated[Horizon, typer.Option("--horizon")]) -> None:
    """Realism stress tests: cost x2/x3, delayed fills, liquidity, parameter noise, regimes."""
    _not_implemented("P1-T33")


@app.command()
def daily(dry_run: DryRun = False) -> None:
    """Run the full evening loop: ingest, features, lab, risk, recommendations, report."""
    _not_implemented("P1-T26")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address. Keep 127.0.0.1.")] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
) -> None:
    """Start the local dashboard and the built-in scheduler."""
    _not_implemented("P1-T27")


if __name__ == "__main__":  # pragma: no cover
    app()
