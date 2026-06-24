from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import Any

from androidtestclii.branding import SLUG
from androidtestclii.context import CommandContext
from androidtestclii.device.connect import connect_device
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.locks import serial_lock
from androidtestclii.session.store import read_session, update_session
from androidtestclii.timeouts import run_with_timeout


DEFAULT_LOG_PATH = f"artifacts/{SLUG}-logcat.log"
LOG_TAG = "AndroidTestClii"


def start(ctx: CommandContext, path: str | None = None, restart: bool = False) -> dict[str, Any]:
    target = str(Path(path or DEFAULT_LOG_PATH))
    marker = f"{SLUG}-log-start-{int(time.time() * 1000)}"
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            bulk_shell = False
            if restart:
                command = f"logcat -c && log -t {LOG_TAG} {shlex.quote(marker)}"
                try:
                    output = _shell_output(device.shell(command))
                    bulk_shell = True
                except BaseException:
                    _shell_output(device.shell("logcat -c"))
                    output = _shell_output(device.shell(f"log -t {LOG_TAG} {shlex.quote(marker)}"))
            else:
                output = _shell_output(device.shell(f"log -t {LOG_TAG} {shlex.quote(marker)}"))
            return {
                "action": "start",
                "available": True,
                "method": "android-logcat",
                "path": target,
                "restart": restart,
                "marker": marker,
                "bulkShell": bulk_shell,
                "output": output,
            }

        data = run_with_timeout(_run, ctx.timeout_ms)
    state = read_session()
    temporary = dict(state.temporary_automation)
    temporary["logCapture"] = {
        "path": target,
        "method": "android-logcat",
        "command": ["logcat", "-d", "-v", "brief"],
        "marker": marker,
        "startedAt": time.time(),
    }
    update_session(
        serial=ctx.serial,
        timeout_ms=ctx.timeout_ms,
        temporary_automation=temporary,
    )
    return data


def stop(ctx: CommandContext) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = read_session()
    capture = state.temporary_automation.get("logCapture")
    if not isinstance(capture, dict) or not capture.get("path"):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "logs stop requires an active log capture; run logs start first",
            {
                "failureStage": "logs-capture",
                "recoveryHint": "Run logs start before logs stop.",
            },
        )
    target = Path(str(capture["path"]))
    marker = capture.get("marker")
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        output = _shell_output(device.shell("logcat -d -v brief"))
        raw_line_count = len(output.splitlines())
        log_text, filtered = logs_after_marker(output, str(marker)) if marker else (output, False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(log_text, encoding="utf-8")
        captured_line_count = len(log_text.splitlines())
        temporary = dict(state.temporary_automation)
        temporary.pop("logCapture", None)
        update_session(
            serial=ctx.serial,
            timeout_ms=ctx.timeout_ms,
            temporary_automation=temporary,
        )
        data = {
            "action": "stop",
            "available": True,
            "method": str(capture.get("method") or "android-logcat"),
            "path": str(target),
            "bytes": target.stat().st_size,
            "filteredByMarker": filtered,
            "rawLineCount": raw_line_count,
            "capturedLineCount": captured_line_count,
        }
        artifacts = [{"type": "logs", "path": str(target), "description": "device logs"}]
        return data, artifacts

    return run_with_timeout(_run, ctx.timeout_ms)


def clear(ctx: CommandContext, restart: bool = False) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            output = _shell_output(device.shell("logcat -c"))
            return {
                "action": "clear",
                "available": True,
                "method": "android-logcat",
                "restart": restart,
                "output": output,
                "note": "Android logcat uses a system buffer; start is represented by a marker.",
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def mark(ctx: CommandContext, message: str | None = None) -> dict[str, Any]:
    text = message or f"{SLUG} mark"
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        output = _shell_output(device.shell(f"log -t {LOG_TAG} {shlex.quote(text)}"))
        return {
            "action": "mark",
            "available": True,
            "method": "android-logcat",
            "message": text,
            "output": output,
        }

    return run_with_timeout(_run, ctx.timeout_ms)


def path(ctx: CommandContext) -> dict[str, Any]:
    return diagnostics(ctx, "path")


def doctor(ctx: CommandContext) -> dict[str, Any]:
    data = diagnostics(ctx, "doctor")
    active = data.get("activeCapture")
    data["diagnostics"] = {
        "captureActive": active is not None,
        "activePath": active.get("path") if isinstance(active, dict) else None,
        "deviceRequired": True,
        "jsonOnlyStdout": True,
        "logSource": "logcat -d -v brief",
    }
    data["nextSteps"] = [
        "logs clear --restart",
        "logs mark <message>",
        "logs stop" if active else "logs start <path>",
        "network --include summary",
    ]
    return data


def diagnostics(ctx: CommandContext, action: str) -> dict[str, Any]:
    state = read_session()
    active = state.temporary_automation.get("logCapture")
    active_capture = active if isinstance(active, dict) else None
    return {
        "action": action,
        "available": True,
        "platform": "android",
        "serial": ctx.serial or state.serial,
        "method": "android-logcat",
        "defaultPath": DEFAULT_LOG_PATH,
        "activeCapture": active_capture,
        "commands": {
            "start": "logs start <path>",
            "stop": "logs stop",
            "clear": "logs clear --restart",
            "mark": "logs mark <message>",
            "read": "device logcat --lines 200",
        },
        "note": "Android logcat can be saved as a logs artifact with logs start/stop.",
    }


def logs_after_marker(raw: str, marker: str) -> tuple[str, bool]:
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        if marker in line:
            remaining = lines[index + 1 :]
            return "\n".join(remaining) + ("\n" if remaining else ""), True
    return raw, False


def _shell_output(result: Any) -> str:
    return str(getattr(result, "output", result)).strip()
