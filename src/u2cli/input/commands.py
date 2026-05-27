from __future__ import annotations

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.locks import serial_lock
from u2cli.screen.snapshot_backend import run_adb
from u2cli.timeouts import run_with_timeout


KEYEVENTS = {
    "back": "4",
    "home": "3",
    "recent": "187",
    "app_switch": "187",
    "enter": "66",
    "delete": "67",
    "del": "67",
    "search": "84",
    "menu": "82",
    "power": "26",
    "volume_up": "24",
    "volume_down": "25",
    "volume_mute": "164",
    "camera": "27",
    "up": "19",
    "down": "20",
    "left": "21",
    "right": "22",
    "center": "23",
}


def _adb_input(ctx: CommandContext, *args: object) -> None:
    run_adb(
        ctx.serial,
        ["shell", "input", *[str(arg) for arg in args]],
        timeout_ms=ctx.timeout_ms,
    )


def _keyevent_arg(key: str | int) -> str:
    raw = str(key)
    return KEYEVENTS.get(raw.lower(), raw)


def _input_text_arg(value: str) -> str:
    return value.replace("%", r"\%").replace(" ", "%s")


def press(ctx: CommandContext, key: str) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> None:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.press(key)
            except BaseException:
                _adb_input(ctx, "keyevent", _keyevent_arg(key))

        run_with_timeout(_run, ctx.timeout_ms)
    return {"key": key, "pressed": True}


def tap(ctx: CommandContext, x: int, y: int) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> None:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.click(x, y)
            except BaseException:
                _adb_input(ctx, "tap", x, y)

        run_with_timeout(_run, ctx.timeout_ms)
    return {"x": x, "y": y, "tapped": True}


def swipe(
    ctx: CommandContext,
    from_point: tuple[int, int],
    to_point: tuple[int, int],
    duration_ms: int,
) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> None:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.swipe(
                    from_point[0],
                    from_point[1],
                    to_point[0],
                    to_point[1],
                    duration=duration_ms / 1000,
                )
            except BaseException:
                _adb_input(ctx, "swipe", *from_point, *to_point, duration_ms)

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
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> None:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
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
            except BaseException:
                _adb_input(ctx, "swipe", *from_point, *to_point, duration_ms)

        run_with_timeout(_run, ctx.timeout_ms)
    return {
        "from": [from_point[0], from_point[1]],
        "to": [to_point[0], to_point[1]],
        "durationMs": duration_ms,
        "dragged": True,
    }


def text(ctx: CommandContext, value: str) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> None:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                device.send_keys(value)
            except BaseException:
                _adb_input(ctx, "text", _input_text_arg(value))

        run_with_timeout(_run, ctx.timeout_ms)
    return {"text": value, "sent": True}


def keyevent(ctx: CommandContext, code: int) -> dict[str, object]:
    with serial_lock(ctx.serial, ctx.timeout_ms):
        try:
            device = connect_device(ctx.serial, ctx.timeout_ms)
        except BaseException:
            device = None

        def _run() -> None:
            try:
                if device is None:
                    raise RuntimeError("uiautomator2 connection unavailable")
                if hasattr(device, "keyevent"):
                    device.keyevent(code)
                elif hasattr(device, "press"):
                    device.press(str(code))
                else:
                    device.shell(f"input keyevent {code}")
            except BaseException:
                _adb_input(ctx, "keyevent", code)

        run_with_timeout(_run, ctx.timeout_ms)
    return {"code": code, "pressed": True}
