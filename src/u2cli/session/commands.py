from __future__ import annotations

import os
from typing import Any

from u2cli.context import CommandContext
from u2cli.errors import ErrorCode, U2CliError


def info(ctx: CommandContext) -> dict[str, Any]:
    return {
        "mode": "per-command",
        "sidecar": False,
        "pid": os.getpid(),
        "serial": ctx.serial,
        "timeoutMs": ctx.timeout_ms,
        "connectionCached": False,
    }


def sidecar_start(ctx: CommandContext) -> dict[str, Any]:
    raise U2CliError(
        ErrorCode.ACTION_FAILED,
        "sidecar mode is not implemented; use per-command CLI mode",
        {"mode": "per-command", "serial": ctx.serial},
    )
