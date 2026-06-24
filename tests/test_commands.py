from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
from typer.testing import CliRunner

import androidtestclii.cli as cli_module


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
    monkeypatch.setenv("ANDROIDTESTCLII_SESSION_PATH", str(path))
    return path


def test_doctor_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("androidtestclii.device.connect.adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr("androidtestclii.device.connect.adb_version", lambda: "Android Debug Bridge version")
    monkeypatch.setattr("androidtestclii.device.connect.list_adb_devices", lambda: [])
    monkeypatch.setattr("androidtestclii.device.health.adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr("androidtestclii.device.health.adb_version", lambda: "Android Debug Bridge version")
    monkeypatch.setattr("androidtestclii.device.health.list_adb_devices", lambda: [])

    code, payload = run_main(["--json", "doctor"], capsys)

    assert code == 0
    assert payload["success"] is True
    assert payload["command"] == "doctor"
    assert payload["data"]["python"]["ok"] is True
    assert payload["data"]["metadata"]["capabilityLayer"] == "adb-fast-path"


def test_main_help_uses_androidtestclii_prog_name(capsys) -> None:
    try:
        cli_module.main(["--help"])
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    captured = capsys.readouterr()

    assert code == 0
    assert "Usage: AndroidTestClii" in captured.out


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
        "androidtestclii.device.health.list_adb_devices",
        lambda: [FakeAdbDevice("emulator-5554", "device")],
    )

    code, payload = run_main(["devices"], capsys)

    assert code == 0
    assert payload["data"]["devices"][0]["serial"] == "emulator-5554"


def test_screen_dump_compact(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "screen", "dump", "--compact"], capsys)

    assert code == 0
    assert payload["command"] == "screen.dump"
    assert payload["data"]["nodes"][0]["ref"] == "@e0"
    assert payload["data"]["nodes"][0]["text"] == "Login"
    assert payload["data"]["snapshot"]["full"] is False
    assert payload["data"]["snapshot"]["complete"] is False
    assert payload["data"]["snapshot"]["canProveAbsence"] is False


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
    from androidtestclii.screen.snapshot_backend import SnapshotHelperArtifact

    apk = tmp_path / "helper.apk"
    apk.write_bytes(b"helper")
    artifact = SnapshotHelperArtifact(
        str(apk),
        {
            "packageName": "com.callstack.androidtestclii.snapshothelper",
            "versionCode": 1,
            "instrumentationRunner": "com.callstack.androidtestclii.snapshothelper/.SnapshotInstrumentation",
            "installArgs": ["install", "-r", "-t"],
        },
    )
    monkeypatch.setattr("androidtestclii.toast.commands.resolve_snapshot_helper", lambda path: artifact)

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

    monkeypatch.setattr("androidtestclii.toast.commands.capture_with_helper", capture_helper)

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
    from androidtestclii.screen.snapshot_backend import SnapshotHelperArtifact

    apk = tmp_path / "helper.apk"
    apk.write_bytes(b"helper")
    artifact = SnapshotHelperArtifact(str(apk), {"versionCode": 1})
    monkeypatch.setattr("androidtestclii.toast.commands.resolve_snapshot_helper", lambda path: artifact)
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

    monkeypatch.setattr("androidtestclii.toast.commands.capture_with_helper", capture_helper)
    monkeypatch.setattr("androidtestclii.toast.commands.time.sleep", lambda seconds: None)

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


