"""Command-line interface: `vnstratlab <command>` or `python -m vnstratlab <command>`.

Most commands are stubs until their task card lands (see docs/roadmap.md).
A stub prints which card implements it and exits with code 1, so scripts never
mistake a stub for success.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import sys
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NoReturn

import typer

from vnstratlab import __version__
from vnstratlab.calendar import holiday_coverage
from vnstratlab.config.loader import ConfigError, load_config, load_config_with_info
from vnstratlab.data.gaps import (
    SEVERITIES,
    Gap,
    GapError,
    GapRegister,
    GapStatus,
    gaps_summary_line,
    load_gaps,
)
from vnstratlab.paths import get_paths

# pandas, numpy and duckdb are imported inside the commands that need them (through
# vnstratlab.data.pipeline / protocol / store), so `vnstratlab --help` and `--version` stay fast.
if TYPE_CHECKING:
    from datetime import datetime

    from vnstratlab.config.models import AppConfig
    from vnstratlab.data.pipeline import IngestReport
    from vnstratlab.data.protocol import DataSource
    from vnstratlab.data.store import DQRecord, Kind, RunRecord
    from vnstratlab.paths import AppPaths

app = typer.Typer(
    name="vnstratlab",
    help="Strategy lab for Vietnamese stocks. Recommendations only; it never places orders.",
    no_args_is_help=True,
    add_completion=False,
)


data_app = typer.Typer(help="Inspect the local market data: stores, runs, checks, gaps.")
app.add_typer(data_app, name="data")
features_app = typer.Typer(help="Point-in-time features (features_daily).")
app.add_typer(features_app, name="features")


class Horizon(StrEnum):
    short = "short"
    medium = "medium"
    long = "long"


DryRun = Annotated[
    bool, typer.Option("--dry-run", help="Print what would be written; write nothing.")
]


def utc_now() -> datetime:
    """Current UTC time (delegates to the pipeline's clock; imported lazily)."""
    from vnstratlab.data.pipeline import utc_now as pipeline_now

    return pipeline_now()


def get_source(name: str, cfg: AppConfig) -> DataSource:
    """Build a data adapter by name (delegates to the registry; imported lazily)."""
    from vnstratlab.data.protocol import get_source as registry_get

    return registry_get(name, cfg)


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
    from vnstratlab.settings import load_settings

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
    try:
        typer.echo(gaps_summary_line(load_gaps()))
    except GapError as exc:
        typer.echo(f"gaps: INVALID ({exc})")
        config_ok = False
    if not config_ok:
        raise typer.Exit(code=1)


@app.command()
def demo(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Also write summary.csv and equity/*.csv here (empty dir)."),
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="No progress lines and no table: warning and footer.")
    ] = False,
) -> None:
    """Run the whole pipeline offline on synthetic data (temporary files, no trials registered)."""
    from vnstratlab.demo import DemoError, format_report, run_demo
    from vnstratlab.runs import BusyError

    _tolerant_output()

    def progress(message: str) -> None:
        if not quiet:
            typer.echo(f"... {message}", err=True)

    try:
        report = run_demo(out, progress=progress, record_home=get_paths().home)
    except (DemoError, BusyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(format_report(report, quiet=quiet))


def _ask_checked(label: str, default: Any, kind: type, check: Any) -> Any:
    """Prompt until the value passes ``check`` (which returns an error text or None)."""
    while True:
        value = typer.prompt(label, default=default, type=kind)
        problem = check(value)
        if problem is None:
            return value
        typer.echo(f"  invalid: {problem}")


def _init_fail(problems: list[str]) -> NoReturn:
    for problem in problems:
        typer.echo(f"error: {problem}", err=True)
    raise typer.Exit(code=1)


@app.command()
def init(
    yes: Annotated[
        bool, typer.Option("--yes", help="No prompts; unspecified values keep defaults.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing config.yaml (after a backup).")
    ] = False,
    capital_short: Annotated[int | None, typer.Option(help="Capital in VND, short book.")] = None,
    capital_medium: Annotated[int | None, typer.Option(help="Capital in VND, medium book.")] = None,
    capital_long: Annotated[int | None, typer.Option(help="Capital in VND, long book.")] = None,
    source: Annotated[str | None, typer.Option(help="Data source: yahoo or synthetic.")] = None,
    brokerage_fee: Annotated[
        float | None, typer.Option(help="Brokerage fee as a fraction, e.g. 0.0015.")
    ] = None,
) -> None:
    """Create your config.yaml (capital per book, data source, fee) and the app home folders."""
    import yaml

    from vnstratlab import init_wizard as wiz

    paths = get_paths()
    config_file = paths.config_file
    if config_file.exists() and not force:
        typer.echo(
            f"error: {config_file} already exists. Re-run with --force to replace it "
            "(a backup copy is kept).",
            err=True,
        )
        raise typer.Exit(code=1)

    existing: dict[str, Any] = {}
    if config_file.exists():
        try:
            loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            _init_fail([f"{config_file}: cannot read existing file ({exc})"])
        if loaded is not None and not isinstance(loaded, dict):
            _init_fail([f"{config_file}: top level must be a mapping"])
        existing = loaded or {}

    wiz.ensure_home_dirs(paths)
    defaults = wiz.packaged_defaults()

    def current(path: tuple[str, ...]) -> Any:
        found = wiz.get_path(existing, path)
        return found if found is not None else wiz.get_path(defaults, path)

    capital: dict[str, int | None] = {}
    given = {"short": capital_short, "medium": capital_medium, "long": capital_long}
    problems: list[str] = []
    for book in wiz.BOOKS:
        value = given[book]
        if yes:
            if value is not None and (problem := wiz.check_capital(value)):
                problems.append(f"books.{book}.capital_vnd: {problem}")
            capital[book] = value
        elif value is not None:  # flag given in interactive mode: use it, no prompt
            capital[book] = value
        else:
            capital[book] = _ask_checked(
                f"Capital for the {book} book (VND)",
                current(("books", book, "capital_vnd")),
                int,
                wiz.check_capital,
            )
    if source is not None and (problem := wiz.check_source(source)):
        if yes:
            problems.append(f"data.source: {problem}")
        else:
            typer.echo(f"  invalid --source: {problem}")
            source = None
    if brokerage_fee is not None and (problem := wiz.check_fee(brokerage_fee)):
        if yes:
            problems.append(f"costs.brokerage_fee_pct: {problem}")
        else:
            typer.echo(f"  invalid --brokerage-fee: {problem}")
            brokerage_fee = None
    if problems:
        _init_fail(problems)

    if not yes:
        if source is None:
            source = str(
                _ask_checked(
                    "Data source (yahoo or synthetic)",
                    current(("data", "source")),
                    str,
                    wiz.check_source,
                )
            )
        if brokerage_fee is None:
            typer.echo("  Brokerage fee is a [VERIFY] value: check it with your broker.")
            brokerage_fee = _ask_checked(
                "Brokerage fee (fraction)",
                current(("costs", "brokerage_fee_pct")),
                float,
                wiz.check_fee,
            )
    if source == "yahoo":
        from vnstratlab.data.pipeline import terms_notice

        typer.echo(terms_notice(get_source("yahoo", wiz.packaged_config())))
        if not yes and not typer.confirm("Use Yahoo Finance under these terms?"):
            source = "synthetic"

    overrides = wiz.build_overrides(
        existing, capital=capital, source=source, brokerage_fee=brokerage_fee, defaults=defaults
    )
    if problems := wiz.validate_overrides(overrides):
        _init_fail(problems)

    now = utc_now()
    stamp = now.strftime("%Y%m%dT%H%M%S") if config_file.exists() else None
    wiz.write_config(config_file, wiz.render_config(overrides, now.date()), backup_stamp=stamp)

    chosen = source or current(("data", "source"))
    typer.echo(f"Wrote {config_file}")
    typer.echo("Telegram report is optional: see .env.example and docs/configuration.md.")
    typer.echo("Next steps:\n  vnstratlab doctor\n  vnstratlab demo")
    if chosen == "yahoo":
        typer.echo("  vnstratlab ingest")


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
    if report.failed:
        typer.echo(f"status {report.status}: {len(report.failed)} ticker(s) failed", err=True)
        for ticker, message in sorted(report.failed.items()):
            typer.echo(f"  {ticker}: {message}", err=True)
        typer.echo(
            "re-run `vnstratlab ingest` to retry: each ticker resumes from its own latest date, "
            "so the failed tickers are fetched again.",
            err=True,
        )
    if not report.dry_run:
        errors = [r for r in report.dq if r.severity == "error"]
        typer.echo(
            f"status {report.status}; checks: {len(errors)} error(s), "
            f"{len(report.dq) - len(errors)} warning(s)"
        )
        for r in errors[:_MAX_ERRORS]:
            typer.echo(f"  error {r.check} {r.ticker or '-'} {r.date}: {r.detail}", err=True)
        if len(errors) > _MAX_ERRORS:
            typer.echo(f"  ... {len(errors) - _MAX_ERRORS} more (vnstratlab data status)", err=True)
    if report.dry_run:
        typer.echo("dry run: nothing was written")
        for name, frame in report.preview.items():
            typer.echo(f"{name} (first 5 of {len(frame)} rows):")
            typer.echo(frame.head(5).to_string(index=False))
    else:
        typer.echo(f"store {report.db_path}")
        typer.echo(f"raw   {report.raw_path}")


def _tracked(pipeline_id: str, label_vi: str, dry_run: bool, body: Callable[[], None]) -> None:
    """Run a command body as a recorded run in the foreground (same output; it shows up in
    `vnstratlab runs list`). A dry run writes nothing, so it is not recorded."""
    if dry_run:
        body()
        return
    from vnstratlab.runs import BusyError, run_inline

    try:
        run_inline(get_paths().home, pipeline_id, label_vi, body)
    except BusyError:
        typer.echo("error: another run is in progress", err=True)
        raise typer.Exit(code=1) from None


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _require_extra(adapter: DataSource) -> None:
    """Exit 1 with the install hint, before any terms prompt, if the adapter's library is absent."""
    from vnstratlab.data.protocol import SourceError

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
    from vnstratlab.data.pipeline import record_terms_acceptance, terms_accepted, terms_notice

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
    _tracked(
        "ingest",
        "Tải dữ liệu",
        dry_run,
        lambda: _ingest_run(source, from_date, to_date, dry_run, accept_source_terms),
    )


def _ingest_run(
    source: str | None,
    from_date: str | None,
    to_date: str | None,
    dry_run: bool,
    accept_source_terms: bool,
) -> None:
    from vnstratlab.data.pipeline import VN_TZ, default_start
    from vnstratlab.data.pipeline import ingest as ingest_data
    from vnstratlab.data.protocol import SourceError, source_names

    _tolerant_output()
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
    if report.status == "failed_dq":
        raise typer.Exit(code=1)
    if report.status == "partial":
        raise typer.Exit(code=3)


# ------------------------------------------------------------------ data status / gaps

_MAX_ERRORS = 10
_RUNS_SHOWN = 5


def _run_dict(run: RunRecord) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "source": run.source,
        "start": str(run.start_date),
        "end": str(run.end_date),
        "rows_written": run.rows_written,
        "rows_changed": run.rows_changed,
        "rows_dropped": run.rows_dropped,
        "status": run.status,
    }


def _checks_dict(run_id: str, records: list[DQRecord]) -> dict[str, Any]:
    errors = [r for r in records if r.severity == "error"]
    return {
        "run_id": run_id,
        "errors": len(errors),
        "warnings": len(records) - len(errors),
        "first_errors": [
            {"check": r.check, "ticker": r.ticker, "date": str(r.date), "detail": r.detail}
            for r in errors[:_MAX_ERRORS]
        ],
    }


def _store_status(path: Path, kind: Kind) -> dict[str, Any]:
    import duckdb

    from vnstratlab.data.protocol import SourceError
    from vnstratlab.data.store import MarketStore

    entry: dict[str, Any] = {"file": path.name, "kind": kind}
    try:
        with MarketStore(path, kind, read_only=True) as store:
            tickers = store.summary()
            runs = store.recent_runs(_RUNS_SHOWN)
            checks = None
            if runs:
                checks = _checks_dict(runs[0].run_id, store.read_dq_results(runs[0].run_id))
            rows = store.row_count()
    except (SourceError, duckdb.Error) as exc:
        entry["error"] = str(exc)
        return entry
    entry["rows"] = rows
    entry["tickers"] = [
        {"ticker": t, "first": str(a), "last": str(b), "rows": n} for t, a, b, n in tickers
    ]
    entry["runs"] = [_run_dict(r) for r in runs]
    entry["last_run_checks"] = checks
    return entry


def _gap_dict(gap: Gap) -> dict[str, Any]:
    return gap.model_dump(mode="json")


def _load_register_or_exit() -> GapRegister:
    try:
        return load_gaps()
    except GapError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None


def _echo_store(entry: dict[str, Any]) -> None:
    typer.echo(f"{entry['file']}  ({entry['kind']})")
    if "error" in entry:
        typer.echo(f"  cannot read: {entry['error']}")
        return
    typer.echo(f"  rows {entry['rows']}, tickers {len(entry['tickers'])}")
    for t in entry["tickers"]:
        typer.echo(f"    {t['ticker']:<8} {t['first']} .. {t['last']}  ({t['rows']} rows)")
    typer.echo("  last runs:")
    for r in entry["runs"]:
        typer.echo(
            f"    {r['run_id']}  {r['source']}  {r['start']} .. {r['end']}  "
            f"written {r['rows_written']}, changed {r['rows_changed']}, "
            f"dropped {r['rows_dropped']}  {r['status']}"
        )
    checks = entry["last_run_checks"]
    if checks is not None:
        typer.echo(
            f"  checks of last run {checks['run_id']}: "
            f"{checks['errors']} error(s), {checks['warnings']} warning(s)"
        )
        for e in checks["first_errors"]:
            typer.echo(f"    error {e['check']} {e['ticker'] or '-'} {e['date']}: {e['detail']}")


def _tolerant_output() -> None:
    """Never crash on Vietnamese text when stdout/stderr is a pipe or file with a legacy code
    page (Windows cp1252): unencodable characters become '?'."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")


def _echo_gap_list(gaps: list[Gap]) -> None:
    for severity in SEVERITIES:
        for gap in (g for g in gaps if g.severity == severity):
            typer.echo(f"  [{severity}] {gap.id}  {gap.title} / {gap.title_vi}")


def build_data_status(paths: AppPaths, register: GapRegister | None = None) -> dict[str, Any]:
    """The facts of `vnstratlab data status --json` (also served by `/api/data/status`)."""
    register = register or load_gaps()
    stores = [
        _store_status(paths.market_db_for(kind), kind)
        for kind in ("real", "synthetic")
        if paths.market_db_for(kind).is_file()
    ]
    return {
        "home": str(paths.home),
        "stores": stores,
        "gaps": {
            "counts": register.open_counts(),
            "open": [_gap_dict(g) for g in register.with_status("open")],
        },
    }


@data_app.command("status")
def data_status(
    as_json: Annotated[bool, typer.Option("--json", help="Print everything as JSON.")] = False,
) -> None:
    """Show stores, the last ingest runs, the last run's checks and open data gaps (offline)."""
    _tolerant_output()
    paths = get_paths()
    register = _load_register_or_exit()
    payload = build_data_status(paths, register)
    stores = payload["stores"]
    open_gaps = register.with_status("open")
    if as_json:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=True))
        return
    typer.echo(f"home {paths.home}")
    typer.echo("stores:")
    if not stores:
        typer.echo("  no data yet. Try: vnstratlab ingest --source synthetic   (offline)")
        typer.echo("  or:               vnstratlab ingest                      (default source)")
    for entry in stores:
        _echo_store(entry)
    typer.echo(gaps_summary_line(register))
    _echo_gap_list(open_gaps)


@data_app.command("rebuild")
def data_rebuild(
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    dry_run: DryRun = False,
) -> None:
    """Rebuild adjusted prices and the execution series from the stored data (offline)."""
    _tracked("rebuild", "Dựng lại chuỗi giá", dry_run, lambda: _data_rebuild_run(source, dry_run))


def _data_rebuild_run(source: str | None, dry_run: bool) -> None:
    from vnstratlab.data.pipeline import rebuild
    from vnstratlab.data.protocol import SourceError, TickTable
    from vnstratlab.data.store import MarketStore, kind_of_source

    _tolerant_output()
    paths = get_paths()
    try:
        cfg = load_config(paths.home)
    except ConfigError as exc:
        typer.echo("config: INVALID", err=True)
        for problem in exc.problems:
            typer.echo(f"  {problem}", err=True)
        raise typer.Exit(code=1) from None
    name = source or cfg.data.source
    db_path = paths.market_db_for(kind_of_source(name))
    if not db_path.is_file():
        typer.echo(f"error: no store at {db_path}: run `vnstratlab ingest` first", err=True)
        raise typer.Exit(code=1)
    try:
        with MarketStore(db_path, kind_of_source(name), read_only=dry_run) as store:
            report = rebuild(store, name, TickTable.from_config(cfg), dry_run=dry_run)
    except SourceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    verb = "would rebuild" if dry_run else "rebuilt"
    typer.echo(f"{verb} {name}: {report.price_rows} price rows")
    typer.echo(
        f"  prices_adjusted {report.adjusted_rows} rows, prices_exec {report.exec_rows} rows"
    )
    typer.echo(
        f"  excluded tickers {len(report.excluded_tickers)} "
        f"({report.excluded_ticker_rows} rows): {', '.join(report.excluded_tickers) or '-'}"
    )
    typer.echo(f"  bad source rows omitted {report.bad_rows_omitted}")
    typer.echo(f"  scale outlier rows omitted {report.outlier_rows_omitted}")
    typer.echo(
        f"  rows before a scale step excluded {report.step_rows_excluded} "
        f"(suspect events {report.suspect_events})"
    )
    typer.echo(f"  non-HOSE history rows excluded {report.non_hose_rows_excluded}")
    typer.echo(f"  rows without reference omitted {report.no_reference_omitted}")
    for item in report.exclusions[:_MAX_ERRORS]:
        typer.echo(f"    {item.kind} {item.ticker} {item.date or '-'}: {item.detail}")
    if len(report.exclusions) > _MAX_ERRORS:
        typer.echo(f"    ... {len(report.exclusions) - _MAX_ERRORS} more (table exec_exclusions)")
    for warning in report.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if dry_run:
        typer.echo("dry run: nothing was written")


@data_app.command("gaps")
def data_gaps(
    status: Annotated[GapStatus | None, typer.Option("--status", help="Filter by status.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print as JSON.")] = False,
) -> None:
    """Print the data gap register (docs/data-gaps.md)."""
    _tolerant_output()
    register = _load_register_or_exit()
    gaps = register.with_status(status)
    if as_json:
        typer.echo(json.dumps([_gap_dict(g) for g in gaps], indent=2, ensure_ascii=True))
        return
    if not gaps:
        typer.echo("no gaps with that status")
        return
    for gap in gaps:
        typer.echo(f"{gap.id}  [{gap.severity}] {gap.status}  {gap.title}")
        typer.echo(f"  vi:         {gap.title_vi}")
        typer.echo(f"  missing:    {gap.missing}")
        typer.echo(f"  affects:    {', '.join(gap.affects)}")
        typer.echo(f"  workaround: {gap.workaround}")
        typer.echo(f"  closed by:  {gap.close_by}")


@features_app.command("build")
def features_build(
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    dry_run: DryRun = False,
) -> None:
    """Compute features_daily from the rebuilt adjusted and execution series (offline)."""
    _tracked("features", "Tính đặc trưng", dry_run, lambda: _features_build_run(source, dry_run))


def _features_build_run(source: str | None, dry_run: bool) -> None:
    from vnstratlab.data.protocol import SourceError, universe_tickers
    from vnstratlab.data.store import MarketStore, kind_of_source
    from vnstratlab.features.build import build_features
    from vnstratlab.features.core import FeatureError

    _tolerant_output()
    paths = get_paths()
    try:
        cfg = load_config(paths.home)
    except ConfigError as exc:
        typer.echo("config: INVALID", err=True)
        for problem in exc.problems:
            typer.echo(f"  {problem}", err=True)
        raise typer.Exit(code=1) from None
    name = source or cfg.data.source
    db_path = paths.market_db_for(kind_of_source(name))
    if not db_path.is_file():
        typer.echo(f"error: no store at {db_path}: run `vnstratlab ingest` first", err=True)
        raise typer.Exit(code=1)
    try:
        with MarketStore(db_path, kind_of_source(name), read_only=dry_run) as store:
            report = build_features(store, name, universe_tickers(cfg), dry_run=dry_run)
    except (SourceError, FeatureError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    verb = "would build" if dry_run else "built"
    typer.echo(f"{verb} features for {name}: {report.rows} rows, version {report.feature_version}")
    typer.echo("rows per ticker:")
    for ticker, count in report.rows_per_ticker.items():
        typer.echo(f"  {ticker} {count}")
    if report.missing_tickers:
        typer.echo(f"universe tickers without data: {', '.join(report.missing_tickers)}")
    typer.echo("NaN share per feature group:")
    for group, share in report.nan_share.items():
        typer.echo(f"  {group} {share:.3f}")
    typer.echo(
        f"sessions_in_window: 20 sessions span {report.span_20:.1f} weekdays, "
        f"250 sessions span {report.span_250:.1f} weekdays (median over tickers)"
    )
    typer.echo(f"runtime {report.seconds:.2f} s")
    for warning in report.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if dry_run:
        typer.echo("dry run: nothing was written")


class BacktestMode(StrEnum):
    ideal = "ideal"
    executable = "executable"
    both = "both"


@app.command()
def backtest(
    strategy: Annotated[
        str | None,
        typer.Option(
            "--strategy",
            help="Strategy id: all its registered trials of the current feature/engine version.",
        ),
    ] = None,
    all_: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Every registered trial of the current feature/engine version (not the config).",
        ),
    ] = False,
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    mode: Annotated[BacktestMode, typer.Option("--mode", help="Which mode(s) to run.")] = (
        BacktestMode.both
    ),
    register: Annotated[
        bool,
        typer.Option(
            "--register",
            help="Register the config trials first (like `lab register`); without it a config "
            "trial that is not registered is an error.",
        ),
    ] = False,
) -> None:
    """Walk-forward backtest of registered trials: out-of-sample returns into lab.duckdb.

    Trials that cannot be rebuilt from the current code are listed as not runnable.
    """
    from vnstratlab.data.protocol import SourceError
    from vnstratlab.lab.trials import UnregisteredTrialError
    from vnstratlab.lab.walkforward import WalkForwardError, format_summary
    from vnstratlab.runs import BusyError, run_pipeline

    _tolerant_output()
    if (strategy is None) == (not all_):
        raise typer.BadParameter("give exactly one of --strategy ID or --all")
    cfg = _load_cfg_or_exit()
    name = source or cfg.data.source
    params = {"source": name, "strategy": strategy, "modes": mode.value, "register": register}

    def progress(message: str) -> None:
        typer.echo(f"... {message}", err=True)

    try:
        result = run_pipeline(get_paths().home, "backtest_all", params, progress=progress)
        result.raise_for_failure()
    except BusyError:
        typer.echo("error: another run is in progress", err=True)
        raise typer.Exit(code=1) from None
    except (UnregisteredTrialError, WalkForwardError, SourceError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    summary = result.state["backtest_summary"]
    outcome = result.state["backtest"]
    if outcome.registered_now:
        typer.echo(
            f"registered {len(outcome.registered_now)} new trial(s) first (--register); "
            f"trials now in the registry include them"
        )
    typer.echo(format_summary(summary, outcome.source))
    for item in outcome.not_runnable:
        typer.echo(f"not runnable: trial {item.trial_id}: {item.reason}")
    typer.echo(
        f"trials run {len(outcome.trials)}, not runnable {len(outcome.not_runnable)}, "
        f"rows written {outcome.rows_written} "
        f"(feature version {outcome.feature_version}); stored in lab.duckdb, table oos_returns"
    )


lab_app = typer.Typer(
    help="The strategy lab: selection cycle and the trial registry.",
    invoke_without_command=True,
)
app.add_typer(lab_app, name="lab")


@lab_app.callback()
def lab(
    ctx: typer.Context,
    horizon: Annotated[
        Horizon | None, typer.Option("--horizon", help="Horizon of the selection cycle.")
    ] = None,
    asof: Annotated[str | None, typer.Option("--asof", help="YYYY-MM-DD")] = None,
    dry_run: DryRun = False,
) -> None:
    """Run one strategy-selection cycle (gates, MCS, weights) for a horizon.

    Sub-commands `trials` and `register` manage the trial registry.
    """
    if ctx.invoked_subcommand is not None:
        return
    if horizon is None:
        raise typer.BadParameter("Missing option '--horizon'.", param_hint="--horizon")
    _not_implemented("P1-T22")


def _load_cfg_or_exit() -> AppConfig:
    try:
        return load_config(get_paths().home)
    except ConfigError as exc:
        typer.echo("config: INVALID", err=True)
        for problem in exc.problems:
            typer.echo(f"  {problem}", err=True)
        raise typer.Exit(code=1) from None


def _lab_db_error(path: Path, exc: Exception) -> NoReturn:
    typer.echo(
        f"error: cannot use {path} (locked by another process or unreadable): {exc}", err=True
    )
    raise typer.Exit(code=1)


def _echo_trial_line(
    trial_id: str, strategy_id: str, horizon: str, params_json: str, note: str
) -> None:
    typer.echo(f"  {trial_id}  {strategy_id:<22} {horizon:<6} {params_json}  {note}".rstrip())


@lab_app.command("trials")
def lab_trials(
    horizon: Annotated[Horizon | None, typer.Option("--horizon", help="Only this horizon.")] = None,
) -> None:
    """List the registered trials and their count (read-only)."""
    import duckdb

    from vnstratlab.lab.trials import TrialRegistry

    _tolerant_output()
    db_path = get_paths().lab_db
    selected = None if horizon is None else horizon.value
    if not db_path.is_file():
        typer.echo("no trial registry yet: run `vnstratlab lab register`")
        typer.echo("trials: 0")
        return
    try:
        with TrialRegistry(db_path, read_only=True) as registry:
            records = registry.list(selected)
            total = registry.count(selected)
    except duckdb.Error as exc:
        _lab_db_error(db_path, exc)
    for r in records:
        stamp = r.registered_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        _echo_trial_line(
            r.trial_id, r.strategy_id, r.horizon, r.params_json, f"{stamp}  [{r.rationale}]"
        )
    typer.echo(f"trials: {total}" + (f" (horizon {selected})" if selected else ""))


@lab_app.command("stats")
def lab_stats(
    horizon: Annotated[Horizon | None, typer.Option("--horizon", help="Only this horizon.")] = None,
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    mode: Annotated[
        BacktestMode, typer.Option("--mode", help="ideal or executable (default executable).")
    ] = BacktestMode.executable,
) -> None:
    """Sharpe, Deflated Sharpe and PBO of the current trials, with the gate-1 verdicts.

    Computes from the stored out-of-sample returns and stores the rows in lab.duckdb (table
    trial_stats). Gate inputs are the historical (in-sample by design) segment; no selection yet.
    """
    import duckdb

    from vnstratlab.lab.stats import add_gate_columns, compute_lab_stats
    from vnstratlab.lab.walkforward import SEGMENT_LABELS, data_label

    if mode is BacktestMode.both:
        raise typer.BadParameter("give one mode: ideal or executable", param_hint="--mode")
    _tolerant_output()
    cfg = _load_cfg_or_exit()
    name = source or cfg.data.source
    paths = get_paths()
    if not paths.lab_db.is_file():
        typer.echo("no lab store yet: run `vnstratlab backtest --all --register`")
        return
    try:
        frame = compute_lab_stats(
            cfg, paths, name, None if horizon is None else horizon.value, mode.value
        )
    except duckdb.Error as exc:
        _lab_db_error(paths.lab_db, exc)
    typer.echo(data_label(name))
    typer.echo(f"mode {mode.value}; historical = {SEGMENT_LABELS['historical']}")
    if frame.empty:
        typer.echo("no trials: run `vnstratlab backtest --all --register`")
        return
    gated = add_gate_columns(frame, cfg)
    hist = gated[gated["segment"] == "historical"]
    fwd_periods = {
        str(k): int(v)
        for k, v in zip(
            frame.loc[frame["segment"] == "forward", "trial_id"],
            frame.loc[frame["segment"] == "forward", "periods"],
            strict=True,
        )
    }

    def num(v: Any, spec: str) -> str:
        return "n/a" if v != v else format(v, spec)

    def mark(v: Any) -> str:
        return "pass" if v else "FAIL"

    header = f"{'trial':<18}{'hz':<7}{'T':>4}{'SR':>8}{'skew':>8}{'kurt':>7}{'DSR':>7}{'N':>4}  "
    typer.echo(header + f"{'PBO':>6}  periods dsr  pbo   fwd T")
    rows: list[dict[Any, Any]] = hist.to_dict("records")
    for r in rows:
        typer.echo(
            f"{r['trial_id']:<18}{r['horizon']:<7}{int(r['periods']):>4}{num(r['sr'], '.3f'):>8}"
            f"{num(r['skew'], '.2f'):>8}{num(r['kurt'], '.2f'):>7}{num(r['dsr'], '.3f'):>7}"
            f"{int(r['n_trials']):>4}  {num(r['pbo'], '.3f'):>6}  "
            f"{mark(r['periods_ok']):<7} {mark(r['dsr_ok']):<5}{mark(r['pbo_ok']):<5} "
            f"{fwd_periods[r['trial_id']]}"
        )
    passing = sum(1 for r in rows if r["periods_ok"] and r["dsr_ok"] and r["pbo_ok"])
    typer.echo(
        f"gate 1: DSR >= {cfg.lab.gate1.dsr_min}, PBO <= {cfg.lab.gate1.pbo_max}, periods >= "
        f"min_periods (no selection yet); passing all three: "
        f"{passing} of {len(rows)}"
    )


@lab_app.command("register")
def lab_register(
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    dry_run: DryRun = False,
) -> None:
    """Register every enabled (strategy, param set, horizon) from config as a trial."""
    import duckdb

    from vnstratlab.data.protocol import SourceError
    from vnstratlab.data.store import MarketStore, kind_of_source
    from vnstratlab.engine import ENGINE_VERSION
    from vnstratlab.lab.trials import TrialError, TrialRegistry, store_feature_version
    from vnstratlab.strategies.registry import (
        StrategyConfigError,
        load_strategies,
        make_trial_spec,
    )

    _tolerant_output()
    paths = get_paths()
    cfg = _load_cfg_or_exit()
    try:
        strategies = load_strategies(cfg)
    except StrategyConfigError as exc:
        typer.echo("strategies config: INVALID", err=True)
        for problem in exc.problems:
            typer.echo(f"  {problem}", err=True)
        raise typer.Exit(code=1) from None
    if not strategies:
        typer.echo("no enabled strategies in config: nothing to register")
        return
    name = source or cfg.data.source
    market_db = paths.market_db_for(kind_of_source(name))
    if not market_db.is_file():
        typer.echo(f"error: no store at {market_db}: run `vnstratlab ingest` first", err=True)
        raise typer.Exit(code=1)
    try:
        with MarketStore(market_db, kind_of_source(name), read_only=True) as store:
            feature_version = store_feature_version(store)
    except (SourceError, TrialError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    specs = [
        make_trial_spec(s, h, feature_version, ENGINE_VERSION)
        for s in strategies
        for h in s.horizons
    ]
    # a dry run never creates lab.duckdb: it only reads one that already exists
    exists = paths.lab_db.is_file()
    registry = None
    if exists or not dry_run:
        try:
            registry = TrialRegistry(paths.lab_db, read_only=dry_run)
        except duckdb.Error as exc:
            _lab_db_error(paths.lab_db, exc)
    created = 0
    try:
        for spec in specs:
            if registry is None:
                is_new = True
            else:
                result = registry.register(spec, "config", dry_run=dry_run)
                is_new = result.created
            created += is_new
            _echo_trial_line(
                spec.trial_id,
                spec.strategy_id,
                spec.horizon,
                spec.params_json,
                ("would register" if dry_run else "registered") if is_new else "already registered",
            )
        total = registry.count() if registry is not None else 0
    except duckdb.Error as exc:
        _lab_db_error(paths.lab_db, exc)
    finally:
        if registry is not None:
            registry.close()
    typer.echo(
        f"{'would register' if dry_run else 'registered'} {created} new trial(s) of {len(specs)} "
        f"(feature version {feature_version}, engine {ENGINE_VERSION})"
    )
    if dry_run:
        typer.echo(f"trials now: {total}; dry run: nothing was written")
    else:
        typer.echo(f"trials now: {total}")


@app.command()
def recommend(
    horizon: Annotated[
        Horizon | None, typer.Option("--horizon", help="Only this horizon; default: all three.")
    ] = None,
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
) -> None:
    """Current recommended stocks per horizon (preview, equal weight over registered trials).

    Recommend-only: it never places orders. Only registered trials count.
    """
    import duckdb

    from vnstratlab.data.protocol import SourceError
    from vnstratlab.insight.recommend import (
        InsightError,
        all_recommendations,
        format_recommendations,
        recommendations,
    )
    from vnstratlab.strategies.registry import StrategyConfigError

    _tolerant_output()
    cfg = _load_cfg_or_exit()
    name = source or cfg.data.source
    try:
        if horizon is not None:
            bodies = [recommendations(cfg, get_paths(), name, horizon.value)]
        else:
            bodies = list(all_recommendations(cfg, get_paths(), name)["horizons"].values())
    except (InsightError, SourceError, StrategyConfigError, duckdb.Error) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo("\n\n".join(format_recommendations(b) for b in bodies))


@app.command()
def stock(
    ticker: Annotated[str, typer.Argument(help="Ticker in the local store, e.g. ACB.")],
    source: Annotated[
        str | None, typer.Option("--source", help="Data source; default data.source in config.")
    ] = None,
    horizon: Annotated[
        Horizon | None, typer.Option("--horizon", help="Only this horizon; default: all three.")
    ] = None,
) -> None:
    """Analyse one stock: numbers, each registered strategy's signal and a recommendation.

    Recommend-only: it never places orders. The result is also what the Console shows.
    """
    from vnstratlab.data.protocol import SourceError
    from vnstratlab.insight.recommend import InsightError
    from vnstratlab.insight.stock import format_analysis
    from vnstratlab.runs import BusyError, ParamError, run_pipeline

    _tolerant_output()
    cfg = _load_cfg_or_exit()
    params = {
        "ticker": ticker,
        "source": source or cfg.data.source,
        "horizons": [horizon.value] if horizon is not None else None,
    }

    def progress(message: str) -> None:
        typer.echo(f"... {message}", err=True)

    try:
        result = run_pipeline(get_paths().home, "stock_analysis", params, progress=progress)
        result.raise_for_failure()
    except BusyError:
        typer.echo("error: another run is in progress", err=True)
        raise typer.Exit(code=1) from None
    except (ParamError, InsightError, SourceError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(format_analysis(result.state["analysis"]))


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


runs_app = typer.Typer(help="History of pipeline runs (tasks, status, logs).")
app.add_typer(runs_app, name="runs")


def _fmt_seconds(value: object) -> str:
    return f"{float(value):.1f}s" if isinstance(value, int | float) else "-"


@runs_app.command("list")
def runs_list(
    limit: Annotated[int, typer.Option("--limit", help="How many runs to show.")] = 20,
) -> None:
    """List the latest runs, newest first."""
    from vnstratlab.runs import RunStore

    _tolerant_output()
    runs = RunStore(get_paths().home).list(max(1, limit))
    if not runs:
        typer.echo("no runs yet. Try: vnstratlab demo")
    for run in runs:
        typer.echo(
            f"{run['run_id']}  {run['status']:<8} {_fmt_seconds(run['duration_s']):>8}  "
            f"{run['pipeline']}"
        )


@runs_app.command("show")
def runs_show(run_id: Annotated[str, typer.Argument(help="A run id from `runs list`.")]) -> None:
    """Show one run: its tasks, status and duration."""
    from vnstratlab.runs import RunStore

    _tolerant_output()
    store = RunStore(get_paths().home)
    run = store.get(run_id)
    if run is None:
        typer.echo(f"error: no run {run_id!r} (see `vnstratlab runs list`)", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{run['run_id']}  {run['status']}  {_fmt_seconds(run['duration_s'])}")
    if run.get("reason"):
        typer.echo(f"reason: {run['reason']}")
    for task in run["tasks"]:
        typer.echo(f"  {task['id']:<12} {task['status']:<8} {_fmt_seconds(task['duration_s']):>8}")
        if task.get("error"):
            typer.echo(f"    error: {task['error']}")
    typer.echo(f"logs {store.run_dir(run_id)}")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address (loopback only).")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8000,
    no_open: Annotated[bool, typer.Option("--no-open", help="Do not open the browser.")] = False,
) -> None:
    """Start the local Console (API and UI) on this machine only."""
    from vnstratlab.app.server import is_loopback

    if not is_loopback(host):
        typer.echo(
            f"error: refusing to bind {host!r}: only loopback (127.0.0.1) is allowed", err=True
        )
        raise typer.Exit(code=1)
    import threading
    import webbrowser

    import uvicorn

    from vnstratlab.app.server import create_app

    url = f"http://{'[::1]' if ':' in host else host}:{port}/"
    typer.echo(f"vnstratlab Console on {url} (Ctrl+C to stop)")
    if not no_open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":  # pragma: no cover
    app()
