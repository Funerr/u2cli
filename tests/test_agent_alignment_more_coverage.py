from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from u2cli.context import CommandContext
from u2cli.device import connect as device_connect
from u2cli.element import action as element_action
from u2cli.element import query as element_query
from u2cli.element.selector import selector_from_kwargs
from u2cli.errors import ErrorCode, U2CliError, normalize_exception
from u2cli.input import commands as input_commands
from u2cli.toast import commands as toast_commands

import u2cli.cli as cli_module


def ctx(serial: str = "emulator-5554", timeout_ms: int = 1000) -> CommandContext:
    return CommandContext.start(serial=serial, timeout_ms=timeout_ms)


def run_main(args: list[str], capsys) -> tuple[int, dict[str, Any]]:  # type: ignore[no-untyped-def]
    try:
        cli_module.main(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    captured = capsys.readouterr()
    import json

    return code, json.loads(captured.out)


def test_more_top_level_routes(fake_device, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")
    out = tmp_path / "screen.png"

    commands = [
        ["--serial", "emulator-5554", "apps", "--kind", "all"],
        ["--serial", "emulator-5554", "open", "com.example", "--activity", ".Main", "--relaunch"],
        ["--serial", "emulator-5554", "close", "com.example"],
        ["--serial", "emulator-5554", "back"],
        ["--serial", "emulator-5554", "home"],
        ["--serial", "emulator-5554", "app-switcher"],
        ["--serial", "emulator-5554", "rotate", "portrait"],
        ["--serial", "emulator-5554", "screenshot", "--out", str(out)],
        ["--serial", "emulator-5554", "screenshot"],
        ["--serial", "emulator-5554", "press", "text=Login"],
        ["--serial", "emulator-5554", "longpress", "text=Login"],
        ["--serial", "emulator-5554", "swipe", "1", "2", "3", "4"],
        ["--serial", "emulator-5554", "scroll", "down", "--pixels", "50"],
        ["--serial", "emulator-5554", "scroll", "--pixels", "50"],
        ["--serial", "emulator-5554", "type", "hello"],
        ["--serial", "emulator-5554", "focus", "text=Login"],
        ["--serial", "emulator-5554", "get", "attrs", "text=Login"],
        ["--serial", "emulator-5554", "find", "text=Login", "click"],
        ["--serial", "emulator-5554", "alert", "get"],
        ["--serial", "emulator-5554", "alert", "wait", "--timeout-ms", "1"],
        ["--serial", "emulator-5554", "clipboard", "write", "copied"],
        ["--serial", "emulator-5554", "clipboard", "read"],
        ["--serial", "emulator-5554", "keyboard", "hide"],
        ["--serial", "emulator-5554", "keyboard", "show"],
        ["--serial", "emulator-5554", "reinstall", "--app", "com.example", "--path", str(apk)],
        ["--serial", "emulator-5554", "install-from-source", str(apk)],
        ["--serial", "emulator-5554", "session", "clear"],
        ["--serial", "emulator-5554", "device", "info"],
        ["--serial", "emulator-5554", "device", "shell", "--command", "getprop ro.build.version.sdk"],
        ["--serial", "emulator-5554", "device", "logcat", "--lines", "1"],
        ["--serial", "emulator-5554", "device", "network"],
        ["--serial", "emulator-5554", "app", "current"],
        ["--serial", "emulator-5554", "app", "info", "--package", "com.example"],
        ["--serial", "emulator-5554", "app", "start", "--package", "com.example"],
        ["--serial", "emulator-5554", "app", "launch", "--package", "com.example", "--activity", ".Main"],
        ["--serial", "emulator-5554", "app", "stop", "--package", "com.example"],
        ["--serial", "emulator-5554", "app", "clear", "--package", "com.example"],
        ["--serial", "emulator-5554", "app", "install", "--apk", str(apk)],
        ["--serial", "emulator-5554", "app", "uninstall", "--package", "com.example"],
        ["--serial", "emulator-5554", "app", "stop-all"],
        ["--serial", "emulator-5554", "app", "revoke", "--package", "com.example", "--permission", "android.permission.CAMERA"],
        ["--serial", "emulator-5554", "app", "intent", "--package", "com.example", "--activity", ".Main"],
        ["--serial", "emulator-5554", "screen", "size"],
        ["--serial", "emulator-5554", "screen", "orientation"],
        ["--serial", "emulator-5554", "screen", "wake"],
        ["--serial", "emulator-5554", "screen", "sleep"],
        ["--serial", "emulator-5554", "screen", "unlock"],
        ["--serial", "emulator-5554", "screen", "notification", "--action", "open"],
        ["--serial", "emulator-5554", "element", "count", "--text", "Login"],
        ["--serial", "emulator-5554", "element", "bounds", "--text", "Login"],
        ["--serial", "emulator-5554", "element", "wait", "--text", "Login"],
        ["--serial", "emulator-5554", "element", "long-click", "--text", "Login"],
        ["--serial", "emulator-5554", "element", "clear-text", "--text", "Login"],
        ["--serial", "emulator-5554", "element", "get-text", "--resource-id", "com.example:id/login"],
        [
            "--serial",
            "emulator-5554",
            "element",
            "drag-to",
            "--resource-id",
            "com.example:id/login",
            "--x",
            "1",
            "--y",
            "2",
        ],
        [
            "--serial",
            "emulator-5554",
            "element",
            "scroll-to",
            "--resource-id",
            "com.example:id/login",
        ],
    ]
    for args in commands:
        code, payload = run_main(args, capsys)
        assert code == 0, (args, payload)


def test_top_level_route_errors(fake_device, capsys) -> None:
    failures = [
        ["--serial", "emulator-5554", "connection", "bad"],
        ["--serial", "emulator-5554", "click", "50", "101"],
        ["--serial", "emulator-5554", "click", "text=Login", "--double-tap", "--hold-ms", "10"],
        ["--serial", "emulator-5554", "get", "bad", "text=Login"],
        ["--serial", "emulator-5554", "is", "bad", "text=Login"],
        ["--serial", "emulator-5554", "alert", "bad"],
        ["--serial", "emulator-5554", "clipboard", "bad"],
        ["--serial", "emulator-5554", "keyboard", "bad"],
        ["--serial", "emulator-5554", "batch", "--steps", "{}"],
    ]
    for args in failures:
        code, payload = run_main(args, capsys)
        assert code != 0, (args, payload)


def test_alert_timeout_option_reaches_agent_handler(
    fake_device,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    seen: list[int] = []

    def wait(context: CommandContext, timeout_ms: int) -> dict[str, Any]:
        seen.append(timeout_ms)
        return {"present": False, "attempts": 1, "durationMs": 0, "matchedCount": 0, "selectedIndex": None}

    monkeypatch.setattr("u2cli.cli.agent_alert.wait", wait)

    code, payload = run_main(["--serial", "emulator-5554", "alert", "wait", "--timeout-ms", "123"], capsys)

    assert code == 0
    assert payload["data"]["matchedCount"] == 0
    assert seen == [123]


class QueryElement:
    def __init__(self, count: int = 1, exists: bool = True) -> None:
        self.count = count
        self.exists = exists
        self.info = {
            "text": "Login",
            "resourceName": "com.example:id/login",
            "className": "android.widget.Button",
            "bounds": {"left": 1},
            "enabled": True,
        }
        self.clicked = False
        self.long_clicked = False
        self.text_value = ""
        self.swiped: list[Any] = []
        self.dragged: tuple[int, int] | None = None
        self.scrolled = False

    def __getitem__(self, index: int) -> "QueryElement":
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
        return "Login"

    def swipe(self, direction: str, percent: float = 0.6, steps: int = 20) -> None:
        self.swiped.append((direction, percent, steps))

    def drag_to(self, x: int, y: int, duration: float = 0.5) -> None:
        self.dragged = (x, y)

    def scroll_to(self) -> None:
        self.scrolled = True


class QueryDevice:
    def __init__(self, element: QueryElement) -> None:
        self.element = element

    def __call__(self, **kwargs: Any) -> QueryElement:
        return self.element

    def xpath(self, value: str) -> QueryElement:
        return self.element


def test_element_query_and_action_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    element = QueryElement()
    device = QueryDevice(element)
    selector = selector_from_kwargs(text="Login")
    monkeypatch.setattr("u2cli.element.query.connect_device", lambda serial, timeout_ms: device)
    monkeypatch.setattr("u2cli.element.action.connect_device", lambda serial, timeout_ms: device)

    assert element_query.find(ctx(), selector)["matched"] is True
    assert element_query.exists(ctx(), selector)["exists"] is True
    assert element_query.count(ctx(), selector)["matchCount"] == 1
    assert element_query.bounds(ctx(), selector)["element"]["text"] == "Login"
    assert element_query.wait(ctx(), selector)["matched"] is True
    assert element_action.click(ctx(), selector)["clicked"] is True
    assert element_action.long_click(ctx(), selector)["clicked"] is True
    assert element_action.set_text(ctx(), selector, "qa")["setText"] is True
    assert element_action.clear_text(ctx(), selector)["cleared"] is True
    assert element_action.get_text(ctx(), selector)["text"] == "Login"
    assert element_action.swipe(ctx(), selector, "up")["swiped"] is True
    assert element_action.drag_to(ctx(), selector, 1, 2)["dragged"] is True
    assert element_action.scroll_to(ctx(), selector)["scrolled"] is True

    with pytest.raises(U2CliError) as exc:
        element_action.swipe(ctx(), selector, "bad")
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_element_query_errors() -> None:
    selector = selector_from_kwargs(text="Login")
    missing = QueryDevice(QueryElement(count=0, exists=False))
    many = QueryDevice(QueryElement(count=2))

    with pytest.raises(U2CliError) as exc:
        element_query.resolve_unique(missing, selector)
    assert exc.value.code == ErrorCode.ELEMENT_NOT_FOUND
    with pytest.raises(U2CliError) as exc:
        element_query.resolve_unique(many, selector)
    assert exc.value.code == ErrorCode.ELEMENT_AMBIGUOUS

    indexed = selector_from_kwargs(text="Login", index=5)
    with pytest.raises(U2CliError) as exc:
        element_query.resolve_unique(QueryDevice(QueryElement(count=1)), indexed)
    assert exc.value.code == ErrorCode.ELEMENT_NOT_FOUND


class BrokenInputDevice:
    def __getattr__(self, name: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("no u2")

        return fail


def test_input_adb_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("u2cli.input.commands.connect_device", lambda serial, timeout_ms: BrokenInputDevice())
    monkeypatch.setattr(
        "u2cli.input.commands.run_adb",
        lambda serial, args, timeout_ms, allow_failure=False, adb_runner=None: calls.append(args),
    )

    input_commands.press(ctx(), "back")
    input_commands.tap(ctx(), 1, 2)
    input_commands.swipe(ctx(), (1, 2), (3, 4), 500)
    input_commands.drag(ctx(), (1, 2), (3, 4), 500)
    input_commands.text(ctx(), "a b%")
    input_commands.keyevent(ctx(), 4)

    assert ["shell", "input", "keyevent", "4"] in calls
    assert ["shell", "input", "tap", "1", "2"] in calls
    assert ["shell", "input", "text", "a%sb\\%"] in calls


class ToastDevice:
    def __init__(self, message: str | None = "Saved") -> None:
        self.toast = SimpleNamespace(
            get_message=lambda timeout, default=None: message,
            reset=lambda: setattr(self, "reset", True),
        )


def test_toast_uiautomator2_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("u2cli.toast.commands.resolve_snapshot_helper", lambda path: None)
    monkeypatch.setattr("u2cli.toast.commands.connect_device", lambda serial, timeout_ms: ToastDevice("Saved"))
    assert toast_commands.get(ctx())["message"] == "Saved"
    assert toast_commands.reset(ctx())["reset"] is True

    monkeypatch.setattr("u2cli.toast.commands.connect_device", lambda serial, timeout_ms: ToastDevice(None))
    with pytest.raises(U2CliError) as exc:
        toast_commands.get(ctx())
    assert exc.value.code == ErrorCode.TOAST_TIMEOUT


def test_install_from_source_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"apk"

    installed_paths: list[str] = []
    monkeypatch.setattr("u2cli.agent.commands.urllib.request.urlopen", lambda source, timeout: Response())
    monkeypatch.setattr(
        "u2cli.agent.commands.app_commands.install",
        lambda context, path: installed_paths.append(path) or {"installed": True, "apkPath": path},
    )

    result = cli_module.agent_commands.install_from_source(ctx(), "https://example.com/app.apk")

    assert result["installed"] is True
    assert result["downloaded"] is True
    assert result["source"] == "https://example.com/app.apk"
    assert installed_paths


def test_device_connect_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("u2cli.device.connect.shutil.which", lambda name: "/usr/bin/adb")

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[-1] == "version":
            return subprocess.CompletedProcess(args, 0, stdout="Android Debug Bridge version\n", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="List of devices attached\nemulator-5554\tdevice\nemulator-5556\toffline\n",
            stderr="",
        )

    monkeypatch.setattr("u2cli.device.connect.subprocess.run", run)
    assert device_connect.adb_path() == "/usr/bin/adb"
    assert device_connect.adb_version() == "Android Debug Bridge version"
    devices = device_connect.list_adb_devices()
    assert devices[0].serial == "emulator-5554"
    assert device_connect.ensure_device_online("emulator-5554") == "emulator-5554"
    with pytest.raises(U2CliError) as exc:
        device_connect.ensure_device_online("emulator-5556")
    assert exc.value.code == ErrorCode.DEVICE_OFFLINE
    with pytest.raises(U2CliError) as exc:
        device_connect.ensure_device_online("missing")
    assert exc.value.code == ErrorCode.DEVICE_NOT_FOUND

    fake_u2 = SimpleNamespace(connect=lambda serial=None: {"serial": serial})
    monkeypatch.setattr("u2cli.device.connect.import_u2", lambda: fake_u2)
    assert device_connect.connect_device("emulator-5554", 1000) == {"serial": "emulator-5554"}
    assert device_connect.python_health()["ok"] is True


def test_normalize_exception_branches() -> None:
    assert normalize_exception(FileNotFoundError("adb")).code == ErrorCode.ADB_NOT_FOUND
    assert normalize_exception(Exception("adb not found")).code == ErrorCode.ADB_NOT_FOUND
    assert normalize_exception(Exception("device offline")).code == ErrorCode.DEVICE_OFFLINE
    assert normalize_exception(Exception("device not found")).code == ErrorCode.DEVICE_NOT_FOUND
    assert normalize_exception(Exception("connect uiautomator failed")).code == ErrorCode.U2_CONNECT_FAILED
    for name, code in [
        ("UiObjectNotFoundError", ErrorCode.ELEMENT_NOT_FOUND),
        ("TimeoutError", ErrorCode.ACTION_TIMEOUT),
        ("GatewayError", ErrorCode.ACTION_FAILED),
    ]:
        exc_type = type(name, (Exception,), {})
        assert normalize_exception(exc_type("boom")).code == code
    assert normalize_exception(ValueError("bad")).code == ErrorCode.INTERNAL_ERROR


def test_import_u2_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(name: str) -> Any:
        raise ImportError("missing")

    monkeypatch.setattr("u2cli.device.connect.importlib.import_module", fail)
    with pytest.raises(U2CliError) as exc:
        device_connect.import_u2()
    assert exc.value.code == ErrorCode.U2_IMPORT_FAILED
