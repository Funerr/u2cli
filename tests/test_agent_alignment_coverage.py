from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from androidtestclii.agent import alert as agent_alert
from androidtestclii.agent import commands as agent_commands
from androidtestclii.app import commands as app_commands
import androidtestclii.cli as cli_module
from androidtestclii.context import CommandContext
from androidtestclii.device import commands as device_commands
from androidtestclii.device import health
from androidtestclii.device.connect import AdbDevice
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.screen import commands as screen_commands
from androidtestclii.screen import screenshot as screen_screenshot
from androidtestclii.session import commands as session_commands
from androidtestclii.session import store as session_store
from androidtestclii.watcher import commands as watcher_commands


class ShellResult:
    def __init__(self, output: str = "ok") -> None:
        self.output = output


class MiniDevice:
    def __init__(self) -> None:
        self.shell_commands: list[str] = []
        self.stopped: list[str] = []
        self.started: list[tuple[str, dict[str, Any]]] = []
        self.installed: list[str] = []
        self.uninstalled: list[str] = []
        self.permissions: list[str] = []
        self.current = {"package": "com.example", "activity": ".Main", "pid": 7}
        self.info = {"displayWidth": 100, "displayHeight": 200}
        self.clip = ""

    def app_current(self) -> dict[str, Any]:
        return self.current

    def app_start(self, package: str, **kwargs: Any) -> dict[str, Any]:
        self.started.append((package, kwargs))
        return {"activity": kwargs.get("activity") or ".Main"}

    def app_stop(self, package: str) -> None:
        self.stopped.append(package)

    def app_clear(self, package: str) -> None:
        self.shell_commands.append(f"clear:{package}")

    def app_install(self, apk: str) -> dict[str, Any]:
        self.installed.append(apk)
        return {"package": "com.example"}

    def app_uninstall(self, package: str) -> None:
        self.uninstalled.append(package)

    def app_list_running(self) -> list[str]:
        return ["com.example"]

    def app_info(self, package: str) -> dict[str, Any]:
        return {"versionName": "1", "versionCode": 2}

    def app_stop_all(self) -> list[str]:
        return ["com.example"]

    def shell(self, command: str) -> ShellResult:
        self.shell_commands.append(command)
        if command == "pm list packages":
            return ShellResult("package:com.example\npackage:com.android.settings")
        if command == "cmd clipboard get":
            return ShellResult(self.clip)
        return ShellResult("ok")

    def set_clipboard(self, text: str) -> None:
        self.clip = text

    def clipboard(self) -> str:
        return self.clip


class WatcherApi:
    def __init__(self) -> None:
        self.conditions: list[Any] = []
        self.clicked = False
        self.ran = False
        self.removed = False

    def when(self, *args: Any, **kwargs: Any) -> "WatcherApi":
        self.conditions.append(args or kwargs)
        return self

    def click(self, *args: Any, **kwargs: Any) -> None:
        self.clicked = True

    def run(self) -> bool:
        self.ran = True
        return True

    def remove(self) -> None:
        self.removed = True


class WatcherDevice:
    def __init__(self) -> None:
        self.api = WatcherApi()
        self.watchers = self.api

    def watcher(self, name: str) -> WatcherApi:
        return self.api


def ctx(serial: str = "emulator-5554", timeout_ms: int = 1000) -> CommandContext:
    return CommandContext.start(serial=serial, timeout_ms=timeout_ms)


def test_session_store_round_trip_and_ref_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "session.json"
    monkeypatch.setenv("ANDROIDTESTCLII_SESSION_PATH", str(path))

    state = session_store.update_session(serial="emulator-5554", timeout_ms=1234)
    assert state.serial == "emulator-5554"
    assert session_store.read_session().timeout_ms == 1234

    with pytest.raises(U2CliError) as exc:
        session_store.ref_entry("@e0")
    assert exc.value.code == ErrorCode.SNAPSHOT_REF_NOT_FOUND

    last = session_store.LastSnapshot(
        capturedAt="2026-05-26T00:00:00.000Z",
        serial="emulator-5554",
        refMap={
            "@e0": session_store.SnapshotRef(
                selector={"text": "Login"},
                bounds={"left": 0, "top": 0, "right": 10, "bottom": 20},
                text="Login",
            )
        },
    )
    session_store.update_session(last_snapshot=last)
    entry, snapshot = session_store.ref_entry("@e0")
    assert entry.text == "Login"
    assert snapshot.captured_at.startswith("2026")

    session_store.mark_stale("emulator-5554")
    assert session_store.read_session().stale is True
    assert session_commands.clear(ctx())["cleared"] is True
    assert session_store.read_session().serial is None


