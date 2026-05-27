from __future__ import annotations

import os
import shlex
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError, normalize_exception
from u2cli.locks import serial_lock
from u2cli.screen.snapshot_backend import run_adb
from u2cli.timeouts import run_with_timeout


def _current_app(device: Any) -> dict[str, Any]:
    current = device.app_current()
    return {
        "package": current.get("package"),
        "activity": current.get("activity"),
        "pid": current.get("pid"),
    }


def current(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)
    return run_with_timeout(lambda: _current_app(device), ctx.timeout_ms)


def _shell_output(result: Any) -> str:
    output = getattr(result, "output", result)
    return str(output).strip()


def _connect_or_none(ctx: CommandContext) -> Any | None:
    try:
        return connect_device(ctx.serial, ctx.timeout_ms)
    except BaseException:
        return None


def _adb_text(ctx: CommandContext, args: list[str], timeout_ms: int | None = None) -> str:
    result = run_adb(ctx.serial, args, timeout_ms=timeout_ms or ctx.timeout_ms)
    return (result.stdout or result.stderr).strip()


def list_apps(ctx: CommandContext, kind: str = "all") -> dict[str, Any]:
    device = _connect_or_none(ctx)

    def _run() -> dict[str, Any]:
        if device is not None and kind == "running" and hasattr(device, "app_list_running"):
            packages = device.app_list_running()
        elif device is not None and hasattr(device, "app_list"):
            try:
                packages = device.app_list(kind if kind != "all" else None)
            except TypeError:
                packages = device.app_list()
        elif device is not None:
            packages = _shell_output(device.shell("pm list packages")).splitlines()
            packages = [line.removeprefix("package:") for line in packages if line]
        else:
            packages = _adb_text(ctx, ["shell", "pm", "list", "packages"]).splitlines()
            packages = [line.removeprefix("package:") for line in packages if line]
        return {"filter": kind, "packages": list(packages), "count": len(packages)}

    return run_with_timeout(_run, ctx.timeout_ms)


def info(ctx: CommandContext, package: str) -> dict[str, Any]:
    device = _connect_or_none(ctx)

    def _run() -> dict[str, Any]:
        if device is not None and hasattr(device, "app_info"):
            data = device.app_info(package)
            if isinstance(data, dict):
                return {"package": package, **data}
        if device is not None:
            output = _shell_output(device.shell(f"dumpsys package {shlex.quote(package)}"))
        else:
            output = _adb_text(ctx, ["shell", "dumpsys", "package", package])
        return {"package": package, "raw": output}

    return run_with_timeout(_run, ctx.timeout_ms)


def launch(
    ctx: CommandContext,
    package: str,
    activity: str | None = None,
    wait: bool = False,
    stop_before_launch: bool = False,
) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                kwargs = {"activity": activity, "wait": wait, "stop": stop_before_launch}
                try:
                    result = device.app_start(package, **{k: v for k, v in kwargs.items() if v})
                except TypeError:
                    result = device.app_start(package)
                launched_activity = None
                if isinstance(result, dict):
                    launched_activity = result.get("activity")
                return {
                    "package": package,
                    "activity": launched_activity or activity,
                    "wait": wait,
                    "stoppedBeforeLaunch": stop_before_launch,
                    "launched": True,
                }
            except BaseException as exc:
                if stop_before_launch:
                    _adb_text(ctx, ["shell", "am", "force-stop", package])
                if activity:
                    args = ["shell", "am", "start"]
                    if wait:
                        args.append("-W")
                    args.extend(["-n", f"{package}/{activity}"])
                    output = _adb_text(ctx, args)
                else:
                    output = _adb_text(
                        ctx,
                        [
                            "shell",
                            "monkey",
                            "-p",
                            package,
                            "-c",
                            "android.intent.category.LAUNCHER",
                            "1",
                        ],
                    )
                return {
                    "package": package,
                    "activity": activity,
                    "wait": wait,
                    "stoppedBeforeLaunch": stop_before_launch,
                    "launched": True,
                    "via": "adb",
                    "output": output,
                    "fallbackReason": str(exc),
                }

        return run_with_timeout(_run, ctx.timeout_ms)