def test_diff_screenshot_reports_pixel_stats_and_overlay(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    diff = tmp_path / "diff.png"
    Image.new("RGBA", (2, 1), (0, 0, 0, 255)).save(baseline)
    image = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    image.putpixel((1, 0), (255, 0, 0, 255))
    image.save(current)

    code, payload = run_main(
        [
            "diff",
            "screenshot",
            str(current),
            "--baseline",
            str(baseline),
            "--threshold",
            "40%",
            "--out",
            str(diff),
        ],
        capsys,
    )

    assert code == 0
    assert payload["command"] == "diff.screenshot"
    data = payload["data"]
    assert data["available"] is True
    assert data["method"] == "png-pixel-diff"
    assert data["totalPixels"] == 2
    assert data["changedPixels"] == 1
    assert data["diffRatio"] == 0.5
    assert data["thresholdRatio"] == 0.4
    assert data["passed"] is False
    assert payload["artifacts"] == [
        {"type": "diff", "path": str(diff), "description": "screenshot pixel diff overlay"}
    ]
    assert diff.exists()


def test_screenshot_overlay_refs_draws_recent_snapshot_refs(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "snapshot", "-i"], capsys)
    assert code == 0
    out = tmp_path / "screen.png"

    def screenshot(path: str) -> object:
        Image.new("RGBA", (1080, 2400), (255, 255, 255, 255)).save(path)

        class Captured:
            width = 1080
            height = 2400

        return Captured()

    fake_device.screenshot = screenshot  # type: ignore[method-assign]

    code, payload = run_main(
        ["--serial", "emulator-5554", "screenshot", str(out), "--overlay-refs"],
        capsys,
    )

    overlay = tmp_path / "screen-refs.png"
    assert code == 0
    assert payload["command"] == "screenshot"
    assert payload["data"]["path"] == str(out)
    assert payload["data"]["overlayRefs"] is True
    assert payload["data"]["overlayCount"] == 1
    assert payload["data"]["overlayPath"] == str(overlay)
    assert payload["artifacts"][-1] == {
        "type": "screenshot-overlay",
        "path": str(overlay),
        "description": "screenshot with snapshot refs",
    }
    assert overlay.exists()


def test_logs_start_stop_filter_marker_and_write_artifact(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    target = tmp_path / "run.log"

    code, payload = run_main(
        ["--serial", "emulator-5554", "logs", "start", str(target), "--restart"],
        capsys,
    )

    assert code == 0
    marker = payload["data"]["marker"]
    fake_device.last_log_marker = marker
    assert payload["command"] == "logs.start"
    assert payload["data"]["method"] == "android-logcat"
    assert payload["data"]["path"] == str(target)
    assert payload["data"]["bulkShell"] is True
    assert fake_device.shell_commands[-1].startswith("logcat -c && log -t AndroidTestClii")

    code, payload = run_main(["--serial", "emulator-5554", "logs", "stop"], capsys)

    assert code == 0
    assert payload["command"] == "logs.stop"
    assert payload["data"]["path"] == str(target)
    assert payload["data"]["filteredByMarker"] is True
    assert payload["data"]["rawLineCount"] == 4
    assert payload["data"]["capturedLineCount"] == 2
    assert payload["artifacts"] == [
        {"type": "logs", "path": str(target), "description": "device logs"}
    ]
    text = target.read_text(encoding="utf-8")
    assert "OkHttp" in text
    assert "old.example.test" not in text

    code, payload = run_main(["logs", "path"], capsys)
    assert code == 0
    assert payload["data"]["activeCapture"] is None


def test_logs_path_doctor_clear_and_mark(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "logs", "path"], capsys)
    assert code == 0
    assert payload["data"]["method"] == "android-logcat"
    assert payload["data"]["defaultPath"] == "artifacts/androidtestclii-logcat.log"

    code, payload = run_main(["--serial", "emulator-5554", "logs", "doctor"], capsys)
    assert code == 0
    assert payload["data"]["diagnostics"]["captureActive"] is False
    assert payload["data"]["nextSteps"][-1] == "network --include summary"

    code, payload = run_main(["--serial", "emulator-5554", "logs", "clear", "--restart"], capsys)
    assert code == 0
    assert payload["data"]["action"] == "clear"
    assert payload["data"]["restart"] is True

    code, payload = run_main(["--serial", "emulator-5554", "logs", "mark", "checkpoint"], capsys)
    assert code == 0
    assert payload["data"]["message"] == "checkpoint"
    assert fake_device.shell_commands[-1] == "log -t AndroidTestClii checkpoint"


def test_trace_start_stop_writes_artifact(fake_device, tmp_path, capsys) -> None:
    target = tmp_path / "trace.html"

    code, payload = run_main(["--serial", "emulator-5554", "trace", "start", str(target)], capsys)
    assert code == 0
    assert payload["command"] == "trace.start"
    assert payload["data"]["method"] == "android-atrace"
    assert payload["data"]["path"] == str(target)
    assert fake_device.shell_commands[-1].startswith("atrace --async_start")

    code, payload = run_main(["--serial", "emulator-5554", "trace", "stop"], capsys)
    assert code == 0
    assert payload["command"] == "trace.stop"
    assert payload["data"]["path"] == str(target)
    assert payload["artifacts"] == [
        {"type": "trace", "path": str(target), "description": "device trace"}
    ]
    assert target.read_text(encoding="utf-8") == "<html>trace</html>"


