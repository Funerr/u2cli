from __future__ import annotations

import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from u2cli.errors import ErrorCode, U2CliError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SnapshotRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    selector: dict[str, Any] | None = None
    bounds: dict[str, int] | None = None
    text: str | None = None
    class_name: str | None = Field(default=None, alias="className")
    resource_id: str | None = Field(default=None, alias="resourceId")
    description: str | None = None
    node: dict[str, Any] | None = None

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class LastSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    captured_at: str = Field(alias="capturedAt")
    serial: str | None = None
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
    updated_at: str | None = Field(default=None, alias="updatedAt")
    stale: bool = False

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


def session_path() -> Path:
    override = os.environ.get("U2CLI_SESSION_PATH")
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "u2cli" / "session.json"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "u2cli" / "session.json"
    return Path.home() / ".config" / "u2cli" / "session.json"


def _lock_path(path: Path) -> Path:
    root = Path(os.environ.get("TMPDIR", tempfile.gettempdir())) / "u2cli" / "locks"
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
                "u2cli session file is not valid JSON",
                {"path": str(target), "error": str(exc)},
            ) from exc
    try:
        return SessionState.model_validate(raw)
    except ValidationError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "u2cli session file has an invalid schema",
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
) -> SessionState:
    state = read_session()
    if serial is not None:
        state.serial = serial
        state.stale = False
    if timeout_ms is not None:
        state.timeout_ms = timeout_ms
    if last_snapshot is not None:
        state.last_snapshot = last_snapshot
    write_session(state)
    return state


def mark_stale(serial: str | None) -> SessionState:
    state = read_session()
    if serial is None or state.serial == serial:
        state.stale = True
        write_session(state)
    return state


def ref_entry(ref: str, state: SessionState | None = None) -> tuple[SnapshotRef, LastSnapshot]:
    session = state or read_session()
    last = session.last_snapshot
    if last is None:
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "No snapshot ref cache is available; run snapshot -i first",
            {"ref": ref},
        )
    normalized = ref if ref.startswith("@") else f"@{ref}"
    entry = last.ref_map.get(normalized)
    if entry is None:
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "Snapshot ref was not found in the latest snapshot cache",
            {"ref": normalized, "capturedAt": last.captured_at},
        )
    return entry, last
