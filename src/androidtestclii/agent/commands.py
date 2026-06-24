from __future__ import annotations

import json
import os
import random
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from androidtestclii.branding import SLUG
from androidtestclii.app import commands as app_commands
from androidtestclii.context import CommandContext
from androidtestclii.device import commands as device_commands
from androidtestclii.device.connect import adb_path, list_adb_devices
from androidtestclii.element import action as element_action
from androidtestclii.element import query as element_query
from androidtestclii.element.target import resolve_element_target
from androidtestclii.element.selector import Selector, parse_target_selector, selector_from_kwargs
from androidtestclii.errors import ErrorCode, U2CliError, normalize_exception
from androidtestclii.input import commands as input_commands
from androidtestclii.screen import commands as screen_commands
from androidtestclii.screen import dump as screen_dump
from androidtestclii.screen import screenshot as screen_screenshot
from androidtestclii.screen import visual as screen_visual
from androidtestclii.screen import size as screen_size
from androidtestclii.screen.snapshot_backend import SnapshotBackendOptions
from androidtestclii.session.store import SnapshotRef, read_session, ref_entry, update_session


def snapshot(
    ctx: CommandContext,
    interactive: bool = False,
    full: bool = False,
    target_text: str | None = None,
) -> dict[str, Any]:
    _ = interactive
    data = screen_dump.dump(ctx, compact=not full, snapshot_options=SnapshotBackendOptions())
    if target_text is not None:
        needle = target_text.strip()
        if not needle:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "--target-text must not be empty",
                {"argument": "target-text"},
            )
        data["targetText"] = target_text_summary(data, needle)
        data["targetLocation"] = target_location(data, needle)
    return data


