from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import FileLock, Timeout

from .errors import ErrorCode, U2CliError


def lock_path_for(serial: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in serial)
    root = Path(os.environ.get("TMPDIR", tempfile.gettempdir())) / "u2cli" / "locks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}.lock"


@contextmanager
def serial_lock(serial: str | None, timeout_ms: int) -> Iterator[None]:
    if not serial:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--serial is required for mutating commands",
            {"argument": "serial"},
        )
    lock = FileLock(str(lock_path_for(serial)))
    try:
        lock.acquire(timeout=timeout_ms / 1000)
    except Timeout as exc:
        raise U2CliError(
            ErrorCode.ACTION_TIMEOUT,
            "Timed out waiting for per-device mutation lock",
            {"lock": "busy", "serial": serial},
        ) from exc
    try:
        yield
    finally:
        lock.release()
