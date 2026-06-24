from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from androidtestclii.branding import DISPLAY_NAME, LEGACY_SESSION_ENV, SESSION_ENV, SLUG
from androidtestclii.errors import ErrorCode, U2CliError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SnapshotRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ref: str | None = None
    snapshot_id: str | None = Field(default=None, alias="snapshotId")
    selector: dict[str, Any] | None = None
    bounds: dict[str, int] | None = None
    center: dict[str, int] | None = None
    text: str | None = None
    content_desc: str | None = Field(default=None, alias="contentDesc")
    class_name: str | None = Field(default=None, alias="className")
    resource_id: str | None = Field(default=None, alias="resourceId")
    package_name: str | None = Field(default=None, alias="packageName")
    description: str | None = None
    role: str | None = None
    parent_ref: str | None = Field(default=None, alias="parentRef")
    stable_key: str | None = Field(default=None, alias="stableKey")
    raw_node_path: list[int] | None = Field(default=None, alias="rawNodePath")
    raw_ordinal: int | None = Field(default=None, alias="rawOrdinal")
    raw_artifact_path: str | None = Field(default=None, alias="rawArtifactPath")
    compact_artifact_path: str | None = Field(default=None, alias="compactArtifactPath")
    ref_map_path: str | None = Field(default=None, alias="refMapPath")
    actions: list[str] = Field(default_factory=list)
    visible: bool | None = None
    enabled: bool | None = None
    clickable: bool | None = None
    focusable: bool | None = None
    scrollable: bool | None = None
    selected: bool | None = None
    checked: bool | None = None
    node: dict[str, Any] | None = None

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class LastSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    captured_at: str = Field(alias="capturedAt")
    snapshot_id: str | None = Field(default=None, alias="snapshotId")
    serial: str | None = None
    raw_artifact_path: str | None = Field(default=None, alias="rawArtifactPath")
    compact_artifact_path: str | None = Field(default=None, alias="compactArtifactPath")
    ref_map_path: str | None = Field(default=None, alias="refMapPath")
    ref_map: dict[str, SnapshotRef] = Field(default_factory=dict, alias="refMap")
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_dict(self, *, include_ref_map: bool = True) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if not include_ref_map:
            data.pop("refMap", None)
        return data


class SessionState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    serial: str | None = None
    timeout_ms: int | None = Field(default=None, alias="timeoutMs")
    last_snapshot: LastSnapshot | None = Field(default=None, alias="lastSnapshot")
    temporary_automation: dict[str, Any] = Field(default_factory=dict, alias="temporaryAutomation")
    persistent_monitoring: dict[str, Any] = Field(default_factory=dict, alias="persistentMonitoring")
    last_fallback: dict[str, Any] = Field(default_factory=dict, alias="lastFallback")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    stale: bool = False

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


def session_path() -> Path:
    override = os.environ.get(SESSION_ENV) or os.environ.get(LEGACY_SESSION_ENV)
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / SLUG / "session.json"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / DISPLAY_NAME / "session.json"
    return Path.home() / ".config" / SLUG / "session.json"


def snapshot_artifact_root() -> Path:
    override = (
        os.environ.get("ANDROIDTESTCLII_ARTIFACT_DIR")
        or os.environ.get("U2CLI_ARTIFACT_DIR")
    )
    if override:
        return Path(override) / "snapshots"
    return Path("artifacts") / "snapshots"


def snapshot_artifact_dir(snapshot_id: str) -> Path:
    return snapshot_artifact_root() / snapshot_id


def snapshot_ref_map_path(snapshot_id: str) -> Path:
    return snapshot_artifact_dir(snapshot_id) / "ref-map.json"


def snapshot_id_for(
    *,
    captured_at: str,
    raw_xml: str,
    serial: str | None,
    backend: str | None,
) -> str:
    safe_time = captured_at.replace(":", "-").replace("+", "-")
    digest = hashlib.sha256(
        "\n".join([raw_xml, serial or "", backend or ""]).encode("utf-8")
    ).hexdigest()[:8]
    return f"{safe_time}-{digest}"


def _lock_path(path: Path) -> Path:
    root = Path(os.environ.get("TMPDIR", tempfile.gettempdir())) / SLUG / "locks"
    root.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(path))
    return root / f"session-{safe}.lock"


def read_session(path: Path | None = None) -> SessionState:
    target = path or session_path()
    if not target.exists():
        return SessionState()
    with FileLock(str(_lock_path(target))):
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                f"{DISPLAY_NAME} session file is not valid JSON",
                {"path": str(target), "error": str(exc)},
            ) from exc
    try:
        return SessionState.model_validate(raw)
    except ValidationError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            f"{DISPLAY_NAME} session file has an invalid schema",
            {"path": str(target), "errors": exc.errors(include_url=False)},
        ) from exc


def write_session(state: SessionState, path: Path | None = None) -> None:
    target = path or session_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = utc_now_iso()
    payload = json.dumps(state.public_dict(), ensure_ascii=False, separators=(",", ":"))
    with FileLock(str(_lock_path(target))):
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, target)


def clear_session(path: Path | None = None) -> None:
    target = path or session_path()
    with FileLock(str(_lock_path(target))):
        target.unlink(missing_ok=True)


