from __future__ import annotations

import json

from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.result import CommandResult


def test_success_json_contract() -> None:
    result = CommandResult.ok(
        command="element.click",
        serial="emulator-5554",
        duration_ms=12,
        data={"clicked": True},
    )

    payload = json.loads(result.to_json())

    assert list(payload) == [
        "success",
        "command",
        "serial",
        "via",
        "data",
        "artifacts",
        "durationMs",
    ]
    assert payload["success"] is True
    assert payload["via"] == "uiautomator2"
    assert payload["data"]["metadata"]["capabilityLayer"] == "pure-adb-ui-query"
    assert payload["data"]["metadata"]["fallbackUsed"] is False


def test_failure_json_contract() -> None:
    result = CommandResult.failed(
        command="element.click",
        serial="emulator-5554",
        duration_ms=12,
        error=U2CliError(ErrorCode.ELEMENT_NOT_FOUND, "missing", {"selector": {"text": "x"}}),
    )

    payload = json.loads(result.to_json())

    assert payload["success"] is False
    assert payload["error"]["code"] == "ELEMENT_NOT_FOUND"
    assert payload["error"]["details"]["selector"] == {"text": "x"}
    assert payload["error"]["metadata"]["capabilityLayer"] == "pure-adb-ui-query"
    assert payload["error"]["metadata"]["failureStage"] == "selector-query"
    assert payload["error"]["metadata"]["recoveryHint"]
