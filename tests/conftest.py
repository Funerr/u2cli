from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from typer.testing import CliRunner

import androidtestclii.cli as cli_module


@pytest.fixture(autouse=True)
def isolated_session(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANDROIDTESTCLII_SESSION_PATH", str(tmp_path / "session.json"))


class FakeElement:
    def __init__(self, text: str = "Login", resource_id: str = "com.example:id/login") -> None:
        self.text_value = text
        self.resource_id = resource_id
        self.clicked = False
        self.long_clicked = False
        self.swipes: list[tuple[str, float, int]] = []
        self.dragged_to: tuple[int, int] | None = None
        self.scrolled = False
        self.count = 1

    @property
    def exists(self) -> bool:
        return self.count > 0

    @property
    def info(self) -> dict[str, Any]:
        return {
            "text": self.text_value,
            "resourceName": self.resource_id,
            "className": "android.widget.Button",
            "clickable": True,
            "enabled": True,
        }

    def __getitem__(self, index: int) -> "FakeElement":
        if index >= self.count:
            raise IndexError(index)
        return self

    def click(self) -> None:
        self.clicked = True

    def long_click(self) -> None:
        self.long_clicked = True

    def set_text(self, value: str) -> None:
        self.text_value = value

    def clear_text(self) -> None:
        self.text_value = ""

    def get_text(self) -> str:
        return self.text_value

    def swipe(self, direction: str, percent: float = 0.6, steps: int = 20) -> None:
        self.swipes.append((direction, percent, steps))

    def drag_to(self, x: int, y: int, duration: float = 0.5) -> None:
        self.dragged_to = (x, y)

    def scroll_to(self) -> None:
        self.scrolled = True


class FakeToast:
    def __init__(self) -> None:
        self.message: str | None = None
        self.reset_called = False

    def get_message(self, timeout: float, default: str | None = None) -> str | None:
        return self.message if self.message is not None else default

    def reset(self) -> None:
        self.reset_called = True


class FakeImage:
    width = 100
    height = 200

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(b"png")


class FakeDevice:
    def __init__(self) -> None:
        self.element = FakeElement()
        self.toast = FakeToast()
        self.info = {
            "displayWidth": 1080,
            "displayHeight": 2400,
            "displayDensity": 3,
            "productName": "Pixel",
            "brand": "Google",
            "sdkInt": 35,
            "battery": {"level": 80, "status": "charging"},
        }
        self.pressed: list[str] = []
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple[int, int, int, int, float]] = []
        self.drags: list[tuple[int, int, int, int, float]] = []
        self.sent_text: list[str] = []
        self.shell_commands: list[str] = []
        self.pushed: list[tuple[str, str]] = []
        self.pulled: list[tuple[str, str]] = []
        self.clipboard_text = ""
        self.orientation = "natural"
        self.screen_awake = True
        self.unlocked = False
        self.last_shell_output = "ok"
        self.last_log_marker = "androidtestclii-log-start-0"
        self.last_logcat_output: str | None = None
        self.global_settings: dict[str, str] = {}
        self.granted_permissions: set[str] = set()

    def __call__(self, **kwargs: Any) -> FakeElement:
        if kwargs.get("text") == "missing":
            missing = FakeElement()
            missing.count = 0
            return missing
        if kwargs.get("text") == "many":
            many = FakeElement()
            many.count = 2
            return many
        if kwargs.get("text") is not None and kwargs.get("text") != self.element.text_value:
            missing = FakeElement()
            missing.count = 0
            return missing
        if kwargs.get("resourceId") is not None and kwargs.get("resourceId") != self.element.resource_id:
            missing = FakeElement()
            missing.count = 0
            return missing
        return self.element

    def xpath(self, value: str) -> FakeElement:
        return self(text=value)

    def app_current(self) -> dict[str, Any]:
        return {"package": "com.example", "activity": ".MainActivity", "pid": 123}

    def app_start(self, package: str) -> dict[str, Any]:
        return {"activity": ".MainActivity"}

    def app_stop(self, package: str) -> None:
        return None

    def app_clear(self, package: str) -> None:
        return None

    def app_install(self, apk: str) -> dict[str, Any]:
        return {"package": "com.example"}

    def app_uninstall(self, package: str) -> None:
        return None

    def app_list(self, kind: str | None = None) -> list[str]:
        return ["com.example", "com.android.settings"]

    def app_info(self, package: str) -> dict[str, Any]:
        return {"versionName": "1.0", "versionCode": 1}

    def app_stop_all(self) -> list[str]:
        return ["com.example"]

    def dump_hierarchy(self) -> str:
        return """
        <hierarchy>
          <node index="0" text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false" enabled="true">
            <node index="1" text="Login" resource-id="com.example:id/login" class="android.widget.Button" bounds="[40,1200][720,1320]" clickable="true" enabled="true" />
          </node>
        </hierarchy>
        """

    def screenshot(self, path: str) -> FakeImage:
        image = FakeImage()
        image.save(path)
        return image

    def window_size(self) -> tuple[int, int]:
        return 1080, 2400

    def press(self, key: str) -> None:
        self.pressed.append(str(key))

    def click(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        self.swipes.append((x1, y1, x2, y2, duration))

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        self.drags.append((x1, y1, x2, y2, duration))

    def send_keys(self, value: str) -> None:
        self.sent_text.append(value)

    def keyevent(self, code: int) -> None:
        self.pressed.append(str(code))

    def shell(self, command: str) -> Any:
        self.shell_commands.append(command)
        if command == "logcat -d -v brief":
            output = self.last_logcat_output or (
                "old.example.test\n"
                f"I/{command}: {self.last_log_marker}\n"
                "OkHttp GET https://example.test\n"
                "HTTP 200\n"
            )
        elif command == "atrace --async_stop -z":
            output = "<html>trace</html>"
        elif command == "cat /proc/meminfo":
            output = "MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 600 kB\nCached: 200 kB"
        elif command == "cat /proc/stat":
            output = "cpu  10 0 20 70 0 0 0 0 0 0"
        elif command == "ps -A":
            output = "USER PID PPID VSZ RSS WCHAN ADDR S NAME\nu0_a1 123 1 1 1 0 0 S com.example"
        elif command.startswith("settings put global "):
            parts = command.split()
            self.global_settings[parts[3]] = parts[4]
            output = ""
        elif command.startswith("settings get global "):
            parts = command.split()
            output = self.global_settings.get(parts[3], "null")
        elif command.startswith("pm grant "):
            parts = command.split()
            self.granted_permissions.add(f"{parts[2]}:{parts[3]}")
            output = ""
        elif command.startswith("pm revoke "):
            parts = command.split()
            self.granted_permissions.discard(f"{parts[2]}:{parts[3]}")
            output = ""
        elif command.startswith("dumpsys package "):
            package = command.split()[2]
            permission = "android.permission.CAMERA"
            granted = str(f"{package}:{permission}" in self.granted_permissions).lower()
            output = f"{permission}: granted={granted}"
        elif command.startswith("am broadcast "):
            output = "Broadcast completed: result=0"
        elif command.startswith("am start "):
            output = f"Starting: Intent {{ {command} }}"
        else:
            output = self.last_shell_output

        class Result:
            pass

        Result.output = output
        return Result()

    def push(self, local: str, remote: str) -> None:
        self.pushed.append((local, remote))

    def pull(self, remote: str, local: str) -> None:
        self.pulled.append((remote, local))
        with open(local, "wb") as f:
            f.write(b"pulled")

    def set_clipboard(self, text: str) -> None:
        self.clipboard_text = text

    def clipboard(self) -> str:
        return self.clipboard_text

    def set_orientation(self, value: str) -> None:
        self.orientation = value

    def screen_on(self) -> None:
        self.screen_awake = True

    def screen_off(self) -> None:
        self.screen_awake = False

    def unlock(self) -> None:
        self.unlocked = True

    def open_notification(self) -> None:
        self.shell_commands.append("open_notification")

    def screenrecord(self, out: str, duration: int = 10) -> None:
        with open(out, "wb") as f:
            f.write(b"video")


@dataclass
class FakeAdbDevice:
    serial: str
    state: str


@pytest.fixture()
def fake_device(monkeypatch: pytest.MonkeyPatch) -> FakeDevice:
    device = FakeDevice()
    monkeypatch.setattr("androidtestclii.device.connect.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.device.commands.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.device.health.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.logs.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.diagnostics.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.system_control.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.recording.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.app.commands.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.screen.commands.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.screen.dump.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr(
        "androidtestclii.screen.dump.capture_snapshot",
        lambda fake, serial, timeout_ms, options=None: type(
            "Capture",
            (),
            {
                "xml": fake.dump_hierarchy(),
                "backend": "uiautomator2",
                "metadata": {"backend": "uiautomator2"},
            },
        )(),
    )
    monkeypatch.setattr("androidtestclii.screen.screenshot.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.screen.size.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.element.query.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.element.action.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.input.commands.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.toast.commands.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("androidtestclii.toast.commands.resolve_snapshot_helper", lambda path: None)
    monkeypatch.setattr("androidtestclii.watcher.commands.connect_device", lambda serial, timeout_ms: device)
    return device


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def invoke(args: list[str]) -> tuple[int, dict[str, Any]]:
    try:
        cli_module.main(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    output = ""
    return code, json.loads(output)