def update_session(
    *,
    serial: str | None = None,
    timeout_ms: int | None = None,
    last_snapshot: LastSnapshot | None = None,
    temporary_automation: dict[str, Any] | None = None,
    persistent_monitoring: dict[str, Any] | None = None,
    last_fallback: dict[str, Any] | None = None,
) -> SessionState:
    state = read_session()
    if serial is not None:
        state.serial = serial
        state.stale = False
    if timeout_ms is not None:
        state.timeout_ms = timeout_ms
    if last_snapshot is not None:
        state.last_snapshot = last_snapshot
    if temporary_automation is not None:
        state.temporary_automation = temporary_automation
    if persistent_monitoring is not None:
        state.persistent_monitoring = persistent_monitoring
    if last_fallback is not None:
        state.last_fallback = last_fallback
    write_session(state)
    return state


def mark_stale(serial: str | None) -> SessionState:
    state = read_session()
    if serial is None or state.serial == serial:
        state.stale = True
        write_session(state)
    return state


def ref_entry(
    ref: str,
    state: SessionState | None = None,
    *,
    snapshot_id: str | None = None,
) -> tuple[SnapshotRef, LastSnapshot]:
    normalized = normalize_ref(ref)
    if snapshot_id:
        snapshot = _load_snapshot_ref_map(snapshot_id, normalized)
        entry = snapshot.ref_map.get(normalized)
        if entry is None:
            raise U2CliError(
                ErrorCode.SNAPSHOT_REF_NOT_FOUND,
                "Snapshot ref was not found in the requested snapshot ref map",
                _ref_error_details(snapshot, normalized),
            )
        return entry, snapshot

    session = state or read_session()
    last = session.last_snapshot
    if last is None:
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "No snapshot ref cache is available; run snapshot -i first",
            {"ref": normalized},
        )
    entry = last.ref_map.get(normalized)
    if entry is None:
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "Snapshot ref was not found in the latest snapshot cache",
            _ref_error_details(last, normalized),
        )
    return entry, last


def normalize_ref(ref: str) -> str:
    raw = str(ref).strip()
    return raw if raw.startswith("@") else f"@{raw}"


def _load_snapshot_ref_map(snapshot_id: str, ref: str) -> LastSnapshot:
    path = snapshot_ref_map_path(snapshot_id)
    if not path.exists():
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "Snapshot ref map was not found; capture a fresh compact snapshot",
            {
                "snapshotId": snapshot_id,
                "ref": ref,
                "candidateRefs": [],
                "refMapPath": str(path),
            },
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_INVALID,
            "Snapshot ref map is not valid JSON",
            {"snapshotId": snapshot_id, "ref": ref, "refMapPath": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(raw, dict):
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_INVALID,
            "Snapshot ref map must be a JSON object",
            {"snapshotId": snapshot_id, "ref": ref, "refMapPath": str(path)},
        )
    refs = raw.get("refs")
    if not isinstance(refs, dict):
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_INVALID,
            "Snapshot ref map does not contain refs",
            {"snapshotId": snapshot_id, "ref": ref, "refMapPath": str(path)},
        )
    ref_map: dict[str, SnapshotRef] = {}
    for raw_ref, value in refs.items():
        if not isinstance(value, dict):
            continue
        normalized = normalize_ref(str(raw_ref))
        payload = {
            **value,
            "ref": value.get("ref") or normalized,
            "snapshotId": value.get("snapshotId") or raw.get("snapshotId") or snapshot_id,
            "rawArtifactPath": value.get("rawArtifactPath") or raw.get("rawArtifactPath"),
            "compactArtifactPath": value.get("compactArtifactPath") or raw.get("compactArtifactPath"),
            "refMapPath": value.get("refMapPath") or str(path),
        }
        ref_map[normalized] = SnapshotRef.model_validate(payload)
    captured_at = str(raw.get("capturedAt") or "")
    if not captured_at:
        captured_at = utc_now_iso()
    return LastSnapshot(
        capturedAt=captured_at,
        snapshotId=str(raw.get("snapshotId") or snapshot_id),
        serial=raw.get("serial"),
        rawArtifactPath=raw.get("rawArtifactPath"),
        compactArtifactPath=raw.get("compactArtifactPath"),
        refMapPath=str(path),
        refMap=ref_map,
        metadata={
            "snapshot": raw.get("snapshot"),
            "screenSize": raw.get("screenSize"),
            "package": raw.get("package"),
            "activity": raw.get("activity"),
        },
    )


def _ref_error_details(snapshot: LastSnapshot, ref: str) -> dict[str, Any]:
    details: dict[str, Any] = {
        "snapshotId": snapshot.snapshot_id,
        "ref": ref,
        "candidateRefs": sorted(snapshot.ref_map.keys()),
        "capturedAt": snapshot.captured_at,
    }
    raw_path = snapshot.raw_artifact_path or snapshot.metadata.get("rawArtifactPath")
    if raw_path:
        details["rawArtifactPath"] = raw_path
    ref_map_path = snapshot.ref_map_path or snapshot.metadata.get("refMapPath")
    if ref_map_path:
        details["refMapPath"] = ref_map_path
    return details
