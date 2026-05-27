from __future__ import annotations

import time
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.screen.snapshot_backend import (
    SnapshotBackendOptions,
    capture_with_helper,
    resolve_snapshot_helper,
)
from u2cli.timeouts import run_with_timeout


def get(ctx: CommandContext) -> dict[str, Any]:
    artifact = resolve_snapshot_helper(None)
    if artifact is not None:
        deadline = time.monotonic() + (ctx.timeout_ms / 1000)
        options = SnapshotBackendOptions(
            backend="helper",
            snapshot_timeout_ms=min(ctx.timeout_ms, 1000),
        )

        def _helper_run() -> dict[str, Any]:
            attempt_options = options
            toast: Any = None
            while True:
                capture = capture_with_helper(
                    ctx.serial,
                    artifact,
                    attempt_options,
                    action="toast-get",
                )
                toast = capture.metadata.get("toastCapture")
                latest = toast.get("latest") if isinstance(toast, dict) else None
                if isinstance(latest, dict) and latest.get("text"):
                    return {
                        "message": latest["text"],
                        "timestamp": latest.get("capturedAtMs") or int(time.time() * 1000),
                        "timeoutHit": False,
                        "toastCapture": toast,
                        "via": "android-snapshot-helper",
                    }
                if time.monotonic() >= deadline:
                    break
                attempt_options = SnapshotBackendOptions(
                    backend="helper",
                    helper_install_policy="never",
                    snapshot_timeout_ms=min(ctx.timeout_ms, 1000),
                )
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
            raise U2CliError(
                ErrorCode.TOAST_TIMEOUT,
                "No toast message was observed before timeout",
                {"timeoutMs": ctx.timeout_ms, "toastCapture": toast},
            )

        return run_with_timeout(_helper_run, ctx.timeout_ms + 1000)

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
        return {
            "message": message,
            "timestamp": int(time.time() * 1000),
            "timeoutHit": False,
            "via": "uiautomator2",
        }

    return run_with_timeout(_run, ctx.timeout_ms + 100)


def reset(ctx: CommandContext) -> dict[str, bool]:
    artifact = resolve_snapshot_helper(None)
    if artifact is not None:
        options = SnapshotBackendOptions(backend="helper", snapshot_timeout_ms=ctx.timeout_ms)

        def _helper_run() -> dict[str, bool]:
            capture_with_helper(
                ctx.serial,
                artifact,
                options,
                action="toast-clear",
            )
            return {"reset": True}

        return run_with_timeout(_helper_run, ctx.timeout_ms + 1000)

    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, bool]:
        toast = getattr(device, "toast", None)
        if toast is not None and hasattr(toast, "reset"):
            toast.reset()
        elif hasattr(device, "toast_reset"):
            device.toast_reset()
        return {"reset": True}

    return run_with_timeout(_run, ctx.timeout_ms)
