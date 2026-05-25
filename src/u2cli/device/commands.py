from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.locks import serial_lock
from u2cli.timeouts import run_with_timeout


def _shell_output(result: Any) -> str:
    return str(getattr(result, "output", result)).strip()


def _require_safe_shell(command: str) -> None:
    if any(token in command for token in [";", "&&", "||", "`", "$(", "\n", "\r"]):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "device shell accepts a single restricted command only",
            {"command": command},
        )


def shell(ctx: CommandContext, command: str) -> dict[str, Any]:
    _require_safe_shell(command)
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        result = device.shell(command)
        return {"command": command, "output": _shell_output(result)}

    return run_with_timeout(_run, ctx.timeout_ms)


def push(ctx: CommandContext, local: str, remote: str) -> dict[str, Any]:
    local_path = Path(local)
    if not local_path.exists():
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "local path does not exist", {"local": local})
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            if hasattr(device, "push"):
                device.push(str(local_path), remote)
            else:
                device.adb_device.sync.push(str(local_path), remote)
            return {
                "local": str(local_path),
                "remote": remote,
                "bytes": local_path.stat().st_size,
                "pushed": True,
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def pull(ctx: CommandContext, remote: str, local: str) -> dict[str, Any]:
    local_path = Path(local)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            if hasattr(device, "pull"):
                device.pull(remote, str(local_path))
            else:
                device.adb_device.sync.pull(remote, str(local_path))
            return {
                "remote": remote,
                "local": str(local_path),
                "bytes": local_path.stat().st_size if local_path.exists() else None,
                "pulled": True,
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def clipboard_get(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        getter = getattr(device, "clipboard", None)
        if callable(getter):
            text = getter()
        elif hasattr(device, "clipboard_get"):
            text = device.clipboard_get()
        else:
            text = _shell_output(device.shell("cmd clipboard get"))
        return {"text": text}

    return run_with_timeout(_run, ctx.timeout_ms)


def clipboard_set(ctx: CommandContext, text: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            setter = getattr(device, "set_clipboard", None) or getattr(
                device, "clipboard_set", None
            )
            if callable(setter):
                setter(text)
            else:
                device.shell(f"cmd clipboard set {shlex.quote(text)}")
            return {"text": text, "set": True}

        return run_with_timeout(_run, ctx.timeout_ms)


def logcat(ctx: CommandContext, lines: int = 200, clear: bool = False) -> dict[str, Any]:
    if lines <= 0 or lines > 5000:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--lines must be between 1 and 5000",
            {"lines": lines},
        )
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        if clear:
            output = _shell_output(device.shell("logcat -c"))
            return {"cleared": True, "lines": [], "output": output}
        output = _shell_output(device.shell(f"logcat -d -t {lines}"))
        return {"cleared": False, "lines": output.splitlines(), "count": len(output.splitlines())}

    return run_with_timeout(_run, ctx.timeout_ms)


def network(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        wifi = _shell_output(device.shell("cmd wifi status"))
        ip_addr = _shell_output(device.shell("ip addr"))
        return {"wifi": wifi, "ipAddr": ip_addr}

    return run_with_timeout(_run, ctx.timeout_ms)
