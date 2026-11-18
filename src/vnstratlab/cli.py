"""Command-line interface: `vnstratlab <command>` or `python -m vnstratlab <command>`.

Most commands are stubs until their task card lands (see docs/roadmap.md).
A stub prints which card implements it and exits with code 1, so scripts never
mistake a stub for success.
"""

from __future__ import annotations

import importlib.util
import platform
import sys
from datetime import date
from enum import StrEnum
from typing import Annotated

import typer

from vnstratlab import __version__
from vnstratlab.calendar import holiday_coverage
from vnstratlab.config.loader import ConfigError, load_config, load_config_with_info
from vnstratlab.data.pipeline import (
    VN_TZ,
    IngestReport,
    default_start,
    record_terms_acceptance,
    terms_accepted,
    terms_notice,
    utc_now,
)
from vnstratlab.data.pipeline import ingest as ingest_data
from vnstratlab.data.protocol import DataSource, SourceError, get_source, source_names
from vnstratlab.paths import AppPaths, get_paths
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
    for warning in report.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if report.refetched:
        typer.echo(
            f"rescale detected, full refetch: {', '.join(report.refetched)} "
            "(earlier rows were revised)"
        )
    if report.status != "ok":
        typer.echo(f"status {report.status}: {len(report.failed)} ticker(s) failed", err=True)
        for ticker, message in sorted(report.failed.items()):
            typer.echo(f"  {ticker}: {message}", err=True)
        typer.echo(
            "re-run `vnstratlab ingest` to retry: each ticker resumes from its own latest date, "
            "so the failed tickers are fetched again.",
            err=True,
        )
    if report.dry_run:
        typer.echo("dry run: nothing was written")
        for name, frame in report.preview.items():
            typer.echo(f"{name} (first 5 of {len(frame)} rows):")
            typer.echo(frame.head(5).to_string(index=False))
    else:
        typer.echo(f"store {report.db_path}")
        typer.echo(f"raw   {report.raw_path}")


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _require_extra(adapter: DataSource) -> None:
    """Exit 1 with the install hint, before any terms prompt, if the adapter's library is absent."""
    module = getattr(adapter, "required_module", None)
    extra = adapter.info.requires_extra
    if module is None or extra is None:
        return
    if importlib.util.find_spec(module) is None:
        raise SourceError(
            f'{adapter.info.name.capitalize()} adapter needs: pip install "vnstratlab[{extra}]"'
        )


def _require_terms(paths: AppPaths, adapter: DataSource, accept: bool, dry_run: bool) -> None:
    """ADR-007 section 2: show the notice once per interim source and store the acceptance."""
    if terms_accepted(paths, adapter):
        return
    typer.echo(terms_notice(adapter), err=True)
    if not accept:
        if not _is_interactive():
            typer.echo(
                "error: terms not accepted. Re-run with --accept-source-terms to accept "
                f"{adapter.info.name}'s terms non-interactively.",
                err=True,
            )
            raise typer.Exit(code=1)
        if not typer.confirm("Do you accept and want to continue? / Bạn đồng ý và muốn tiếp tục?"):
            raise typer.Exit(code=1)
    if not dry_run:  # a dry run creates no file
        record_terms_acceptance(paths, adapter, utc_now())


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
    accept_source_terms: Annotated[
        bool,
        typer.Option(
            "--accept-source-terms",
            help="Accept the terms of an interim source without asking (for OS schedulers).",
        ),
    ] = False,
) -> None:
    """Download or refresh market data into the local data directory."""
    start = _parse_date(from_date, "--from")
    end = _parse_date(to_date, "--to") or utc_now().astimezone(VN_TZ).date()  # Vietnam today
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
        _require_extra(adapter)
        _require_terms(paths, adapter, accept_source_terms, dry_run)
        start = start or default_start(cfg, paths, adapter)
        if start > end:
            typer.echo(f"{name}: up to date (latest stored session is on or after {end})")
            return
        report = ingest_data(cfg, paths, adapter, start, end, dry_run=dry_run)
    except SourceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2 if name not in source_names() else 1) from None
    _echo_ingest_report(report)
    if report.status == "partial":
        raise typer.Exit(code=3)


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
