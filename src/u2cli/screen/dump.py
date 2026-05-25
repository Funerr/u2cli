from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.element.selector import bounds_to_list, short_class_name
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
                "cls": short_class_name(attrs.get("class")),
                "text": node_text,
                "desc": desc,
                "rid": rid,
                "bounds": bounds_to_list(attrs.get("bounds")),
                "clickable": _bool(attrs.get("clickable")),
                "enabled": _bool(attrs.get("enabled")),
                "checked": _bool(attrs.get("checked")),
                "selected": _bool(attrs.get("selected")),
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


def dump(ctx: CommandContext, compact: bool = False) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        xml = device.dump_hierarchy()
        if not compact:
            return {"xml": xml}
        info = dict(getattr(device, "info", {}) or {})
        return compact_projection(xml, info)

    return run_with_timeout(_run, ctx.timeout_ms)
