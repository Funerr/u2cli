from __future__ import annotations

from pathlib import Path
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.screen.dump import LazyDevice
from androidtestclii.screen.dump import compact_projection


REQUIRED_NODE_FIELDS = {
    "ref",
    "text",
    "contentDesc",
    "resourceId",
    "className",
    "packageName",
    "role",
    "bounds",
    "center",
    "visible",
    "enabled",
    "clickable",
    "focusable",
    "scrollable",
    "selected",
    "checked",
    "actions",
    "parentRef",
    "stableKey",
}


def fixture_xml() -> str:
    return Path("tests/fixtures/raw_ui_dump_compact_refs.xml").read_text(encoding="utf-8")


def test_compact_projection_returns_full_field_nodes_and_canonical_refs() -> None:
    data = compact_projection(fixture_xml(), {"displayWidth": 1080, "displayHeight": 2400})

    assert data["screenSize"] == [1080, 2400]
    assert data["package"] == "com.example"
    assert data["snapshotId"]
    assert data["nodes"]
    assert all(REQUIRED_NODE_FIELDS <= set(node.keys()) for node in data["nodes"])
    assert [node["ref"] for node in data["nodes"]] == ["@e0", "@e1", "@e2", "@e3", "@e4"]

    email = next(node for node in data["nodes"] if node["resourceId"] == "com.example:id/email")
    assert email["role"] == "input"
    assert email["actions"] == ["focus", "setText"]
    assert email["center"] == {"x": 520, "y": 300}
    assert email["stableKey"]


def test_compact_projection_denoises_and_folds_siblings() -> None:
    data = compact_projection(fixture_xml(), {"displayWidth": 1080, "displayHeight": 2400})
    texts = {node.get("text") for node in data["nodes"]}

    assert "Welcome" in texts
    assert "Email" in texts
    assert "Hidden label" not in texts
    assert "Zero size" not in texts
    assert "Offscreen" not in texts

    repeat_nodes = [node for node in data["nodes"] if node.get("text") == "Repeat"]
    assert len(repeat_nodes) == 1
    assert repeat_nodes[0]["count"] == 3
    assert repeat_nodes[0]["foldedCount"] == 3


def test_text_truncation() -> None:
    xml = f'<hierarchy><node text="{"x" * 201}" class="TextView" enabled="true" /></hierarchy>'

    data = compact_projection(xml)

    assert len(data["nodes"][0]["text"]) == 200
    assert data["nodes"][0]["textTruncated"] is True


def test_lazy_device_connects_only_when_used(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    connected: list[bool] = []

    class Device:
        info = {"displayWidth": 1}

        def dump_hierarchy(self) -> str:
            return "<hierarchy/>"

    def connect(serial: str | None, timeout_ms: int) -> Any:
        connected.append(True)
        return Device()

    monkeypatch.setattr("androidtestclii.screen.dump.connect_device", connect)
    lazy = LazyDevice(CommandContext.start(serial="emulator-5554", timeout_ms=1000))

    assert lazy.connected is False
    assert connected == []
    assert lazy.dump_hierarchy() == "<hierarchy/>"
    assert lazy.connected is True
    assert connected == [True]