def screenshot(
    ctx: CommandContext,
    out: str | None = None,
    *,
    overlay_refs: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if overlay_refs:
        return screen_visual.screenshot_with_overlay_refs(ctx, out)
    return screen_screenshot.screenshot(ctx, out or "artifacts/screenshot.png")


def diff_screenshot(
    baseline: str,
    current: str,
    threshold: str | None = None,
    out: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return screen_visual.diff_screenshot(
        baseline=baseline,
        current=current,
        threshold=threshold,
        out=out,
    )


def diff_snapshot(ctx: CommandContext) -> dict[str, Any]:
    return screen_visual.diff_snapshot(ctx)


def back(ctx: CommandContext) -> dict[str, Any]:
    return input_commands.press(ctx, "back")


def home(ctx: CommandContext) -> dict[str, Any]:
    return input_commands.press(ctx, "home")


def app_switcher(ctx: CommandContext) -> dict[str, Any]:
    return input_commands.press(ctx, "recent")


def rotate(ctx: CommandContext, value: str) -> dict[str, Any]:
    mapped = {
        "0": "natural",
        "90": "left",
        "180": "upsidedown",
        "270": "right",
        "portrait": "natural",
        "landscape": "left",
    }.get(value, value)
    return screen_commands.orientation_set(ctx, mapped)


def open_app(
    ctx: CommandContext,
    package: str,
    activity: str | None = None,
    relaunch: bool = False,
) -> dict[str, Any]:
    return app_commands.launch(ctx, package, activity, wait=False, stop_before_launch=relaunch)


def close_app(ctx: CommandContext, package: str | None = None, shutdown: bool = False) -> dict[str, Any]:
    if shutdown:
        return app_commands.stop_all(ctx)
    target = package
    if target is None:
        current = app_commands.current(ctx)
        target = current.get("package")
    if not target:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "close requires a package or a detectable foreground app",
            {"argument": "package"},
        )
    return app_commands.stop(ctx, str(target))


def appstate(ctx: CommandContext) -> dict[str, Any]:
    current = app_commands.current(ctx)
    return {
        "package": current.get("package"),
        "activity": current.get("activity"),
        "pid": current.get("pid"),
        "source": "uiautomator2",
        "system": _is_system_package(str(current.get("package") or "")),
    }


def apps(ctx: CommandContext, kind: str = "all") -> dict[str, Any]:
    listed = app_commands.list_apps(ctx, kind)
    packages = []
    for package in listed.get("packages", []):
        name = str(package)
        packages.append({"package": name, "activity": None, "source": "unknown", "system": _is_system_package(name)})
    return {"filter": kind, "apps": packages, "packages": listed.get("packages", []), "count": listed.get("count", len(packages))}


def reinstall(ctx: CommandContext, package: str, path: str) -> dict[str, Any]:
    uninstalled = app_commands.uninstall(ctx, package)
    installed = app_commands.install(ctx, path)
    return {"package": package, "path": path, "uninstall": uninstalled, "install": installed, "reinstalled": True}


def install_from_source(ctx: CommandContext, source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        fd, path = tempfile.mkstemp(prefix=f"{SLUG}-install-", suffix=".apk")
        os.close(fd)
        try:
            with urllib.request.urlopen(source, timeout=max(1, ctx.timeout_ms / 1000)) as response:
                Path(path).write_bytes(response.read())
            installed = app_commands.install(ctx, path)
            installed.update({"source": source, "downloaded": True})
            return installed
        except BaseException as exc:
            raise U2CliError(
                ErrorCode.APP_ACTION_FAILED,
                "Failed to install app from URL source",
                {"source": source, "error": str(exc)},
            ) from exc
        finally:
            Path(path).unlink(missing_ok=True)
    installed = app_commands.install(ctx, source)
    installed.update({"source": source, "downloaded": False})
    return installed


def type_text(ctx: CommandContext, text: str) -> dict[str, Any]:
    return input_commands.text(ctx, text)


def focus(ctx: CommandContext, target: str) -> dict[str, Any]:
    return click(ctx, target)


def get_attr(ctx: CommandContext, attr: str, target: str) -> dict[str, Any]:
    if attr not in {"text", "attrs", "bounds"}:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "get attr must be one of text, attrs, or bounds",
            {"attr": attr},
        )
    resolved = resolve_target(ctx, target)
    if attr == "text" and resolved.cache_allowed and resolved.ref is not None and resolved.ref.text is not None:
        return {"target": target, "text": resolved.ref.text, "cached": True}
    if attr == "bounds" and resolved.cache_allowed and resolved.point is not None:
        return {"target": target, "bounds": resolved.ref.public_dict().get("bounds") if resolved.ref else None, "cached": True}
    selector = resolved.selector
    if selector is None:
        raise_invalid_ref(target, resolved.ref)
    assert selector is not None
    cached = cached_matches(ctx, selector)
    if cached:
        entry = cached[0]
        if attr == "text":
            return {
                "target": target,
                "text": entry.text,
                "cached": True,
                "selector": selector.public_dict(),
            }
        if attr == "bounds":
            return {
                "target": target,
                "bounds": entry.public_dict().get("bounds"),
                "cached": True,
                "selector": selector.public_dict(),
            }
        return {
            "target": target,
            "attrs": entry.public_dict(),
            "cached": True,
            "selector": selector.public_dict(),
        }
    if attr == "text":
        return element_action.get_text(ctx, selector)
    if attr == "bounds":
        return element_query.bounds(ctx, selector)
    found = element_query.find(ctx, selector)
    return {"target": target, "attrs": found.get("element"), "selector": selector.public_dict()}


def click(
    ctx: CommandContext,
    target: str,
    *,
    double_tap: bool = False,
    hold_ms: int | None = None,
    count: int = 1,
    interval_ms: int = 0,
    jitter_px: int = 0,
) -> dict[str, Any]:
    if double_tap and hold_ms is not None:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--double-tap and --hold-ms are mutually exclusive",
            {"doubleTap": double_tap, "holdMs": hold_ms},
        )
    repetitions = count * (2 if double_tap else 1)
    if repetitions <= 0:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "--count must be greater than 0", {"count": count})
    resolved = resolve_target(ctx, target)
    if resolved.point is not None:
        return tap_point(
            ctx,
            resolved.point,
            target=target,
            repetitions=repetitions,
            interval_ms=interval_ms,
            hold_ms=hold_ms,
            jitter_px=jitter_px,
            ref=resolved.ref_name,
        )
    if resolved.selector is None:
        raise_invalid_ref(target, resolved.ref)
    selector = resolved.selector
    assert selector is not None
    cached = cached_matches(ctx, selector)
    result: dict[str, Any] | None = None
    for index in range(repetitions):
        try:
            if hold_ms is not None:
                result = element_action.long_click(ctx, selector)
            else:
                result = element_action.click(ctx, selector)
        except BaseException as exc:
            if not _can_use_cached_point_fallback(exc, cached):
                raise
            point = point_from_ref(cached[0])
            if point is None:
                raise
            result = tap_point(
                ctx,
                point,
                target=target,
                hold_ms=hold_ms,
                ref=None,
            )
        sleep_between(index, repetitions, interval_ms)
    assert result is not None
    result.update({"target": target, "count": count, "tapCount": repetitions})
    return result


def click_percent(
    ctx: CommandContext,
    x_percent: int,
    y_percent: int,
    *,
    double_tap: bool = False,
    hold_ms: int | None = None,
    count: int = 1,
    interval_ms: int = 0,
    jitter_px: int = 0,
) -> dict[str, Any]:
    if double_tap and hold_ms is not None:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--double-tap and --hold-ms are mutually exclusive",
            {"doubleTap": double_tap, "holdMs": hold_ms},
        )
    if not (0 <= x_percent <= 100 and 0 <= y_percent <= 100):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "percentage coordinates must be between 0 and 100",
            {"x": x_percent, "y": y_percent},
        )
    size = screen_size.size(ctx)
    width = int(size.get("width") or 0)
    height = int(size.get("height") or 0)
    if width <= 0 or height <= 0:
        raise U2CliError(ErrorCode.ACTION_FAILED, "Unable to resolve screen size")
    repetitions = count * (2 if double_tap else 1)
    if repetitions <= 0:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "--count must be greater than 0", {"count": count})
    point = (round(width * x_percent / 100), round(height * y_percent / 100))
    result = tap_point(
        ctx,
        point,
        target=f"{x_percent},{y_percent}",
        repetitions=repetitions,
        interval_ms=interval_ms,
        hold_ms=hold_ms,
        jitter_px=jitter_px,
    )
    result["percent"] = [x_percent, y_percent]
    return result


