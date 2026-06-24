from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from androidtestclii.branding import SLUG
from androidtestclii.context import CommandContext
from androidtestclii.device.connect import connect_device
from androidtestclii.device.connect import adb_path
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.locks import serial_lock
from androidtestclii.screen.snapshot_backend import adb_failure
from androidtestclii.screen.snapshot_backend import AdbResult
from androidtestclii.screen.snapshot_backend import run_adb
from androidtestclii.timeouts import run_with_timeout


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
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.set_orientation(value)
                return {"orientation": value, "set": True}
            except AttributeError:
                if device is None:
                    _adb_set_orientation(ctx, value)
                    return {"orientation": value, "set": True, "via": "adb"}
                setattr(device, "orientation", value)
                return {"orientation": value, "set": True}
            except BaseException:
                _adb_set_orientation(ctx, value)
                return {"orientation": value, "set": True, "via": "adb"}

        return run_with_timeout(_run, ctx.timeout_ms)


def _adb_set_orientation(ctx: CommandContext, value: str) -> None:
    rotation = {
        "natural": "0",
        "left": "1",
        "upsidedown": "2",
        "right": "3",
    }[value]
    run_adb(ctx.serial, ["shell", "settings", "put", "system", "accelerometer_rotation", "0"], timeout_ms=ctx.timeout_ms)
    run_adb(ctx.serial, ["shell", "settings", "put", "system", "user_rotation", rotation], timeout_ms=ctx.timeout_ms)


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
                try:
                    run_adb(
                        ctx.serial,
                        ["shell", "cmd", "statusbar", "collapse"],
                        timeout_ms=ctx.timeout_ms,
                    )
                except BaseException:
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
        def _run() -> dict[str, Any]:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            remote = f"/sdcard/{SLUG}-record.mp4"
            recorded_with_u2 = False
            try:
                device = connect_device(ctx.serial, ctx.timeout_ms)
            except BaseException:
                device = None
            try:
                screenrecord = getattr(device, "screenrecord") if device is not None else None
            except (AttributeError, ImportError, ModuleNotFoundError):
                screenrecord = None
            if callable(screenrecord):
                try:
                    screenrecord(out, duration=duration_sec)
                    recorded_with_u2 = True
                except (ImportError, ModuleNotFoundError):
                    recorded_with_u2 = False
                except BaseException:
                    recorded_with_u2 = False
            if not recorded_with_u2:
                result = run_adb(
                    ctx.serial,
                    ["shell", "screenrecord", "--time-limit", str(duration_sec), remote],
                    timeout_ms=max(ctx.timeout_ms, (duration_sec + 5) * 1000),
                    allow_failure=True,
                )
                if result.exit_code == 0:
                    run_adb(
                        ctx.serial,
                        ["pull", remote, out],
                        timeout_ms=ctx.timeout_ms,
                    )
                    run_adb(
                        ctx.serial,
                        ["shell", "rm", "-f", remote],
                        timeout_ms=ctx.timeout_ms,
                        allow_failure=True,
                    )
                elif _screenrecord_missing(result):
                    _record_with_screencap(ctx, out, duration_sec)
                else:
                    raise adb_failure("adb screenrecord failed", result)
            return {"path": out, "durationSec": duration_sec, "recorded": True}

        return run_with_timeout(_run, max(ctx.timeout_ms, (duration_sec + 10) * 1000))


def _screenrecord_missing(result: AdbResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return result.exit_code == 127 or "not found" in text or "inaccessible" in text


def _record_with_screencap(ctx: CommandContext, out: str, duration_sec: int) -> None:
    executable = adb_path()
    ffmpeg = shutil.which("ffmpeg")
    if executable is None:
        raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")
    if ffmpeg is None:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "screenrecord is unavailable on the device and ffmpeg was not found",
            {"path": out},
        )
    fps = 2
    frame_count = max(1, duration_sec * fps)
    with tempfile.TemporaryDirectory(prefix=f"{SLUG}-record-") as tmp:
        tmp_dir = Path(tmp)
        for index in range(frame_count):
            command = [executable]
            if ctx.serial:
                command.extend(["-s", ctx.serial])
            command.extend(["exec-out", "screencap", "-p"])
            frame = tmp_dir / f"frame-{index:04d}.png"
            with frame.open("wb") as handle:
                screencap_proc = subprocess.run(
                    command,
                    check=False,
                    stdout=handle,
                    stderr=subprocess.PIPE,
                    timeout=max(5, ctx.timeout_ms / 1000),
                )
            if screencap_proc.returncode != 0:
                raise U2CliError(
                    ErrorCode.ACTION_FAILED,
                    "adb screencap failed while recording",
                    {
                        "exitCode": screencap_proc.returncode,
                        "stderr": screencap_proc.stderr.decode(errors="replace"),
                    },
                )
            if index < frame_count - 1:
                time.sleep(1 / fps)
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(tmp_dir / "frame-%04d.png"),
                "-t",
                str(duration_sec),
                "-pix_fmt",
                "yuv420p",
                out,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(10, duration_sec + 10),
        )
    if proc.returncode != 0:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "ffmpeg failed while encoding screencap recording",
            {"exitCode": proc.returncode, "stderr": proc.stderr},
        )
