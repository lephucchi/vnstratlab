"""Console v2: a built-in terminal that runs ``vnstratlab`` commands (card X-console-api).

Only ``vnstratlab`` subcommands run: the child is ``[sys.executable, "-m", "vnstratlab", *args]``
with ``shell=False`` and ``stdin=DEVNULL``, so a typed line is split into arguments (``shlex``) and
never reaches a shell; ``;``, ``&&``, ``|`` and ``$(...)`` stay literal arguments. ``serve`` is
refused (it would recurse) and ``init`` needs ``--yes`` (it prompts). Every command is a run of the
pipeline ``cli`` with one task ``cli`` whose output goes to ``cli.log``. The environment is passed
to the child but never read or echoed by this module, so no secret reaches a response.
"""

from __future__ import annotations

import contextlib
import difflib
import enum
import os
import shlex
import subprocess
import sys
import threading
import typing
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vnstratlab.app.api_config import json_error
from vnstratlab.config.loader import ConfigError, load_config
from vnstratlab.paths import AppPaths
from vnstratlab.runs import BusyError, Pipeline, RunContext, RunManager, Task, create_run
from vnstratlab.runs.core import PARENT_ENV, execute_run

CLI_TIMEOUT_S = 30 * 60
TERMS_FLAG = "--accept-source-terms"
PROGRAM = "vnstratlab"
_NOT_ALLOWED = {
    "serve": "Không thể chạy `serve` trong terminal của Console (sẽ tự khởi động lại chính nó).",
}
# the command line equivalent to each pipeline the UI can start (None when there is no single one)
PIPELINE_CLI = {
    "demo": "vnstratlab demo",
    "ingest": "vnstratlab ingest",
    "rebuild": "vnstratlab data rebuild",
    "features": "vnstratlab features build",
    "backtest_all": "vnstratlab backtest --all",
    "refresh": "vnstratlab ingest && vnstratlab data rebuild && vnstratlab features build",
}

Launcher = Callable[[list[str]], list[str]]


class CliBody(BaseModel):
    command: str
    accept_terms: bool = False


class CommandError(Exception):
    """A typed line is refused: ``response`` is what the API returns."""

    def __init__(self, response: JSONResponse) -> None:
        super().__init__("command refused")
        self.response = response