def test_perf_collect_procfs_snapshot(fake_device, tmp_path, capsys) -> None:
    out = tmp_path / "perf.json"

    code, payload = run_main(
        ["--serial", "emulator-5554", "perf", "collect", "--app", "com.example", "--out", str(out)],
        capsys,
    )

    assert code == 0
    assert payload["command"] == "perf.collect"
    data = payload["data"]
    assert data["method"] == "android-procfs"
    assert data["memory"]["totalKb"] == 1000
    assert data["memory"]["availableKb"] == 600
    assert data["cpu"]["totalJiffies"] == 100
    assert data["cpu"]["busyJiffies"] == 30
    assert data["processes"][0]["pid"] == 123
    assert data["path"] == str(out)
    assert payload["artifacts"] == [
        {"type": "perf", "path": str(out), "description": "procfs perf snapshot"}
    ]
    assert out.exists()


def test_network_summary_parses_logcat_and_artifact(fake_device, tmp_path, capsys) -> None:
    fake_device.last_logcat_output = "\n".join(
        [
            "D/OkHttp: --> GET https://api.example.test/users",
            "D/OkHttp: <-- 200 https://api.example.test/users (120ms)",
            "D/OkHttp: --> POST https://api.example.test/login",
            "D/OkHttp: status=401 https://api.example.test/login duration=5ms",
        ]
    )

    code, payload = run_main(
        ["--serial", "emulator-5554", "network", "--limit", "2", "--include", "summary"],
        capsys,
    )

    assert code == 0
    assert payload["command"] == "network"
    data = payload["data"]
    assert data["source"] == "android-logcat"
    assert data["count"] == 2
    assert data["traffic"][0]["method"] == "GET"
    assert data["traffic"][0]["url"] == "https://api.example.test/users"
    assert data["traffic"][0]["status"] == 200
    assert data["traffic"][0]["durationMs"] == 120
    assert "raw" not in data["traffic"][0]
    assert data["traffic"][1]["method"] == "POST"
    assert data["traffic"][1]["status"] == 401

    log = tmp_path / "network.log"
    log.write_text("I/App: GET https://api.example.test/raw status=204 duration=9ms\n", encoding="utf-8")
    code, payload = run_main(["network", "--log-path", str(log), "--include", "all"], capsys)
    assert code == 0
    assert payload["data"]["source"] == "logs-artifact"
    assert payload["data"]["traffic"][0]["raw"].endswith("duration=9ms")


def test_settings_write_and_readback(fake_device, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "settings", "animations", "off"], capsys)
    assert code == 0
    assert payload["command"] == "settings"
    assert payload["data"]["setting"] == "animations"
    assert payload["data"]["verified"] is True
    assert payload["data"]["readback"]["window_animation_scale"] == "0"

    code, payload = run_main(["--serial", "emulator-5554", "settings", "wifi", "on"], capsys)
    assert code == 0
    assert payload["data"]["readback"]["wifi_on"] == "1"

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "settings",
            "permission",
            "grant",
            "com.example",
            "android.permission.CAMERA",
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["verified"] is True
    assert payload["data"]["readback"]["granted"] is True


def test_push_and_trigger_app_event_parse_results(fake_device, capsys) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "push",
            "com.example",
            '{"action":"com.example.PUSH","id":1}',
        ],
        capsys,
    )
    assert code == 0
    assert payload["command"] == "push"
    assert payload["data"]["action"] == "com.example.PUSH"
    assert payload["data"]["extrasCount"] == 1
    assert payload["data"]["broadcastResult"] == 0
    assert payload["data"]["delivered"] is True
    assert "am broadcast" in fake_device.shell_commands[-1]

    code, payload = run_main(
        ["--serial", "emulator-5554", "trigger-app-event", "screenshot_taken", '{"id":1}'],
        capsys,
    )
    assert code == 0
    assert payload["command"] == "trigger-app-event"
    assert payload["data"]["event"] == "screenshot_taken"
    assert payload["data"]["started"] is True
    assert payload["data"]["alreadyRunning"] is False
    assert "devicetestcli://event/screenshot_taken" in payload["data"]["uri"]


