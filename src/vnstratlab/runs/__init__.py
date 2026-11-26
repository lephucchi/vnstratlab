"""Run registry: every pipeline the user starts is a run of tasks with a status and a log each
(P1-T27a). See ``vnstratlab.runs.core`` and ``vnstratlab.runs.pipelines``."""

from vnstratlab.runs.core import (
    KEEP_RUNS,
    BusyError,
    ParamError,
    Pipeline,
    RunContext,
    RunError,
    RunManager,
    RunResult,
    RunStore,
    Task,
    create_run,
    execute_run,
    run_inline,
    run_pipeline,
)
from vnstratlab.runs.pipelines import PIPELINES, SOURCE_PIPELINES, get_pipeline

__all__ = [
    "KEEP_RUNS",
    "PIPELINES",
    "SOURCE_PIPELINES",
    "BusyError",
    "ParamError",
    "Pipeline",
    "RunContext",
    "RunError",
    "RunManager",
    "RunResult",
    "RunStore",
    "Task",
    "create_run",
    "execute_run",
    "get_pipeline",
    "run_inline",
    "run_pipeline",
]
