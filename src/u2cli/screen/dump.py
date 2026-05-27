from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.element.selector import bounds_to_list, short_class_name
from u2cli.screen.snapshot_backend import SnapshotBackendOptions, capture_snapshot
from u2cli.session.store import LastSnapshot, SnapshotRef, update_session, utc_now_iso
from u2cli.timeouts import run_with_timeout


def _bool(value: str | None) -> bool:
    return str(value).lower() == "true"


def compact_projection(xml: str, device_info: dict[str, Any] | None = None) -> dict[str, Any]:
    root = ET.fromstring(xml)
    nodes: list[dict[str, Any]] = []

    info = device_info or {}
    raw_display = info.get("display")
    display = raw_display if isinstance(raw_display, dict) else {}
    width = info.get("displayWidth") or display.get("width") or info.get("width")
    height = info.get("displayHeight") or display.get("height") or info.get("height")
    package = root.attrib.get("package") or info.get("currentPackageName")
    activity = info.get("currentActivityName") or info.get("activity")

    def walk(element: ET.Element, depth: int, parent_kept: int | None) -> None:
        attrs = element.attrib
        text = attrs.get("text") or None
        desc = attrs.get("content-desc") or None
        rid = attrs.get("resource-id") or None
        flags = [
            _bool(attrs.get("clickable")),
            _bool(attrs.get("long-clickable")),
            _bool(attrs.get("scrollable")),
            _bool(attrs.get("checkable")),
        ]
        keep = bool(text or desc or rid or any(flags))
        current_parent = parent_kept
        if keep:
            node_id = len(nodes)
            node_text = text
            node: dict[str, Any] = {
                "id": node_id,
                "ref": f"e{node_id}",
                "cls": short_class_name(attrs.get("class")),
                "text": node_text,
                "desc": desc,
                "rid": rid,
                "bounds": bounds_to_list(attrs.get("bounds")),
                "clickable": _bool(attrs.get("clickable")),
                "longClickable": _bool(attrs.get("long-clickable")),
                "focusable": _bool(attrs.get("focusable")),
                "enabled": _bool(attrs.get("enabled")),
                "checked": _bool(attrs.get("checked")),
                "selected": _bool(attrs.get("selected")),
                "scrollable": _bool(attrs.get("scrollable")),
                "depth": depth,
                "parent": parent_kept,
            }
            if node_text and len(node_text) > 200:
                node["text"] = node_text[:200]
                node["textTruncated"] = True
            nodes.append(node)
            current_parent = node_id
        for child in list(element):
            walk(child, depth + 1, current_parent)

    walk(root, 0, None)
    return {"screenSize": [width, height], "package": package, "activity": activity, "nodes": nodes}


def ref_map_from_projection(projected: dict[str, Any]) -> dict[str, SnapshotRef]:
    refs: dict[str, SnapshotRef] = {}
    for node in projected.get("nodes", []):
        if not isinstance(node, dict):
            continue
        ref = node.get("ref")
        if not isinstance(ref, str):
            continue
        selector: dict[str, Any] = {}
        if node.get("text"):
            selector["text"] = node["text"]
        if node.get("rid"):
            selector["resourceId"] = node["rid"]
        if node.get("desc"):
            selector["description"] = node["desc"]
        if node.get("cls"):
            selector["className"] = node["cls"]
        bounds = bounds_dict(node.get("bounds"))
        refs[f"@{ref}"] = SnapshotRef(
            selector=selector or None,
            bounds=bounds,
            text=node.get("text"),
            className=node.get("cls"),
            resourceId=node.get("rid"),
            description=node.get("desc"),
            node=node,
        )
    return refs


def bounds_dict(value: Any) -> dict[str, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        left, top, right, bottom = [int(part) for part in value]
    except (TypeError, ValueError):
        return None
    return {"left": left, "top": top, "right": right, "bottom": bottom}


class LazyDevice:
    def __init__(self, ctx: CommandContext) -> None:
        self._ctx = ctx
        self._device: Any | None = None

    @property
    def connected(self) -> bool:
        return self._device is not None

    @property
    def info(self) -> dict[str, Any]:
        return dict(getattr(self._connect(), "info", {}) or {})

    def dump_hierarchy(self) -> str:
        return str(self._connect().dump_hierarchy())

    def _connect(self) -> Any:
        if self._device is None:
            self._device = connect_device(self._ctx.serial, self._ctx.timeout_ms)
        return self._device


def dump(
    ctx: CommandContext,
    compact: bool = False,
    snapshot_options: SnapshotBackendOptions | None = None,
) -> dict[str, Any]:
    device = LazyDevice(ctx)

    def _run() -> dict[str, Any]:
        capture = capture_snapshot(device, ctx.serial, ctx.timeout_ms, snapshot_options)
        if not compact:
            return {"xml": capture.xml, "snapshot": capture.metadata}
        info = device.info if device.connected else {}
        projected = compact_projection(capture.xml, info)
        projected["snapshot"] = capture.metadata
        ref_map = ref_map_from_projection(projected)
        captured_at = utc_now_iso()
        projected["capturedAt"] = captured_at
        if ctx.serial:
            update_session(
                serial=ctx.serial,
                timeout_ms=ctx.timeout_ms,
                last_snapshot=LastSnapshot(
                    capturedAt=captured_at,
                    serial=ctx.serial,
                    refMap=ref_map,
                    metadata={
                        "screenSize": projected.get("screenSize"),
                        "package": projected.get("package"),
                        "activity": projected.get("activity"),
                        "snapshot": capture.metadata,
                    },
                ),
            )
        return projected

    return run_with_timeout(_run, ctx.timeout_ms)
