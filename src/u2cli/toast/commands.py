from __future__ import annotations

import time
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.timeouts import run_with_timeout


def get(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        getter = getattr(device, "toast", None)
        message = None
        if getter is not None and hasattr(getter, "get_message"):
            message = getter.get_message(ctx.timeout_ms / 1000, default=None)
        elif hasattr(device, "toast_get_message"):
            message = device.toast_get_message(ctx.timeout_ms / 1000, default=None)
        if not message:
            raise U2CliError(
                ErrorCode.TOAST_TIMEOUT,
                "No toast message was observed before timeout",
                {"timeoutMs": ctx.timeout_ms},
            )
        return {"message": message, "timestamp": int(time.time() * 1000), "timeoutHit": False}

    return run_with_timeout(_run, ctx.timeout_ms + 100)


def reset(ctx: CommandContext) -> dict[str, bool]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, bool]:
        toast = getattr(device, "toast", None)
        if toast is not None and hasattr(toast, "reset"):
            toast.reset()
        elif hasattr(device, "toast_reset"):
            device.toast_reset()
        return {"reset": True}

    return run_with_timeout(_run, ctx.timeout_ms)
