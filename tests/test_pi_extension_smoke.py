from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

TOOL_PREFIXES = ("android_cli_", "u2cli_")

REQUIRED_TOOLS = {
    "android_cli_doctor",
    "android_cli_devices",
    "android_cli_screen_dump",
    "android_cli_screen_screenshot",
    "android_cli_screen_size",
    "android_cli_screen_orientation",
    "android_cli_element_find",
    "android_cli_element_exists",
    "android_cli_element_wait",
    "android_cli_element_click",
    "android_cli_element_set_text",
    "android_cli_element_get_text",
    "android_cli_element_clear_text",
    "android_cli_input_tap",
    "android_cli_input_swipe",
    "android_cli_input_press",
    "android_cli_input_text",
    "android_cli_toast_get",
    "android_cli_device_clipboard_get",
    "android_cli_device_clipboard_set",
    "android_cli_app_current",
    "android_cli_app_launch",
    "android_cli_app_stop",
    "u2cli_doctor",
    "u2cli_devices",
    "u2cli_screen_dump",
    "u2cli_screen_screenshot",
    "u2cli_screen_size",
    "u2cli_screen_orientation",
    "u2cli_element_find",
    "u2cli_element_exists",
    "u2cli_element_wait",
    "u2cli_element_click",
    "u2cli_element_set_text",
    "u2cli_element_get_text",
    "u2cli_element_clear_text",
    "u2cli_input_tap",
    "u2cli_input_swipe",
    "u2cli_input_press",
    "u2cli_input_text",
    "u2cli_toast_get",
    "u2cli_device_clipboard_get",
    "u2cli_device_clipboard_set",
    "u2cli_app_current",
    "u2cli_app_launch",
    "u2cli_app_stop",
}


def _schema_tools_where(mutating: bool | None = None) -> set[str]:
    schema = json.loads(Path("src/u2cli/pi/tools.json").read_text(encoding="utf-8"))
    names = set()
    for spec in schema["tools"]:
        is_mutating = bool(spec.get("mutates") or spec.get("confirm") or spec.get("confirmWhen"))
        if mutating is not None and is_mutating != mutating:
            continue
        for prefix in TOOL_PREFIXES:
            names.add(f"{prefix}{spec['name']}")
    return names


def _require_node_22() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for Pi extension smoke test")

    version = subprocess.run(
        [node, "-p", "process.versions.node.split('.')[0]"],
        check=True,
        capture_output=True,
        text=True,
    )
    if int(version.stdout.strip()) < 22:
        pytest.skip("Node 22+ is required to load TypeScript extension files directly")
    return node


def _prepare_extension_fixture(tmp_path: Path, settings: dict[str, object] | None = None) -> Path:
    shutil.copytree("extensions", tmp_path / "extensions")
    shutil.copytree("src", tmp_path / "src")
    (tmp_path / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    if settings is not None:
        settings_dir = tmp_path / ".pi"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    typebox_dir = tmp_path / "node_modules" / "typebox"
    typebox_dir.mkdir(parents=True)
    (typebox_dir / "package.json").write_text(
        '{"type":"module","exports":"./index.js"}\n',
        encoding="utf-8",
    )
    (typebox_dir / "index.js").write_text(
        """
        const schema = (type) => (options = {}) => ({ type, ...options });
        export const Type = {
          String: schema("string"),
          Integer: schema("integer"),
          Number: schema("number"),
          Boolean: schema("boolean"),
          Optional: (inner) => ({ ...inner, optional: true }),
          Tuple: (items) => ({ type: "array", items }),
          Object: (properties, options = {}) => ({ type: "object", properties, ...options }),
        };
        export default Type;
        """,
        encoding="utf-8",
    )

    agent_dir = tmp_path / "node_modules" / "@earendil-works" / "pi-coding-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "package.json").write_text(
        '{"type":"module","exports":"./index.js"}\n',
        encoding="utf-8",
    )
    (agent_dir / "index.js").write_text("export {};\n", encoding="utf-8")

    script = tmp_path / "smoke.mjs"
    script.write_text(
        """
        import extension from "./extensions/u2cli.ts";
        const tools = [];
        extension({
          on() {},
          registerTool(tool) { tools.push(tool.name); },
        });
        console.log(JSON.stringify(tools.sort()));
        """,
        encoding="utf-8",
    )
    return script


def _registered_tools(
    tmp_path: Path,
    env: dict[str, str] | None = None,
    settings: dict[str, object] | None = None,
) -> set[str]:
    node = _require_node_22()
    script = _prepare_extension_fixture(tmp_path, settings)
    result = subprocess.run(
        [node, str(script)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return set(json.loads(result.stdout))


def test_pi_package_manifest_points_to_extensions_dir() -> None:
    manifest = json.loads(Path("package.json").read_text(encoding="utf-8"))

    assert manifest["keywords"] == ["pi-package"]
    assert manifest["pi"]["extensions"] == ["./extensions"]
    assert set(manifest["peerDependencies"]) == {
        "@earendil-works/pi-ai",
        "@earendil-works/pi-coding-agent",
        "@earendil-works/pi-tui",
        "typebox",
    }


def test_pi_extension_registers_required_u2cli_tools(tmp_path: Path) -> None:
    registered = _registered_tools(tmp_path)

    assert REQUIRED_TOOLS <= registered


@pytest.mark.parametrize("role", ["planner", "healer"])
def test_pi_extension_role_gate_exposes_readonly_tools_only(tmp_path: Path, role: str) -> None:
    registered = _registered_tools(tmp_path, {"PI_AGENT_ROLE": role})

    assert _schema_tools_where(mutating=False) <= registered
    assert registered.isdisjoint(_schema_tools_where(mutating=True))


def test_pi_extension_role_gate_exposes_all_tools_to_executor(tmp_path: Path) -> None:
    registered = _registered_tools(tmp_path, {"PI_AGENT_ROLE": "executor"})

    assert _schema_tools_where() <= registered


def test_pi_extension_role_gate_exposes_no_tools_to_memory_role(tmp_path: Path) -> None:
    registered = _registered_tools(tmp_path, {"PI_AGENT_ROLE": "memory"})

    assert registered == set()


def test_pi_extension_project_settings_can_require_agent_role(tmp_path: Path) -> None:
    registered = _registered_tools(tmp_path, settings={"u2cli": {"requireAgentRole": True}})

    assert registered == set()
