from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from androidtestclii.context import CommandContext
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.screen import screenshot as screen_screenshot
from androidtestclii.screen import dump as screen_dump
from androidtestclii.screen.snapshot_backend import SnapshotBackendOptions
from androidtestclii.session.store import read_session


def diff_screenshot(
    *,
    baseline: str,
    current: str,
    threshold: str | None = None,
    out: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    threshold_ratio = _parse_threshold(threshold)
    baseline_path = Path(baseline)
    current_path = Path(current)
    baseline_image = _open_rgba_png(baseline_path)
    current_image = _open_rgba_png(current_path)
    if baseline_image.size != current_image.size:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "screenshot dimensions do not match",
            {
                "failureStage": "visual-diff",
                "baseline": {
                    "path": str(baseline_path),
                    "width": baseline_image.width,
                    "height": baseline_image.height,
                },
                "current": {
                    "path": str(current_path),
                    "width": current_image.width,
                    "height": current_image.height,
                },
            },
        )
    diff = ImageChops.difference(baseline_image, current_image)
    changed_pixels = 0
    max_channel_delta = 0
    overlay = current_image.copy()
    overlay_pixels = overlay.load()
    assert overlay_pixels is not None
    for y in range(diff.height):
        for x in range(diff.width):
            delta = diff.getpixel((x, y))
            max_delta = _max_channel_delta(delta)
            if max_delta:
                changed_pixels += 1
                max_channel_delta = max(max_channel_delta, max_delta)
                overlay_pixels[x, y] = (255, 0, 0, 255)
    total_pixels = baseline_image.width * baseline_image.height
    diff_ratio = changed_pixels / total_pixels if total_pixels else 0.0
    output = Path(out) if out else None
    artifacts: list[dict[str, Any]] = []
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(output, format="PNG")
        artifacts.append(
            {"type": "diff", "path": str(output), "description": "screenshot pixel diff overlay"}
        )
    data: dict[str, Any] = {
        "kind": "screenshot",
        "available": True,
        "method": "png-pixel-diff",
        "baseline": str(baseline_path),
        "current": str(current_path),
        "out": str(output) if output else None,
        "width": baseline_image.width,
        "height": baseline_image.height,
        "dimensionsMatch": True,
        "totalPixels": total_pixels,
        "changedPixels": changed_pixels,
        "unchangedPixels": total_pixels - changed_pixels,
        "diffRatio": round(diff_ratio, 6),
        "thresholdRatio": threshold_ratio,
        "maxChannelDelta": max_channel_delta,
        "changed": changed_pixels > 0,
        "passed": diff_ratio <= threshold_ratio,
    }
    return data, artifacts


def diff_snapshot(ctx: CommandContext) -> dict[str, Any]:
    previous_snapshot = _previous_snapshot_data()
    current = screen_dump.dump(ctx, compact=True, snapshot_options=SnapshotBackendOptions())
    diff = snapshot_signature_diff(previous_snapshot, current)
    return {
        "kind": "snapshot",
        "changed": diff["addedCount"] > 0 or diff["removedCount"] > 0,
        "diff": diff,
        "current": {
            "source": _snapshot_source(current),
            "nodeCount": _node_count(current),
            "capturedAt": current.get("capturedAt"),
        },
        "previous": previous_snapshot,
    }


def screenshot_with_overlay_refs(
    ctx: CommandContext,
    out: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data, artifacts = screen_screenshot.screenshot(ctx, out or "artifacts/screenshot.png")
    source = data.get("path")
    if not isinstance(source, str) or not source:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "screenshot result did not include a PNG path",
            {"failureStage": "screenshot-overlay"},
        )
    overlay_data, overlay_path = overlay_snapshot_refs(source)
    merged = dict(data)
    merged.update(overlay_data)
    return merged, [
        *artifacts,
        {
            "type": "screenshot-overlay",
            "path": overlay_path,
            "description": "screenshot with snapshot refs",
        },
    ]