def test_app_commands_shell_and_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    device = MiniDevice()
    monkeypatch.setattr("androidtestclii.app.commands.connect_device", lambda serial, timeout_ms: device)
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")

    assert app_commands.current(ctx())["package"] == "com.example"
    assert app_commands.list_apps(ctx(), "running")["packages"] == ["com.example"]
    assert app_commands.list_apps(ctx(), "all")["count"] == 2
    assert app_commands.info(ctx(), "com.example")["versionCode"] == 2
    assert app_commands.launch(ctx(), "com.example", ".Main", True, True)["launched"] is True
    assert app_commands.start(ctx(), "com.example")["launched"] is True
    assert app_commands.stop(ctx(), "com.example")["stopped"] is True
    assert app_commands.clear(ctx(), "com.example")["cleared"] is True
    assert app_commands.install(ctx(), str(apk))["installed"] is True
    assert app_commands.uninstall(ctx(), "com.example")["uninstalled"] is True
    assert app_commands.stop_all(ctx())["count"] == 1
    assert app_commands.permission(ctx(), "com.example", "android.permission.CAMERA", True)["granted"] is True
    assert app_commands.intent(ctx(), package="com.example", activity=".Main")["started"] is True


def test_device_commands_shell_restrictions_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    device = MiniDevice()
    monkeypatch.setattr("androidtestclii.device.commands.connect_device", lambda serial, timeout_ms: device)

    assert device_commands.shell(ctx(), "getprop ro.product.model")["output"] == "ok"
    with pytest.raises(U2CliError):
        device_commands.shell(ctx(), "echo ok; rm -rf /")

    local = tmp_path / "in.txt"
    local.write_text("hello")
    pulled = tmp_path / "out.txt"
    device.push = lambda src, dst: device.shell_commands.append(f"push:{src}:{dst}")  # type: ignore[attr-defined]

    def pull(remote: str, local_path: str) -> None:
        Path(local_path).write_text("pulled")

    device.pull = pull  # type: ignore[attr-defined]
    assert device_commands.push(ctx(), str(local), "/sdcard/in.txt")["pushed"] is True
    assert device_commands.pull(ctx(), "/sdcard/in.txt", str(pulled))["pulled"] is True
    assert device_commands.clipboard_set(ctx(), "copied")["set"] is True
    assert device_commands.clipboard_get(ctx())["text"] == "copied"
    assert device_commands.logcat(ctx(), lines=2)["count"] >= 1
    assert device_commands.network(ctx())["wifi"] == "ok"