def longpress(ctx: CommandContext, target: str, duration_ms: int = 800) -> dict[str, Any]:
    return click(ctx, target, hold_ms=duration_ms)


def press(ctx: CommandContext, target: str, **kwargs: Any) -> dict[str, Any]:
    return click(ctx, target, **kwargs)


def fill(ctx: CommandContext, target: str, text: str, delay_ms: int = 0) -> dict[str, Any]:
    resolved = resolve_target(ctx, target)
    focused: dict[str, Any]
    if resolved.point is not None:
        focused = tap_point(ctx, resolved.point, target=target, ref=resolved.ref_name)
    elif resolved.selector is not None:
        focused = element_action.click(ctx, resolved.selector)
    else:
        raise_invalid_ref(target, resolved.ref)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)
    sent = input_commands.text(ctx, text)
    return {"target": target, "text": text, "focused": focused, "sent": sent, "filled": True}


def swipe(
    ctx: CommandContext,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    duration_ms: int = 400,
    count: int = 1,
    interval_ms: int = 0,
) -> dict[str, Any]:
    if count <= 0:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "--count must be greater than 0", {"count": count})
    result: dict[str, Any] | None = None
    for index in range(count):
        result = input_commands.swipe(ctx, (from_x, from_y), (to_x, to_y), duration_ms)
        sleep_between(index, count, interval_ms)
    assert result is not None
    result["count"] = count
    return result


