from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from androidtestclii.branding import ALERT_BUTTONS_ENV, LEGACY_ALERT_BUTTONS_ENV, SLUG
from androidtestclii.context import CommandContext
from androidtestclii.element import action as element_action
from androidtestclii.element import query as element_query
from androidtestclii.element.selector import selector_from_kwargs
from androidtestclii.errors import ErrorCode, U2CliError


ALERT_BUTTONS = (
    ("Allow", "accept"),
    ("OK", "accept"),
    ("Yes", "accept"),
    ("Confirm", "accept"),
    ("Continue", "accept"),
    ("允许", "accept"),
    ("确定", "accept"),
    ("同意", "accept"),
    ("好", "accept"),
    ("Cancel", "dismiss"),
    ("Deny", "dismiss"),
    ("No", "dismiss"),
    ("Not now", "dismiss"),
    ("取消", "dismiss"),
    ("拒绝", "dismiss"),
    ("否", "dismiss"),
)


def get(ctx: CommandContext) -> dict[str, Any]:
    candidates = scan_candidates(ctx)
    return {
        "present": bool(candidates),
        "attempts": 1,
        "durationMs": 0,
        "matchedCount": len(candidates),
        "selectedIndex": 0 if candidates else None,
        "candidates": candidates,
    }


def wait(ctx: CommandContext, timeout_ms: int) -> dict[str, Any]:
    started = time.perf_counter()
    deadline = started + timeout_ms / 1000
    attempts = 0
    candidates: list[dict[str, Any]] = []
    while True:
        attempts += 1
        candidates = scan_candidates(ctx)
        if candidates:
            return {
                "present": True,
                "attempts": attempts,
                "durationMs": int((time.perf_counter() - started) * 1000),
                "matchedCount": len(candidates),
                "selectedIndex": 0,
                "candidates": candidates,
            }
        if time.perf_counter() >= deadline:
            return {
                "present": False,
                "attempts": attempts,
                "durationMs": int((time.perf_counter() - started) * 1000),
                "matchedCount": 0,
                "selectedIndex": None,
                "candidates": [],
            }
        time.sleep(0.1)


def accept(ctx: CommandContext, timeout_ms: int) -> dict[str, Any]:
    return click_role(ctx, "accept", timeout_ms)


def dismiss(ctx: CommandContext, timeout_ms: int) -> dict[str, Any]:
    return click_role(ctx, "dismiss", timeout_ms)


def click_role(ctx: CommandContext, role: str, timeout_ms: int) -> dict[str, Any]:
    found = wait(ctx, timeout_ms)
    for candidate in found["candidates"]:
        if candidate.get("role") == role:
            selector = selector_from_kwargs(text=str(candidate["text"]))
            clicked = element_action.click(ctx, selector)
            return {
                "role": role,
                "attempts": found.get("attempts"),
                "durationMs": found.get("durationMs"),
                "matchedCount": found.get("matchedCount"),
                "selectedIndex": found["candidates"].index(candidate),
                "candidate": candidate,
                "clicked": clicked,
            }
    raise U2CliError(
        ErrorCode.ALERT_NOT_FOUND,
        f"No alert {role} candidate was found",
        {"role": role, "timeoutMs": timeout_ms, "candidates": found["candidates"]},
    )


def scan_candidates(ctx: CommandContext) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for text, role in configured_buttons():
        selector = selector_from_kwargs(text=text)
        try:
            result = element_query.exists(ctx, selector)
        except U2CliError:
            continue
        if result.get("exists"):
            candidates.append({"text": text, "role": role, "selector": selector.public_dict()})
    return candidates


def configured_buttons() -> tuple[tuple[str, str], ...]:
    path = os.environ.get(ALERT_BUTTONS_ENV) or os.environ.get(LEGACY_ALERT_BUTTONS_ENV)
    if not path:
        path = str(Path.home() / ".config" / SLUG / "alert-buttons.json")
    override = Path(path)
    if not override.exists():
        return ALERT_BUTTONS
    raw = json.loads(override.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return ALERT_BUTTONS
    parsed: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("role") in {"accept", "dismiss"}:
            parsed.append((item["text"], item["role"]))
    return tuple(parsed) or ALERT_BUTTONS
