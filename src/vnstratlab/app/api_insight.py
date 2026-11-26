"""Console: current recommendations and per-stock analysis (card X-stock-api).

Contract: ``docs/cards/stock-insight-api.md``. Loopback and the ``X-Vnstratlab: 1`` header on POST
are enforced by the middleware in ``server.py``. Recommend-only: no endpoint here places, routes or
confirms an order; every body carries the data ``label`` and the Vietnamese ``disclaimer_vi``.
"""

from __future__ import annotations

import re
from typing import Any

import duckdb
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vnstratlab.app.api_config import json_error
from vnstratlab.config.loader import ConfigError, load_config
from vnstratlab.insight.recommend import (
    DISCLAIMER_VI,
    InsightError,
    all_recommendations,
    recommendations,
)
from vnstratlab.insight.stock import compare, list_stocks, load_latest
from vnstratlab.lab.walkforward import data_label
from vnstratlab.paths import AppPaths
from vnstratlab.runs import BusyError, ParamError, RunError, RunManager
from vnstratlab.strategies.base import HORIZONS
from vnstratlab.strategies.registry import StrategyConfigError

_SOURCE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_STATUS = {
    "no_data": 404,
    "no_features": 409,
    "unknown_ticker": 404,
    "bad_horizon": 422,
    "bad_ticker": 422,
    "bad_tickers": 422,
}


class AnalyzeBody(BaseModel):
    source: str | None = None
    horizons: list[str] | None = None


def register(app: FastAPI, paths: AppPaths, manager: RunManager) -> None:
    def resolve(source: str | None) -> tuple[Any, str] | JSONResponse:
        try:
            cfg = load_config(paths.home)
        except ConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))
        name = source or cfg.data.source
        if not _SOURCE.match(name):
            return json_error(422, "bad_source", source=name)
        return cfg, name

    def guarded(call: Any) -> Any:
        try:
            return call()
        except InsightError as exc:
            return json_error(_STATUS.get(exc.code, 422), exc.code, message=str(exc))
        except StrategyConfigError as exc:
            return json_error(422, "config_invalid", problems=list(exc.problems))
        except duckdb.Error as exc:  # a store is being written (a run is in progress)
            return json_error(409, "store_busy", message=str(exc))

    @app.get("/api/recommendations", response_model=None)
    def get_recommendations(horizon: str = "medium", source: str | None = None) -> Any:
        if horizon not in HORIZONS:
            return json_error(422, "bad_horizon", horizon=horizon, available=list(HORIZONS))
        resolved = resolve(source)
        if isinstance(resolved, JSONResponse):
            return resolved
        cfg, name = resolved
        return guarded(lambda: recommendations(cfg, paths, name, horizon, None))

    @app.get("/api/recommendations/all", response_model=None)
    def get_all_recommendations(source: str | None = None) -> Any:
        resolved = resolve(source)
        if isinstance(resolved, JSONResponse):
            return resolved
        cfg, name = resolved
        return guarded(lambda: all_recommendations(cfg, paths, name))

    @app.get("/api/stocks", response_model=None)
    def get_stocks(source: str | None = None) -> Any:
        resolved = resolve(source)
        if isinstance(resolved, JSONResponse):
            return resolved
        cfg, name = resolved
        return guarded(lambda: list_stocks(cfg, paths, name))

    @app.get("/api/stocks/compare", response_model=None)
    def get_compare(tickers: str = "", source: str | None = None) -> Any:
        resolved = resolve(source)
        if isinstance(resolved, JSONResponse):
            return resolved
        _cfg, name = resolved
        names = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        return guarded(lambda: compare(paths, name, names))

    @app.post("/api/stocks/{ticker}/analyze", response_model=None)
    def analyze(ticker: str, body: AnalyzeBody | None = None) -> Any:
        params: dict[str, Any] = {"ticker": ticker}
        if body is not None and body.source:
            params["source"] = body.source
        if body is not None and body.horizons is not None:
            params["horizons"] = body.horizons
        if manager.active_run_id is not None:
            return json_error(409, "busy", active_run_id=manager.active_run_id)
        try:
            run_id = manager.start("stock_analysis", params)
        except ParamError as exc:
            return json_error(422, exc.code, message=str(exc))
        except BusyError as exc:
            return json_error(409, "busy", active_run_id=exc.active)
        except RunError as exc:
            return json_error(422, "run_error", message=str(exc))
        return JSONResponse(
            {
                "run_id": run_id,
                "pipeline": "stock_analysis",
                "cli": f"vnstratlab stock {ticker.strip().upper()}",
            },
            status_code=202,
        )

    @app.get("/api/stocks/{ticker}/analysis", response_model=None)
    def get_analysis(ticker: str, source: str | None = None) -> Any:
        resolved = resolve(source)
        if isinstance(resolved, JSONResponse):
            return resolved
        _cfg, name = resolved
        found = guarded(lambda: load_latest(paths, name, ticker))
        if isinstance(found, JSONResponse):
            return found
        if found is None:
            return json_error(
                404,
                "no_analysis",
                ticker=ticker.upper(),
                source=name,
                label=data_label(name),
                disclaimer_vi=DISCLAIMER_VI,
            )
        return found
