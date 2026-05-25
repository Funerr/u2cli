from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def enabled_level(verbosity: int) -> str:
    if verbosity >= 2:
        return "debug"
    if verbosity == 1:
        return "info"
    return "warn"


def log(
    level: str,
    *,
    cmd: str,
    serial: str | None,
    msg: str,
    verbosity: int = 0,
    **kv: Any,
) -> None:
    if LEVELS[level] < LEVELS[enabled_level(verbosity)]:
        return
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "cmd": cmd,
        "serial": serial,
        "msg": msg,
        "kv": kv,
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
