from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.element.selector import Selector, parse_target_selector, selector_from_ref
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.session.store import SnapshotRef, normalize_ref, ref_entry


@dataclass
class ResolvedElementTarget:
    selector: Selector | None = None
    point: tuple[int, int] | None = None
    ref: SnapshotRef | None = None
    ref_name: str | None = None
    snapshot_id: str | None = None
    cache_allowed: bool = True
    raw_target: Any = None


def resolve_element_target(
    ctx: CommandContext,
    target: Selector | str | dict[str, Any],
) -> ResolvedElementTarget:
    if isinstance(target, Selector):
        return ResolvedElementTarget(selector=target, raw_target=target)
    if isinstance(target, dict):
        ref = target.get("ref")
        snapshot_id = target.get("snapshotId") or target.get("snapshot_id")
        if not isinstance(ref, str) or not ref.strip():
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "target ref object must include ref",
                {"target": target},
            )
        entry, snapshot = ref_entry(ref, snapshot_id=snapshot_id if isinstance(snapshot_id, str) else None)
        cache_allowed = not (ctx.serial and snapshot.serial and snapshot.serial != ctx.serial)
        return ResolvedElementTarget(
            selector=selector_from_ref(entry),
            point=point_from_ref(entry) if cache_allowed else None,
            ref=entry,
            ref_name=normalize_ref(ref),
            snapshot_id=snapshot.snapshot_id,
            cache_allowed=cache_allowed,
            raw_target=target,
        )
    raw = str(target).strip()
    if raw.startswith("@e"):
        entry, snapshot = ref_entry(raw)
        cache_allowed = not (ctx.serial and snapshot.serial and snapshot.serial != ctx.serial)
        return ResolvedElementTarget(
            selector=selector_from_ref(entry),
            point=point_from_ref(entry) if cache_allowed else None,
            ref=entry,
            ref_name=normalize_ref(raw),
            snapshot_id=snapshot.snapshot_id,
            cache_allowed=cache_allowed,
            raw_target=target,
        )
    return ResolvedElementTarget(selector=parse_target_selector(raw), raw_target=target)


def point_from_ref(entry: SnapshotRef) -> tuple[int, int] | None:
    center = entry.center
    if isinstance(center, dict):
        x = center.get("x")
        y = center.get("y")
        if isinstance(x, int) and isinstance(y, int):
            return (x, y)
    bounds = entry.bounds
    if not bounds:
        return None
    required = ["left", "top", "right", "bottom"]
    if not all(isinstance(bounds.get(key), int) for key in required):
        return None
    return ((bounds["left"] + bounds["right"]) // 2, (bounds["top"] + bounds["bottom"]) // 2)


def ref_error_details(ref_name: str | None, ref: SnapshotRef | None) -> dict[str, Any]:
    details: dict[str, Any] = {
        "ref": ref_name,
        "candidateRefs": [ref.ref] if ref is not None and ref.ref else [],
    }
    if ref is not None:
        details.update(
            {
                "snapshotId": ref.snapshot_id,
                "rawArtifactPath": ref.raw_artifact_path,
                "refMapPath": ref.ref_map_path,
                "entry": ref.public_dict(),
            }
        )
    return {key: value for key, value in details.items() if value is not None}


def raise_invalid_ref(ref_name: str | None, ref: SnapshotRef | None) -> None:
    raise U2CliError(
        ErrorCode.SNAPSHOT_REF_INVALID,
        "Snapshot ref does not contain executable bounds or selector",
        ref_error_details(ref_name, ref),
    )