def test_health_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("androidtestclii.device.health.adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr("androidtestclii.device.health.adb_version", lambda: "Android Debug Bridge")
    monkeypatch.setattr(
        "androidtestclii.device.health.list_adb_devices",
        lambda: [AdbDevice("emulator-5554", "device")],
    )
    monkeypatch.setattr("androidtestclii.device.health.import_u2", lambda: type("U2", (), {"__version__": "3"})())
    monkeypatch.setattr("androidtestclii.device.health.connect_device", lambda serial, timeout_ms: object())
    data = health.doctor_data(ctx())
    assert data["adb"]["ok"] is True
    assert any(check["name"] == "u2-connect" and check["ok"] for check in data["checks"])
    assert health.device_info_data(ctx())["serial"] == "emulator-5554"


def test_screen_commands_and_screenshot_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class ScreenDevice(MiniDevice):
        orientation = "natural"

        def set_orientation(self, value: str) -> None:
            self.orientation = value

        def screen_on(self) -> None:
            self.shell_commands.append("screen_on")

        def screen_off(self) -> None:
            self.shell_commands.append("screen_off")

        def unlock(self) -> None:
            self.shell_commands.append("unlock")

        def open_notification(self) -> None:
            self.shell_commands.append("notification")

        def screenshot(self, path: str) -> object:
            class Image:
                width = 10
                height = 20

                def save(self, out: str) -> None:
                    Path(out).write_bytes(b"png")

            return Image()

    device = ScreenDevice()
    monkeypatch.setattr("androidtestclii.screen.commands.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.screen.screenshot.connect_device", lambda serial, timeout_ms: device)

    assert screen_commands.orientation_get(ctx())["orientation"] == "natural"
    assert screen_commands.orientation_set(ctx(), "left")["orientation"] == "left"
    with pytest.raises(U2CliError):
        screen_commands.orientation_set(ctx(), "bad")
    assert screen_commands.wake(ctx())["awake"] is True
    assert screen_commands.sleep(ctx())["sleeping"] is True
    assert screen_commands.unlock(ctx())["unlocked"] is True
    assert screen_commands.notification(ctx(), "open")["done"] is True
    assert screen_commands.notification(ctx(), "quick-settings")["done"] is True
    assert screen_commands.notification(ctx(), "close")["done"] is True
    with pytest.raises(U2CliError):
        screen_commands.notification(ctx(), "bad")
    out = tmp_path / "screen.png"
    data, artifacts = screen_screenshot.screenshot(ctx(), str(out))
    assert data["bytes"] == 3
    assert artifacts[0]["type"] == "screenshot"


def test_watcher_xpath_and_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    device = WatcherDevice()
    monkeypatch.setattr("androidtestclii.watcher.commands.connect_device", lambda serial, timeout_ms: device)

    added = watcher_commands.add(ctx(), "allow", "Allow", "com.example:id/ok", "OK")
    assert added["added"] is True
    assert device.api.clicked is True
    assert any("Allow" in str(condition) for condition in device.api.conditions)
    assert watcher_commands.run(ctx())["triggered"] is True
    assert watcher_commands.reset(ctx())["reset"] is True


def test_agent_alert_and_batch_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("androidtestclii.agent.alert.scan_candidates", lambda context: [])
    waited = agent_alert.wait(ctx(), 1)
    assert waited["present"] is False
    with pytest.raises(U2CliError) as exc:
        agent_alert.accept(ctx(), 1)
    assert exc.value.code == ErrorCode.ALERT_NOT_FOUND

    monkeypatch.setattr("androidtestclii.agent.commands.back", lambda context: {"pressed": True})
    out = tmp_path / "batch.json"
    data, artifacts = agent_commands.batch(ctx(), json.dumps([{"command": "back"}]), str(out))
    assert data["failed"] is None
    assert artifacts[0]["type"] == "batch-result"
    assert json.loads(out.read_text())["total"] == 1


def test_batch_success_cli_uses_top_level_contract(
    monkeypatch: pytest.MonkeyPatch,
    fake_device: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("androidtestclii.agent.commands.back", lambda context: {"pressed": True})

    try:
        cli_module.main(["--serial", "emulator-5554", "batch", "--steps", json.dumps([{"command": "back"}])])
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["success"] is True
    assert payload["steps"][0]["success"] is True
    assert payload["failed"] is None
    assert payload["metadata"]["capabilityLayer"] == "adb-fast-path"
    assert "data" not in payload


def test_agent_connection_and_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "androidtestclii.agent.commands.list_adb_devices",
        lambda: [AdbDevice("emulator-5554", "device")],
    )
    assert agent_commands.connect(ctx(serial=None))["serial"] == "emulator-5554"
    assert agent_commands.connection_status(ctx())["connected"] is True
    assert agent_commands.disconnect(ctx())["disconnected"] is True

    monkeypatch.setattr(
        "androidtestclii.agent.commands.device_commands.shell",
        lambda context, command: {"output": "mInputShown=true\nmCurId=ime\nmServedView=view"},
    )
    assert agent_commands.keyboard_status(ctx())["shown"] is True


def test_agent_connect_address_calls_adb_and_verifies_online(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("androidtestclii.agent.commands.adb_path", lambda: "/usr/bin/adb")

    def run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        return type("Proc", (), {"returncode": 0, "stdout": "connected", "stderr": ""})()

    monkeypatch.setattr("androidtestclii.agent.commands.subprocess.run", run)
    monkeypatch.setattr(
        "androidtestclii.agent.commands.list_adb_devices",
        lambda: [AdbDevice("1.2.3.4:5555", "device")],
    )

    result = agent_commands.connect(ctx(serial=None), address="1.2.3.4:5555")

    assert result["connected"] is True
    assert result["serial"] == "1.2.3.4:5555"
    assert calls == [["/usr/bin/adb", "connect", "1.2.3.4:5555"]]


def test_agent_disconnect_remote_calls_adb(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("androidtestclii.agent.commands.adb_path", lambda: "/usr/bin/adb")

    def run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        return type("Proc", (), {"returncode": 0, "stdout": "disconnected", "stderr": ""})()

    monkeypatch.setattr("androidtestclii.agent.commands.subprocess.run", run)
    result = agent_commands.disconnect(ctx(serial="127.0.0.1:5555"))

    assert result["sessionCleared"] is True
    assert calls == [["/usr/bin/adb", "disconnect", "127.0.0.1:5555"]]


def test_snapshot_ref_cache_is_not_used_across_serials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ANDROIDTESTCLII_SESSION_PATH", str(tmp_path / "session.json"))
    session_store.update_session(
        serial="device-a",
        last_snapshot=session_store.LastSnapshot(
            capturedAt="2026-05-26T00:00:00.000Z",
            serial="device-a",
            refMap={
                "@e0": session_store.SnapshotRef(
                    selector={"text": "Login"},
                    bounds={"left": 0, "top": 0, "right": 10, "bottom": 20},
                    text="Cached",
                )
            },
        ),
    )

    clicked: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "androidtestclii.agent.commands.element_action.click",
        lambda context, selector: clicked.append(selector.public_dict()) or {"clicked": True},
    )

    result = agent_commands.click(ctx(serial="device-b"), "@e0")

    assert result["clicked"] is True
    assert clicked == [{"text": "Login"}]

    monkeypatch.setattr(
        "androidtestclii.agent.commands.element_action.get_text",
        lambda context, selector: {"text": "Queried", "selector": selector.public_dict()},
    )

    text = agent_commands.get_attr(ctx(serial="device-b"), "text", "@e0")

    assert text["text"] == "Queried"
