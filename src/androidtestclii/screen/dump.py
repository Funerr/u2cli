from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.device.connect import connect_device
from androidtestclii.element.selector import bounds_to_list, short_class_name
from androidtestclii.screen.compact_snapshot import (
    build_compact_snapshot,
    build_ref_map,
    compact_artifacts,
    canonical_ref,
)
from androidtestclii.screen.snapshot_backend import SnapshotBackendOptions, capture_snapshot
from androidtestclii.session.store import (
    LastSnapshot,
    SnapshotRef,
    snapshot_artifact_dir,
    update_session,
    utc_now_iso,
)
from androidtestclii.timeouts import run_with_timeout


FULL_COVERAGE_FAILURE = "FULL_SNAPSHOT_COVERAGE_FAILED"


def _bool(value: str | None) -> bool:
    return str(value).lower() == "true"


def compact_projection(xml: str, device_info: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_compact_snapshot(xml, device_info)


def full_projection(xml: str, device_info: dict[str, Any] | None = None) -> dict[str, Any]:
    root = ET.fromstring(xml)
    nodes: list[dict[str, Any]] = []

    info = device_info or {}
    raw_display = info.get("display")
    display = raw_display if isinstance(raw_display, dict) else {}
    width = info.get("displayWidth") or display.get("width") or info.get("width")
    height = info.get("displayHeight") or display.get("height") or info.get("height")
    package = root.attrib.get("package") or info.get("currentPackageName")
    activity = info.get("currentActivityName") or info.get("activity")

    def walk(element: ET.Element, depth: int, parent: int | None) -> None:
        attrs = element.attrib
        node_id = len(nodes)
        node: dict[str, Any] = {
            "id": node_id,
            "ref": f"e{node_id}",
            "cls": short_class_name(attrs.get("class")),
            "text": attrs.get("text") or None,
            "desc": attrs.get("content-desc") or None,
            "rid": attrs.get("resource-id") or None,
            "bounds": bounds_to_list(attrs.get("bounds")),
            "clickable": _bool(attrs.get("clickable")),
            "longClickable": _bool(attrs.get("long-clickable")),
            "focusable": _bool(attrs.get("focusable")),
            "enabled": _bool(attrs.get("enabled")),
            "checked": _bool(attrs.get("checked")),
            "selected": _bool(attrs.get("selected")),
            "scrollable": _bool(attrs.get("scrollable")),
            "visible": _bool(attrs.get("visible-to-user")) if attrs.get("visible-to-user") else None,
            "depth": depth,
            "parent": parent,
        }
        nodes.append({key: value for key, value in node.items() if value is not None})
        for child in list(element):
            walk(child, depth + 1, node_id)

    walk(root, 0, None)
    return {"screenSize": [width, height], "package": package, "activity": activity, "nodes": nodes}


def snapshot_contract(
    data: dict[str, Any],
    *,
    mode: str,
    capture_metadata: dict[str, Any],
) -> dict[str, Any]:
    raw_nodes = data.get("nodes")
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    observed_node_count = len(nodes)
    node_count = _int_or_default(capture_metadata.get("nodeCount"), observed_node_count)
    backend = capture_metadata.get("backend")
    truncated = bool(
        capture_metadata.get("truncated")
        or capture_metadata.get("helperTruncated")
        or observed_node_count < node_count
    )
    if mode == "full":
        return {
            "mode": "full",
            "presentation": "full",
            "source": backend or "unknown",
            "backend": backend,
            "full": False,
            "complete": False,
            "canProveAbsence": False,
            "coverage": "diagnostic",
            "coverageFailureReason": (
                "FULL_SNAPSHOT_TRUNCATED" if truncated else FULL_COVERAGE_FAILURE
            ),
            "degraded": True,
            "degradeReason": "FULL_SNAPSHOT_TRUNCATED" if truncated else FULL_COVERAGE_FAILURE,
            "failureStage": "snapshot-capture",
            "nodeCount": node_count,
            "observedNodeCount": observed_node_count,
            "scrollContextCount": 0,
            "truncated": truncated,
            "emptyTree": observed_node_count == 0,
            "busy": False,
            "unstable": False,
            "usableForScrollToText": False,
        }
    return {
        "mode": "compact" if mode == "compact" else "default",
        "presentation": "compact",
        "tokenBudget": "low",
        "source": backend or "unknown",
        "backend": backend,
        "full": False,
        "complete": False,
        "canProveAbsence": False,
        "coverage": "interactive",
        "coverageFailureReason": None,
        "degraded": False,
        "degradeReason": None,
        "failureStage": None,
        "nodeCount": node_count,
        "observedNodeCount": observed_node_count,
        "scrollContextCount": 0,
        "truncated": truncated,
        "emptyTree": observed_node_count == 0,
        "busy": False,
        "unstable": False,
        "usableForScrollToText": False,
    }


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ref_map_from_projection(projected: dict[str, Any]) -> dict[str, SnapshotRef]:
    refs: dict[str, SnapshotRef] = {}
    for node in projected.get("nodes", []):
        if not isinstance(node, dict):
            continue
        ref = canonical_ref(node.get("ref"))
        if ref is None:
            continue
        text = node.get("text")
        content_desc = node.get("contentDesc") or node.get("desc") or node.get("description")
        resource_id = node.get("resourceId") or node.get("rid")
        class_name = node.get("className") or node.get("cls")
        selector: dict[str, Any] = {}
        if text:
            selector["text"] = text
        if resource_id:
            selector["resourceId"] = resource_id
        if content_desc:
            selector["description"] = content_desc
        if class_name:
            selector["className"] = class_name
        bounds = bounds_dict(node.get("bounds"))
        center = node.get("center")
        if center is None and bounds:
            center = {
                "x": (bounds["left"] + bounds["right"]) // 2,
                "y": (bounds["top"] + bounds["bottom"]) // 2,
            }
        refs[ref] = SnapshotRef(
            ref=ref,
            snapshotId=projected.get("snapshotId"),
            selector=selector or None,
            bounds=bounds,
            center=center if isinstance(center, dict) else None,
            text=text if isinstance(text, str) else None,
            contentDesc=content_desc if isinstance(content_desc, str) else None,
            className=class_name if isinstance(class_name, str) else None,
            resourceId=resource_id if isinstance(resource_id, str) else None,
            description=content_desc if isinstance(content_desc, str) else None,
            packageName=node.get("packageName"),
            role=node.get("role"),
            parentRef=node.get("parentRef"),
            stableKey=node.get("stableKey"),
            rawNodePath=node.get("rawNodePath"),
            rawOrdinal=node.get("rawOrdinal"),
            rawArtifactPath=projected.get("rawArtifactPath"),
            compactArtifactPath=projected.get("compactArtifactPath"),
            refMapPath=projected.get("refMapPath"),
            actions=node.get("actions") if isinstance(node.get("actions"), list) else [],
            visible=node.get("visible"),
            enabled=node.get("enabled"),
            clickable=node.get("clickable"),
            focusable=node.get("focusable"),
            scrollable=node.get("scrollable"),
            selected=node.get("selected"),
            checked=node.get("checked"),
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


def dump_with_artifacts(
    ctx: CommandContext,
    compact: bool = False,
    snapshot_options: SnapshotBackendOptions | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = dump(ctx, compact=compact, snapshot_options=snapshot_options)
    return data, compact_artifacts(data) if compact else []


def _snapshot_paths(snapshot_id: str) -> tuple[Path, Path, Path]:
    root = snapshot_artifact_dir(snapshot_id)
    return root / "raw.xml", root / "compact.json", root / "ref-map.json"


def _write_text_artifact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _write_json_artifact(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


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
            info = device.info if device.connected else {}
            projected = full_projection(capture.xml, info)
            projected["xml"] = capture.xml
            projected["snapshot"] = {
                **capture.metadata,
                **snapshot_contract(projected, mode="full", capture_metadata=capture.metadata),
            }
            captured_at = utc_now_iso()
            projected["capturedAt"] = captured_at
            if ctx.serial:
                ref_map = ref_map_from_projection(projected)
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
                            "snapshot": projected["snapshot"],
                        },
                    ),
                )
            return projected
        info = device.info if device.connected else {}
        captured_at = utc_now_iso()
        backend = capture.metadata.get("backend")
        projected = build_compact_snapshot(
            capture.xml,
            info,
            captured_at=captured_at,
            serial=ctx.serial,
            backend=str(backend) if backend is not None else None,
        )
        snapshot_id = str(projected["snapshotId"])
        raw_path, compact_path, ref_map_path = _snapshot_paths(snapshot_id)
        projected["rawArtifactPath"] = str(raw_path)
        projected["compactArtifactPath"] = str(compact_path)
        projected["refMapPath"] = str(ref_map_path)
        projected["snapshot"] = {
            **capture.metadata,
            **snapshot_contract(projected, mode="compact", capture_metadata=capture.metadata),
        }
        ref_map_doc = build_ref_map(projected)
        _write_text_artifact(raw_path, capture.xml)
        _write_json_artifact(compact_path, projected)
        _write_json_artifact(ref_map_path, ref_map_doc)
        ref_map = ref_map_from_projection(projected)
        if ctx.serial:
            update_session(
                serial=ctx.serial,
                timeout_ms=ctx.timeout_ms,
                last_snapshot=LastSnapshot(
                    capturedAt=captured_at,
                    snapshotId=snapshot_id,
                    serial=ctx.serial,
                    rawArtifactPath=str(raw_path),
                    compactArtifactPath=str(compact_path),
                    refMapPath=str(ref_map_path),
                    refMap=ref_map,
                    metadata={
                        "screenSize": projected.get("screenSize"),
                        "package": projected.get("package"),
                        "activity": projected.get("activity"),
                        "snapshot": projected["snapshot"],
                        "snapshotId": snapshot_id,
                        "rawArtifactPath": str(raw_path),
                        "compactArtifactPath": str(compact_path),
                        "refMapPath": str(ref_map_path),
                    },
                ),
            )
        return projected

    return run_with_timeout(_run, ctx.timeout_ms)
