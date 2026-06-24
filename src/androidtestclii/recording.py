from __future__ import annotations

from pathlib import Path
from typing import Any

from androidtestclii.branding import SLUG
from androidtestclii.context import CommandContext
from androidtestclii.device.connect import connect_device
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.screen.snapshot_backend import adb_failure, run_adb
from androidtestclii.session.store import read_session, update_session, utc_now_iso


DEFAULT_RECORD_PATH = "artifacts/recording.mp4"
REMOTE_RECORD_PATH = f"/sdcard/{SLUG}-recording.mp4"


def start(
    ctx: CommandContext,
    path: str | None = None,
    *,
    fps: int | None = None,
    quality: int | None = None,
    hide_touches: bool = False,
) -> dict[str, Any]:
    target = Path(path or DEFAULT_RECORD_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        device = connect_device(ctx.serial, ctx.timeout_ms)
    except BaseException:
        device = None
    if device is not None:
        shell = getattr(device, "shell", None)
        if callable(shell):
            shell(f"screenrecord {REMOTE_RECORD_PATH}")
    else:
        args = ["shell", "screenrecord"]
        if hide_touches:
            args.append("--bugreport")
        args.append(REMOTE_RECORD_PATH)
        result = run_adb(ctx.serial, args, timeout_ms=ctx.timeout_ms, allow_failure=True)
        if result.exit_code != 0:
            raise adb_failure("adb screenrecord start failed", result)
    state = read_session()
    temporary = dict(state.temporary_automation)
    recording = {
        "path": str(target),
        "remotePath": REMOTE_RECORD_PATH,
        "serial": ctx.serial or state.serial,
        "startedAt": utc_now_iso(),
        "method": "android-screenrecord",
        "fps": fps,
        "quality": quality,
        "hideTouches": hide_touches,
    }
    temporary["recording"] = recording
    update_session(
        serial=ctx.serial or state.serial,
        timeout_ms=ctx.timeout_ms,
        temporary_automation=temporary,
    )
    return {
        "record": "started",
        "available": True,
        "method": "android-screenrecord",
        "path": str(target),
        "remotePath": REMOTE_RECORD_PATH,
        "fps": fps,
        "quality": quality,
        "hideTouches": hide_touches,
        "startedAt": recording["startedAt"],
    }


def stop(ctx: CommandContext, path: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = read_session()
    recording = state.temporary_automation.get("recording")
    if not isinstance(recording, dict) or not recording.get("remotePath"):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "no active recording; run record start first",
            {"recording": False},
        )
    target = Path(path or str(recording.get("path") or DEFAULT_RECORD_PATH))
    target.parent.mkdir(parents=True, exist_ok=True)
    remote = str(recording.get("remotePath") or REMOTE_RECORD_PATH)
    try:
        device = connect_device(ctx.serial or state.serial, ctx.timeout_ms)
    except BaseException:
        device = None
    pulled = False
    if device is not None:
        shell = getattr(device, "shell", None)
        if callable(shell):
            shell("pkill -l 2 screenrecord")
        pull_method = getattr(device, "pull", None)
        if callable(pull_method):
            pull_method(remote, str(target))
            pulled = True
        if callable(shell):
            shell(f"rm -f {remote}")
    if not pulled:
        run_adb(
            ctx.serial or state.serial,
            ["shell", "pkill", "-l", "2", "screenrecord"],
            timeout_ms=ctx.timeout_ms,
            allow_failure=True,
        )
        pull = run_adb(
            ctx.serial or state.serial,
            ["pull", remote, str(target)],
            timeout_ms=ctx.timeout_ms,
            allow_failure=True,
        )
        if pull.exit_code != 0:
            target.write_bytes(b"")
        run_adb(
            ctx.serial or state.serial,
            ["shell", "rm", "-f", remote],
            timeout_ms=ctx.timeout_ms,
            allow_failure=True,
        )
    temporary = dict(state.temporary_automation)
    temporary.pop("recording", None)
    update_session(
        serial=ctx.serial or state.serial,
        timeout_ms=ctx.timeout_ms,
        temporary_automation=temporary,
    )
    data = {
        "record": "stopped",
        "available": True,
        "method": "android-screenrecord",
        "path": str(target),
        "remotePath": remote,
        "bytes": target.stat().st_size if target.exists() else 0,
        "startedAt": recording.get("startedAt"),
    }
    artifacts = [
        {"type": "recording", "path": str(target), "description": "device screen recording"}
    ]
    return data, artifacts
