"""The packaged pipelines (ids are fixed: the Console UI uses them).

- ``demo``: ingest -> rebuild -> features -> strategies -> simulate -> report on the synthetic
  market (the stages of ``vnstratlab.demo``; nothing touches the user's stores or trial registry).
- ``refresh``: ingest -> rebuild -> features on the configured source (real data).
- ``ingest``, ``rebuild``, ``features``: one task each.
- ``backtest_all``: features (check only, never ingests or builds) -> backtest (walk-forward of the
  registered trials, results in ``lab.duckdb``) -> report. Parameters: ``source``, ``strategy``,
  ``modes``, ``register``, ``start``, ``end``; all optional.

Heavy imports (pandas, duckdb) happen inside the task functions, so importing this module is cheap.
"""

from __future__ import annotations

import importlib.util
import tempfile
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vnstratlab.config.loader import load_config
from vnstratlab.paths import get_paths
from vnstratlab.runs.core import Pipeline, RunContext, RunError, Task

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig
    from vnstratlab.demo import DemoState

# Pipelines that read from the configured (real) source: the ones that may need its terms.
SOURCE_PIPELINES = ("refresh", "ingest")


def _as_date(value: object, default: date) -> date:
    if value is None:
        return default
    return value if isinstance(value, date) else date.fromisoformat(str(value))


# ------------------------------------------------------------------ demo tasks


def _demo_state(ctx: RunContext) -> DemoState:
    state: DemoState = ctx.state["demo"]
    return state


