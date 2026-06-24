from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.input import commands as input_commands
from androidtestclii.unsupported import unsupported_result


def gesture(ctx: CommandContext, parts: list[str], file: str | None = None) -> dict[str, Any]:
    if not parts:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "gesture requires record, replay, pan, fling, pinch, rotate, or transform",
            {"argument": "gesture"},
        )
    kind = parts[0]
    values = parts[1:]
    if kind == "record":
        return gesture_record()
    if kind == "replay":
        return gesture_replay(ctx, file)
    if kind == "pan":
        return gesture_pan(ctx, values)
    if kind == "fling":
        return gesture_fling(ctx, values)
    if kind in {"pinch", "rotate", "transform"}:
        payload: dict[str, Any] = {"args": values}
        if kind == "pinch":
            scale = float(values[0]) if values else 1.0
            payload = {
                "scale": scale,
                "center": {
                    "x": int(float(values[1])) if len(values) > 1 else None,
                    "y": int(float(values[2])) if len(values) > 2 else None,
                },
            }
        return unsupported_multitouch_shape(kind, **payload)
    raise U2CliError(
        ErrorCode.INVALID_ARGUMENT,
        "unsupported gesture kind",
        {"kind": kind},
    )


def gesture_pan(ctx: CommandContext, values: list[str]) -> dict[str, Any]:
    if len(values) < 4:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "gesture pan requires x y dx dy [durationMs]",
            {"args": values},
        )
    x, y, dx, dy = [int(float(item)) for item in values[:4]]
    duration_ms = int(float(values[4])) if len(values) > 4 else 500
    input_commands.swipe(ctx, (x, y), (x + dx, y + dy), duration_ms)
    return {
        "type": "pan",
        "method": "android-swipe",
        "from": {"x": x, "y": y},
        "to": {"x": x + dx, "y": y + dy},
        "durationMs": duration_ms,
    }


def gesture_fling(ctx: CommandContext, values: list[str]) -> dict[str, Any]:
    if len(values) < 3:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "gesture fling requires direction x y [distance] [durationMs]",
            {"args": values},
        )
    direction, x_raw, y_raw = values[:3]
    x = int(float(x_raw))
    y = int(float(y_raw))
    distance = int(float(values[3])) if len(values) > 3 else 600
    duration_ms = int(float(values[4])) if len(values) > 4 else 200
    deltas = {
        "up": (0, -distance),
        "down": (0, distance),
        "left": (-distance, 0),
        "right": (distance, 0),
    }
    if direction not in deltas:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "fling direction must be up, down, left, or right",
            {"direction": direction},
        )
    dx, dy = deltas[direction]
    input_commands.swipe(ctx, (x, y), (x + dx, y + dy), duration_ms)
    return {
        "type": "fling",
        "method": "android-swipe",
        "direction": direction,
        "from": {"x": x, "y": y},
        "to": {"x": x + dx, "y": y + dy},
        "distance": distance,
        "durationMs": duration_ms,
    }


def gesture_record() -> dict[str, Any]:
    return {
        **unsupported_result(
            "gesture.record",
            reason="not_in_scope",
            recovery_hint=(
                "Write a gesture replay JSON file with absolute single-touch points, "
                "or use swipe/gesture pan/fling."
            ),
        ),
        "action": "record",
        "fallbackSuggestion": "Use gesture replay JSON absolute touches, swipe, pan, or fling.",
        "template": {
            "coordinateMode": "absolute",
            "touches": [
                {
                    "finger": "f1",
                    "points": [
                        {"x": 100, "y": 200, "atMs": 0},
                        {"x": 300, "y": 500, "atMs": 250},
                    ],
                }
            ],
        },
    }


def gesture_replay(ctx: CommandContext, file: str | None) -> dict[str, Any]:
    if not file:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "gesture replay requires --file",
            {"argument": "file"},
        )
    path = Path(file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "gesture replay file must be valid JSON",
            {"path": file, "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "gesture replay file must contain a JSON object",
            {"path": file},
        )
    result = replay_single_touch_gesture(ctx, payload)
    result["file"] = file
    return result


def replay_single_touch_gesture(ctx: CommandContext, payload: dict[str, Any]) -> dict[str, Any]:
    touches = payload.get("touches")
    if not isinstance(touches, list) or not touches:
        return {"gesture": payload, "available": False, "reason": "gesture payload is missing touches"}
    if len(touches) != 1:
        return {
            "gesture": payload,
            "available": False,
            "reason": "single fast path only supports one absolute touch",
        }
    coordinate_mode = payload.get("coordinateMode") or "absolute"
    if coordinate_mode != "absolute":
        return {
            "gesture": payload,
            "available": False,
            "reason": "single fast path only supports absolute coordinates",
        }
    points = touches[0].get("points") if isinstance(touches[0], dict) else None
    if not isinstance(points, list) or len(points) < 2:
        return {
            "gesture": payload,
            "available": False,
            "reason": "single-touch replay requires at least two points",
        }
    segments = []
    for start, end in zip(points, points[1:]):
        try:
            x1 = int(round(float(start["x"])))
            y1 = int(round(float(start["y"])))
            x2 = int(round(float(end["x"])))
            y2 = int(round(float(end["y"])))
            start_ms = int(float(start.get("atMs", 0)))
            end_ms = int(float(end.get("atMs", start_ms)))
        except (KeyError, TypeError, ValueError) as exc:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "gesture points require numeric x, y, and atMs fields",
                {"point": {"start": start, "end": end}},
            ) from exc
        duration_ms = max(1, end_ms - start_ms)
        input_commands.swipe(ctx, (x1, y1), (x2, y2), duration_ms)
        segments.append(
            {
                "from": {"x": x1, "y": y1},
                "to": {"x": x2, "y": y2},
                "durationMs": duration_ms,
            }
        )
    return {
        "gesture": payload,
        "available": True,
        "method": "android-single-touch-swipe",
        "segments": segments,
        "segmentCount": len(segments),
        "bulkShell": False,
    }


def screen_multi_touch(ctx: CommandContext, gesture_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(gesture_json)
    except json.JSONDecodeError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--gesture must be valid JSON",
            {"argument": "gesture", "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--gesture must be a JSON object",
            {"argument": "gesture"},
        )
    result = replay_single_touch_gesture(ctx, payload)
    result["input"] = "screen.multi-touch"
    return result


def unsupported_multitouch_shape(kind: str, **payload: Any) -> dict[str, Any]:
    return {
        **unsupported_result(
            f"screen.{kind}",
            recovery_hint="Use screen multi-touch/gesture replay with single absolute touches, or use swipe/pan/fling.",
        ),
        "type": kind,
        **payload,
        "fallbackSuggestion": "Use single-touch replay JSON, swipe, gesture pan, or gesture fling.",
    }