class CliFailedError(RuntimeError):
    def __init__(self, message: str, summary: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.summary = dict(summary)


# ------------------------------------------------------------------ introspection


def click_root() -> Any:
    # typer 0.29 ships its own click classes, so the command tree is walked by duck typing
    import typer.main

    from vnstratlab.cli import app as typer_app

    return typer.main.get_command(typer_app)


def _is_group(node: Any) -> bool:
    return hasattr(node, "commands")


def _annotation(param: Any) -> Any:
    """The Python type of an option (Typer keeps it on ``type_descriptor``; older click on
    ``type``), without ``None`` for an optional one."""
    ann = getattr(getattr(param, "type_descriptor", None), "annotation", None)
    for arg in typing.get_args(ann) or (ann,):
        if arg is not type(None) and arg is not None:
            return arg
    return None


def _choices(param: Any) -> list[str] | None:
    ann = _annotation(param)
    if isinstance(ann, type) and issubclass(ann, enum.Enum):
        return [str(m.value) for m in ann]
    old = getattr(getattr(param, "type", None), "choices", None)
    return [str(c) for c in old] if old is not None else None


def _option_type(param: Any) -> str:
    ann = _annotation(param)
    if _choices(param) is not None:
        return "choice"
    if getattr(param, "is_flag", False) or ann is bool:
        return "bool"
    if ann is int or getattr(getattr(param, "type", None), "name", "") == "integer":
        return "int"
    return "str"


def _is_option(param: Any) -> bool:
    return getattr(param, "param_type_name", "") == "option"


def _leaf_options(command: Any) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for param in command.params:
        if not _is_option(param) or getattr(param, "hidden", False) or "--help" in param.opts:
            continue
        name = next((o for o in [*param.opts, *param.secondary_opts] if o.startswith("--")), "")
        item: dict[str, Any] = {
            "name": name or param.opts[0],
            "type": _option_type(param),
            "help": (param.help or "").strip(),
            "required": bool(param.required),
        }
        choices = _choices(param)
        if choices is not None:
            item["choices"] = choices
        options.append(item)
    return options


def _walk(group: Any, prefix: list[str]) -> list[tuple[list[str], Any]]:
    found: list[tuple[list[str], Any]] = []
    for name in sorted(group.commands):
        command = group.commands[name]
        if getattr(command, "hidden", False):
            continue
        if _is_group(command):
            found.extend(_walk(command, [*prefix, name]))
            if command.invoke_without_command:
                found.append(([*prefix, name], command))
        else:
            found.append(([*prefix, name], command))
    return found


def list_commands() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path, command in _walk(click_root(), []):
        item: dict[str, Any] = {
            "path": path,
            "help": ((command.help or command.short_help or "").strip().splitlines() or [""])[0],
            "options": _leaf_options(command),
            "allowed": path[0] not in _NOT_ALLOWED,
        }
        if path[0] in _NOT_ALLOWED:
            item["reason_vi"] = _NOT_ALLOWED[path[0]]
        elif path == ["init"]:
            item["reason_vi"] = "Cần thêm --yes: terminal không có bàn phím để trả lời câu hỏi."
        out.append(item)
    return out


def resolve(tokens: list[str]) -> tuple[list[str], Any]:
    """The command path at the start of ``tokens`` and its click command. Raises ``CommandError``
    for an unknown command. Options (tokens starting with ``-``) are left to the command."""
    node = click_root()
    path: list[str] = []
    for token in tokens:
        if not _is_group(node) or token.startswith("-"):
            break
        child = node.commands.get(token)
        if child is None:
            known = sorted(node.commands)
            raise CommandError(
                json_error(
                    422,
                    "unknown_command",
                    message=f"unknown command {token!r}",
                    suggestions=difflib.get_close_matches(token, known, n=3, cutoff=0.4) or known,
                )
            )
        node = child
        path.append(token)
    return path, node


# ------------------------------------------------------------------ parsing and checks


def parse_line(text: str) -> list[str]:
    """The arguments after ``vnstratlab`` for a typed line (an optional leading ``vnstratlab``)."""
    if not text.strip():
        raise CommandError(json_error(422, "empty_command", message="type a command"))
    if "\n" in text or "\r" in text or "\x00" in text:
        raise CommandError(json_error(422, "bad_command", message="one line only"))
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError as exc:
        raise CommandError(json_error(422, "bad_command", message=str(exc))) from None
    if tokens and tokens[0] == PROGRAM:
        tokens = tokens[1:]
    if not tokens:
        raise CommandError(json_error(422, "empty_command", message="type a command"))
    return tokens


def _source_arg(args: list[str]) -> str | None:
    for i, arg in enumerate(args):
        if arg == "--source" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--source="):
            return arg.split("=", 1)[1]
    return None


def check_allowed(path: list[str], args: list[str]) -> None:
    if path and path[0] in _NOT_ALLOWED:
        raise CommandError(
            json_error(422, "not_allowed", reason_vi=_NOT_ALLOWED[path[0]], command=path[0])
        )
    if path == ["init"] and "--yes" not in args:
        raise CommandError(
            json_error(
                422,
                "not_allowed",
                reason_vi="`init` cần --yes: terminal không có bàn phím để trả lời câu hỏi.",
                command="init",
            )
        )
    if any(a.startswith("--install-completion") or a.startswith("--show-completion") for a in args):
        raise CommandError(
            json_error(422, "not_allowed", reason_vi="Không hỗ trợ cài completion.", command="")
        )


def apply_terms_gate(paths: AppPaths, command: Any, args: list[str], accept: bool) -> list[str]:
    """For a command that takes ``--accept-source-terms``: 409 until the source's terms are
    accepted (by an earlier run, ``accept_terms`` or the typed flag); with ``accept`` the flag
    is appended."""
    from vnstratlab.data.pipeline import terms_accepted, terms_notice
    from vnstratlab.data.protocol import SourceError, get_source

    if not any(TERMS_FLAG in p.opts for p in command.params if _is_option(p)):
        return args
    if TERMS_FLAG in args:
        return args
    try:
        cfg = load_config(paths.home)
        adapter = get_source(_source_arg(args) or cfg.data.source, cfg)
    except (ConfigError, SourceError):
        return args  # the command itself reports the problem
    if terms_accepted(paths, adapter):
        return args
    if not accept:
        raise CommandError(
            json_error(
                409, "terms_required", source=adapter.info.name, notice=terms_notice(adapter)
            )
        )
    return [*args, TERMS_FLAG]


# ------------------------------------------------------------------ running


def _pump(stream: Any, path: Any) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as out:
        for raw in stream:
            out.write(raw.decode("utf-8", errors="replace").replace("\r\n", "\n"))
            out.flush()


def make_pipeline(command: str, launcher: Launcher | None) -> Pipeline:
    def run(ctx: RunContext) -> Mapping[str, Any]:
        args: list[str] = list(ctx.params["argv"])
        real = launcher(args) if launcher else [sys.executable, "-m", PROGRAM, *args]
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            PARENT_ENV: ctx.run_dir.name,
        }
        proc = subprocess.Popen(  # noqa: S603  (argv list, shell=False, vnstratlab only)
            real,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=ctx.home,
            env=env,
        )
        stream = proc.stdout
        if stream is None:  # pragma: no cover (stdout is always a pipe here)
            raise CliFailedError("no output pipe", {"command": command, "exit_code": None})
        reader = threading.Thread(target=_pump, args=(stream, ctx.run_dir / "cli.log"))
        reader.start()
        waited, stopped = 0.0, None
        while True:
            try:
                proc.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                waited += 0.1
            if ctx.cancel.is_set():
                stopped = "cancelled"
            elif waited >= CLI_TIMEOUT_S:
                stopped = "timeout"
            if stopped:
                proc.kill()
                proc.wait()
                break
        reader.join(timeout=10)
        summary = {"command": command, "exit_code": proc.returncode}
        if stopped:
            raise CliFailedError(stopped, summary)
        if proc.returncode != 0:
            raise CliFailedError(f"exit code {proc.returncode}", summary)
        return summary

    label = command if len(command) <= 120 else command[:117] + "..."
    return Pipeline("cli", "Lệnh tùy chọn", (Task("cli", label, run),))


