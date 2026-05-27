from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import adb_path
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.timeouts import run_with_timeout


def screenshot(ctx: CommandContext, out: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        device = connect_device(ctx.serial, ctx.timeout_ms)
    except BaseException:
        device = None

    def _run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        result: Any = None
        width = None
        height = None
        try:
            if device is None:
                raise RuntimeError("uiautomator2 connection unavailable")
            result = device.screenshot(str(path))
        except BaseException as exc:
            try:
                _adb_screencap(ctx, path)
            except BaseException as adb_exc:
                raise U2CliError(
                    ErrorCode.SCREENSHOT_FAILED,
                    "Failed to capture screenshot",
                    {"path": str(path), "error": str(exc), "adbError": str(adb_exc)},
                ) from adb_exc
        if not path.exists():
            if hasattr(result, "save"):
                try:
                    result.save(str(path))
                except BaseException as exc:
                    raise U2CliError(
                        ErrorCode.SCREENSHOT_FAILED,
                        "Failed to save screenshot",
                        {"path": str(path), "error": str(exc)},
                    ) from exc
            else:
                raise U2CliError(
                    ErrorCode.SCREENSHOT_FAILED,
                    "Screenshot command did not create output file",
                    {"path": str(path)},
                )
        size = os.path.getsize(path)
        if result is not None:
            width = getattr(result, "width", None)
            height = getattr(result, "height", None)
        data = {"path": str(path), "width": width, "height": height, "bytes": size}
        artifacts = [{"type": "screenshot", "path": str(path), "sizeBytes": size}]
        return data, artifacts

    return run_with_timeout(_run, ctx.timeout_ms)


def _adb_screencap(ctx: CommandContext, path: Path) -> None:
    executable = adb_path()
    if executable is None:
        raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")
    command = [executable]
    if ctx.serial:
        command.extend(["-s", ctx.serial])
    command.extend(["exec-out", "screencap", "-p"])
    with path.open("wb") as handle:
        proc = subprocess.run(
            command,
            check=False,
            stdout=handle,
            stderr=subprocess.PIPE,
            timeout=ctx.timeout_ms / 1000,
        )
    if proc.returncode != 0:
        raise U2CliError(
            ErrorCode.SCREENSHOT_FAILED,
            "adb screencap failed",
            {
                "path": str(path),
                "exitCode": proc.returncode,
                "stderr": proc.stderr.decode(errors="replace"),
            },
        )