def _demo_ingest(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab import demo

    tmp = ctx.exit_stack.enter_context(
        tempfile.TemporaryDirectory(prefix="vnstratlab-demo-", ignore_cleanup_errors=True)
    )
    out = ctx.params.get("out_dir")
    ctx.state["demo"] = demo.new_state(
        Path(tmp),
        _as_date(ctx.params.get("start"), demo.DEMO_START),
        _as_date(ctx.params.get("end"), demo.DEMO_END),
        out_dir=Path(out) if out else None,
        artifact_dir=ctx.run_dir / "demo",
    )
    ctx.note("ingest, rebuild and features on the synthetic market")
    return demo.stage_ingest(_demo_state(ctx))


def _demo_rebuild(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab import demo

    return demo.stage_rebuild(_demo_state(ctx))


def _demo_features(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab import demo

    return demo.stage_features(_demo_state(ctx))


def _demo_strategies(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab import demo

    return demo.stage_strategies(_demo_state(ctx))


def _demo_simulate(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab import demo

    return demo.stage_simulate(_demo_state(ctx), ctx.note)


def _demo_report(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab import demo

    return demo.stage_report(_demo_state(ctx))


# ------------------------------------------------------------------ real-source tasks


def _config(ctx: RunContext) -> AppConfig:
    return load_config(ctx.home)


def _real_ingest(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab.data.pipeline import VN_TZ, default_start, terms_accepted, utc_now
    from vnstratlab.data.pipeline import ingest as ingest_data
    from vnstratlab.data.protocol import SourceError, get_source

    cfg = _config(ctx)
    paths = get_paths(ctx.home)
    name = cfg.data.source
    adapter = get_source(name, cfg)
    module = getattr(adapter, "required_module", None)
    extra = adapter.info.requires_extra
    if module is not None and extra is not None and importlib.util.find_spec(module) is None:
        raise SourceError(f'{name} adapter needs: pip install "vnstratlab[{extra}]"')
    if not terms_accepted(paths, adapter):
        raise SourceError(f"the terms of source {name!r} were not accepted")
    end = utc_now().astimezone(VN_TZ).date()
    start = default_start(cfg, paths, adapter)
    if start > end:
        ctx.note(f"{name}: up to date (latest stored session is on or after {end})")
        return {"source": name, "up_to_date": True}
    ctx.note(f"ingest {name} {start} .. {end}")
    report = ingest_data(cfg, paths, adapter, start, end)
    for warning in report.warnings:
        ctx.note(f"warning: {warning}")
    if report.status in ("failed_dq", "partial"):
        detail = "; ".join(f"{t}: {m}" for t, m in sorted(report.failed.items()))
        raise SourceError(f"ingest finished with status {report.status} {detail}".rstrip())
    return {
        "source": name,
        "status": report.status,
        "rows_in": report.rows_in,
        "rows_written": report.rows_written,
        "rows_changed": report.rows_changed,
        "rows_dropped": report.rows_dropped,
    }


def _open_store(ctx: RunContext, cfg: AppConfig) -> Any:
    from vnstratlab.data.protocol import SourceError
    from vnstratlab.data.store import MarketStore, kind_of_source

    name = cfg.data.source
    db_path = get_paths(ctx.home).market_db_for(kind_of_source(name))
    if not db_path.is_file():
        raise SourceError(f"no store at {db_path}: run the ingest task first")
    return MarketStore(db_path, kind_of_source(name))


def _real_rebuild(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab.data.pipeline import rebuild
    from vnstratlab.data.protocol import TickTable

    cfg = _config(ctx)
    with _open_store(ctx, cfg) as store:
        report = rebuild(store, cfg.data.source, TickTable.from_config(cfg))
    for warning in report.warnings:
        ctx.note(f"warning: {warning}")
    return {
        "source": cfg.data.source,
        "price_rows": report.price_rows,
        "adjusted_rows": report.adjusted_rows,
        "exec_rows": report.exec_rows,
        "excluded_tickers": len(report.excluded_tickers),
    }


def _real_features(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab.data.protocol import universe_tickers
    from vnstratlab.features.build import build_features

    cfg = _config(ctx)
    with _open_store(ctx, cfg) as store:
        report = build_features(store, cfg.data.source, universe_tickers(cfg))
    for warning in report.warnings:
        ctx.note(f"warning: {warning}")
    return {
        "source": cfg.data.source,
        "rows": report.rows,
        "feature_version": report.feature_version,
    }


# ------------------------------------------------------------------ backtest tasks


def _bt_source(ctx: RunContext) -> str:
    given = ctx.params.get("source")
    return str(given) if given else _config(ctx).data.source


def _bt_features(ctx: RunContext) -> Mapping[str, Any]:
    """Check only: the features of the source are built. Never ingests, rebuilds or builds."""
    from vnstratlab.data.protocol import SourceError
    from vnstratlab.data.store import MarketStore, kind_of_source
    from vnstratlab.lab.trials import TrialError, store_feature_version

    source = _bt_source(ctx)
    db_path = get_paths(ctx.home).market_db_for(kind_of_source(source))
    if not db_path.is_file():
        raise SourceError(f"no store at {db_path}: run the refresh pipeline first")
    with MarketStore(db_path, kind_of_source(source), read_only=True) as store:
        try:
            version = store_feature_version(store)
        except TrialError as exc:
            raise SourceError(f"{exc} (run the refresh pipeline)") from None
    ctx.note(f"features of {source} are built (version {version})")
    return {"source": source, "feature_version": version}


def _bt_backtest(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab.lab.walkforward import run_backtest

    modes = str(ctx.params.get("modes") or "both")
    result = run_backtest(
        _config(ctx),
        get_paths(ctx.home),
        source=_bt_source(ctx),
        strategy_id=ctx.params.get("strategy") or None,
        modes=("ideal", "executable") if modes == "both" else (modes,),
        register=bool(ctx.params.get("register", False)),
        run_id=ctx.run_dir.name,
        start=_opt_date(ctx.params.get("start")),
        end=_opt_date(ctx.params.get("end")),
        progress=ctx.note,
    )
    ctx.state["backtest"] = result
    return {
        "source": result.source,
        "trials": len(result.trials),
        "registered_now": len(result.registered_now),
        "rows_written": result.rows_written,
    }


def _bt_report(ctx: RunContext) -> Mapping[str, Any]:
    from vnstratlab.lab.walkforward import load_summary

    result = ctx.state["backtest"]
    summary = load_summary(get_paths(ctx.home), result.source, result.trials, result.modes)
    ctx.state["backtest_summary"] = summary
    out = ctx.run_dir / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "summary.csv", index=False, lineterminator="\n")
    ctx.note(result.label)
    return {"source": result.source, "trials": len(result.trials), "summary_rows": len(summary)}


def _opt_date(value: object) -> date | None:
    return None if value is None else _as_date(value, date.min)


# ------------------------------------------------------------------ registry

_INGEST = Task("ingest", "Tải dữ liệu", _real_ingest)
_REBUILD = Task("rebuild", "Dựng lại chuỗi giá", _real_rebuild, ("ingest",))
_FEATURES = Task("features", "Tính đặc trưng", _real_features, ("rebuild",))


def _build() -> dict[str, Pipeline]:
    demo = Pipeline(
        "demo",
        "Chạy thử trên dữ liệu giả lập",
        (
            Task("ingest", "Nạp dữ liệu giả lập", _demo_ingest),
            Task("rebuild", "Dựng lại chuỗi giá", _demo_rebuild, ("ingest",)),
            Task("features", "Tính đặc trưng", _demo_features, ("rebuild",)),
            Task("strategies", "Tính danh mục mục tiêu", _demo_strategies, ("features",)),
            Task("simulate", "Mô phỏng giao dịch", _demo_simulate, ("strategies",)),
            Task("report", "Lập báo cáo", _demo_report, ("simulate",)),
        ),
    )
    refresh = Pipeline(
        "refresh",
        "Cập nhật dữ liệu thật",
        (
            _INGEST,
            _REBUILD,
            _FEATURES,
        ),
    )
    backtest_all = Pipeline(
        "backtest_all",
        "Chạy backtest walk-forward",
        (
            Task("features", "Kiểm tra đặc trưng", _bt_features),
            Task("backtest", "Chạy walk-forward", _bt_backtest, ("features",)),
            Task("report", "Lập báo cáo", _bt_report, ("backtest",)),
        ),
    )
    return {
        "demo": demo,
        "refresh": refresh,
        "backtest_all": backtest_all,
        "ingest": Pipeline("ingest", "Tải dữ liệu", (Task("ingest", "Tải dữ liệu", _real_ingest),)),
        "rebuild": Pipeline(
            "rebuild", "Dựng lại chuỗi giá", (Task("rebuild", "Dựng lại chuỗi giá", _real_rebuild),)
        ),
        "features": Pipeline(
            "features", "Tính đặc trưng", (Task("features", "Tính đặc trưng", _real_features),)
        ),
    }


PIPELINES: dict[str, Pipeline] = _build()


def get_pipeline(pipeline_id: str) -> Pipeline:
    try:
        return PIPELINES[pipeline_id]
    except KeyError:
        raise RunError(
            f"unknown pipeline {pipeline_id!r}; available: {', '.join(PIPELINES)}"
        ) from None