def test_boot_and_ensure_simulator_persist_session(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    session_file(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "androidtestclii.system_control.list_adb_devices",
        lambda: [FakeAdbDevice("emulator-5554", "device")],
    )

    code, payload = run_main(["--serial", "emulator-5554", "boot"], capsys)
    assert code == 0
    assert payload["command"] == "boot"
    assert payload["data"]["available"] is True
    assert payload["data"]["sessionPersisted"] is True
    assert payload["data"]["compatCommand"] == "boot"

    code, payload = run_main(["ensure-simulator", "--boot", "--runtime", "android"], capsys)
    assert code == 0
    assert payload["command"] == "ensure-simulator"
    assert payload["data"]["bootRequested"] is True
    assert payload["data"]["runtime"] == "android"
    assert payload["serial"] == "emulator-5554"


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
    assert tools["element_set_text"]["optionFlags"] == {"target": "--target", "text": "--value"}
    assert tools["runtime_status"]["command"] == ["runtime", "status"]
    assert tools["session_list"]["command"] == ["session", "list"]
    assert tools["snapshot_capture"]["command"] == ["snapshot", "capture"]
    assert tools["diff_screenshot"]["command"] == ["diff", "screenshot"]
    assert tools["diff_snapshot"]["command"] == ["diff", "snapshot"]
    assert tools["screenshot"]["command"] == ["screenshot"]
    assert tools["logs_start"]["command"] == ["logs", "start"]
    assert tools["logs_stop"]["command"] == ["logs", "stop"]
    assert tools["logs_doctor"]["command"] == ["logs", "doctor"]
    assert tools["trace_start"]["command"] == ["trace", "start"]
    assert tools["trace_stop"]["command"] == ["trace", "stop"]
    assert tools["perf_collect"]["command"] == ["perf", "collect"]
    assert tools["network"]["command"] == ["network"]
    assert tools["settings"]["command"] == ["settings"]
    assert tools["push"]["command"] == ["push"]
    assert tools["trigger_app_event"]["command"] == ["trigger-app-event"]
    assert tools["boot"]["command"] == ["boot"]
    assert tools["ensure_simulator"]["command"] == ["ensure-simulator"]
    assert tools["replay"]["command"] == ["replay"]
    assert tools["test"]["command"] == ["test"]
    assert tools["gesture"]["command"] == ["gesture"]
    assert tools["record_start"]["command"] == ["record", "start"]
    assert tools["record_stop"]["command"] == ["record", "stop"]
    assert tools["react_native"]["command"] == ["react-native"]


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


def test_explicit_serial_overrides_session(
    fake_device,
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    session_file(tmp_path, monkeypatch)

    code, payload = run_main(["--serial", "session-device", "connect"], capsys)
    assert code == 0
    assert payload["data"]["serial"] == "session-device"

    code, payload = run_main(["--serial", "explicit-device", "appstate"], capsys)
    assert code == 0
    assert payload["serial"] == "explicit-device"


def test_runtime_and_session_status_commands(
    fake_device,
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    session_file(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "androidtestclii.session.commands.list_adb_devices",
        lambda: [FakeAdbDevice("emulator-5554", "device")],
    )
    monkeypatch.setattr("androidtestclii.session.commands.resolve_snapshot_helper", lambda path: None)
    monkeypatch.setattr("androidtestclii.session.commands.resolve_snapshot_jar", lambda path: None)

    code, payload = run_main(["--serial", "emulator-5554", "snapshot", "-i"], capsys)
    assert code == 0

    code, payload = run_main(["runtime", "status"], capsys)
    assert code == 0
    assert payload["command"] == "runtime.status"
    assert payload["data"]["lastSnapshotState"] == "available"
    assert payload["data"]["snapshotHelper"]["available"] is False
    assert payload["data"]["metadata"]["capabilityLayer"] == "adb-fast-path"

    code, payload = run_main(["session", "status"], capsys)
    assert code == 0
    assert payload["data"]["status"] == "connected"
    assert payload["data"]["deviceOnline"] is True

    code, payload = run_main(["session", "list"], capsys)
    assert code == 0
    assert payload["data"]["count"] == 1
    assert payload["data"]["sessions"][0]["serial"] == "emulator-5554"

    code, payload = run_main(["runtime", "clear"], capsys)
    assert code == 0
    assert payload["data"]["runtime"]["temporaryAutomation"]["state"] == "cleared"


def test_session_status_marks_missing_cached_device_stale(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    from androidtestclii.session import store as session_store

    session_file(tmp_path, monkeypatch)
    session_store.update_session(serial="missing-device", timeout_ms=1000)
    monkeypatch.setattr(
        "androidtestclii.session.commands.list_adb_devices",
        lambda: [FakeAdbDevice("emulator-5554", "device")],
    )

    code, payload = run_main(["session", "status"], capsys)

    assert code == 0
    assert payload["data"]["stale"] is True
    assert payload["data"]["staleReason"] == "session-device-not-listed"


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
    assert payload["data"]["nodes"][0]["ref"] == "@e0"
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


def test_ref_errors_are_structured(fake_device, monkeypatch, tmp_path, capsys) -> None:
    from androidtestclii.session import store as session_store

    session_file(tmp_path, monkeypatch)
    session_store.update_session(
        serial="emulator-5554",
        last_snapshot=session_store.LastSnapshot(
            capturedAt="2026-05-28T00:00:00.000Z",
            serial="emulator-5554",
            refMap={
                "@e0": session_store.SnapshotRef(text="No selector or bounds"),
            },
        ),
    )

    code, payload = run_main(["click", "@e1"], capsys)
    assert code == 1
    assert payload["error"]["code"] == "SNAPSHOT_REF_NOT_FOUND"

    code, payload = run_main(["click", "@e0"], capsys)
    assert code == 1
    assert payload["error"]["code"] == "SNAPSHOT_REF_INVALID"


def test_snapshot_target_text_reports_compact_matches(fake_device, capsys) -> None:
    code, payload = run_main(
        ["--serial", "emulator-5554", "snapshot", "-i", "--target-text", "Login"],
        capsys,
    )

    assert code == 0
    assert payload["data"]["targetText"]["state"] == "found"
    assert payload["data"]["targetText"]["matchedCount"] == 1
    assert payload["data"]["targetText"]["refs"] == ["@e0"]
    assert payload["data"]["snapshot"]["canProveAbsence"] is False
    assert payload["data"]["targetLocation"]["state"] == "found"
    assert payload["data"]["targetLocation"]["canProveAbsence"] is False

    code, payload = run_main(["--serial", "emulator-5554", "snapshot", "--target-text", ""], capsys)
    assert code == 64
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_snapshot_capture_full_returns_diagnostic_contract(fake_device, capsys) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "snapshot",
            "capture",
            "--full",
            "--target-text",
            "Missing",
        ],
        capsys,
    )

    assert code == 0
    assert payload["command"] == "snapshot.capture"
    snapshot = payload["data"]["snapshot"]
    assert snapshot["mode"] == "full"
    assert snapshot["full"] is False
    assert snapshot["complete"] is False
    assert snapshot["canProveAbsence"] is False
    assert snapshot["coverage"] == "diagnostic"
    assert snapshot["coverageFailureReason"] == "FULL_SNAPSHOT_COVERAGE_FAILED"
    assert snapshot["nodeCount"] >= 1
    assert snapshot["observedNodeCount"] >= 1
    assert payload["data"]["targetLocation"]["state"] == "coverage-failed"
    assert payload["data"]["targetLocation"]["canProveAbsence"] is False
    assert payload["data"]["metadata"]["snapshotFull"] is False
    assert payload["data"]["metadata"]["snapshotCanProveAbsence"] is False


def test_diff_snapshot_compares_node_signatures_and_refreshes_session(
    fake_device,
    capsys,
) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "snapshot", "-i"], capsys)
    assert code == 0

    fake_device.dump_hierarchy = lambda: """
        <hierarchy>
          <node index="0" text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false" enabled="true">
            <node index="1" text="Signup" resource-id="com.example:id/signup" class="android.widget.Button" bounds="[40,1200][720,1320]" clickable="true" enabled="true" />
          </node>
        </hierarchy>
    """  # type: ignore[method-assign]

    code, payload = run_main(["--serial", "emulator-5554", "diff", "snapshot"], capsys)

    assert code == 0
    assert payload["command"] == "diff.snapshot"
    data = payload["data"]
    assert data["changed"] is True
    assert data["diff"]["addedCount"] == 1
    assert data["diff"]["removedCount"] == 1
    assert data["diff"]["commonCount"] == 0
    assert data["current"]["nodeCount"] == 1

    code, payload = run_main(["get", "text", "@e0"], capsys)
    assert code == 0
    assert payload["data"]["text"] == "Signup"


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