def overlay_snapshot_refs(image_path: str, out_path: str | None = None) -> tuple[dict[str, Any], str]:
    state = read_session()
    last = state.last_snapshot
    if last is None or not last.ref_map:
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "screenshot overlay refs requires a recent snapshot refMap",
            {
                "failureStage": "screenshot-overlay",
                "recoveryHint": "Run snapshot -i or screen dump --compact before screenshot --overlay-refs.",
            },
        )
    source = Path(image_path)
    image = _open_rgba_png(source)
    output = Path(out_path) if out_path else _overlay_path_for(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    draw = ImageDraw.Draw(image)
    overlay_count = 0
    for ref, entry in sorted(last.ref_map.items()):
        bounds = _bounds_tuple(entry.public_dict().get("bounds"), image.width, image.height)
        if bounds is None:
            continue
        left, top, right, bottom = bounds
        if left >= right or top >= bottom:
            continue
        label = ref if ref.startswith("@") else f"@{ref}"
        draw.rectangle([left, top, right, bottom], outline=(255, 64, 64, 255), width=2)
        label_top = max(0, top - 12)
        label_width = max(18, 6 * len(label) + 4)
        draw.rectangle(
            [left, label_top, min(image.width - 1, left + label_width), label_top + 10],
            fill=(255, 64, 64, 255),
        )
        draw.text((left + 2, label_top), label, fill=(255, 255, 255, 255))
        overlay_count += 1
    image.save(output, format="PNG")
    return {"overlayRefs": True, "overlayCount": overlay_count, "overlayPath": str(output)}, str(output)


def snapshot_signature_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_signatures = snapshot_signatures(previous)
    current_signatures = snapshot_signatures(current)
    added = sorted(current_signatures - previous_signatures)
    removed = sorted(previous_signatures - current_signatures)
    common = current_signatures & previous_signatures
    return {
        "addedCount": len(added),
        "removedCount": len(removed),
        "commonCount": len(common),
        "currentCount": len(current_signatures),
        "previousCount": len(previous_signatures),
        "sampleAdded": added[:5],
        "sampleRemoved": removed[:5],
    }


def snapshot_signatures(snapshot: dict[str, Any]) -> set[str]:
    nodes = snapshot.get("nodes")
    if not isinstance(nodes, list):
        nodes = snapshot.get("elements")
    signatures: set[str] = set()
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                signatures.add(_snapshot_node_signature(node))
    if not signatures:
        source = _snapshot_source(snapshot) or ""
        signatures.add(f"snapshot|{source}|nodeCount={_node_count(snapshot)}")
    return signatures


def _open_rgba_png(path: Path) -> Image.Image:
    if not path.exists():
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "PNG file does not exist",
            {"argument": "path", "path": str(path)},
        )
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise U2CliError(
                    ErrorCode.INVALID_ARGUMENT,
                    "visual diagnostics only support PNG files",
                    {"argument": "path", "path": str(path), "format": image.format},
                )
            return image.convert("RGBA")
    except U2CliError:
        raise
    except BaseException as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "failed to read PNG file",
            {"argument": "path", "path": str(path), "error": str(exc)},
        ) from exc


def _parse_threshold(value: str | None) -> float:
    if value is None:
        return 0.0
    raw = value.strip()
    if not raw:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--threshold must not be empty",
            {"argument": "threshold"},
        )
    try:
        if raw.endswith("%"):
            threshold = float(raw[:-1]) / 100
        else:
            threshold = float(raw)
    except ValueError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--threshold must be a ratio or percentage",
            {"argument": "threshold", "value": value},
        ) from exc
    if threshold < 0:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--threshold must be greater than or equal to 0",
            {"argument": "threshold", "value": value},
        )
    return threshold


def _overlay_path_for(source: Path) -> Path:
    suffix = source.suffix or ".png"
    return source.with_name(f"{source.stem}-refs{suffix}")


def _bounds_tuple(value: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        left = int(value["left"])
        top = int(value["top"])
        right = int(value["right"])
        bottom = int(value["bottom"])
    except (KeyError, TypeError, ValueError):
        return None
    return (
        max(0, min(width - 1, left)),
        max(0, min(height - 1, top)),
        max(0, min(width - 1, right)),
        max(0, min(height - 1, bottom)),
    )


def _previous_snapshot_data() -> dict[str, Any]:
    last = read_session().last_snapshot
    if last is None:
        return {}
    data = last.public_dict(include_ref_map=True)
    metadata = data.pop("metadata", {})
    if isinstance(metadata, dict):
        for key in ("screenSize", "package", "activity", "snapshot"):
            if key in metadata and key not in data:
                data[key] = metadata[key]
    data["nodes"] = [entry.node for entry in last.ref_map.values() if isinstance(entry.node, dict)]
    return data


def _snapshot_source(snapshot: dict[str, Any]) -> Any:
    nested = snapshot.get("snapshot")
    if isinstance(nested, dict):
        return nested.get("source") or nested.get("backend")
    return snapshot.get("source")


def _node_count(snapshot: dict[str, Any]) -> int:
    nodes = snapshot.get("nodes")
    if isinstance(nodes, list):
        return len(nodes)
    nested = snapshot.get("snapshot")
    if isinstance(nested, dict):
        raw = nested.get("nodeCount") or nested.get("observedNodeCount")
        return _int_or_zero(raw)
    raw = snapshot.get("nodeCount")
    return _int_or_zero(raw)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _max_channel_delta(delta: float | tuple[int, ...] | None) -> int:
    if delta is None:
        return 0
    if isinstance(delta, tuple):
        return max(int(channel) for channel in delta)
    return int(delta)


def _snapshot_node_signature(node: dict[str, Any]) -> str:
    stable_key = node.get("stableKey")
    if isinstance(stable_key, str) and stable_key:
        return stable_key
    class_name = _signature_value(node, "className", "class", "cls", "type")
    resource_id = _signature_value(node, "resourceId", "resource-id", "rid", "id")
    description = _signature_value(
        node, "contentDesc", "description", "contentDescription", "content-desc", "desc", "label"
    )
    text = _signature_value(node, "text", "name")
    bounds = _bounds_signature(node.get("bounds"))
    return "|".join([class_name, resource_id, description, text, bounds])


def _signature_value(node: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = node.get(key)
        if value is not None:
            return str(value).replace("|", "\\|")
    return ""


def _bounds_signature(bounds: Any) -> str:
    if isinstance(bounds, dict):
        values = [bounds.get("left"), bounds.get("top"), bounds.get("right"), bounds.get("bottom")]
        if any(value is not None for value in values):
            return ",".join("" if value is None else str(value) for value in values)
    if isinstance(bounds, list):
        return ",".join(str(value) for value in bounds)
    if isinstance(bounds, str):
        return bounds.replace("|", "\\|")
    return ""
