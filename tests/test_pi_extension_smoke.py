from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REQUIRED_TOOLS = {
    "u2cli_doctor",
    "u2cli_devices",
    "u2cli_screen_dump",
    "u2cli_screen_screenshot",
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

    shutil.copytree("extensions", tmp_path / "extensions")
    shutil.copytree("src", tmp_path / "src")
    (tmp_path / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")

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

    result = subprocess.run(
        [node, str(script)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    registered = set(json.loads(result.stdout))

    assert REQUIRED_TOOLS <= registered
