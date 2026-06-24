from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from androidtestclii.branding import DISPLAY_NAME
from androidtestclii.errors import U2CliError


class CapabilityLayer(str, Enum):
    ADB_FAST_PATH = "adb-fast-path"
    PURE_ADB_UI_QUERY = "pure-adb-ui-query"
    SNAPSHOT_HELPER = "snapshot-helper"
    UIAUTOMATOR2 = "uiautomator2"
    PERSISTENT_ACCESSIBILITY = "persistent-accessibility"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CapabilityRequest:
    command: str
    layer: CapabilityLayer
    best_effort: bool = False


COMMAND_CAPABILITIES: dict[str, CapabilityRequest] = {
    "doctor": CapabilityRequest("doctor", CapabilityLayer.ADB_FAST_PATH),
    "devices": CapabilityRequest("devices", CapabilityLayer.ADB_FAST_PATH),
    "connect": CapabilityRequest("connect", CapabilityLayer.ADB_FAST_PATH),
    "disconnect": CapabilityRequest("disconnect", CapabilityLayer.ADB_FAST_PATH),
    "connection.status": CapabilityRequest("connection.status", CapabilityLayer.ADB_FAST_PATH),
    "runtime.status": CapabilityRequest("runtime.status", CapabilityLayer.ADB_FAST_PATH),
    "runtime.clear": CapabilityRequest("runtime.clear", CapabilityLayer.ADB_FAST_PATH),
    "session.info": CapabilityRequest("session.info", CapabilityLayer.ADB_FAST_PATH),
    "session.status": CapabilityRequest("session.status", CapabilityLayer.ADB_FAST_PATH),
    "session.list": CapabilityRequest("session.list", CapabilityLayer.ADB_FAST_PATH),
    "session.clear": CapabilityRequest("session.clear", CapabilityLayer.ADB_FAST_PATH),
    "session.sidecar-start": CapabilityRequest("session.sidecar-start", CapabilityLayer.UNSUPPORTED),
    "apps": CapabilityRequest("apps", CapabilityLayer.ADB_FAST_PATH),
    "appstate": CapabilityRequest("appstate", CapabilityLayer.UIAUTOMATOR2),
    "open": CapabilityRequest("open", CapabilityLayer.ADB_FAST_PATH),
    "close": CapabilityRequest("close", CapabilityLayer.ADB_FAST_PATH),
    "reinstall": CapabilityRequest("reinstall", CapabilityLayer.ADB_FAST_PATH),
    "install-from-source": CapabilityRequest("install-from-source", CapabilityLayer.ADB_FAST_PATH),
    "app.current": CapabilityRequest("app.current", CapabilityLayer.UIAUTOMATOR2),
    "app.list": CapabilityRequest("app.list", CapabilityLayer.ADB_FAST_PATH),
    "app.info": CapabilityRequest("app.info", CapabilityLayer.ADB_FAST_PATH),
    "app.start": CapabilityRequest("app.start", CapabilityLayer.ADB_FAST_PATH),
    "app.launch": CapabilityRequest("app.launch", CapabilityLayer.ADB_FAST_PATH),
    "app.stop": CapabilityRequest("app.stop", CapabilityLayer.ADB_FAST_PATH),
    "app.clear": CapabilityRequest("app.clear", CapabilityLayer.ADB_FAST_PATH),
    "app.install": CapabilityRequest("app.install", CapabilityLayer.ADB_FAST_PATH),
    "app.uninstall": CapabilityRequest("app.uninstall", CapabilityLayer.ADB_FAST_PATH),
    "app.stop-all": CapabilityRequest("app.stop-all", CapabilityLayer.ADB_FAST_PATH),
    "app.grant": CapabilityRequest("app.grant", CapabilityLayer.ADB_FAST_PATH),
    "app.revoke": CapabilityRequest("app.revoke", CapabilityLayer.ADB_FAST_PATH),
    "app.intent": CapabilityRequest("app.intent", CapabilityLayer.ADB_FAST_PATH),
    "back": CapabilityRequest("back", CapabilityLayer.ADB_FAST_PATH),
    "home": CapabilityRequest("home", CapabilityLayer.ADB_FAST_PATH),
    "app-switcher": CapabilityRequest("app-switcher", CapabilityLayer.ADB_FAST_PATH),
    "rotate": CapabilityRequest("rotate", CapabilityLayer.ADB_FAST_PATH),
    "screen.orientation": CapabilityRequest("screen.orientation", CapabilityLayer.ADB_FAST_PATH),
    "screen.size": CapabilityRequest("screen.size", CapabilityLayer.ADB_FAST_PATH),
    "screen.wake": CapabilityRequest("screen.wake", CapabilityLayer.UIAUTOMATOR2),
    "screen.sleep": CapabilityRequest("screen.sleep", CapabilityLayer.UIAUTOMATOR2),
    "screen.unlock": CapabilityRequest("screen.unlock", CapabilityLayer.UIAUTOMATOR2),
    "screen.notification": CapabilityRequest("screen.notification", CapabilityLayer.ADB_FAST_PATH),
    "screen.record": CapabilityRequest("screen.record", CapabilityLayer.ADB_FAST_PATH),
    "screenshot": CapabilityRequest("screenshot", CapabilityLayer.ADB_FAST_PATH),
    "screen.screenshot": CapabilityRequest("screen.screenshot", CapabilityLayer.ADB_FAST_PATH),
    "diff.screenshot": CapabilityRequest("diff.screenshot", CapabilityLayer.ADB_FAST_PATH),
    "diff.snapshot": CapabilityRequest("diff.snapshot", CapabilityLayer.SNAPSHOT_HELPER),
    "logs.start": CapabilityRequest("logs.start", CapabilityLayer.ADB_FAST_PATH),
    "logs.stop": CapabilityRequest("logs.stop", CapabilityLayer.ADB_FAST_PATH),
    "logs.clear": CapabilityRequest("logs.clear", CapabilityLayer.ADB_FAST_PATH),
    "logs.mark": CapabilityRequest("logs.mark", CapabilityLayer.ADB_FAST_PATH),
    "logs.path": CapabilityRequest("logs.path", CapabilityLayer.ADB_FAST_PATH),
    "logs.doctor": CapabilityRequest("logs.doctor", CapabilityLayer.ADB_FAST_PATH),
    "trace.start": CapabilityRequest("trace.start", CapabilityLayer.ADB_FAST_PATH),
    "trace.stop": CapabilityRequest("trace.stop", CapabilityLayer.ADB_FAST_PATH),
    "perf.collect": CapabilityRequest("perf.collect", CapabilityLayer.ADB_FAST_PATH),
    "network": CapabilityRequest("network", CapabilityLayer.ADB_FAST_PATH),
    "settings": CapabilityRequest("settings", CapabilityLayer.ADB_FAST_PATH),
    "push": CapabilityRequest("push", CapabilityLayer.ADB_FAST_PATH),
    "trigger-app-event": CapabilityRequest("trigger-app-event", CapabilityLayer.ADB_FAST_PATH),
    "boot": CapabilityRequest("boot", CapabilityLayer.ADB_FAST_PATH),
    "ensure-simulator": CapabilityRequest("ensure-simulator", CapabilityLayer.ADB_FAST_PATH),
    "snapshot": CapabilityRequest("snapshot", CapabilityLayer.SNAPSHOT_HELPER),
    "snapshot.capture": CapabilityRequest("snapshot.capture", CapabilityLayer.SNAPSHOT_HELPER),
    "screen.dump": CapabilityRequest("screen.dump", CapabilityLayer.SNAPSHOT_HELPER),
    "click": CapabilityRequest("click", CapabilityLayer.PURE_ADB_UI_QUERY, best_effort=True),
    "press": CapabilityRequest("press", CapabilityLayer.PURE_ADB_UI_QUERY, best_effort=True),
    "longpress": CapabilityRequest("longpress", CapabilityLayer.PURE_ADB_UI_QUERY),
    "swipe": CapabilityRequest("swipe", CapabilityLayer.ADB_FAST_PATH),
    "scroll": CapabilityRequest("scroll", CapabilityLayer.ADB_FAST_PATH),
    "fill": CapabilityRequest("fill", CapabilityLayer.PURE_ADB_UI_QUERY, best_effort=True),
    "type": CapabilityRequest("type", CapabilityLayer.ADB_FAST_PATH),
    "focus": CapabilityRequest("focus", CapabilityLayer.PURE_ADB_UI_QUERY, best_effort=True),
    "get": CapabilityRequest("get", CapabilityLayer.PURE_ADB_UI_QUERY),
    "find": CapabilityRequest("find", CapabilityLayer.PURE_ADB_UI_QUERY),
    "is": CapabilityRequest("is", CapabilityLayer.PURE_ADB_UI_QUERY),
    "wait": CapabilityRequest("wait", CapabilityLayer.PURE_ADB_UI_QUERY),
    "alert": CapabilityRequest("alert", CapabilityLayer.PURE_ADB_UI_QUERY),
    "clipboard": CapabilityRequest("clipboard", CapabilityLayer.ADB_FAST_PATH),
    "keyboard": CapabilityRequest("keyboard", CapabilityLayer.ADB_FAST_PATH),
    "batch": CapabilityRequest("batch", CapabilityLayer.ADB_FAST_PATH),
    "replay": CapabilityRequest("replay", CapabilityLayer.ADB_FAST_PATH),
    "test": CapabilityRequest("test", CapabilityLayer.ADB_FAST_PATH),
    "gesture": CapabilityRequest("gesture", CapabilityLayer.ADB_FAST_PATH),
    "record.start": CapabilityRequest("record.start", CapabilityLayer.ADB_FAST_PATH),
    "record.stop": CapabilityRequest("record.stop", CapabilityLayer.ADB_FAST_PATH),
    "screen.multi-touch": CapabilityRequest("screen.multi-touch", CapabilityLayer.ADB_FAST_PATH),
    "screen.pinch": CapabilityRequest("screen.pinch", CapabilityLayer.UNSUPPORTED),
    "screen.expand": CapabilityRequest("screen.expand", CapabilityLayer.UNSUPPORTED),
    "harmonyos": CapabilityRequest("harmonyos", CapabilityLayer.UNSUPPORTED),
    "react-native": CapabilityRequest("react-native", CapabilityLayer.UNSUPPORTED),
    "react-devtools": CapabilityRequest("react-devtools", CapabilityLayer.UNSUPPORTED),
    "cloud": CapabilityRequest("cloud", CapabilityLayer.UNSUPPORTED),
    "daemon": CapabilityRequest("daemon", CapabilityLayer.UNSUPPORTED),
    "device.info": CapabilityRequest("device.info", CapabilityLayer.UIAUTOMATOR2),
    "device.shell": CapabilityRequest("device.shell", CapabilityLayer.ADB_FAST_PATH),
    "device.push": CapabilityRequest("device.push", CapabilityLayer.ADB_FAST_PATH),
    "device.pull": CapabilityRequest("device.pull", CapabilityLayer.ADB_FAST_PATH),
    "device.clipboard-get": CapabilityRequest("device.clipboard-get", CapabilityLayer.ADB_FAST_PATH),
    "device.clipboard-set": CapabilityRequest("device.clipboard-set", CapabilityLayer.ADB_FAST_PATH),
    "device.logcat": CapabilityRequest("device.logcat", CapabilityLayer.ADB_FAST_PATH),
    "device.network": CapabilityRequest("device.network", CapabilityLayer.ADB_FAST_PATH),
    "element.find": CapabilityRequest("element.find", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.exists": CapabilityRequest("element.exists", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.count": CapabilityRequest("element.count", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.bounds": CapabilityRequest("element.bounds", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.wait": CapabilityRequest("element.wait", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.click": CapabilityRequest("element.click", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.long-click": CapabilityRequest("element.long-click", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.set-text": CapabilityRequest("element.set-text", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.clear-text": CapabilityRequest("element.clear-text", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.get-text": CapabilityRequest("element.get-text", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.swipe": CapabilityRequest("element.swipe", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.drag-to": CapabilityRequest("element.drag-to", CapabilityLayer.PURE_ADB_UI_QUERY),
    "element.scroll-to": CapabilityRequest("element.scroll-to", CapabilityLayer.PURE_ADB_UI_QUERY),
    "input.press": CapabilityRequest("input.press", CapabilityLayer.ADB_FAST_PATH),
    "input.tap": CapabilityRequest("input.tap", CapabilityLayer.ADB_FAST_PATH),
    "input.swipe": CapabilityRequest("input.swipe", CapabilityLayer.ADB_FAST_PATH),
    "input.text": CapabilityRequest("input.text", CapabilityLayer.ADB_FAST_PATH),
    "input.drag": CapabilityRequest("input.drag", CapabilityLayer.ADB_FAST_PATH),
    "input.keyevent": CapabilityRequest("input.keyevent", CapabilityLayer.ADB_FAST_PATH),
    "toast.get": CapabilityRequest("toast.get", CapabilityLayer.PERSISTENT_ACCESSIBILITY),
    "toast.reset": CapabilityRequest("toast.reset", CapabilityLayer.PERSISTENT_ACCESSIBILITY),
    "watcher.add": CapabilityRequest("watcher.add", CapabilityLayer.PERSISTENT_ACCESSIBILITY),
    "watcher.run": CapabilityRequest("watcher.run", CapabilityLayer.PERSISTENT_ACCESSIBILITY),
    "watcher.reset": CapabilityRequest("watcher.reset", CapabilityLayer.PERSISTENT_ACCESSIBILITY),
    "pi.schema": CapabilityRequest("pi.schema", CapabilityLayer.ADB_FAST_PATH),
}


RECOVERY_HINTS: dict[str, str] = {
    "invalid-argument": "Fix the command arguments and retry.",
    "device-discovery": "Check adb authorization, device connection, and --serial.",
    "runtime-connect": "Check uiautomator2 connectivity, then retry or use an ADB fast-path command.",
    "selector-query": "Wait for the UI to settle or use a more specific selector.",
    "snapshot-capture": "Retry when the UI is idle, or use screenshot as visual truth.",
    "fallback-unavailable": "Use explicit coordinates or a more precise selector.",
    "capability-unavailable": f"Use an implemented {DISPLAY_NAME} command or add a dedicated adapter.",
}


def capability_for_command(command: str) -> CapabilityRequest:
    return COMMAND_CAPABILITIES.get(
        command, CapabilityRequest(command, CapabilityLayer.UNKNOWN)
    )


def with_capability_metadata(
    data: dict[str, Any] | None,
    command: str,
    *,
    error: U2CliError | None = None,
) -> dict[str, Any]:
    payload = dict(data or {})
    existing = payload.get("metadata")
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata.update(capability_metadata(command, payload, error=error))
    payload["metadata"] = metadata
    return payload


def capability_metadata(
    command: str,
    data: dict[str, Any] | None = None,
    *,
    error: U2CliError | None = None,
) -> dict[str, Any]:
    request = capability_for_command(command)
    payload = data or {}
    actual_layer = actual_capability_layer(request.layer, payload)
    fallback = fallback_info(payload)
    failure_stage = failure_stage_for(command, error)
    degraded = bool(
        fallback["fallbackUsed"]
        or payload.get("degraded")
        or _nested_bool(payload.get("snapshot"), "degraded")
    )
    metadata: dict[str, Any] = {
        "capabilityLayer": actual_layer.value,
        "requestedCapabilityLayer": request.layer.value,
        "fallbackUsed": fallback["fallbackUsed"],
        "fallbackMethod": fallback["fallbackMethod"],
        "fallbackReason": fallback["fallbackReason"],
        "preparationState": preparation_state(payload),
        "degraded": degraded,
        "failureStage": failure_stage,
        "recoveryHint": recovery_hint(failure_stage, error),
    }
    if request.best_effort:
        metadata["bestEffort"] = True
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        metadata["snapshotBackend"] = snapshot.get("backend")
        if "fallbackErrors" in snapshot:
            metadata["fallbackErrors"] = snapshot["fallbackErrors"]
        metadata["snapshotMode"] = snapshot.get("mode")
        metadata["snapshotPresentation"] = snapshot.get("presentation")
        metadata["snapshotFull"] = snapshot.get("full")
        metadata["snapshotComplete"] = snapshot.get("complete")
        metadata["snapshotCanProveAbsence"] = snapshot.get("canProveAbsence")
        metadata["snapshotCoverage"] = snapshot.get("coverage")
        metadata["snapshotCoverageFailureReason"] = snapshot.get("coverageFailureReason")
        if "nodeCount" in snapshot:
            metadata["snapshotNodeCount"] = snapshot["nodeCount"]
        if "observedNodeCount" in snapshot:
            metadata["snapshotObservedNodeCount"] = snapshot["observedNodeCount"]
        if "scrollContextCount" in snapshot:
            metadata["snapshotScrollContextCount"] = snapshot["scrollContextCount"]
        if "usableForScrollToText" in snapshot:
            metadata["snapshotUsableForScrollToText"] = snapshot["usableForScrollToText"]
    target_location = payload.get("targetLocation")
    if isinstance(target_location, dict):
        metadata["targetLocationState"] = target_location.get("state")
        metadata["targetCanScrollToTarget"] = target_location.get("canScrollToTarget")
        metadata["targetLocationReason"] = target_location.get("reason")
    return metadata


def actual_capability_layer(default: CapabilityLayer, payload: dict[str, Any]) -> CapabilityLayer:
    direct = _layer_from_via(payload.get("via"))
    if direct is not None:
        return direct
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        backend = str(snapshot.get("backend") or "")
        if backend == "android-snapshot-helper":
            return CapabilityLayer.SNAPSHOT_HELPER
        if backend in {"android-uiautomator-jar", "adb-uiautomator-dump"}:
            return CapabilityLayer.PURE_ADB_UI_QUERY
        if backend == "uiautomator2":
            return CapabilityLayer.UIAUTOMATOR2
    if payload.get("cached") or payload.get("ref"):
        return CapabilityLayer.ADB_FAST_PATH
    return default


def fallback_info(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    sources = [payload, action if isinstance(action, dict) else {}]
    for source in sources:
        if source.get("fallbackUsed") is not None:
            return {
                "fallbackUsed": bool(source.get("fallbackUsed")),
                "fallbackMethod": source.get("fallbackMethod"),
                "fallbackReason": source.get("fallbackReason"),
            }
    snapshot = payload.get("snapshot")
    if payload.get("via") == "adb" or _nested_has(snapshot, "fallbackErrors"):
        return {
            "fallbackUsed": True,
            "fallbackMethod": str(payload.get("via") or "snapshot-backend"),
            "fallbackReason": payload.get("fallbackReason") or "preferred-path-unavailable",
        }
    return {"fallbackUsed": False, "fallbackMethod": None, "fallbackReason": None}


def preparation_state(payload: dict[str, Any]) -> str:
    runtime = payload.get("runtime")
    if isinstance(runtime, dict) and runtime.get("preparationState"):
        return str(runtime["preparationState"])
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        install = snapshot.get("install")
        if isinstance(install, dict):
            reason = install.get("reason")
            if install.get("installed"):
                return f"installed-{reason or 'helper'}"
            if reason == "current":
                return "already-installed"
            if reason == "skipped":
                return "install-skipped"
            if install.get("cached"):
                return "cached-installed"
    return "not-needed"


def failure_stage_for(command: str, error: U2CliError | None) -> str | None:
    if error is None:
        return None
    detail_stage = error.details.get("failureStage") or error.details.get("stage")
    if detail_stage:
        return str(detail_stage)
    code = error.code.value
    if code == "INVALID_ARGUMENT":
        return "invalid-argument"
    if code in {"DEVICE_NOT_FOUND", "DEVICE_OFFLINE", "ADB_NOT_FOUND"}:
        return "device-discovery"
    if code == "U2_CONNECT_FAILED":
        return "runtime-connect"
    if code == "PLATFORM_UNSUPPORTED":
        return "capability-unavailable"
    if code in {"ELEMENT_NOT_FOUND", "ELEMENT_AMBIGUOUS"}:
        return "selector-query"
    if command in {"snapshot", "screen.dump"}:
        return "snapshot-capture"
    return "execution"


def recovery_hint(stage: str | None, error: U2CliError | None) -> str | None:
    if error is not None:
        detail_hint = error.details.get("recovery") or error.details.get("recoveryHint")
        if detail_hint:
            return str(detail_hint)
    if stage is None:
        return None
    return RECOVERY_HINTS.get(stage)


def _layer_from_via(value: Any) -> CapabilityLayer | None:
    if value == "adb":
        return CapabilityLayer.ADB_FAST_PATH
    if value == "bounds":
        return CapabilityLayer.ADB_FAST_PATH
    if value == "android-snapshot-helper":
        return CapabilityLayer.SNAPSHOT_HELPER
    if value == "uiautomator2":
        return CapabilityLayer.UIAUTOMATOR2
    return None


def _nested_bool(value: Any, key: str) -> bool:
    return bool(value.get(key)) if isinstance(value, dict) else False


def _nested_has(value: Any, key: str) -> bool:
    return key in value if isinstance(value, dict) else False
