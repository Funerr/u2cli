from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Any

from androidtestclii.element.selector import bounds_to_list, short_class_name
from androidtestclii.session.store import normalize_ref, snapshot_id_for, utc_now_iso

WRAPPER_CLASSES = {
    "FrameLayout",
    "LinearLayout",
    "RelativeLayout",
    "ConstraintLayout",
    "ViewGroup",
    "androidx.constraintlayout.widget.ConstraintLayout",
}

HEADING_HINTS = {"title", "header", "heading", "toolbar"}


def build_compact_snapshot(
    xml: str,
    device_info: dict[str, Any] | None = None,
    *,
    captured_at: str | None = None,
    serial: str | None = None,
    backend: str | None = None,
    snapshot_id: str | None = None,
    raw_artifact_path: str | None = None,
    compact_artifact_path: str | None = None,
    ref_map_path: str | None = None,
) -> dict[str, Any]:
    root = ET.fromstring(xml)
    info = device_info or {}
    width, height = screen_size(info)
    package = normalize_text(root.attrib.get("package") or info.get("currentPackageName"))
    activity = normalize_text(info.get("currentActivityName") or info.get("activity"))
    captured_at_value = captured_at or utc_now_iso()
    snapshot_id_value = snapshot_id or snapshot_id_for(
        captured_at=captured_at_value,
        raw_xml=xml,
        serial=serial,
        backend=backend,
    )

    nodes: list[dict[str, Any]] = []
    raw_ordinal = 0
    ref_counter = 0

    def next_ref() -> str:
        nonlocal ref_counter
        ref = f"@e{ref_counter}"
        ref_counter += 1
        return ref

    def walk(element: ET.Element, depth: int, parent_path: list[int], parent_ref: str | None) -> None:
        nonlocal raw_ordinal
        for index, child in enumerate(list(element)):
            path = [*parent_path, index]
            raw_ordinal += 1
            node = build_node(
                child,
                depth=depth + 1,
                raw_ordinal=raw_ordinal,
                raw_node_path=path,
                parent_ref=parent_ref,
                package_name=package,
                screen_width=width,
                screen_height=height,
            )
            child_nodes: list[dict[str, Any]] = []
            walk_collect(child, depth + 1, path, parent_ref, child_nodes)
            if should_keep(node, child_nodes):
                ref = next_ref()
                node["ref"] = ref
                node["parentRef"] = parent_ref
                node["count"] = 1
                node["foldedCount"] = 1
                node["children"] = child_nodes
                for child_node in child_nodes:
                    if child_node.get("parentRef") == parent_ref:
                        child_node["parentRef"] = ref
                node["signature"] = node_signature(node, child_nodes)
                nodes.append(node)
                nodes.extend(child_nodes)
            else:
                for child_node in child_nodes:
                    if child_node.get("parentRef") == parent_ref:
                        child_node["parentRef"] = parent_ref
                nodes.extend(child_nodes)

    def walk_collect(
        element: ET.Element,
        depth: int,
        raw_node_path: list[int],
        parent_ref: str | None,
        out: list[dict[str, Any]],
    ) -> None:
        nonlocal raw_ordinal
        for index, child in enumerate(list(element)):
            path = [*raw_node_path, index]
            raw_ordinal += 1
            node = build_node(
                child,
                depth=depth + 1,
                raw_ordinal=raw_ordinal,
                raw_node_path=path,
                parent_ref=parent_ref,
                package_name=package,
                screen_width=width,
                screen_height=height,
            )
            child_nodes: list[dict[str, Any]] = []
            walk_collect(child, depth + 1, path, parent_ref, child_nodes)
            if should_keep(node, child_nodes):
                ref = next_ref()
                node["ref"] = ref
                node["parentRef"] = parent_ref
                node["count"] = 1
                node["foldedCount"] = 1
                node["children"] = child_nodes
                for child_node in child_nodes:
                    if child_node.get("parentRef") == parent_ref:
                        child_node["parentRef"] = ref
                node["signature"] = node_signature(node, child_nodes)
                out.append(node)
                out.extend(child_nodes)
            else:
                for child_node in child_nodes:
                    if child_node.get("parentRef") == parent_ref:
                        child_node["parentRef"] = parent_ref
                out.extend(child_nodes)

    walk(root, 0, [], None)
    compact_nodes = fold_duplicate_siblings(nodes)
    compact_nodes = renumber_refs(compact_nodes)
    for index, node in enumerate(compact_nodes):
        node.pop("signature", None)
        node.pop("_signature", None)
        node.pop("children", None)
        node["id"] = index
        node["stableKey"] = node.get("stableKey") or stable_key_for_node(node)
        if "ref" not in node:
            node["ref"] = f"@e{index}"
        node["count"] = int(node.get("count") or node.get("foldedCount") or 1)
        node["foldedCount"] = node["count"]

    return {
        "snapshotId": snapshot_id_value,
        "capturedAt": captured_at_value,
        "screenSize": [width, height],
        "package": package,
        "activity": activity,
        "rawArtifactPath": raw_artifact_path,
        "compactArtifactPath": compact_artifact_path,
        "refMapPath": ref_map_path,
        "nodes": compact_nodes,
    }


