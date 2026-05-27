from __future__ import annotations

import os
from typing import Any

from u2cli.context import CommandContext
from u2cli.errors import ErrorCode, U2CliError
from u2cli.session.store import clear_session, read_session, session_path


def info(ctx: CommandContext) -> dict[str, Any]:
    state = read_session()
    return {
        "mode": "per-command",
        "sidecar": False,
        "pid": os.getpid(),
        "serial": ctx.serial,
        "timeoutMs": ctx.timeout_ms,
        "connectionCached": False,
        "sessionPath": str(session_path()),
        "stored": state.public_dict(),
    }


def sidecar_start(ctx: CommandContext) -> dict[str, Any]:
    raise U2CliError(
        ErrorCode.ACTION_FAILED,
        "sidecar mode is not implemented; use per-command CLI mode",
        {"mode": "per-command", "serial": ctx.serial},
    )


def clear(ctx: CommandContext) -> dict[str, Any]:
    clear_session()
    return {"cleared": True, "sessionPath": str(session_path())}