def scroll(ctx: CommandContext, direction: str = "down", pixels: int | None = None) -> dict[str, Any]:
    if direction not in {"up", "down", "left", "right", "top", "bottom"}:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "scroll direction must be one of up, down, left, right, top, or bottom",
            {"direction": direction},
        )
    size = screen_size.size(ctx)
    width = int(size.get("width") or 1080)
    height = int(size.get("height") or 2400)
    distance = pixels or int(height * 0.6)
    cx = width // 2
    cy = height // 2
    if direction in {"down", "bottom"}:
        start, end = (cx, min(height - 1, cy + distance // 2)), (cx, max(0, cy - distance // 2))
    elif direction in {"up", "top"}:
        start, end = (cx, max(0, cy - distance // 2)), (cx, min(height - 1, cy + distance // 2))
    elif direction == "left":
        start, end = (min(width - 1, cx + distance // 2), cy), (max(0, cx - distance // 2), cy)
    else:
        start, end = (max(0, cx - distance // 2), cy), (min(width - 1, cx + distance // 2), cy)
    count = 3 if direction in {"top", "bottom"} else 1
    result = swipe(ctx, start[0], start[1], end[0], end[1], count=count)
    result.update({"direction": direction, "pixels": pixels, "scrolled": True})
    return result


def find(
    ctx: CommandContext,
    target: str,
    action: str | None = None,
    action_value: str | None = None,
    first: bool = False,
    last: bool = False,
) -> dict[str, Any]:
    selector = selector_from_target_for_query(target)
    selected_index = None
    if first and last:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "--first and --last are mutually exclusive")
    cached = cached_matches(ctx, selector)
    if cached:
        matched_count = len(cached)
        if matched_count > 1:
            if first:
                selected_index = 0
            elif last:
                selected_index = matched_count - 1
            else:
                raise U2CliError(
                    ErrorCode.ELEMENT_AMBIGUOUS,
                    "Multiple elements matched selector",
                    {"selector": selector.public_dict(), "matchCount": matched_count, "cached": True},
                )
        else:
            selected_index = 0
        selected = cached[selected_index or 0]
        data = diagnostic_payload(
            selector,
            "exists",
            ctx.timeout_ms,
            attempts=1,
            duration_ms=0,
            matched_count=matched_count,
            selected_index=selected_index,
        )
        data.update(
            {
                "matched": True,
                "matchCount": matched_count,
                "element": selected.public_dict(),
                "cached": True,
            }
        )
        if action is None:
            return data
        # For actions, use the selector path below so stale cached bounds are not the only path.
    queried = element_query.find(ctx, selector)
    matched_count = int(queried.get("matchCount", 0))
    if matched_count > 1:
        if first:
            selected_index = 0
        elif last:
            selected_index = matched_count - 1
        else:
            raise U2CliError(
                ErrorCode.ELEMENT_AMBIGUOUS,
                "Multiple elements matched selector",
                {"selector": selector.public_dict(), "matchCount": matched_count},
            )
    elif matched_count == 1:
        selected_index = 0
    data = diagnostic_payload(selector, "exists", ctx.timeout_ms, attempts=1, duration_ms=0, matched_count=matched_count, selected_index=selected_index)
    data.update(queried)
    if action == "click":
        action_selector = selector_with_index(selector, selected_index)
        data["action"] = element_action.click(ctx, action_selector)
    elif action == "fill":
        if action_value is None:
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, "find fill requires text", {"action": action})
        action_selector = selector_with_index(selector, selected_index)
        data["action"] = element_action.set_text(ctx, action_selector, action_value)
    elif action is not None:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "find action must be click or fill", {"action": action})
    return data


def is_state(ctx: CommandContext, state: str, target: str) -> dict[str, Any]:
    if state not in {"exists", "visible", "enabled", "checked"}:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "is state must be one of exists, visible, enabled, or checked",
            {"state": state},
        )
    selector = selector_from_target_for_query(target)
    cached = cached_matches(ctx, selector)
    if cached:
        entry = cached[0]
        matched_count = len(cached)
        if state in {"exists", "visible"}:
            passed = True
        elif state == "enabled":
            passed = bool((entry.node or {}).get("enabled"))
        else:
            passed = bool((entry.node or {}).get("checked"))
        return {
            **diagnostic_payload(
                selector,
                state,
                ctx.timeout_ms,
                attempts=1,
                duration_ms=0,
                matched_count=matched_count,
                selected_index=0,
            ),
            "result": passed,
            "matched": passed,
            "element": entry.public_dict(),
            "cached": True,
        }
    result = element_query.find(ctx, selector)
    element = result.get("element") or {}
    matched_count = int(result.get("matchCount", 0))
    if state in {"exists", "visible"}:
        passed = matched_count > 0
    elif state == "enabled":
        passed = bool(element.get("enabled")) if matched_count > 0 else False
    else:
        passed = bool(element.get("checked")) if matched_count > 0 else False
    return {
        **diagnostic_payload(selector, state, ctx.timeout_ms, attempts=1, duration_ms=0, matched_count=matched_count, selected_index=0 if matched_count else None),
        "result": passed,
        "matched": passed,
        "element": element,
    }


def wait(ctx: CommandContext, kind: str, value: str, timeout_ms: int) -> dict[str, Any]:
    selector = selector_for_kind(kind, value)
    cached = cached_matches(ctx, selector)
    if cached:
        return {
            **diagnostic_payload(
                selector,
                "exists",
                timeout_ms,
                attempts=1,
                duration_ms=0,
                matched_count=len(cached),
                selected_index=0,
            ),
            "cached": True,
        }
    wait_ctx = CommandContext.start(
        json_output=ctx.json_output,
        serial=ctx.serial,
        timeout_ms=timeout_ms,
        timeout_ms_explicit=True,
        verbosity=ctx.verbosity,
    )
    started = time.perf_counter()
    attempts = 0
    last_count = 0
    deadline = started + timeout_ms / 1000
    while True:
        attempts += 1
        try:
            result = element_query.exists(wait_ctx, selector)
            last_count = int(result.get("matchCount", 0))
            if result.get("exists"):
                duration = int((time.perf_counter() - started) * 1000)
                return diagnostic_payload(selector, "exists", timeout_ms, attempts, duration, last_count, 0 if last_count else None)
        except U2CliError as exc:
            if exc.code != ErrorCode.ELEMENT_NOT_FOUND:
                raise
        if time.perf_counter() >= deadline:
            duration = int((time.perf_counter() - started) * 1000)
            raise U2CliError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "No element matched selector before timeout",
                {
                    **diagnostic_payload(selector, "exists", timeout_ms, attempts, duration, last_count, None),
                },
            )
        time.sleep(0.1)


def clipboard(ctx: CommandContext, action: str, text: str | None = None) -> dict[str, Any]:
    if action == "read":
        return device_commands.clipboard_get(ctx)
    if action == "write":
        if text is None:
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, "clipboard write requires text")
        return device_commands.clipboard_set(ctx, text)
    raise U2CliError(ErrorCode.INVALID_ARGUMENT, "clipboard action must be read or write", {"action": action})


def keyboard(ctx: CommandContext, action: str) -> dict[str, Any]:
    if action == "hide":
        pressed = input_commands.press(ctx, "back")
        status = keyboard_status(ctx)
        status.update({"shown": False, "action": action, "result": pressed})
        return status
    if action == "show":
        status = keyboard_status(ctx)
        status.update({"action": action, "message": "keyboard show requires a focused editable element"})
        return status
    if action != "status":
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "keyboard action must be status, hide, or show", {"action": action})
    return keyboard_status(ctx)


def keyboard_status(ctx: CommandContext) -> dict[str, Any]:
    output = device_commands.shell(ctx, "dumpsys input_method").get("output", "")
    text = str(output)
    return {
        "shown": "mInputShown=true" in text or "InputShown=true" in text,
        "currentIme": extract_after(text, "mCurId=") or extract_after(text, "mCurrentInputMethodId="),
        "servedView": extract_after(text, "mServedView="),
        "raw": text,
    }


def connect(ctx: CommandContext, serial: str | None = None, address: str | None = None) -> dict[str, Any]:
    target_serial = serial or ctx.serial
    if address:
        path = adb_path()
        if not path:
            raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")

        proc = subprocess.run([path, "connect", address], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(5, ctx.timeout_ms / 1000))
        if proc.returncode != 0:
            raise U2CliError(ErrorCode.ACTION_FAILED, "adb connect failed", {"address": address, "stderr": proc.stderr, "stdout": proc.stdout})
        target_serial = address
        devices = list_adb_devices()
        if not any(device.serial == target_serial and device.state == "device" for device in devices):
            raise U2CliError(
                ErrorCode.SESSION_STALE,
                "Connected address is not listed as an online adb device",
                {
                    "address": address,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "devices": [{"serial": device.serial, "state": device.state} for device in devices],
                },
            )
    if not target_serial:
        devices = [device for device in list_adb_devices() if device.state == "device"]
        if len(devices) == 1:
            target_serial = devices[0].serial
        elif len(devices) > 1:
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, "--serial is required when multiple devices are online", {"onlineDevices": [device.serial for device in devices]})
        else:
            raise U2CliError(ErrorCode.DEVICE_NOT_FOUND, "Android device was not found")
    update_session(serial=target_serial, timeout_ms=ctx.timeout_ms)
    return {"serial": target_serial, "address": address, "connected": True}