def test_legacy_u2cli_element_click_matches_android_cli(fake_device, capsys) -> None:
    try:
        cli_module.main(["--serial", "emulator-5554", "element", "click", "--text", "Login"], prog_name="u2cli")
    except SystemExit as exc:
        u2cli_code = int(exc.code or 0)
    else:
        u2cli_code = 0
    u2cli_payload = json.loads(capsys.readouterr().out)

    fake_device.element.clicked = False
    code, android_payload = run_main(
        ["--serial", "emulator-5554", "element", "click", "--text", "Login"],
        capsys,
    )

    assert u2cli_code == 0
    assert code == 0
    assert u2cli_payload["command"] == android_payload["command"] == "element.click"
    assert u2cli_payload["data"]["selector"] == android_payload["data"]["selector"]
    assert android_payload["data"]["clicked"] is True


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


def test_replay_executes_ad_script_context_env_and_quoted_args(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    script = tmp_path / "flow.ad"
    script.write_text(
        "\n".join(
            [
                "# smoke",
                "context serial=emulator-5554 timeoutMs=1000",
                "back",
                "click 10,20",
                'fill "text=Login" "${EMAIL}"',
            ]
        ),
        encoding="utf-8",
    )

    code, payload = run_main(["replay", str(script), "--replay-env", "EMAIL=qa@example.com"], capsys)

    assert code == 0
    assert payload["command"] == "replay"
    data = payload["data"]
    assert data["path"] == str(script)
    assert data["replayed"] == 3
    assert data["healed"] == 0
    assert data["updated"] is False
    assert [step["command"] for step in data["results"]] == ["back", "click", "fill"]
    assert fake_device.pressed[-1] == "back"
    assert fake_device.taps[-1] == (10, 20)
    assert fake_device.sent_text[-1] == "qa@example.com"


def test_replay_update_rewrites_script_with_normalized_steps(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    script = tmp_path / "flow.ad"
    script.write_text(
        "\n".join(
            [
                "# old smoke",
                "context serial=emulator-5554 timeoutMs=1000",
                "u2cli back",
                "AndroidTestClii click 10,20",
            ]
        ),
        encoding="utf-8",
    )

    code, payload = run_main(["replay", str(script), "--replay-update"], capsys)

    assert code == 0
    data = payload["data"]
    backup = tmp_path / "flow.ad.bak"
    assert data["updated"] is True
    assert data["normalizedSteps"] == 2
    assert data["backupPath"] == str(backup)
    assert backup.exists()
    assert script.read_text(encoding="utf-8").splitlines() == [
        "# updated by AndroidTestClii replay --replay-update",
        "context serial=emulator-5554 timeoutMs=1000",
        "back",
        "click 10,20",
    ]


def test_replay_heals_selector_step_from_recent_snapshot_ref(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    from androidtestclii.session import store as session_store

    fake_device.element.text_value = "Login"
    script = tmp_path / "flow.ad"
    script.write_text("context serial=emulator-5554\nclick text=Email\n", encoding="utf-8")
    session_store.update_session(
        serial="emulator-5554",
        last_snapshot=session_store.LastSnapshot(
            capturedAt="2026-05-28T00:00:00.000Z",
            serial="emulator-5554",
            refMap={
                "@e0": session_store.SnapshotRef(
                    selector={"text": "Login"},
                    bounds={"left": 40, "top": 1200, "right": 720, "bottom": 1320},
                    text="Email",
                )
            },
        ),
    )

    code, payload = run_main(["replay", str(script), "--replay-update"], capsys)

    assert code == 0
    data = payload["data"]
    assert data["replayed"] == 1
    assert data["healed"] == 1
    assert data["results"][0]["healed"] is True
    assert data["results"][0]["healedStep"] == ["click", "@e0"]
    assert fake_device.taps[-1] == (380, 1260)
    assert script.read_text(encoding="utf-8").splitlines() == [
        "# updated by AndroidTestClii replay --replay-update",
        "context serial=emulator-5554",
        "click @e0",
    ]


def test_replay_expect_screenshot_runs_visual_diff(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    baseline = tmp_path / "baseline.png"
    Image.new("RGBA", (100, 200), (255, 255, 255, 255)).save(baseline)
    script = tmp_path / "visual.ad"
    script.write_text(
        "\n".join(
            [
                "context serial=emulator-5554",
                f"# expect-screenshot {baseline} threshold=0",
                "back",
            ]
        ),
        encoding="utf-8",
    )

    def screenshot(path: str) -> object:
        Image.new("RGBA", (100, 200), (255, 255, 255, 255)).save(path)

        class Captured:
            width = 100
            height = 200

        return Captured()

    fake_device.screenshot = screenshot  # type: ignore[method-assign]

    code, payload = run_main(["replay", str(script)], capsys)

    assert code == 0
    visual = payload["data"]["visualChecks"][0]
    assert visual["baseline"] == str(baseline)
    assert visual["passed"] is True
    assert visual["diffRatio"] == 0
    assert payload["artifacts"] == [
        {"type": "diff", "path": str(tmp_path / "visual-diff.png"), "description": "replay screenshot diff"}
    ]


def test_test_command_runs_ad_files_and_writes_junit_report(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    script = tmp_path / "flow.ad"
    report = tmp_path / "reports" / "flow.xml"
    script.write_text("context serial=emulator-5554\nback\n", encoding="utf-8")

    code, payload = run_main(["test", str(script), "--report-junit", str(report)], capsys)

    assert code == 0
    data = payload["data"]
    assert data["total"] == 1
    assert data["passed"] == 1
    assert data["failed"] == 0
    assert data["reportJunit"] == str(report)
    assert payload["artifacts"] == [
        {"type": "junit", "path": str(report), "description": ".ad test suite JUnit XML"}
    ]
    suite = ET.parse(report).getroot()
    assert suite.tag == "testsuite"
    assert suite.attrib["tests"] == "1"
    assert suite.attrib["failures"] == "0"


def test_test_command_counts_failed_visual_checks_and_junit_failure(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    baseline = tmp_path / "baseline.png"
    Image.new("RGBA", (100, 200), (0, 0, 0, 255)).save(baseline)
    script = tmp_path / "visual.ad"
    report = tmp_path / "visual.xml"
    script.write_text(
        "\n".join(
            [
                "context serial=emulator-5554",
                f"# expect-screenshot {baseline} threshold=0",
                "back",
            ]
        ),
        encoding="utf-8",
    )

    def screenshot(path: str) -> object:
        Image.new("RGBA", (100, 200), (255, 255, 255, 255)).save(path)

        class Captured:
            width = 100
            height = 200

        return Captured()

    fake_device.screenshot = screenshot  # type: ignore[method-assign]

    code, payload = run_main(["test", str(script), "--report-junit", str(report)], capsys)

    assert code == 1
    data = payload["data"]
    assert data["passed"] == 0
    assert data["failed"] == 1
    result = data["results"][0]
    assert result["ok"] is False
    assert result["error"]["code"] == "REPLAY_VISUAL_ASSERTION_FAILED"
    assert result["visualChecks"][0]["passed"] is False
    suite = ET.parse(report).getroot()
    assert suite.attrib["failures"] == "1"


def test_replay_rejects_unsupported_platform_context(tmp_path, capsys) -> None:
    script = tmp_path / "ios.ad"
    script.write_text("context platform=ios\nsnapshot\n", encoding="utf-8")

    code, payload = run_main(["replay", str(script)], capsys)

    assert code == 1
    assert payload["error"]["code"] == "PLATFORM_UNSUPPORTED"


def test_gesture_pan_fling_replay_and_record_template(fake_device, tmp_path, capsys) -> None:
    code, payload = run_main(["--serial", "emulator-5554", "gesture", "pan", "10", "20", "30", "40", "250"], capsys)
    assert code == 0
    assert payload["data"]["type"] == "pan"
    assert payload["data"]["to"] == {"x": 40, "y": 60}
    assert fake_device.swipes[-1] == (10, 20, 40, 60, 0.25)

    code, payload = run_main(["--serial", "emulator-5554", "gesture", "fling", "up", "100", "200"], capsys)
    assert code == 0
    assert payload["data"]["direction"] == "up"
    assert fake_device.swipes[-1] == (100, 200, 100, -400, 0.2)

    gesture_file = tmp_path / "gesture.json"
    gesture_file.write_text(
        json.dumps(
            {
                "coordinateMode": "absolute",
                "touches": [
                    {
                        "finger": "f1",
                        "points": [
                            {"x": 1, "y": 2, "atMs": 0},
                            {"x": 3, "y": 4, "atMs": 100},
                            {"x": 6, "y": 8, "atMs": 250},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    code, payload = run_main(["--serial", "emulator-5554", "gesture", "replay", "--file", str(gesture_file)], capsys)
    assert code == 0
    assert payload["data"]["available"] is True
    assert payload["data"]["segmentCount"] == 2
    assert fake_device.swipes[-2:] == [(1, 2, 3, 4, 0.1), (3, 4, 6, 8, 0.15)]

    code, payload = run_main(["gesture", "record"], capsys)
    assert code == 0
    assert payload["data"]["available"] is False
    assert payload["data"]["template"]["coordinateMode"] == "absolute"


def test_screen_multitouch_pinch_expand_structured_unavailable(
    fake_device,
    tmp_path,
    capsys,
) -> None:
    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "screen",
            "multi-touch",
            "--gesture",
            json.dumps(
                {
                    "coordinateMode": "absolute",
                    "touches": [
                        {
                            "points": [
                                {"x": 10, "y": 20, "atMs": 0},
                                {"x": 30, "y": 40, "atMs": 200},
                            ]
                        }
                    ],
                }
            ),
        ],
        capsys,
    )
    assert code == 0
    assert payload["data"]["available"] is True
    assert payload["data"]["input"] == "screen.multi-touch"

    code, payload = run_main(["screen", "pinch", "--center-x", "50", "--center-y", "60", "--scale", "0.5"], capsys)
    assert code == 0
    assert payload["data"]["available"] is False
    assert payload["data"]["unsupported"] is True
    assert payload["data"]["type"] == "pinch"

    code, payload = run_main(["screen", "expand", "--center-x", "50", "--center-y", "60", "--scale", "2"], capsys)
    assert code == 0
    assert payload["data"]["available"] is False
    assert payload["data"]["unsupported"] is True
    assert payload["data"]["type"] == "expand"


def test_record_start_stop_sessionized_screenrecord(fake_device, tmp_path, capsys) -> None:
    out = tmp_path / "record.mp4"

    code, payload = run_main(["--serial", "emulator-5554", "record", "start", str(out)], capsys)
    assert code == 0
    assert payload["data"]["record"] == "started"
    assert payload["data"]["path"] == str(out)
    assert payload["data"]["remotePath"] == "/sdcard/androidtestclii-recording.mp4"

    code, payload = run_main(["--serial", "emulator-5554", "record", "stop"], capsys)
    assert code == 0
    assert payload["data"]["record"] == "stopped"
    assert payload["data"]["path"] == str(out)
    assert out.exists()
    assert payload["artifacts"] == [
        {"type": "recording", "path": str(out), "description": "device screen recording"}
    ]


def test_platform_and_ecosystem_boundaries_return_structured_unsupported(capsys) -> None:
    for argv in [
        ["harmonyos", "status"],
        ["react-native", "dismiss-overlay"],
        ["react-devtools", "status"],
        ["cloud", "auth"],
        ["daemon", "start"],
        ["session", "sidecar-start"],
    ]:
        code, payload = run_main(argv, capsys)
        assert code == 0
        assert payload["data"]["available"] is False
        assert payload["data"]["unsupported"] is True
        assert payload["data"]["reason"] == "not_in_scope"


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
