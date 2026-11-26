"""Console v2: overview and chart data from the local store (card X-console-api).

Read-only: every query opens the market store read-only and nothing leaves the machine.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import duckdb
from fastapi import FastAPI, Query

from vnstratlab import __version__
from vnstratlab.app import api_strategies
from vnstratlab.app.api_config import json_error
from vnstratlab.config.loader import ConfigError, load_config
from vnstratlab.paths import AppPaths
from vnstratlab.runs import RunManager

MAX_POINTS = 3000
_TICKER = re.compile(r"^[A-Za-z0-9._-]{1,12}$")


def downsample(n: int, limit: int = MAX_POINTS) -> list[int]:
    """Indices of at most ``limit`` evenly spaced points out of ``n``, keeping first and last."""
    if n <= limit:
        return list(range(n))
    picked = {round(i * (n - 1) / (limit - 1)) for i in range(limit)}
    return sorted(picked)


def verify_count(cfg: Any) -> int:
    """Market rules and holidays still marked ``VERIFY`` (release gate G3 lists them)."""
    rules = cfg.market.rules
    count = sum(1 for name in type(rules).model_fields if getattr(rules, name).status == "VERIFY")
    for block in cfg.market.holidays.values():
        count += sum(1 for day in block.days if day.status == "VERIFY")
    return count


def _open_store(paths: AppPaths, source: str) -> Any:
    from vnstratlab.data.store import MarketStore, kind_of_source

    kind = kind_of_source(source)
    db = paths.market_db_for(kind)
    return MarketStore(db, kind, read_only=True) if db.is_file() else None


def _store_overview(paths: AppPaths, source: str, today: dt.date) -> dict[str, Any] | None:
    from vnstratlab.data.protocol import SourceError
    from vnstratlab.data.store import kind_of_source

    try:
        store = _open_store(paths, source)
        if store is None:
            return None
        with store:
            rows = store.summary()
            total = store.row_count()
    except (SourceError, duckdb.Error):
        return None
    if not rows:
        return None
    last = max(r[2] for r in rows)
    return {
        "kind": kind_of_source(source),
        "tickers": [r[0] for r in rows],
        "ticker_count": len(rows),
        "first": str(min(r[1] for r in rows)),
        "last": str(last),
        "rows": total,
        "stale_days": max((today - last).days, 0),
    }


def build_overview(paths: AppPaths, manager: RunManager) -> dict[str, Any]:
    from vnstratlab.data.gaps import GapError, load_gaps
    from vnstratlab.strategies.registry import StrategyConfigError, load_strategies, registered_ids

    cfg = load_config(paths.home)
    try:
        counts = load_gaps().open_counts()
    except GapError:
        counts = {}
    try:
        enabled = len({s.id for s in load_strategies(cfg)})
    except StrategyConfigError:
        enabled = 0
    try:
        with api_strategies.LAB_LOCK:
            trials = api_strategies.trial_total(paths)
    except duckdb.Error:
        trials = 0
    return {
        "version": __version__,
        "home": str(paths.home),
        "source": cfg.data.source,
        "store": _store_overview(paths, cfg.data.source, dt.datetime.now(dt.UTC).date()),
        "last_runs": manager.store.list(5),
        "active_run_id": manager.active_run_id,
        "gaps": {k: int(counts.get(k, 0)) for k in ("high", "medium", "low")},
        "verify_count": verify_count(cfg),
        "strategies": {"registered": len(registered_ids()), "enabled": enabled, "trials": trials},
    }


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def register(app: FastAPI, paths: AppPaths, manager: RunManager) -> None:
    @app.get("/api/overview", response_model=None)
    def overview() -> Any:
        try:
            return build_overview(paths, manager)
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))

    @app.get("/api/data/prices/{ticker}", response_model=None)
    def prices(
        ticker: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = None,
        series: str = "adjusted",
    ) -> Any:
        from vnstratlab.data.protocol import SourceError
        from vnstratlab.data.store import kind_of_source

        if not _TICKER.match(ticker):
            return json_error(422, "bad_ticker", ticker=ticker)
        if series not in ("adjusted", "exec"):
            return json_error(422, "bad_series", message="series must be adjusted or exec")
        try:
            start, end = _date(from_), _date(to)
        except ValueError:
            return json_error(422, "bad_date", message="from and to must be YYYY-MM-DD")
        try:
            source = load_config(paths.home).data.source
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))
        table = "prices_adjusted" if series == "adjusted" else "prices_exec"
        where = "WHERE a.ticker = ? AND a.source = ?"
        args: list[Any] = [ticker.upper(), source]
        if start:
            where += " AND a.date >= ?"
            args.append(start)
        if end:
            where += " AND a.date <= ?"
            args.append(end)
        if series == "adjusted":
            sql = (
                "SELECT a.date, a.adj_close, d.volume FROM prices_adjusted a "  # noqa: S608
                "LEFT JOIN prices_daily d ON d.ticker = a.ticker AND d.date = a.date "
                f"AND d.source = a.source {where} ORDER BY a.date"
            )
        else:
            sql = f"SELECT a.date, a.close, a.volume FROM prices_exec a {where} ORDER BY a.date"  # noqa: S608
        try:
            store = _open_store(paths, source)
            if store is None:
                return json_error(404, "no_data", message="no local store yet")
            with store:
                if not store.has_table(table):
                    return json_error(404, "no_data", message=f"no {table} yet: run rebuild")
                rows = store.connection.execute(sql, args).fetchall()
        except (SourceError, duckdb.Error) as exc:
            return json_error(503, "store_unavailable", message=str(exc))
        if not rows:
            return json_error(404, "no_data", ticker=ticker.upper())
        keep = downsample(len(rows))
        rows = [rows[i] for i in keep]
        return {
            "ticker": ticker.upper(),
            "kind": kind_of_source(source),
            "series": series,
            "dates": [str(r[0])[:10] for r in rows],
            "close": [None if r[1] is None or r[1] != r[1] else float(r[1]) for r in rows],
            "volume": [None if r[2] is None else int(r[2]) for r in rows],
        }

    @app.get("/api/data/quality", response_model=None)
    def quality(limit: int = 100) -> Any:
        from vnstratlab.data.protocol import SourceError

        limit = min(max(limit, 1), 1000)
        try:
            source = load_config(paths.home).data.source
            store = _open_store(paths, source)
            if store is None:
                return {"rows": []}
            with store:
                if not store.has_table("dq_results"):
                    return {"rows": []}
                found = store.connection.execute(
                    'SELECT date, ticker, "check", severity, detail FROM dq_results '
                    'ORDER BY date DESC, "check", ticker LIMIT ?',
                    [limit],
                ).fetchall()
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))
        except (SourceError, duckdb.Error) as exc:
            return json_error(503, "store_unavailable", message=str(exc))
        return {
            "rows": [
                {
                    "date": str(r[0])[:10],
                    "ticker": r[1],
                    "check": r[2],
                    "level": r[3],
                    "detail": r[4],
                }
                for r in found
            ]
        }