def disconnect(ctx: CommandContext) -> dict[str, Any]:
    from androidtestclii.session.store import clear_session

    output = None
    if ctx.serial and ":" in ctx.serial:
        path = adb_path()
        if path:
            proc = subprocess.run(
                [path, "disconnect", ctx.serial],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(5, ctx.timeout_ms / 1000),
            )
            output = (proc.stdout or proc.stderr).strip()
            if proc.returncode != 0:
                raise U2CliError(
                    ErrorCode.ACTION_FAILED,
                    "adb disconnect failed",
                    {"serial": ctx.serial, "output": output},
                )
    clear_session()
    return {"serial": ctx.serial, "disconnected": True, "sessionCleared": True, "output": output}


def connection_status(ctx: CommandContext) -> dict[str, Any]:
    devices = list_adb_devices()
    return {
        "serial": ctx.serial,
        "connected": any(device.serial == ctx.serial and device.state == "device" for device in devices) if ctx.serial else False,
        "devices": [{"serial": device.serial, "state": device.state} for device in devices],
    }


def batch(ctx: CommandContext, steps_json: str, out: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        steps = json.loads(steps_json)
    except json.JSONDecodeError as exc:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "batch --steps must be valid JSON", {"error": str(exc)}) from exc
    if not isinstance(steps, list):
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "batch --steps must be a JSON array")
    results: list[dict[str, Any]] = []
    failed: int | None = None
    for index, step in enumerate(steps):
        started = time.perf_counter()
        try:
            value = run_batch_step(ctx, step)
            results.append({"index": index, "command": batch_step_name(step), "success": True, "data": value, "durationMs": int((time.perf_counter() - started) * 1000)})
        except BaseException as exc:
            error = normalize_exception(exc)
            failed = index
            results.append({"index": index, "command": batch_step_name(step), "success": False, "error": {"code": error.code.value, "message": error.message, **({"details": error.details} if error.details else {})}, "durationMs": int((time.perf_counter() - started) * 1000)})
            break
    payload = {"steps": results, "failed": failed, "total": len(steps), "completed": len(results)}
    artifacts: list[dict[str, Any]] = []
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        artifacts.append({"type": "batch-result", "path": str(path), "sizeBytes": path.stat().st_size})
    if failed is not None:
        raise U2CliError(
            ErrorCode.BATCH_STEP_FAILED,
            "batch step failed",
            {**payload, "artifacts": artifacts},
        )
    return payload, artifacts