def start(ctx: CommandContext, package: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                result = device.app_start(package)
                activity = None
                if isinstance(result, dict):
                    activity = result.get("activity")
                return {"package": package, "launched": True, "activity": activity}
            except BaseException as exc:
                err = normalize_exception(exc)
                if err.code == ErrorCode.INTERNAL_ERROR:
                    output = _adb_text(
                        ctx,
                        [
                            "shell",
                            "monkey",
                            "-p",
                            package,
                            "-c",
                            "android.intent.category.LAUNCHER",
                            "1",
                        ],
                    )
                    return {
                        "package": package,
                        "launched": True,
                        "activity": None,
                        "via": "adb",
                        "output": output,
                        "fallbackReason": str(exc),
                    }
                raise err

        return run_with_timeout(_run, ctx.timeout_ms)


def stop(ctx: CommandContext, package: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.app_stop(package)
                return {"package": package, "stopped": True}
            except BaseException as exc:
                output = _adb_text(ctx, ["shell", "am", "force-stop", package])
                return {
                    "package": package,
                    "stopped": True,
                    "via": "adb",
                    "output": output,
                    "fallbackReason": str(exc),
                }

        return run_with_timeout(_run, ctx.timeout_ms)


def clear(ctx: CommandContext, package: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.app_clear(package)
                return {"package": package, "cleared": True}
            except BaseException as exc:
                output = _adb_text(ctx, ["shell", "pm", "clear", package])
                return {
                    "package": package,
                    "cleared": True,
                    "via": "adb",
                    "output": output,
                    "fallbackReason": str(exc),
                }

        return run_with_timeout(_run, ctx.timeout_ms)


def install(ctx: CommandContext, apk: str) -> dict[str, Any]:
    if not os.path.exists(apk):
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "APK path does not exist", {"apkPath": apk})
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                result = device.app_install(apk)
                package = result.get("package") if isinstance(result, dict) else None
                return {"package": package, "apkPath": apk, "installed": True}
            except BaseException as exc:
                output = _adb_text(ctx, ["install", "-r", "-t", apk], max(ctx.timeout_ms, 60_000))
                return {
                    "package": None,
                    "apkPath": apk,
                    "installed": True,
                    "via": "adb",
                    "output": output,
                    "fallbackReason": str(exc),
                }

        return run_with_timeout(_run, ctx.timeout_ms)


def uninstall(ctx: CommandContext, package: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.app_uninstall(package)
                return {"package": package, "uninstalled": True}
            except BaseException as exc:
                output = _adb_text(ctx, ["uninstall", package])
                return {
                    "package": package,
                    "uninstalled": True,
                    "via": "adb",
                    "output": output,
                    "fallbackReason": str(exc),
                }

        return run_with_timeout(_run, ctx.timeout_ms)


def stop_all(ctx: CommandContext) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            if device is not None and hasattr(device, "app_stop_all"):
                stopped = device.app_stop_all()
                packages = list(stopped) if stopped is not None else []
                return {"stopped": True, "packages": packages, "count": len(packages)}
            running = list_apps(ctx, "running")["packages"]
            for package in running:
                if device is not None:
                    device.app_stop(package)
                else:
                    _adb_text(ctx, ["shell", "am", "force-stop", str(package)])
            return {
                "stopped": True,
                "packages": running,
                "count": len(running),
                **({"via": "adb"} if device is None else {}),
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def permission(
    ctx: CommandContext, package: str, permission_name: str, grant: bool
) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            action = "grant" if grant else "revoke"
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                output = _shell_output(
                    device.shell(
                        f"pm {action} {shlex.quote(package)} {shlex.quote(permission_name)}"
                    )
                )
                return {
                    "package": package,
                    "permission": permission_name,
                    "granted": grant,
                    "revoked": not grant,
                    "output": output,
                }
            except BaseException as exc:
                output = _adb_text(ctx, ["shell", "pm", action, package, permission_name])
                return {
                    "package": package,
                    "permission": permission_name,
                    "granted": grant,
                    "revoked": not grant,
                    "output": output,
                    "via": "adb",
                    "fallbackReason": str(exc),
                }

        return run_with_timeout(_run, ctx.timeout_ms)


def intent(
    ctx: CommandContext,
    *,
    package: str | None = None,
    activity: str | None = None,
    action: str | None = None,
    data_uri: str | None = None,
    category: str | None = None,
    extras: list[str] | None = None,
) -> dict[str, Any]:
    if not any([package, activity, action, data_uri]):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "intent requires at least one of --package, --activity, --action, or --data",
        )
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = _connect_or_none(ctx)

        def _run() -> dict[str, Any]:
            args = ["am", "start"]
            if action:
                args.extend(["-a", action])
            if data_uri:
                args.extend(["-d", data_uri])
            if category:
                args.extend(["-c", category])
            for item in extras or []:
                if "=" not in item:
                    raise U2CliError(
                        ErrorCode.INVALID_ARGUMENT,
                        "--extra must be formatted as key=value",
                        {"extra": item},
                    )
                key, value = item.split("=", 1)
                args.extend(["--es", key, value])
            if package and activity:
                component = f"{package}/{activity}"
                args.extend(["-n", component])
            elif package:
                args.extend(["-p", package])
            if device is not None:
                command = " ".join(shlex.quote(part) for part in args)
                output = _shell_output(device.shell(command))
                via = "uiautomator2"
            else:
                output = _adb_text(ctx, ["shell", *args])
                via = "adb"
            return {
                "package": package,
                "activity": activity,
                "action": action,
                "data": data_uri,
                "category": category,
                "extras": extras or [],
                "started": True,
                "via": via,
                "output": output,
            }

        return run_with_timeout(_run, ctx.timeout_ms)
