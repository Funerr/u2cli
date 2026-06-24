from __future__ import annotations

from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.device.connect import (
    adb_path,
    adb_version,
    connect_device,
    import_u2,
    list_adb_devices,
    python_health,
)
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.timeouts import run_with_timeout


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _device_prop(device: Any, name: str) -> str | None:
    try:
        value = device.shell(f"getprop {name}").output.strip()
        return str(value) if value else None
    except Exception:
        return None


def _display_info(info: dict[str, Any]) -> dict[str, Any]:
    raw_display = info.get("display")
    display = raw_display if isinstance(raw_display, dict) else {}
    return {
        "w": info.get("displayWidth") or display.get("width") or info.get("width"),
        "h": info.get("displayHeight") or display.get("height") or info.get("height"),
        "density": info.get("displayDensity") or display.get("density") or info.get("density"),
    }


def devices_data() -> dict[str, Any]:
    devices = []
    try:
        for device in list_adb_devices():
            devices.append(
                {
                    "serial": device.serial,
                    "state": device.state,
                    "model": None,
                    "brand": None,
                    "sdk": None,
                }
            )
    except U2CliError as exc:
        if exc.code == ErrorCode.ADB_NOT_FOUND:
            return {"devices": []}
        raise
    return {"devices": devices}


def doctor_data(ctx: CommandContext) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    python = python_health()
    checks.append({"name": "python", "ok": python["ok"], "detail": python["version"]})

    try:
        u2 = import_u2()
        version = getattr(u2, "__version__", None)
        u2_data = {"version": version, "ok": True}
        checks.append({"name": "uiautomator2", "ok": True, "detail": version})
    except U2CliError as exc:
        u2_data = {"version": None, "ok": False}
        checks.append({"name": "uiautomator2", "ok": False, "detail": exc.message})

    path = adb_path()
    adb = {"path": path, "version": adb_version(), "ok": bool(path)}
    checks.append({"name": "adb", "ok": bool(path), "detail": path})

    try:
        devices = devices_data()["devices"]
    except U2CliError as exc:
        devices = []
        checks.append({"name": "devices", "ok": False, "detail": exc.message})
    else:
        checks.append({"name": "devices", "ok": True, "detail": f"{len(devices)} device(s)"})

    if ctx.serial:
        online = any(d["serial"] == ctx.serial and d["state"] == "device" for d in devices)
        checks.append({"name": "target-device", "ok": online, "detail": ctx.serial})
        if online:
            try:
                connect_device(ctx.serial, ctx.timeout_ms)
                checks.append({"name": "u2-connect", "ok": True, "detail": ctx.serial})
            except U2CliError as exc:
                checks.append({"name": "u2-connect", "ok": False, "detail": exc.message})

    return {"python": python, "u2": u2_data, "adb": adb, "devices": devices, "checks": checks}


def device_info_data(ctx: CommandContext) -> dict[str, Any]:
    if not ctx.serial:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--serial is required for device info",
            {"argument": "serial"},
        )
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _read() -> dict[str, Any]:
        info = dict(getattr(device, "info", {}) or {})
        serial = ctx.serial
        model = (
            info.get("productName") or info.get("model") or _device_prop(device, "ro.product.model")
        )
        brand = info.get("brand") or _device_prop(device, "ro.product.brand")
        sdk = info.get("sdkInt") or _device_prop(device, "ro.build.version.sdk")
        abi = info.get("abi") or _device_prop(device, "ro.product.cpu.abi")
        raw_battery = info.get("battery")
        battery = raw_battery if isinstance(raw_battery, dict) else {}
        return {
            "serial": serial,
            "model": model,
            "brand": brand,
            "sdk": sdk,
            "abi": abi,
            "display": _display_info(info),
            "battery": {
                "level": battery.get("level") or info.get("batteryLevel"),
                "status": battery.get("status") or info.get("batteryStatus"),
            },
        }

    return run_with_timeout(_read, ctx.timeout_ms)