def run_batch_step(ctx: CommandContext, step: Any) -> Any:
    if not isinstance(step, dict):
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "batch step must be an object", {"step": step})
    command = step.get("command")
    args = step.get("args") or []
    flags = step.get("flags") or {}
    if not isinstance(command, str) or not isinstance(args, list) or not isinstance(flags, dict):
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "batch step requires command, args, and flags", {"step": step})
    if command == "back":
        return back(ctx)
    if command == "home":
        return home(ctx)
    if command == "snapshot":
        target_text = flags.get("targetText") or flags.get("target-text")
        return snapshot(
            ctx,
            interactive=bool(flags.get("interactive") or flags.get("i")),
            full=bool(flags.get("full")),
            target_text=str(target_text) if target_text is not None else None,
        )
    if command in {"click", "press"}:
        if not args:
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, f"{command} step requires target")
        return click(ctx, str(args[0]))
    if command == "fill":
        if len(args) < 2:
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, "fill step requires target and text")
        return fill(ctx, str(args[0]), str(args[1]))
    if command == "wait":
        if len(args) < 3:
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, "wait step requires kind, value, timeout")
        return wait(ctx, str(args[0]), str(args[1]), int(args[2]))
    raise U2CliError(ErrorCode.INVALID_ARGUMENT, "unsupported batch command", {"command": command})


def batch_step_name(step: Any) -> str | None:
    return step.get("command") if isinstance(step, dict) else None


class ResolvedTarget:
    def __init__(
        self,
        *,
        selector: Selector | None = None,
        point: tuple[int, int] | None = None,
        ref: SnapshotRef | None = None,
        ref_name: str | None = None,
        cache_allowed: bool = True,
    ) -> None:
        self.selector = selector
        self.point = point
        self.ref = ref
        self.ref_name = ref_name
        self.cache_allowed = cache_allowed


def resolve_target(ctx: CommandContext, target: Any) -> ResolvedTarget:
    if isinstance(target, dict):
        resolved = resolve_element_target(ctx, target)
        return ResolvedTarget(
            selector=resolved.selector,
            point=resolved.point,
            ref=resolved.ref,
            ref_name=resolved.ref_name,
            cache_allowed=resolved.cache_allowed,
        )
    raw_target = str(target)
    if raw_target.startswith("@e"):
        entry, snapshot = ref_entry(raw_target)
        cache_allowed = not (ctx.serial and snapshot.serial and snapshot.serial != ctx.serial)
        point = point_from_ref(entry) if cache_allowed else None
        selector = selector_from_ref(entry)
        return ResolvedTarget(
            selector=selector,
            point=point,
            ref=entry,
            ref_name=raw_target,
            cache_allowed=cache_allowed,
        )
    coords = parse_coordinate_target(raw_target)
    if coords is not None:
        return ResolvedTarget(point=coords)
    return ResolvedTarget(selector=parse_target_selector(raw_target))


def selector_from_target_for_query(target: Any) -> Selector:
    if isinstance(target, dict):
        ref = target.get("ref")
        snapshot_id = target.get("snapshotId") or target.get("snapshot_id")
        if not isinstance(ref, str):
            raise U2CliError(ErrorCode.INVALID_ARGUMENT, "ref target requires ref", {"target": target})
        entry, _ = ref_entry(ref, snapshot_id=snapshot_id if isinstance(snapshot_id, str) else None)
        selector = selector_from_ref(entry)
        if selector is None:
            raise_invalid_ref(ref, entry)
        return selector
    raw_target = str(target)
    if raw_target.startswith("@e"):
        entry, _ = ref_entry(raw_target)
        selector = selector_from_ref(entry)
        if selector is None:
            raise_invalid_ref(raw_target, entry)
        assert selector is not None
        return selector
    return parse_target_selector(raw_target)


def selector_for_kind(kind: str, value: str) -> Selector:
    mapping = {
        "text": "text",
        "resource-id": "resource_id",
        "resource_id": "resource_id",
        "id": "resource_id",
        "description": "description",
        "desc": "description",
        "class": "class_name",
        "class-name": "class_name",
        "xpath": "xpath",
    }
    field = mapping.get(kind)
    if field is None:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "unsupported wait kind", {"kind": kind})
    if field == "text":
        return selector_from_kwargs(text=value)
    if field == "resource_id":
        return selector_from_kwargs(resource_id=value)
    if field == "description":
        return selector_from_kwargs(description=value)
    if field == "class_name":
        return selector_from_kwargs(class_name=value)
    return selector_from_kwargs(xpath=value)


def selector_from_ref(entry: SnapshotRef) -> Selector | None:
    raw = entry.selector
    if not raw:
        return None
    try:
        return selector_from_kwargs(
            text=raw.get("text"),
            resource_id=raw.get("resourceId") or raw.get("resource_id"),
            description=raw.get("description"),
            class_name=raw.get("className") or raw.get("class_name"),
        )
    except U2CliError:
        return None


