from __future__ import annotations

from typing import Any


DEFAULT_UNSUPPORTED_HINT = (
    "Use Android uiautomator2-backed commands or implement a dedicated platform adapter."
)


def unsupported_result(
    feature: str,
    *,
    reason: str = "not_in_scope",
    recovery_hint: str = DEFAULT_UNSUPPORTED_HINT,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "feature": feature,
        "available": False,
        "unsupported": True,
        "reason": reason,
        "recoveryHint": recovery_hint,
        **extra,
    }
