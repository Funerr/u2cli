from __future__ import annotations

import json
from importlib import resources
from typing import Any

from androidtestclii.branding import DISPLAY_NAME


def tool_schema() -> dict[str, Any]:
    raw = resources.files("androidtestclii.pi").joinpath("tools.json").read_text(encoding="utf-8")
    schema = json.loads(raw)
    if not isinstance(schema, dict):
        raise TypeError(f"{DISPLAY_NAME} Pi tools schema must be a JSON object")
    return schema