def point_from_ref(entry: SnapshotRef) -> tuple[int, int] | None:
    bounds = entry.bounds
    if not bounds:
        return None
    required = ["left", "top", "right", "bottom"]
    if not all(isinstance(bounds.get(key), int) for key in required):
        return None
    return ((bounds["left"] + bounds["right"]) // 2, (bounds["top"] + bounds["bottom"]) // 2)


def parse_coordinate_target(target: str) -> tuple[int, int] | None:
    if "," in target:
        left, right = target.split(",", 1)
        try:
            return int(left), int(right)
        except ValueError:
            return None
    return None


def tap_point(
    ctx: CommandContext,
    point: tuple[int, int],
    *,
    target: str,
    repetitions: int = 1,
    interval_ms: int = 0,
    hold_ms: int | None = None,
    jitter_px: int = 0,
    ref: str | None = None,
) -> dict[str, Any]:
    for index in range(repetitions):
        x, y = jittered_point(point, target, jitter_px)
        if hold_ms is not None:
            input_commands.swipe(ctx, (x, y), (x, y), hold_ms)
        else:
            input_commands.tap(ctx, x, y)
        sleep_between(index, repetitions, interval_ms)
    return {
        "target": target,
        "ref": ref,
        "x": point[0],
        "y": point[1],
        "tapCount": repetitions,
        "holdMs": hold_ms,
        "tapped": hold_ms is None,
        "held": hold_ms is not None,
        "via": "bounds",
    }


def jittered_point(point: tuple[int, int], seed_value: str, jitter_px: int) -> tuple[int, int]:
    if jitter_px <= 0:
        return point
    rng = random.Random(f"{seed_value}:{point[0]}:{point[1]}:{jitter_px}")
    return point[0] + rng.randint(-jitter_px, jitter_px), point[1] + rng.randint(-jitter_px, jitter_px)


def sleep_between(index: int, total: int, interval_ms: int) -> None:
    if interval_ms > 0 and index < total - 1:
        time.sleep(interval_ms / 1000)


def raise_invalid_ref(target: str, ref: SnapshotRef | None) -> None:
    details: dict[str, Any] = {"ref": target}
    if ref is not None:
        details.update(
            {
                "snapshotId": ref.snapshot_id,
                "candidateRefs": [ref.ref] if ref.ref else [],
                "rawArtifactPath": ref.raw_artifact_path,
                "refMapPath": ref.ref_map_path,
                "entry": ref.public_dict(),
            }
        )
    raise U2CliError(
        ErrorCode.SNAPSHOT_REF_INVALID,
        "Snapshot ref does not contain executable bounds or selector",
        {key: value for key, value in details.items() if value is not None},
    )


def selector_with_index(selector: Selector, index: int | None) -> Selector:
    if index is None:
        return selector
    return selector_from_kwargs(
        text=selector.text,
        text_contains=selector.text_contains,
        resource_id=selector.resource_id,
        description=selector.description,
        description_contains=selector.description_contains,
        class_name=selector.class_name,
        xpath=selector.xpath,
        index=index,
    )


def diagnostic_payload(
    selector: Selector,
    state: str,
    timeout_ms: int,
    attempts: int,
    duration_ms: int,
    matched_count: int,
    selected_index: int | None,
) -> dict[str, Any]:
    return {
        "selector": selector.public_dict(),
        "state": state,
        "timeoutMs": timeout_ms,
        "attempts": attempts,
        "durationMs": duration_ms,
        "matchedCount": matched_count,
        "selectedIndex": selected_index,
    }


def cached_matches(ctx: CommandContext, selector: Selector) -> list[SnapshotRef]:
    session = read_session()
    snapshot = session.last_snapshot
    if snapshot is None:
        return []
    if ctx.serial and snapshot.serial and snapshot.serial != ctx.serial:
        return []
    expected = selector.public_dict()
    matches: list[SnapshotRef] = []
    for entry in snapshot.ref_map.values():
        if selector_matches_ref(expected, entry.selector or {}):
            matches.append(entry)
    return matches


def selector_matches_ref(expected: dict[str, Any], raw: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key == "index":
            continue
        if key == "textContains":
            text = raw.get("text")
            if not isinstance(text, str) or str(value) not in text:
                return False
            continue
        if key == "descriptionContains":
            desc = raw.get("description")
            if not isinstance(desc, str) or str(value) not in desc:
                return False
            continue
        if raw.get(key) != value:
            return False
    return True


def _can_use_cached_point_fallback(exc: BaseException, cached: list[SnapshotRef]) -> bool:
    if not cached:
        return False
    if not isinstance(exc, U2CliError):
        return True
    return exc.code in {
        ErrorCode.ELEMENT_NOT_FOUND,
        ErrorCode.ELEMENT_AMBIGUOUS,
        ErrorCode.U2_CONNECT_FAILED,
        ErrorCode.ACTION_FAILED,
        ErrorCode.ACTION_TIMEOUT,
        ErrorCode.INTERNAL_ERROR,
    }


def target_text_summary(snapshot_data: dict[str, Any], target_text: str) -> dict[str, Any]:
    matches = compact_target_matches(snapshot_data, target_text)
    source = "compact"
    if not matches and isinstance(snapshot_data.get("xml"), str):
        source = "xml"
        matches = xml_target_matches(str(snapshot_data["xml"]), target_text)
    return {
        "text": target_text,
        "state": "found" if matches else "unknown",
        "matchedCount": len(matches),
        "selectedIndex": 0 if matches else None,
        "refs": [normalize_snapshot_ref(match["ref"]) for match in matches if match.get("ref")],
        "matches": matches,
        "source": source,
        "canProveAbsence": False,
    }


def target_location(snapshot_data: dict[str, Any], target_text: str) -> dict[str, Any]:
    snapshot = snapshot_data.get("snapshot")
    snapshot_info = snapshot if isinstance(snapshot, dict) else {}
    query = {"text": target_text}
    matches = full_target_matches(snapshot_data, target_text)
    if len(matches) > 1:
        return {
            "query": query,
            "state": "ambiguous",
            "matchedNodeIds": [str(match.get("ref") or match.get("id")) for match in matches],
            "scrollContextIds": [],
            "canScrollToTarget": None,
            "canProveAbsence": False,
            "reason": "multiple-target-matches",
        }
    if len(matches) == 1:
        return {
            "query": query,
            "state": "found",
            "matchedNodeIds": [str(matches[0].get("ref") or matches[0].get("id"))],
            "scrollContextIds": [],
            "canScrollToTarget": None,
            "canProveAbsence": False,
            "reason": (
                "target-found-in-full-snapshot"
                if supports_target_absence(snapshot_info)
                else "target-found-in-diagnostic-snapshot"
            ),
        }
    if supports_target_absence(snapshot_info):
        return {
            "query": query,
            "state": "absent",
            "matchedNodeIds": [],
            "scrollContextIds": [],
            "canScrollToTarget": False,
            "canProveAbsence": True,
            "reason": "full-snapshot-complete-no-match",
        }
    if snapshot_info.get("mode") in {"default", "compact"}:
        return {
            "query": query,
            "state": "requires-full",
            "matchedNodeIds": [],
            "scrollContextIds": [],
            "canScrollToTarget": None,
            "canProveAbsence": False,
            "reason": "compact-snapshot-cannot-prove-offscreen-absence",
        }
    return {
        "query": query,
        "state": "coverage-failed",
        "matchedNodeIds": [],
        "scrollContextIds": [],
        "canScrollToTarget": None,
        "canProveAbsence": False,
        "reason": snapshot_info.get("coverageFailureReason") or "FULL_SNAPSHOT_COVERAGE_FAILED",
    }


def full_target_matches(snapshot_data: dict[str, Any], target_text: str) -> list[dict[str, Any]]:
    matches = []
    for node in snapshot_data.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if target_text in {
            node.get("text"),
            node.get("contentDesc"),
            node.get("desc"),
            node.get("description"),
        }:
            matches.append(node)
    return matches


def supports_target_absence(snapshot_info: dict[str, Any]) -> bool:
    return (
        snapshot_info.get("mode") == "full"
        and bool(snapshot_info.get("full"))
        and bool(snapshot_info.get("complete"))
        and bool(snapshot_info.get("canProveAbsence"))
        and snapshot_info.get("coverage") == "logical-screen"
        and not bool(snapshot_info.get("degraded"))
        and not bool(snapshot_info.get("truncated"))
        and not bool(snapshot_info.get("busy"))
        and not bool(snapshot_info.get("unstable"))
    )


def compact_target_matches(snapshot_data: dict[str, Any], target_text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for node in snapshot_data.get("nodes", []):
        if not isinstance(node, dict):
            continue
        text = node.get("text")
        desc = node.get("contentDesc") or node.get("desc")
        if target_text not in {text, desc}:
            continue
        matches.append(
            {
                "ref": node.get("ref"),
                "text": text,
                "description": desc,
                "resourceId": node.get("resourceId") or node.get("rid"),
                "className": node.get("className") or node.get("cls"),
                "bounds": node.get("bounds"),
            }
        )
    return matches


def normalize_snapshot_ref(value: Any) -> str:
    raw = str(value)
    return raw if raw.startswith("@") else f"@{raw}"


def xml_target_matches(xml: str, target_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    matches: list[dict[str, Any]] = []
    for node in root.iter():
        text = node.attrib.get("text")
        desc = node.attrib.get("content-desc")
        if target_text not in {text, desc}:
            continue
        matches.append(
            {
                "text": text,
                "description": desc,
                "resourceId": node.attrib.get("resource-id"),
                "className": node.attrib.get("class"),
                "bounds": node.attrib.get("bounds"),
            }
        )
    return matches


def _is_system_package(package: str) -> bool:
    return package.startswith("com.android.") or package.startswith("android") or package.startswith("com.google.android.")


def extract_after(text: str, prefix: str) -> str | None:
    marker = text.find(prefix)
    if marker < 0:
        return None
    start = marker + len(prefix)
    end = text.find("\n", start)
    value = text[start:] if end < 0 else text[start:end]
    return value.strip() or None