def renumber_refs(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: dict[str, str] = {}
    for index, node in enumerate(nodes):
        old_ref = node.get("ref")
        if isinstance(old_ref, str):
            mapping[old_ref] = f"@e{index}"
    for node in nodes:
        old_ref = node.get("ref")
        if isinstance(old_ref, str):
            node["ref"] = mapping.get(old_ref, old_ref)
        parent_ref = node.get("parentRef")
        if isinstance(parent_ref, str):
            node["parentRef"] = mapping.get(parent_ref)
            node["parent"] = node["parentRef"]
    return nodes


def build_ref_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = snapshot.get("snapshotId")
    raw_artifact_path = snapshot.get("rawArtifactPath")
    compact_artifact_path = snapshot.get("compactArtifactPath")
    ref_map_path = snapshot.get("refMapPath")
    refs: dict[str, Any] = {}
    for node in snapshot.get("nodes", []):
        if not isinstance(node, dict):
            continue
        ref = canonical_ref(node.get("ref"))
        if ref is None:
            continue
        selector: dict[str, Any] = {}
        if node.get("text"):
            selector["text"] = node["text"]
        if node.get("resourceId"):
            selector["resourceId"] = node["resourceId"]
        if node.get("contentDesc"):
            selector["description"] = node["contentDesc"]
        if node.get("className"):
            selector["className"] = node["className"]
        entry = {
            "ref": ref,
            "snapshotId": snapshot_id,
            "stableKey": node.get("stableKey"),
            "rawNodePath": node.get("rawNodePath"),
            "rawOrdinal": node.get("rawOrdinal"),
            "selector": selector or None,
            "bounds": bounds_dict(node.get("bounds")),
            "center": node.get("center"),
            "text": node.get("text"),
            "contentDesc": node.get("contentDesc"),
            "resourceId": node.get("resourceId"),
            "className": node.get("className"),
            "packageName": node.get("packageName"),
            "role": node.get("role"),
            "parentRef": node.get("parentRef"),
            "actions": node.get("actions"),
            "visible": node.get("visible"),
            "enabled": node.get("enabled"),
            "clickable": node.get("clickable"),
            "focusable": node.get("focusable"),
            "scrollable": node.get("scrollable"),
            "selected": node.get("selected"),
            "checked": node.get("checked"),
            "rawArtifactPath": raw_artifact_path,
            "compactArtifactPath": compact_artifact_path,
            "refMapPath": ref_map_path,
            "node": node,
        }
        refs[ref] = {key: value for key, value in entry.items() if value is not None}
    return {
        "snapshotId": snapshot_id,
        "capturedAt": snapshot.get("capturedAt"),
        "rawArtifactPath": raw_artifact_path,
        "compactArtifactPath": compact_artifact_path,
        "refMapPath": ref_map_path,
        "refs": refs,
    }


def compact_artifacts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    raw_path = snapshot.get("rawArtifactPath")
    compact_path = snapshot.get("compactArtifactPath")
    ref_map_path = snapshot.get("refMapPath")
    if raw_path:
        artifacts.append(
            {"type": "raw-snapshot", "path": str(raw_path), "description": "raw UI hierarchy xml"}
        )
    if compact_path:
        artifacts.append(
            {
                "type": "compact-snapshot",
                "path": str(compact_path),
                "description": "compact snapshot json",
            }
        )
    if ref_map_path:
        artifacts.append(
            {
                "type": "snapshot-ref-map",
                "path": str(ref_map_path),
                "description": "snapshot ref map json",
            }
        )
    return artifacts


def canonical_ref(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return normalize_ref(value)


def screen_size(device_info: dict[str, Any]) -> tuple[int | None, int | None]:
    raw_display = device_info.get("display")
    display = raw_display if isinstance(raw_display, dict) else {}
    width = int_or_none(device_info.get("displayWidth") or display.get("width") or device_info.get("width"))
    height = int_or_none(
        device_info.get("displayHeight") or display.get("height") or device_info.get("height")
    )
    return width, height


def build_node(
    element: ET.Element,
    *,
    depth: int,
    raw_ordinal: int,
    raw_node_path: list[int],
    parent_ref: str | None,
    package_name: str | None,
    screen_width: int | None,
    screen_height: int | None,
) -> dict[str, Any]:
    attrs = element.attrib
    text = normalize_text(attrs.get("text"))
    text_truncated = False
    if text and len(text) > 200:
        text = text[:200]
        text_truncated = True
    content_desc = normalize_text(attrs.get("content-desc"))
    resource_id = normalize_text(attrs.get("resource-id"))
    class_name = short_class_name(attrs.get("class"))
    node_package = normalize_text(attrs.get("package") or package_name)
    bounds = parse_bounds(attrs.get("bounds"))
    center = bounds_center(bounds)
    visible = is_visible(attrs, bounds, screen_width, screen_height, text, content_desc, resource_id)
    enabled = bool_attr(attrs.get("enabled"), default=True)
    clickable = bool_attr(attrs.get("clickable"))
    focusable = bool_attr(attrs.get("focusable"))
    scrollable = bool_attr(attrs.get("scrollable"))
    selected = bool_attr(attrs.get("selected"))
    checked = bool_attr(attrs.get("checked"))
    long_clickable = bool_attr(attrs.get("long-clickable"))
    checkable = bool_attr(attrs.get("checkable"))
    editable = class_name == "EditText" or bool_attr(attrs.get("editable"))
    actions = actions_for(
        clickable=clickable,
        focusable=focusable,
        scrollable=scrollable,
        long_clickable=long_clickable,
        checkable=checkable,
        editable=editable,
    )
    role = role_for(class_name, actions, text, content_desc, resource_id)
    if class_name and class_name in WRAPPER_CLASSES and not text and not content_desc and not actions:
        role = "container"
    node = {
        "rawNodePath": raw_node_path,
        "rawOrdinal": raw_ordinal,
        "depth": depth,
        "parentRef": parent_ref,
        "text": text,
        "contentDesc": content_desc,
        "resourceId": resource_id,
        "className": class_name,
        "packageName": node_package,
        "role": role,
        "bounds": bounds,
        "center": center,
        "visible": visible,
        "enabled": enabled,
        "clickable": clickable,
        "focusable": focusable,
        "scrollable": scrollable,
        "selected": selected,
        "checked": checked,
        "actions": actions,
        "cls": class_name,
        "desc": content_desc,
        "rid": resource_id,
        "parent": parent_ref,
    }
    if text_truncated:
        node["textTruncated"] = True
    node["stableKey"] = stable_key_for_node(node)
    node["_signature"] = node_signature(node, [])
    return node


def should_keep(node: dict[str, Any], child_nodes: list[dict[str, Any]]) -> bool:
    if not node.get("visible"):
        return False
    if node.get("text") or node.get("contentDesc") or node.get("resourceId"):
        return True
    if node.get("actions"):
        return True
    if node.get("role") in {"heading", "label"}:
        return True
    if node.get("className") and node.get("className") not in WRAPPER_CLASSES and child_nodes:
        return True
    return False


def fold_duplicate_siblings(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    groups: dict[str | None, list[dict[str, Any]]] = {}
    for node in nodes:
        groups.setdefault(node.get("parentRef"), []).append(node)

    skip_refs: set[str] = set()
    folded_counts: dict[str, int] = {}
    for siblings in groups.values():
        seen: dict[str, dict[str, Any]] = {}
        for node in siblings:
            signature = str(node.get("signature") or node_signature(node, []))
            ref = str(node.get("ref") or "")
            if signature in seen:
                rep = seen[signature]
                rep_ref = str(rep.get("ref") or "")
                folded_counts[rep_ref] = folded_counts.get(rep_ref, int(rep.get("foldedCount") or 1)) + int(
                    node.get("foldedCount") or 1
                )
                skip_refs.add(ref)
            else:
                seen[signature] = node
    for node in nodes:
        ref = str(node.get("ref") or "")
        if ref in skip_refs:
            continue
        count = folded_counts.get(ref) or int(node.get("foldedCount") or 1)
        node["foldedCount"] = count
        node["count"] = count
        ordered.append(node)
    return ordered


def node_signature(node: dict[str, Any], child_nodes: list[dict[str, Any]]) -> str:
    parts = [
        str(node.get("role") or ""),
        str(node.get("text") or ""),
        str(node.get("contentDesc") or ""),
        str(node.get("resourceId") or ""),
        str(node.get("className") or ""),
        ",".join(str(action) for action in node.get("actions") or []),
        str(node.get("visible")),
        str(node.get("enabled")),
        str(node.get("clickable")),
        str(node.get("focusable")),
        str(node.get("scrollable")),
        str(node.get("selected")),
        str(node.get("checked")),
        "|".join(str(child.get("stableKey") or "") for child in child_nodes),
    ]
    return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()


def stable_key_for_node(node: dict[str, Any]) -> str:
    parts = [
        str(node.get("role") or ""),
        str(node.get("text") or ""),
        str(node.get("contentDesc") or ""),
        str(node.get("resourceId") or ""),
        str(node.get("className") or ""),
        str(node.get("packageName") or ""),
        bounds_signature(node.get("bounds")),
        str(node.get("rawNodePath") or []),
    ]
    return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()


def role_for(
    class_name: str | None,
    actions: list[str],
    text: str | None,
    content_desc: str | None,
    resource_id: str | None,
) -> str | None:
    if not class_name:
        if text:
            return "text"
        if content_desc:
            return "label"
        return None
    lower = class_name.lower()
    if "button" in lower:
        return "button"
    if "edittext" in lower or "textfield" in lower or "input" in lower:
        return "input"
    if "checkbox" in lower:
        return "checkbox"
    if "radiobutton" in lower:
        return "radio"
    if "switch" in lower:
        return "switch"
    if "scroll" in lower or "list" in lower or "recycler" in lower:
        return "scrollable"
    if "toolbar" in lower:
        return "heading"
    if class_name in WRAPPER_CLASSES:
        return "container"
    if text:
        return "text"
    if content_desc:
        return "label"
    if resource_id:
        return "control" if actions else "container"
    return "container"


def actions_for(
    *,
    clickable: bool,
    focusable: bool,
    scrollable: bool,
    long_clickable: bool,
    checkable: bool,
    editable: bool,
) -> list[str]:
    actions: list[str] = []
    if clickable:
        actions.append("click")
    if long_clickable:
        actions.append("longClick")
    if focusable or editable:
        actions.append("focus")
    if editable:
        actions.append("setText")
    if scrollable:
        actions.append("scroll")
    if checkable:
        actions.append("toggle")
    return actions


def is_visible(
    attrs: dict[str, str],
    bounds: list[int] | None,
    screen_width: int | None,
    screen_height: int | None,
    text: str | None,
    content_desc: str | None,
    resource_id: str | None,
) -> bool:
    visible_attr = attrs.get("visible-to-user")
    if visible_attr is not None and visible_attr.lower() == "false":
        return False
    if bounds is None:
        return bool(text or content_desc or resource_id or attrs.get("clickable") or attrs.get("focusable"))
    left, top, right, bottom = bounds
    if left >= right or top >= bottom:
        return False
    if screen_width is None or screen_height is None:
        return True
    return not (right <= 0 or bottom <= 0 or left >= screen_width or top >= screen_height)


def parse_bounds(value: str | None) -> list[int] | None:
    return bounds_to_list(value)


def bounds_center(bounds: list[int] | None) -> dict[str, int] | None:
    if not bounds:
        return None
    left, top, right, bottom = bounds
    return {"x": (left + right) // 2, "y": (top + bottom) // 2}


def bounds_dict(bounds: Any) -> dict[str, int] | None:
    if not isinstance(bounds, list) or len(bounds) != 4:
        return None
    try:
        left, top, right, bottom = [int(part) for part in bounds]
    except (TypeError, ValueError):
        return None
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def bounds_signature(bounds: Any) -> str:
    if not isinstance(bounds, list) or len(bounds) != 4:
        return ""
    try:
        return ",".join(str(int(part)) for part in bounds)
    except (TypeError, ValueError):
        return ""


def bool_attr(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).lower() == "true"


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    stripped = " ".join(text.split())
    return stripped or None


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
