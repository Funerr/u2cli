from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.timeouts import run_with_timeout


def screenshot(ctx: CommandContext, out: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = device.screenshot(str(path))
        except BaseException as exc:
            raise U2CliError(
                ErrorCode.SCREENSHOT_FAILED,
                "Failed to capture screenshot",
                {"path": str(path), "error": str(exc)},
            ) from exc
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
        width = getattr(result, "width", None)
        height = getattr(result, "height", None)
        data = {"path": str(path), "width": width, "height": height, "bytes": size}
        artifacts = [{"type": "screenshot", "path": str(path), "sizeBytes": size}]
        return data, artifacts

    return run_with_timeout(_run, ctx.timeout_ms)