class CliService:
    """Starts typed commands as runs; shared by ``POST /api/cli`` and rerun of a ``cli`` run."""

    def __init__(self, paths: AppPaths, manager: RunManager, launcher: Launcher | None) -> None:
        self.paths = paths
        self.manager = manager
        self.launcher = launcher

    def start(self, text: str, accept_terms: bool) -> JSONResponse:
        try:
            tokens = parse_line(text)
            path, command = resolve(tokens)
            args = tokens
            check_allowed(path, args)
            args = apply_terms_gate(self.paths, command, args, accept_terms)
        except CommandError as exc:
            return exc.response
        if self.manager.active_run_id is not None:
            return json_error(409, "busy", active_run_id=self.manager.active_run_id)
        line = shlex.join([PROGRAM, *tokens])
        pipeline = make_pipeline(line, self.launcher)
        params = {"command": text.strip(), "argv": args}
        try:
            run_id = create_run(self.paths.home, pipeline, params)
        except BusyError as exc:
            return json_error(409, "busy", active_run_id=exc.active)
        threading.Thread(
            target=self._run, args=(pipeline, run_id, params), name=f"cli-{run_id}", daemon=True
        ).start()
        return JSONResponse({"run_id": run_id, "argv": [PROGRAM, *args]}, status_code=202)

    def _run(self, pipeline: Pipeline, run_id: str, params: Mapping[str, Any]) -> None:
        with contextlib.suppress(BaseException):  # the failure is recorded in run.json
            execute_run(self.paths.home, pipeline, run_id, params)


def register(
    app: FastAPI, paths: AppPaths, manager: RunManager, launcher: Launcher | None = None
) -> CliService:
    service = CliService(paths, manager, launcher)

    @app.get("/api/cli/commands")
    def commands() -> dict[str, Any]:
        return {"commands": list_commands()}

    @app.post("/api/cli", response_model=None)
    def run_cli(body: CliBody) -> Any:
        return service.start(body.command, body.accept_terms)

    return service
