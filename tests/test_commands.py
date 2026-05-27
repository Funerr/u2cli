from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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


def session_file(tmp_path: Path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    path = tmp_path / "session.json"
    monkeypatch.setenv("U2CLI_SESSION_PATH", str(path))
    return path


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


def test_main_help_uses_android_cli_prog_name(capsys) -> None:
    try:
        cli_module.main(["--help"])
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    captured = capsys.readouterr()

    assert code == 0
    assert "Usage: android-cli" in captured.out


def test_main_can_keep_u2cli_compat_prog_name(capsys) -> None:
    try:
        cli_module.main(["--help"], prog_name="u2cli")
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    captured = capsys.readouterr()

    assert code == 0
    assert "Usage: u2cli" in captured.out


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
    assert payload["data"]["nodes"][0]["ref"] == "e0"
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


def test_element_set_text_value_allows_selector_text(fake_device, capsys) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "element",
            "set-text",
            "--text",
            "Login",
            "--value",
            "qa@example.com",
        ],
        capsys,
    )

    assert code == 0
    assert payload["data"]["selector"] == {"text": "Login"}
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


def test_toast_get_uses_snapshot_helper(fake_device, monkeypatch, tmp_path, capsys) -> None:
    from u2cli.screen.snapshot_backend import SnapshotHelperArtifact

    apk = tmp_path / "helper.apk"
    apk.write_bytes(b"helper")
    artifact = SnapshotHelperArtifact(
        str(apk),
        {
            "packageName": "com.callstack.ata.snapshothelper",
            "versionCode": 1,
            "instrumentationRunner": "com.callstack.ata.snapshothelper/.SnapshotInstrumentation",
            "installArgs": ["install", "-r", "-t"],
        },
    )
    monkeypatch.setattr("u2cli.toast.commands.resolve_snapshot_helper", lambda path: artifact)

    def capture_helper(serial, artifact, options, adb_runner=None, action="snapshot"):
        assert action == "toast-get"
        return type(
            "Capture",
            (),
            {
                "metadata": {
                    "toastCapture": {
                        "status": "captured",
                        "latest": {"text": "Saved", "capturedAtMs": 1710000000000},
                    }
                }
            },
        )()

    monkeypatch.setattr("u2cli.toast.commands.capture_with_helper", capture_helper)

    code, payload = run_main(
        ["--serial", "emulator-5554", "--timeout-ms", "1000", "toast", "get"],
        capsys,
    )

    assert code == 0
    assert payload["data"]["message"] == "Saved"
    assert payload["data"]["via"] == "android-snapshot-helper"


