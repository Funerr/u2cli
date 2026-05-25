from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .errors import ErrorCode, U2CliError


@dataclass
class CommandResult:
    success: bool
    command: str
    serial: str | None
    duration_ms: int
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    via: str = "uiautomator2"

    @classmethod
    def ok(
        cls,
        *,
        command: str,
        serial: str | None,
        duration_ms: int,
        data: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> "CommandResult":
        return cls(
            success=True,
            command=command,
            serial=serial,
            duration_ms=duration_ms,
            data=data or {},
            artifacts=artifacts or [],
        )

    @classmethod
    def failed(
        cls,
        *,
        command: str,
        serial: str | None,
        duration_ms: int,
        error: U2CliError,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> "CommandResult":
        payload: dict[str, Any] = {"code": error.code.value, "message": error.message}
        if error.details:
            payload["details"] = error.details
        return cls(
            success=False,
            command=command,
            serial=serial,
            duration_ms=duration_ms,
            error=payload,
            artifacts=artifacts or [],
        )

    def to_dict(self) -> dict[str, Any]:
        obj: dict[str, Any] = {
            "success": self.success,
            "command": self.command,
            "serial": self.serial,
            "via": self.via,
        }
        if self.success:
            obj["data"] = self.data or {}
        else:
            obj["error"] = self.error or {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Unknown error",
            }
        obj["artifacts"] = self.artifacts
        obj["durationMs"] = self.duration_ms
        return obj

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))
