from __future__ import annotations

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.locks import serial_lock
from u2cli.timeouts import run_with_timeout


def press(ctx: CommandContext, key: str) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)
        run_with_timeout(lambda: device.press(key), ctx.timeout_ms)
    return {"key": key, "pressed": True}


def tap(ctx: CommandContext, x: int, y: int) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)
        run_with_timeout(lambda: device.click(x, y), ctx.timeout_ms)
    return {"x": x, "y": y, "tapped": True}


def swipe(
    ctx: CommandContext,
    from_point: tuple[int, int],
    to_point: tuple[int, int],
    duration_ms: int,
) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> None:
            device.swipe(
                from_point[0],
                from_point[1],
                to_point[0],
                to_point[1],
                duration=duration_ms / 1000,
            )

        run_with_timeout(_run, ctx.timeout_ms)
    return {
        "from": [from_point[0], from_point[1]],
        "to": [to_point[0], to_point[1]],
        "durationMs": duration_ms,
        "swiped": True,
    }


def drag(
    ctx: CommandContext,
    from_point: tuple[int, int],
    to_point: tuple[int, int],
    duration_ms: int,
) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> None:
            if hasattr(device, "drag"):
                device.drag(
                    from_point[0],
                    from_point[1],
                    to_point[0],
                    to_point[1],
                    duration=duration_ms / 1000,
                )
            else:
                device.swipe(
                    from_point[0],
                    from_point[1],
                    to_point[0],
                    to_point[1],
                    duration=duration_ms / 1000,
                )

        run_with_timeout(_run, ctx.timeout_ms)
    return {
        "from": [from_point[0], from_point[1]],
        "to": [to_point[0], to_point[1]],
        "durationMs": duration_ms,
        "dragged": True,
    }


def text(ctx: CommandContext, value: str) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)
        run_with_timeout(lambda: device.send_keys(value), ctx.timeout_ms)
    return {"text": value, "sent": True}


def keyevent(ctx: CommandContext, code: int) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        device = connect_device(ctx.serial, ctx.timeout_ms)

        def _run() -> None:
            if hasattr(device, "keyevent"):
                device.keyevent(code)
            elif hasattr(device, "press"):
                device.press(code)
            else:
                device.shell(f"input keyevent {code}")

        run_with_timeout(_run, ctx.timeout_ms)
    return {"code": code, "pressed": True}
