from __future__ import annotations

from typing import Any


def tool_schema() -> dict[str, Any]:
    tools = [
        {"name": "doctor", "command": ["u2cli", "--json", "doctor"], "inputSchema": {}},
        {"name": "devices", "command": ["u2cli", "--json", "devices"], "inputSchema": {}},
        {
            "name": "screen_dump_compact",
            "command": ["u2cli", "--json", "screen", "dump", "--compact"],
            "inputSchema": {"serial": "string"},
        },
        {
            "name": "screen_screenshot",
            "command": ["u2cli", "--json", "screen", "screenshot"],
            "inputSchema": {"serial": "string", "out": "string"},
        },
        {
            "name": "element_find",
            "command": ["u2cli", "--json", "element", "find"],
            "inputSchema": {"serial": "string", "selector": "Selector"},
        },
        {
            "name": "element_click",
            "command": ["u2cli", "--json", "element", "click"],
            "inputSchema": {"serial": "string", "selector": "Selector"},
        },
        {
            "name": "element_set_text",
            "command": ["u2cli", "--json", "element", "set-text"],
            "inputSchema": {"serial": "string", "selector": "Selector", "text": "string"},
        },
        {
            "name": "input_tap",
            "command": ["u2cli", "--json", "input", "tap"],
            "inputSchema": {"serial": "string", "x": "integer", "y": "integer"},
        },
        {
            "name": "toast_get",
            "command": ["u2cli", "--json", "toast", "get"],
            "inputSchema": {"serial": "string", "timeoutMs": "integer"},
        },
        {
            "name": "device_clipboard_set",
            "command": ["u2cli", "--json", "device", "clipboard-set"],
            "inputSchema": {"serial": "string", "text": "string"},
        },
    ]
    return {
        "name": "u2cli",
        "description": "Typed wrappers for u2cli Android automation commands.",
        "selectorSchema": {
            "text": "string?",
            "textContains": "string?",
            "resourceId": "string?",
            "description": "string?",
            "descriptionContains": "string?",
            "className": "string?",
            "xpath": "string?",
            "index": "integer?",
        },
        "tools": tools,
    }
