from __future__ import annotations

import json
from dataclasses import dataclass

from typer.testing import CliRunner

import u2cli.cli as cli_module


@dataclass
class FakeAdbDevice:
    serial: str
    state: str


def run_cli(runner: CliRunner, args: list[str]) -> tuple[int, dict]:
    result = runner.invoke(cli_module.app, args, obj={})
    assert result.output
    return result.exit_code, json.loads(result.output)


def run_main(args: list[str], capsys) -> tuple[int, dict]:
    try:
        cli_module.main(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def test_doctor_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("u2cli.device.connect.adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr("u2cli.device.connect.adb_version", lambda: "Android Debug Bridge version")
    monkeypatch.setattr("u2cli.device.connect.list_adb_devices", lambda: [])
    monkeypatch.setattr("u2cli.device.health.adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr("u2cli.device.health.adb_version", lambda: "Android Debug Bridge version")
    monkeypatch.setattr("u2cli.device.health.list_adb_devices", lambda: [])

    code, payload = run_main(["--json", "doctor"], capsys)

    assert code == 0
    assert payload["success"] is True
    assert payload["command"] == "doctor"
    assert payload["data"]["python"]["ok"] is True


def test_devices_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "u2cli.device.health.list_adb_devices",
        lambda: [FakeAdbDevice("emulator-5554", "device")],
    )

    code, payload = run_main(["devices"], capsys)

    assert code == 0
    assert payload["data"]["devices"][0]["serial"] == "emulator-5554"


def test_screen_dump_compact(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "screen", "dump", "--compact"], capsys)

    assert code == 0
    assert payload["command"] == "screen.dump"
    assert payload["data"]["nodes"][0]["text"] == "Login"


def test_element_click_success(fake_device, capsys) -> None:
    code, payload = run_main(
        ["--serial", "emulator-5554", "element", "click", "--text", "Login"],
        capsys,
    )

    assert code == 0
    assert payload["data"]["clicked"] is True
    assert fake_device.element.clicked is True


def test_element_click_ambiguous(fake_device, capsys) -> None:
    code, payload = run_main(
        ["--serial", "emulator-5554", "element", "click", "--text", "many"],
        capsys,
    )

    assert code == 1
    assert payload["error"]["code"] == "ELEMENT_AMBIGUOUS"


def test_element_set_text(fake_device, capsys) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "element",
            "set-text",
            "--resource-id",
            "com.example:id/login",
            "--text",
            "qa@example.com",
        ],
        capsys,
    )

    assert code == 0
    assert payload["data"]["setText"] is True
    assert fake_device.element.text_value == "qa@example.com"


def test_app_list_and_permission(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "app", "list"], capsys)
    assert code == 0
    assert payload["data"]["count"] == 2

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "app",
            "grant",
            "--package",
            "com.example",
            "--permission",
            "android.permission.CAMERA",
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["granted"] is True
    assert "pm grant com.example android.permission.CAMERA" in fake_device.shell_commands


def test_device_clipboard_push_pull(fake_device, tmp_path, capsys) -> None:
    local = tmp_path / "local.txt"
    pulled = tmp_path / "pulled.txt"
    local.write_text("hello")

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "device",
            "push",
            "--local",
            str(local),
            "--remote",
            "/sdcard/local.txt",
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["pushed"] is True

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "device",
            "pull",
            "--remote",
            "/sdcard/local.txt",
            "--local",
            str(pulled),
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["pulled"] is True
    assert pulled.exists()

    code, payload = run_main(
        ["--serial", "emulator-5554", "device", "clipboard-set", "--text", "copied"],
        capsys,
    )
    assert code == 0
    assert payload["data"]["set"] is True

    code, payload = run_main(["--serial", "emulator-5554", "device", "clipboard-get"], capsys)
    assert code == 0
    assert payload["data"]["text"] == "copied"


def test_screen_and_element_extensions(fake_device, tmp_path, capsys) -> None:
    code, payload = run_main(
        ["--serial", "emulator-5554", "screen", "orientation", "--set", "left"],
        capsys,
    )
    assert code == 0
    assert payload["data"]["orientation"] == "left"

    code, payload = run_main(
        ["--serial", "emulator-5554", "element", "exists", "--text", "Login"],
        capsys,
    )
    assert code == 0
    assert payload["data"]["exists"] is True

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "element",
            "swipe",
            "--text",
            "Login",
            "--direction",
            "up",
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["swiped"] is True

    out = tmp_path / "record.mp4"
    code, payload = run_main(
        ["--serial", "emulator-5554", "screen", "record", "--out", str(out)],
        capsys,
    )
    assert code == 0
    assert payload["data"]["recorded"] is True


def test_input_swipe(fake_device, capsys) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "input",
            "swipe",
            "--from",
            "1,2",
            "--to",
            "3,4",
            "--duration-ms",
            "400",
        ],
        capsys,
    )

    assert code == 0
    assert payload["data"]["from"] == [1, 2]
    assert fake_device.swipes == [(1, 2, 3, 4, 0.4)]


def test_input_drag_and_keyevent(fake_device, capsys) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "input",
            "drag",
            "--from",
            "1,2",
            "--to",
            "3,4",
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["dragged"] is True

    code, payload = run_main(
        ["--serial", "emulator-5554", "input", "keyevent", "--code", "4"],
        capsys,
    )
    assert code == 0
    assert payload["data"]["pressed"] is True


def test_toast_get_requires_explicit_timeout(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "toast", "get"], capsys)

    assert code == 64
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_toast_timeout(fake_device, capsys) -> None:
    code, payload = run_main(
        ["--serial", "emulator-5554", "--timeout-ms", "10", "toast", "get"],
        capsys,
    )

    assert code == 1
    assert payload["error"]["code"] == "TOAST_TIMEOUT"


def test_screenshot_artifact(fake_device, tmp_path, capsys) -> None:
    out = tmp_path / "screen.png"

    code, payload = run_main(
        ["--serial", "emulator-5554", "screen", "screenshot", "--out", str(out)],
        capsys,
    )

    assert code == 0
    assert out.exists()
    assert payload["artifacts"][0]["type"] == "screenshot"


def test_missing_option_is_json(capsys) -> None:
    code, payload = run_main(["app", "start"], capsys)

    assert code == 64
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_pi_schema(capsys) -> None:
    code, payload = run_main(["pi", "schema"], capsys)

    assert code == 0
    assert payload["command"] == "pi.schema"
    assert payload["data"]["tools"][0]["name"] == "doctor"


def test_session_info(capsys) -> None:
    code, payload = run_main(["session", "info"], capsys)

    assert code == 0
    assert payload["command"] == "session.info"
    assert payload["data"]["mode"] == "per-command"
