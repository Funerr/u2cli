from __future__ import annotations

import time
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.element.selector import Selector
from u2cli.errors import ErrorCode, U2CliError
from u2cli.timeouts import run_with_timeout


def _count(obj: Any) -> int:
    value = getattr(obj, "count", None)
    if callable(value):
        return int(value())
    if value is not None:
        return int(value)
    exists = getattr(obj, "exists", None)
    if callable(exists):
        return 1 if exists() else 0
    if exists is not None:
        return 1 if exists else 0
    return 0


def _exists(obj: Any) -> bool:
    exists = getattr(obj, "exists", None)
    if callable(exists):
        return bool(exists())
    if exists is not None:
        return bool(exists)
    return _count(obj) > 0


def _indexed(obj: Any, index: int) -> Any:
    try:
        return obj[index]
    except TypeError:
        return obj


def locator_for(device: Any, selector: Selector) -> tuple[Any, int]:
    kind, payload = selector.u2_payload()
    if kind == "xpath":
        xp = device.xpath(payload["xpath"])
        count = _count(xp)
        if selector.index is not None and count > 0:
            return _indexed(xp, selector.index), count
        return xp, count
    obj = device(**payload)
    return obj, _count(obj)


def resolve_unique(device: Any, selector: Selector) -> tuple[Any, int]:
    obj, count = locator_for(device, selector)
    selector_payload = selector.public_dict()
    if count == 0:
        raise U2CliError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "No element matched selector",
            {"selector": selector_payload},
        )
    if selector.index is None:
        if count > 1:
            raise U2CliError(
                ErrorCode.ELEMENT_AMBIGUOUS,
                "Multiple elements matched selector",
                {"selector": selector_payload, "matchCount": count},
            )
        return obj, count
    if selector.index >= count:
        raise U2CliError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "Selector index is outside the matched element range",
            {"selector": selector_payload, "matchCount": count},
        )
    return _indexed(obj, selector.index), count


def element_info(obj: Any) -> dict[str, Any]:
    info = getattr(obj, "info", None)
    if callable(info):
        info = info()
    if isinstance(info, dict):
        return {
            "text": info.get("text"),
            "description": info.get("contentDescription") or info.get("description"),
            "resourceId": info.get("resourceName") or info.get("resourceId"),
            "className": info.get("className"),
            "bounds": info.get("bounds"),
            "clickable": info.get("clickable"),
            "enabled": info.get("enabled"),
        }
    return {}


def find(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        obj, count = locator_for(device, selector)
        payload: dict[str, Any] = {
            "selector": selector.public_dict(),
            "matched": count > 0,
            "matchCount": count,
        }
        if count > 0:
            target = _indexed(obj, selector.index or 0)
            payload["element"] = element_info(target)
            payload["nodeId"] = selector.index if selector.index is not None else 0
        return payload

    return run_with_timeout(_run, ctx.timeout_ms)


def exists(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        obj, count = locator_for(device, selector)
        return {
            "selector": selector.public_dict(),
            "exists": count > 0 or _exists(obj),
            "matchCount": count,
        }

    return run_with_timeout(_run, ctx.timeout_ms)


def count(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        _, match_count = locator_for(device, selector)
        return {"selector": selector.public_dict(), "matchCount": match_count}

    return run_with_timeout(_run, ctx.timeout_ms)


def bounds(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        obj, match_count = resolve_unique(device, selector)
        info = element_info(obj)
        raw_bounds = info.get("bounds")
        return {
            "selector": selector.public_dict(),
            "matchCount": match_count,
            "bounds": raw_bounds,
            "element": info,
        }

    return run_with_timeout(_run, ctx.timeout_ms)


def wait(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        started = time.perf_counter()
        deadline = started + (ctx.timeout_ms / 1000)
        while True:
            obj, count = locator_for(device, selector)
            if count > 0 or _exists(obj):
                return {
                    "selector": selector.public_dict(),
                    "matched": True,
                    "elapsedMs": int((time.perf_counter() - started) * 1000),
                }
            if time.perf_counter() >= deadline:
                raise U2CliError(
                    ErrorCode.ELEMENT_NOT_FOUND,
                    "No element matched selector before timeout",
                    {"selector": selector.public_dict()},
                )
            time.sleep(0.1)

    return run_with_timeout(_run, ctx.timeout_ms + 100)
