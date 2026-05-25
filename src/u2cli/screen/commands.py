from __future__ import annotations

from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.locks import serial_lock
from u2cli.timeouts import run_with_timeout


ORIENTATION_VALUES = {"natural", "left", "right", "upsidedown"}


def orientation_get(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        value = getattr(device, "orientation", None)
        if callable(value):
            value = value()
        return {"orientation": value}

    return run_with_timeout(_run, ctx.timeout_ms)


def orientation_set(ctx: CommandContext, value: str) -> dict[str, Any]:
    if value not in ORIENTATION_VALUES:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "invalid orientation",
            {"value": value, "allowed": sorted(ORIENTATION_VALUES)},
        )
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            try:
                device.set_orientation(value)
            except AttributeError:
                setattr(device, "orientation", value)
            return {"orientation": value, "set": True}

        return run_with_timeout(_run, ctx.timeout_ms)


def wake(ctx: CommandContext) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)
        run_with_timeout(lambda: device.screen_on(), ctx.timeout_ms)
    return {"awake": True}


def sleep(ctx: CommandContext) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)
        run_with_timeout(lambda: device.screen_off(), ctx.timeout_ms)
    return {"sleeping": True}


def unlock(ctx: CommandContext) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> None:
            if hasattr(device, "unlock"):
                device.unlock()
            else:
                device.shell("input keyevent 82")

        run_with_timeout(_run, ctx.timeout_ms)
    return {"unlocked": True}


def notification(ctx: CommandContext, action: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> None:
            if action == "open":
                if hasattr(device, "open_notification"):
                    device.open_notification()
                else:
                    device.shell("cmd statusbar expand-notifications")
            elif action == "quick-settings":
                if hasattr(device, "open_quick_settings"):
                    device.open_quick_settings()
                else:
                    device.shell("cmd statusbar expand-settings")
            elif action == "close":
                if hasattr(device, "press"):
                    device.press("back")
                else:
                    device.shell("cmd statusbar collapse")
            else:
                raise U2CliError(
                    ErrorCode.INVALID_ARGUMENT,
                    "invalid notification action",
                    {"action": action},
                )

        run_with_timeout(_run, ctx.timeout_ms)
    return {"action": action, "done": True}


def record(ctx: CommandContext, out: str, duration_sec: int = 10) -> dict[str, Any]:
    if duration_sec <= 0 or duration_sec > 180:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--duration-sec must be between 1 and 180",
            {"durationSec": duration_sec},
        )
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            if hasattr(device, "screenrecord"):
                device.screenrecord(out, duration=duration_sec)
            else:
                device.shell(f"screenrecord --time-limit {duration_sec} /sdcard/u2cli-record.mp4")
                if hasattr(device, "pull"):
                    device.pull("/sdcard/u2cli-record.mp4", out)
            return {"path": out, "durationSec": duration_sec, "recorded": True}

        return run_with_timeout(_run, ctx.timeout_ms)
