from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.device.connect import list_adb_devices
from androidtestclii.device.connect import connect_device
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.locks import serial_lock
from androidtestclii.session.store import update_session
from androidtestclii.timeouts import run_with_timeout


def settings(
    ctx: CommandContext,
    setting: str,
    state: str,
    target: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    if setting == "animations":
        value = _on_off_value(state, off_value="0", on_value="1")
        keys = [
            "window_animation_scale",
            "transition_animation_scale",
            "animator_duration_scale",
        ]
        readback = _write_read_global_settings(ctx, {key: value for key in keys})
        return {
            "setting": "animations",
            "state": state,
            "value": value,
            "verified": all(readback.get(key) == value for key in keys),
            "readback": readback,
            "verificationSource": "settings get global",
        }
    if setting in {"wifi", "airplane"}:
        value = _on_off_value(state, off_value="0", on_value="1")
        key = "wifi_on" if setting == "wifi" else "airplane_mode_on"
        readback = _write_read_global_settings(ctx, {key: value})
        return {
            "setting": setting,
            "state": state,
            "value": value,
            "verified": readback.get(key) == value,
            "readback": readback,
            "verificationSource": "settings get global",
        }
    if setting == "permission":
        if state not in {"grant", "revoke"}:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "settings permission state must be grant or revoke",
                {"setting": setting, "state": state},
            )
        if not target or not mode:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "settings permission requires package and permission",
                {"setting": setting, "target": target, "mode": mode},
            )
        permission_readback = _write_read_permission(ctx, state, target, mode)
        expected = state == "grant"
        return {
            "setting": "permission",
            "state": state,
            "target": target,
            "permission": mode,
            "verified": permission_readback.get("granted") is expected,
            "readback": permission_readback,
            "verificationSource": "dumpsys package",
        }
    raise U2CliError(
        ErrorCode.INVALID_ARGUMENT,
        "unsupported settings command",
        {
            "setting": setting,
            "state": state,
            "supported": ["animations", "wifi", "airplane", "permission"],
        },
    )


def push(ctx: CommandContext, package: str, payload_or_json: str) -> dict[str, Any]:
    payload = _load_payload(payload_or_json)
    action = str(payload.get("action") or f"{package}.PUSH")
    extras = {key: value for key, value in payload.items() if key != "action"}
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            args = ["am", "broadcast", "-a", action, "-p", package]
            for key, value in extras.items():
                args.extend(["--es", str(key), _extra_value(value)])
            output = _shell_output(device.shell(" ".join(shlex.quote(part) for part in args)))
            broadcast_result = parse_android_broadcast_result(output)
            return {
                "package": package,
                "action": action,
                "extrasCount": len(extras),
                "broadcastResult": broadcast_result,
                "delivered": broadcast_result is not None and broadcast_result >= 0,
                "output": output,
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def trigger_app_event(ctx: CommandContext, event: str, payload_json: str | None = None) -> dict[str, Any]:
    payload = payload_json or "{}"
    uri = f"devicetestcli://event/{event}?payload={payload}"
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            output = _shell_output(
                device.shell(
                    " ".join(
                        shlex.quote(part)
                        for part in ["am", "start", "-a", "android.intent.action.VIEW", "-d", uri]
                    )
                )
            )
            return {"event": event, "payload": payload, "uri": uri, **parse_android_am_start_output(output)}

        return run_with_timeout(_run, ctx.timeout_ms)


def boot(ctx: CommandContext, headless: bool = False) -> dict[str, Any]:
    return _confirm_device(ctx, compat_command="boot", boot_requested=headless)


def ensure_simulator(
    ctx: CommandContext,
    boot_requested: bool = False,
    runtime: str | None = None,
    reuse_existing: bool = False,
) -> dict[str, Any]:
    data = _confirm_device(ctx, compat_command="ensure-simulator", boot_requested=boot_requested)
    data["runtime"] = runtime
    data["reuseExisting"] = reuse_existing
    return data


def parse_android_broadcast_result(raw: str) -> int | None:
    match = re.search(r"\bBroadcast completed:\s*result=(-?\d+)\b", raw)
    if not match:
        return None
    return int(match.group(1))


def parse_android_am_start_output(raw: str) -> dict[str, Any]:
    already_running = "Warning: Activity not started" in raw
    started = "Starting:" in raw or already_running
    return {"started": started, "alreadyRunning": already_running, "output": raw.strip()}


def _confirm_device(ctx: CommandContext, *, compat_command: str, boot_requested: bool) -> dict[str, Any]:
    devices = list_adb_devices()
    requested = ctx.serial
    selected = None
    if requested:
        selected = next((device for device in devices if device.serial == requested), None)
    elif devices:
        selected = next((device for device in devices if device.state == "device"), devices[0])
    if selected is not None:
        update_session(serial=selected.serial, timeout_ms=ctx.timeout_ms)
    return {
        "available": selected is not None and selected.state == "device",
        "selectedDevice": selected.serial if selected is not None else requested,
        "device": (
            {"serial": selected.serial, "state": selected.state}
            if selected is not None
            else None
        ),
        "deviceCount": len(devices),
        "devices": [{"serial": device.serial, "state": device.state} for device in devices],
        "booted": False,
        "bootRequested": boot_requested,
        "sessionPersisted": selected is not None,
        "compatCommand": compat_command,
        "note": "Android devices are managed by adb; this command confirms device availability and writes CLI session.",
    }


def _write_read_global_settings(ctx: CommandContext, updates: dict[str, str]) -> dict[str, str | None]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, str | None]:
            readback: dict[str, str | None] = {}
            for key, value in updates.items():
                _shell_output(
                    device.shell(
                        f"settings put global {shlex.quote(key)} {shlex.quote(value)}"
                    )
                )
            for key in updates:
                value = _shell_output(device.shell(f"settings get global {shlex.quote(key)}"))
                readback[key] = None if value == "null" else value
            return readback

        return run_with_timeout(_run, ctx.timeout_ms)


def _write_read_permission(
    ctx: CommandContext,
    action: str,
    package: str,
    permission: str,
) -> dict[str, bool | None]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, bool | None]:
            _shell_output(
                device.shell(
                    f"pm {action} {shlex.quote(package)} {shlex.quote(permission)}"
                )
            )
            raw = _shell_output(device.shell(f"dumpsys package {shlex.quote(package)}"))
            return {"granted": parse_android_permission_granted(raw, permission)}

        return run_with_timeout(_run, ctx.timeout_ms)


def parse_android_permission_granted(raw: str, permission: str) -> bool | None:
    escaped = re.escape(permission)
    match = re.search(rf"\b{escaped}\b[^\n]*\bgranted=(true|false)\b", raw, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _on_off_value(state: str, *, off_value: str, on_value: str) -> str:
    if state in {"off", "disable", "disabled", "0"}:
        return off_value
    if state in {"on", "enable", "enabled", "1"}:
        return on_value
    raise U2CliError(
        ErrorCode.INVALID_ARGUMENT,
        "state must be on or off",
        {"state": state},
    )


def _load_payload(value: str) -> dict[str, Any]:
    try:
        path = Path(value)
        if path.exists():
            raw = path.read_text(encoding="utf-8")
        else:
            raw = value
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {"payload": value}
    if isinstance(parsed, dict):
        return parsed
    return {"payload": parsed}


def _extra_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _shell_output(result: Any) -> str:
    return str(getattr(result, "output", result)).strip()