def test_toast_get_polls_snapshot_helper_until_captured(
    fake_device,
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    from u2cli.screen.snapshot_backend import SnapshotHelperArtifact

    apk = tmp_path / "helper.apk"
    apk.write_bytes(b"helper")
    artifact = SnapshotHelperArtifact(str(apk), {"versionCode": 1})
    monkeypatch.setattr("u2cli.toast.commands.resolve_snapshot_helper", lambda path: artifact)
    captures = 0

    def capture_helper(serial, artifact, options, adb_runner=None, action="snapshot"):
        nonlocal captures
        captures += 1
        latest = {"text": "Saved"} if captures == 2 else None
        return type(
            "Capture",
            (),
            {
                "metadata": {
                    "toastCapture": {"status": "captured" if latest else "empty", "latest": latest}
                }
            },
        )()

    monkeypatch.setattr("u2cli.toast.commands.capture_with_helper", capture_helper)
    monkeypatch.setattr("u2cli.toast.commands.time.sleep", lambda seconds: None)

    code, payload = run_main(
        ["--serial", "emulator-5554", "--timeout-ms", "1000", "toast", "get"],
        capsys,
    )

    assert code == 0
    assert payload["data"]["message"] == "Saved"
    assert captures == 2


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
    tools = {tool["name"]: tool for tool in payload["data"]["tools"]}
    assert tools["element_set_text"]["optionFlags"] == {"text": "--value"}


def test_session_info(capsys) -> None:
    code, payload = run_main(["session", "info"], capsys)

    assert code == 0
    assert payload["command"] == "session.info"
    assert payload["data"]["mode"] == "per-command"


def test_connect_writes_session_and_hydrates_serial(
    fake_device,
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    session_file(tmp_path, monkeypatch)

    code, payload = run_main(["--serial", "emulator-5554", "connect"], capsys)
    assert code == 0
    assert payload["data"]["serial"] == "emulator-5554"

    code, payload = run_main(["connect", "--serial", "emulator-5554"], capsys)
    assert code == 0
    assert payload["data"]["serial"] == "emulator-5554"

    code, payload = run_main(["appstate"], capsys)
    assert code == 0
    assert payload["serial"] == "emulator-5554"
    assert payload["data"]["package"] == "com.example"


def test_snapshot_writes_ref_cache_and_click_fill_get_ref(
    fake_device,
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    session_file(tmp_path, monkeypatch)

    code, payload = run_main(["--serial", "emulator-5554", "snapshot", "-i"], capsys)
    assert code == 0
    assert payload["command"] == "snapshot"
    assert payload["data"]["nodes"][0]["ref"] == "e0"
    assert "refMap" not in payload["data"]

    code, payload = run_main(["click", "@e0"], capsys)
    assert code == 0
    assert payload["data"]["via"] == "bounds"
    assert fake_device.taps[-1] == (380, 1260)

    code, payload = run_main(["fill", "@e0", "qa@example.com"], capsys)
    assert code == 0
    assert payload["data"]["filled"] is True
    assert fake_device.sent_text[-1] == "qa@example.com"

    code, payload = run_main(["get", "text", "@e0"], capsys)
    assert code == 0
    assert payload["data"]["cached"] is True
    assert payload["data"]["text"] == "Login"

    code, payload = run_main(["find", "text=Login"], capsys)
    assert code == 0
    assert payload["data"]["cached"] is True
    assert payload["data"]["matchedCount"] == 1

    code, payload = run_main(["wait", "text", "Login", "1000"], capsys)
    assert code == 0
    assert payload["data"]["cached"] is True

    code, payload = run_main(
        ["click", "@e0", "--double-tap", "--count", "2", "--jitter-px", "4"], capsys
    )
    assert code == 0
    assert payload["data"]["tapCount"] == 4
    assert len(fake_device.taps) >= 5

    code, payload = run_main(["click", "@e0", "--hold-ms", "800"], capsys)
    assert code == 0
    assert payload["data"]["held"] is True
    assert fake_device.swipes[-1][4] == 0.8


def test_snapshot_target_text_reports_compact_matches(fake_device, capsys) -> None:
    code, payload = run_main(
        ["--serial", "emulator-5554", "snapshot", "-i", "--target-text", "Login"],
        capsys,
    )

    assert code == 0
    assert payload["data"]["targetText"]["state"] == "found"
    assert payload["data"]["targetText"]["matchedCount"] == 1
    assert payload["data"]["targetText"]["refs"] == ["@e0"]

    code, payload = run_main(["--serial", "emulator-5554", "snapshot", "--target-text", ""], capsys)
    assert code == 64
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_top_level_selector_commands_and_wait_diagnostics(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "click", "text=Login"], capsys)
    assert code == 0
    assert payload["command"] == "click"
    assert fake_device.element.clicked is True

    code, payload = run_main(["--serial", "emulator-5554", "wait", "text", "Login", "1000"], capsys)
    assert code == 0
    assert payload["data"]["attempts"] >= 1
    assert payload["data"]["matchedCount"] == 1
    assert payload["data"]["selectedIndex"] == 0

    code, payload = run_main(["--serial", "emulator-5554", "is", "enabled", "text=Login"], capsys)
    assert code == 0
    assert payload["data"]["result"] is True


def test_top_level_click_percent_coordinates(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "click", "50", "80"], capsys)

    assert code == 0
    assert payload["data"]["percent"] == [50, 80]
    assert fake_device.taps[-1] == (540, 1920)


def test_find_ambiguous_requires_first_or_last(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "find", "text=many"], capsys)
    assert code == 1
    assert payload["error"]["code"] == "ELEMENT_AMBIGUOUS"

    code, payload = run_main(["--serial", "emulator-5554", "find", "text=many", "--first"], capsys)
    assert code == 0
    assert payload["data"]["matchedCount"] == 2
    assert payload["data"]["selectedIndex"] == 0


def test_batch_preserves_successful_steps_on_failure(fake_device, tmp_path, capsys) -> None:
    steps = json.dumps(
        [
            {"command": "back"},
            {"command": "click", "args": ["text=missing"]},
            {"command": "home"},
        ]
    )

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "batch",
            "--steps",
            steps,
            "--out",
            str(tmp_path / "batch-failed.json"),
        ],
        capsys,
    )

    assert code == 1
    assert payload["success"] is False
    assert payload["error"]["code"] == "BATCH_STEP_FAILED"
    assert payload["failed"] == 1
    assert payload["steps"][0]["success"] is True
    assert payload["steps"][1]["success"] is False
    assert payload["artifacts"][0]["type"] == "batch-result"


def test_alert_accept_finds_candidate(fake_device, capsys) -> None:
    fake_device.element.text_value = "OK"

    code, payload = run_main(["--serial", "emulator-5554", "alert", "accept"], capsys)

    assert code == 0
    assert payload["data"]["role"] == "accept"
    assert payload["data"]["attempts"] >= 1
    assert payload["data"]["matchedCount"] >= 1
    assert payload["data"]["candidate"]["text"] == "OK"


def test_keyboard_status(fake_device, capsys) -> None:
    fake_device.last_shell_output = (
        "mInputShown=true\nmCurId=com.example/.Ime\nmServedView=EditText"
    )

    code, payload = run_main(["--serial", "emulator-5554", "keyboard", "status"], capsys)

    assert code == 0
    assert payload["data"]["shown"] is True
    assert payload["data"]["currentIme"] == "com.example/.Ime"


def test_install_from_source_local_apk(fake_device, tmp_path, capsys) -> None:
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")

    code, payload = run_main(
        ["--serial", "emulator-5554", "install-from-source", str(apk)],
        capsys,
    )

    assert code == 0
    assert payload["command"] == "install-from-source"
    assert payload["data"]["installed"] is True
    assert payload["data"]["downloaded"] is False
