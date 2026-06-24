from __future__ import annotations

from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.device.connect import connect_device
from androidtestclii.timeouts import run_with_timeout


def size(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        info = dict(getattr(device, "info", {}) or {})
        raw_display = info.get("display")
        display = raw_display if isinstance(raw_display, dict) else {}
        width = info.get("displayWidth") or display.get("width") or info.get("width")
        height = info.get("displayHeight") or display.get("height") or info.get("height")
        density = info.get("displayDensity") or display.get("density") or info.get("density")
        if (width is None or height is None) and hasattr(device, "window_size"):
            width, height = device.window_size()
        return {"width": width, "height": height, "density": density}

    return run_with_timeout(_run, ctx.timeout_ms)
