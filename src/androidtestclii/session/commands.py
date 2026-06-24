from __future__ import annotations

import os
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.device.connect import list_adb_devices
from androidtestclii.errors import U2CliError
from androidtestclii.screen.snapshot_backend import resolve_snapshot_helper, resolve_snapshot_jar
from androidtestclii.session.store import clear_session, read_session, session_path, write_session
from androidtestclii.unsupported import unsupported_result


def info(ctx: CommandContext) -> dict[str, Any]:
    state = read_session()
    return {
        "mode": "per-command",
        "sidecar": False,
        "pid": os.getpid(),
        "serial": ctx.serial,
        "timeoutMs": ctx.timeout_ms,
        "connectionCached": False,
        "sessionPath": str(session_path()),
        "stored": state.public_dict(),
    }


def runtime_status(ctx: CommandContext) -> dict[str, Any]:
    state = read_session()
    helper = resolve_snapshot_helper(None)
    jar = resolve_snapshot_jar(None)
    snapshot = state.last_snapshot
    snapshot_metadata = snapshot.metadata if snapshot is not None else {}
    return {
        "mode": "per-command",
        "serial": ctx.serial or state.serial,
        "adb": {"available": _adb_available()},
        "snapshotHelper": {
            "available": helper is not None,
            "path": helper.apk_path if helper is not None else None,
            "packageName": helper.manifest.get("packageName") if helper is not None else None,
        },
        "snapshotJar": {"available": jar is not None, "path": jar},
        "temporaryAutomation": state.temporary_automation,
        "persistentMonitoring": state.persistent_monitoring,
        "lastSnapshot": snapshot.public_dict(include_ref_map=False) if snapshot is not None else None,
        "lastSnapshotState": _snapshot_state(snapshot_metadata),
        "stale": state.stale,
        "sessionPath": str(session_path()),
    }


def runtime_clear(ctx: CommandContext) -> dict[str, Any]:
    state = read_session()
    state.temporary_automation = {"state": "cleared"}
    state.persistent_monitoring = {"state": "cleared"}
    write_session(state)
    return {
        "cleared": True,
        "runtime": {
            "temporaryAutomation": state.temporary_automation,
            "persistentMonitoring": state.persistent_monitoring,
        },
        "sessionPath": str(session_path()),
    }


def sidecar_start(ctx: CommandContext) -> dict[str, Any]:
    return unsupported_result(
        "session.sidecar-start",
        recovery_hint="Use per-command CLI mode or implement a daemon runtime adapter.",
        mode="per-command",
        serial=ctx.serial,
    )


def clear(ctx: CommandContext) -> dict[str, Any]:
    clear_session()
    return {"cleared": True, "sessionPath": str(session_path())}


def status(ctx: CommandContext) -> dict[str, Any]:
    state = read_session()
    probe = _probe_serial(state.serial)
    session = state.public_dict()
    return {
        "session": session if state.serial or state.updated_at or state.last_snapshot else None,
        "status": "connected" if probe["deviceOnline"] and not state.stale else "disconnected",
        "deviceOnline": probe["deviceOnline"],
        "stale": state.stale or probe.get("stale", False),
        "staleReason": probe.get("staleReason"),
        "runtimeIdle": False if state.temporary_automation else True,
        "sessionPath": str(session_path()),
    }


def list_sessions(ctx: CommandContext) -> dict[str, Any]:
    state = read_session()
    sessions: list[dict[str, Any]] = []
    if state.serial or state.updated_at or state.last_snapshot is not None:
        probe = _probe_serial(state.serial)
        sessions.append(
            {
                **state.public_dict(),
                "deviceOnline": probe["deviceOnline"],
                "stale": state.stale or probe.get("stale", False),
                "staleReason": probe.get("staleReason"),
            }
        )
    return {"sessions": sessions, "count": len(sessions), "sessionPath": str(session_path())}


def _probe_serial(serial: str | None) -> dict[str, Any]:
    if not serial:
        return {"deviceOnline": False, "stale": False, "staleReason": "no-session-serial"}
    try:
        devices = list_adb_devices()
    except U2CliError as exc:
        return {"deviceOnline": False, "stale": True, "staleReason": exc.code.value}
    for device in devices:
        if device.serial == serial:
            return {
                "deviceOnline": device.state == "device",
                "stale": device.state != "device",
                "staleReason": None if device.state == "device" else f"device-{device.state}",
            }
    return {"deviceOnline": False, "stale": True, "staleReason": "session-device-not-listed"}


def _adb_available() -> bool:
    try:
        list_adb_devices()
    except U2CliError:
        return False
    return True


def _snapshot_state(metadata: dict[str, Any]) -> str:
    snapshot = metadata.get("snapshot")
    if isinstance(snapshot, dict):
        if snapshot.get("helperTruncated") or snapshot.get("truncated"):
            return "degraded"
        if snapshot.get("backend"):
            return "available"
    return "empty"
