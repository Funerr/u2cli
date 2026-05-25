from __future__ import annotations

from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.element.query import resolve_unique
from u2cli.element.selector import Selector
from u2cli.errors import ErrorCode, U2CliError
from u2cli.locks import serial_lock
from u2cli.timeouts import run_with_timeout


def _call(obj: Any, *names: str, **kwargs: Any) -> Any:
    for name in names:
        method = getattr(obj, name, None)
        if callable(method):
            return method(**kwargs) if kwargs else method()
    raise U2CliError(ErrorCode.ACTION_FAILED, "Element does not support requested action")


def click(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, count = resolve_unique(device, selector)
            _call(obj, "click")
            return {"selector": selector.public_dict(), "clicked": True, "matchCount": count}

        return run_with_timeout(_run, ctx.timeout_ms)


def long_click(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, _ = resolve_unique(device, selector)
            _call(obj, "long_click", "longClick")
            return {
                "selector": selector.public_dict(),
                "clicked": True,
                "durationMs": ctx.timeout_ms,
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def set_text(ctx: CommandContext, selector: Selector, text: str) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, _ = resolve_unique(device, selector)
            method = getattr(obj, "set_text", None) or getattr(obj, "setText", None)
            if not callable(method):
                raise U2CliError(ErrorCode.ACTION_FAILED, "Element does not support set_text")
            method(text)
            return {"selector": selector.public_dict(), "setText": True, "text": text}

        return run_with_timeout(_run, ctx.timeout_ms)


def clear_text(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, _ = resolve_unique(device, selector)
            method = getattr(obj, "clear_text", None) or getattr(obj, "clearText", None)
            if callable(method):
                method()
            else:
                setter = getattr(obj, "set_text", None) or getattr(obj, "setText", None)
                if not callable(setter):
                    raise U2CliError(
                        ErrorCode.ACTION_FAILED,
                        "Element does not support clear_text",
                    )
                setter("")
            return {"selector": selector.public_dict(), "cleared": True}

        return run_with_timeout(_run, ctx.timeout_ms)


def get_text(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        obj, _ = resolve_unique(device, selector)
        value = getattr(obj, "get_text", None)
        if callable(value):
            text = value()
        else:
            text = getattr(obj, "text", None)
            if callable(text):
                text = text()
            if text is None:
                info = getattr(obj, "info", None)
                if callable(info):
                    info = info()
                text = info.get("text") if isinstance(info, dict) else None
        return {"selector": selector.public_dict(), "text": text}

    return run_with_timeout(_run, ctx.timeout_ms)


def swipe(
    ctx: CommandContext,
    selector: Selector,
    direction: str,
    percent: float = 0.6,
    steps: int = 20,
) -> dict[str, Any]:
    if direction not in {"up", "down", "left", "right"}:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "direction must be one of up, down, left, or right",
            {"direction": direction},
        )
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, count = resolve_unique(device, selector)
            method = getattr(obj, "swipe", None)
            if callable(method):
                try:
                    method(direction, percent=percent, steps=steps)
                except TypeError:
                    method(direction)
            else:
                raise U2CliError(ErrorCode.ACTION_FAILED, "Element does not support swipe")
            return {
                "selector": selector.public_dict(),
                "direction": direction,
                "percent": percent,
                "steps": steps,
                "matchCount": count,
                "swiped": True,
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def drag_to(
    ctx: CommandContext,
    selector: Selector,
    x: int,
    y: int,
    duration_ms: int = 500,
) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, count = resolve_unique(device, selector)
            method = getattr(obj, "drag_to", None) or getattr(obj, "dragTo", None)
            if not callable(method):
                raise U2CliError(ErrorCode.ACTION_FAILED, "Element does not support drag_to")
            try:
                method(x, y, duration=duration_ms / 1000)
            except TypeError:
                method(x, y)
            return {
                "selector": selector.public_dict(),
                "to": [x, y],
                "durationMs": duration_ms,
                "matchCount": count,
                "dragged": True,
            }

        return run_with_timeout(_run, ctx.timeout_ms)


def scroll_to(ctx: CommandContext, selector: Selector) -> dict[str, Any]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> dict[str, Any]:
            obj, count = resolve_unique(device, selector)
            method = getattr(obj, "scroll_to", None) or getattr(obj, "scrollTo", None)
            if callable(method):
                method()
            else:
                raise U2CliError(ErrorCode.ACTION_FAILED, "Element does not support scroll_to")
            return {"selector": selector.public_dict(), "matchCount": count, "scrolled": True}

        return run_with_timeout(_run, ctx.timeout_ms)
