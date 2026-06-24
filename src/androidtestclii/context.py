from __future__ import annotations

import time
from dataclasses import dataclass


DEFAULT_TIMEOUT_MS = 5000
DEFAULT_MUTATION_TIMEOUT_MS = 10000


@dataclass
class CommandContext:
    json_output: bool = True
    serial: str | None = None
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    timeout_ms_explicit: bool = False
    verbosity: int = 0
    command_alias: str | None = None
    started_at: float = 0.0

    @classmethod
    def start(
        cls,
        *,
        json_output: bool = True,
        serial: str | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        timeout_ms_explicit: bool = False,
        verbosity: int = 0,
        command_alias: str | None = None,
    ) -> "CommandContext":
        return cls(
            json_output=json_output,
            serial=serial,
            timeout_ms=timeout_ms,
            timeout_ms_explicit=timeout_ms_explicit,
            verbosity=verbosity,
            command_alias=command_alias,
            started_at=time.perf_counter(),
        )

    def elapsed_ms(self) -> int:
        return max(0, int((time.perf_counter() - self.started_at) * 1000))
