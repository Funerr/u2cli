from __future__ import annotations

import base64
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.screen.snapshot_backend import (
    ANDROID_JAR_METADATA_PREFIX,
    ANDROID_JAR_XML_CHUNK_PREFIX,
    AdbResult,
    INSTALLED_SNAPSHOT_HELPERS,
    SnapshotBackendOptions,
    SnapshotHelperArtifact,
    adb_failure,
    capture_snapshot,
    capture_with_adb_dump,
    capture_with_helper,
    capture_with_jar,
    decode_helper_xml,
    decode_jar_metadata,
    decode_optional_base64,
    ensure_snapshot_helper,
    extract_ui_dump_xml,
    helper_install_reason,
    is_install_update_incompatible,
    is_snapshot_busy_timeout,
    parse_helper_output,
    parse_instrumentation_records,
    parse_jar_output,
    read_bool_value,
    read_capture_mode,
    read_helper_install_args,
    read_int_value,
    read_optional_text,
    read_snapshot_helper_manifest,
    resolve_dump_path,
    run_adb,
)


XML = "<hierarchy><node text=\"Login\" class=\"android.widget.Button\" /></hierarchy>"


@pytest.fixture(autouse=True)
def clear_helper_install_cache() -> None:
    INSTALLED_SNAPSHOT_HELPERS.clear()


class DumpDevice:
    def __init__(self) -> None:
        self.dumped = False

    def dump_hierarchy(self) -> str:
        self.dumped = True
        return XML


def jar_output(xml: str = XML, *, ok: bool = True, error_type: str | None = None) -> str:
    metadata: dict[str, object] = {
        "protocol": "androidtestclii-android-snapshot-jar-v1",
        "helperApiVersion": "1",
        "outputFormat": "uiautomator-xml",
        "ok": ok,
        "captureMode": "interactive-windows",
        "windowCount": 2,
        "nodeCount": 7,
        "rootPresent": True,
        "truncated": False,
        "elapsedMs": 42,
    }
    if error_type:
        metadata["errorType"] = error_type
        metadata["message"] = "timed out"
    metadata_payload = base64.b64encode(json.dumps(metadata).encode()).decode()
    xml_payload = base64.b64encode(xml.encode()).decode()
    return "\n".join(
        [
            "noise from uiautomator runner",
            f"ANDROIDTESTCLII_SNAPSHOT_METADATA_BASE64:{metadata_payload}",
            f"ANDROIDTESTCLII_SNAPSHOT_XML_CHUNK:0/1:{xml_payload}",
            "ANDROIDTESTCLII_SNAPSHOT_DONE",
        ]
    )


def helper_manifest(apk: Path) -> dict[str, Any]:
    return {
        "name": "android-snapshot-helper",
        "version": "0.1.0",
        "assetName": apk.name,
        "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "packageName": "com.callstack.androidtestclii.snapshothelper",
        "versionCode": 1000,
        "instrumentationRunner": "com.callstack.androidtestclii.snapshothelper/.SnapshotInstrumentation",
        "minSdk": 23,
        "targetSdk": 36,
        "outputFormat": "uiautomator-xml",
        "statusProtocol": "androidtestclii-snapshot-helper-v1",
        "installArgs": ["install", "-r", "-t"],
    }


def helper_record(prefix: str, values: dict[str, str]) -> str:
    lines = [f"{prefix}: androidtestcliiProtocol=androidtestclii-snapshot-helper-v1"]
    lines.extend(f"{prefix}: {key}={value}" for key, value in values.items())
    return "\n".join(lines)


def helper_status(values: dict[str, str]) -> str:
    return f"{helper_record('INSTRUMENTATION_STATUS', values)}\nINSTRUMENTATION_STATUS_CODE: 1"


def helper_result(values: dict[str, str]) -> str:
    return f"{helper_record('INSTRUMENTATION_RESULT', values)}\nINSTRUMENTATION_CODE: 0"


def helper_output(
    xml: str = XML,
    *,
    ok: bool = True,
    error_type: str | None = None,
    toast_text: str | None = "保存成功!",
) -> str:
    midpoint = len(xml.encode()) // 2
    xml_bytes = xml.encode()
    chunks = [xml_bytes[:midpoint], xml_bytes[midpoint:]]
    result = {
        "ok": "true" if ok else "false",
        "action": "snapshot",
        "helperApiVersion": "1",
        "outputFormat": "uiautomator-xml",
        "waitForIdleTimeoutMs": "25",
        "timeoutMs": "8000",
        "maxDepth": "128",
        "maxNodes": "5000",
        "rootPresent": "true",
        "captureMode": "interactive-windows",
        "windowCount": "2",
        "nodeCount": "7",
        "truncated": "false",
        "elapsedMs": "42",
        "toastStatus": "captured" if toast_text else "empty",
        "toastReason": "latest" if toast_text else "no_unconsumed_toast",
        "toastMessage": "Latest Toast captured" if toast_text else "No unconsumed Toast",
        "toastHistorySize": "3" if toast_text else "0",
        "toastMaxHistorySize": "20",
    }
    if toast_text:
        result.update(
            {
                "toastLatestId": "7",
                "toastLatestTextBase64": base64.b64encode(toast_text.encode()).decode(),
                "toastLatestPackage": "com.example.app",
                "toastLatestCapturedAtMs": "1710000000000",
            }
        )
    if error_type:
        result["errorType"] = error_type
        result["message"] = "timed out"
    return "\n".join(
        [
            helper_status(
                {
                    "outputFormat": "uiautomator-xml",
                    "chunkIndex": "0",
                    "chunkCount": "2",
                    "payloadBase64": base64.b64encode(chunks[0]).decode(),
                }
            ),
            helper_status(
                {
                    "outputFormat": "uiautomator-xml",
                    "chunkIndex": "1",
                    "chunkCount": "2",
                    "payloadBase64": base64.b64encode(chunks[1]).decode(),
                }
            ),
            helper_result(result),
        ]
    )


def helper_artifact(tmp_path: Path) -> SnapshotHelperArtifact:
    apk = tmp_path / "androidtestclii-android-snapshot-helper-0.1.0.apk"
    apk.write_bytes(b"helper-apk")
    return SnapshotHelperArtifact(str(apk), helper_manifest(apk))


def test_parse_helper_output_decodes_chunks_and_toast_metadata() -> None:
    parsed = parse_helper_output(helper_output())

    assert parsed["xml"] == XML
    assert parsed["metadata"]["captureMode"] == "interactive-windows"
    assert parsed["metadata"]["windowCount"] == 2
    assert parsed["metadata"]["ok"] is True
    assert parsed["metadata"]["toastCapture"] == {
        "status": "captured",
        "reason": "latest",
        "message": "Latest Toast captured",
        "latest": {
            "id": "7",
            "text": "保存成功!",
            "packageName": "com.example.app",
            "capturedAtMs": 1710000000000,
            "source": "toast",
        },
        "historySize": 3,
        "maxHistorySize": 20,
    }


def test_parse_helper_output_accepts_toast_clear_without_xml_chunks() -> None:
    parsed = parse_helper_output(
        helper_result(
            {
                "ok": "true",
                "action": "toast-clear",
                "outputFormat": "uiautomator-xml",
                "toastStatus": "empty",
                "toastReason": "history_cleared",
                "toastHistorySize": "0",
                "toastMaxHistorySize": "20",
            }
        )
    )

    assert parsed["xml"] == ""
    assert parsed["metadata"]["toastCapture"]["reason"] == "history_cleared"


def test_capture_with_helper_installs_and_runs_instrumentation(tmp_path: Path) -> None:
    artifact = helper_artifact(tmp_path)
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        if args[:6] == ["shell", "cmd", "package", "list", "packages", "--show-versioncode"]:
            return AdbResult(args=args, exit_code=1, stdout="", stderr="not found")
        if args[:1] == ["install"]:
            return AdbResult(args=args, exit_code=0, stdout="Success", stderr="")
        return AdbResult(args=args, exit_code=0, stdout=helper_output(), stderr="")

    capture = capture_with_helper(
        "emulator-5554",
        artifact,
        SnapshotBackendOptions(backend="helper"),
        adb,
    )

    assert capture.xml == XML
    assert capture.metadata["backend"] == "android-snapshot-helper"
    assert capture.metadata["install"]["reason"] == "missing"
    assert capture.metadata["toastCapture"]["latest"]["text"] == "保存成功!"
    assert calls[0][-1] == "com.callstack.androidtestclii.snapshothelper"
    assert calls[1] == ["install", "-r", "-t", artifact.apk_path]
    assert calls[2][:7] == ["shell", "am", "instrument", "-w", "-e", "action", "snapshot"]


def test_ensure_snapshot_helper_skips_current_version(tmp_path: Path) -> None:
    artifact = helper_artifact(tmp_path)
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        return AdbResult(
            args=args,
            exit_code=0,
            stdout="package:com.callstack.androidtestclii.snapshothelper versionCode:1000",
            stderr="",
        )

    result = ensure_snapshot_helper(
        "emulator-5554",
        artifact,
        SnapshotBackendOptions(backend="helper"),
        adb,
    )

    assert result["installed"] is False
    assert result["reason"] == "current"
    assert calls == [
        [
            "shell",
            "cmd",
            "package",
            "list",
            "packages",
            "--show-versioncode",
            "com.callstack.androidtestclii.snapshothelper",
        ]
    ]


def test_ensure_snapshot_helper_caches_successful_install(tmp_path: Path) -> None:
    artifact = helper_artifact(tmp_path)
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        if args[:6] == ["shell", "cmd", "package", "list", "packages", "--show-versioncode"]:
            return AdbResult(args=args, exit_code=1, stdout="", stderr="not found")
        return AdbResult(args=args, exit_code=0, stdout="Success", stderr="")

    installed = ensure_snapshot_helper(
        "emulator-5554",
        artifact,
        SnapshotBackendOptions(backend="helper"),
        adb,
    )
    cached = ensure_snapshot_helper(
        "emulator-5554",
        artifact,
        SnapshotBackendOptions(backend="helper"),
        adb,
    )

    assert installed["reason"] == "missing"
    assert cached["reason"] == "current"
    assert cached["cached"] is True
    assert calls == [
        [
            "shell",
            "cmd",
            "package",
            "list",
            "packages",
            "--show-versioncode",
            "com.callstack.androidtestclii.snapshothelper",
        ],
        ["install", "-r", "-t", artifact.apk_path],
    ]


def test_capture_snapshot_auto_uses_helper_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = helper_artifact(tmp_path)
    device = DumpDevice()
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        if args[:6] == ["shell", "cmd", "package", "list", "packages", "--show-versioncode"]:
            return AdbResult(args=args, exit_code=1, stdout="", stderr="not found")
        if args[:1] == ["install"]:
            return AdbResult(args=args, exit_code=0, stdout="Success", stderr="")
        return AdbResult(args=args, exit_code=0, stdout=helper_output(), stderr="")

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.resolve_snapshot_helper", lambda path: artifact)

    capture = capture_snapshot(
        device,
        "emulator-5554",
        5000,
        SnapshotBackendOptions(backend="auto"),
        adb,
    )

    assert capture.metadata["backend"] == "android-snapshot-helper"
    assert device.dumped is False
    assert calls[1][:1] == ["install"]
    assert calls[2][:3] == ["shell", "am", "instrument"]


def test_parse_jar_output_decodes_chunks_and_metadata() -> None:
    parsed = parse_jar_output(jar_output())

    assert parsed["xml"] == XML
    assert parsed["metadata"]["captureMode"] == "interactive-windows"
    assert parsed["metadata"]["helperApiVersion"] == "1"
    assert parsed["metadata"]["windowCount"] == 2
    assert parsed["metadata"]["ok"] is True


def test_capture_with_jar_pushes_and_runs_uiautomator_runtest(tmp_path: Path) -> None:
    snapshot_jar = tmp_path / "androidtestclii-android-snapshot-jar-0.1.0.jar"
    snapshot_jar.write_bytes(b"jar")
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        if args[:1] == ["push"]:
            return AdbResult(args=args, exit_code=0, stdout="pushed", stderr="")
        return AdbResult(args=args, exit_code=0, stdout=jar_output(), stderr="")

    capture = capture_with_jar(
        "emulator-5554",
        str(snapshot_jar),
        SnapshotBackendOptions(backend="jar"),
        adb,
    )

    assert capture.xml == XML
    assert capture.metadata["backend"] == "android-uiautomator-jar"
    assert capture.metadata["windowCount"] == 2
    assert capture.metadata["helperTruncated"] is False
    assert calls[0] == [
        "push",
        str(snapshot_jar),
        "/data/local/tmp/androidtestclii-android-snapshot.jar",
    ]
    assert calls[1][:5] == [
        "shell",
        "uiautomator",
        "runtest",
        "/data/local/tmp/androidtestclii-android-snapshot.jar",
        "-c",
    ]


def test_capture_snapshot_auto_uses_jar_when_helper_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_jar = tmp_path / "snapshot.jar"
    snapshot_jar.write_bytes(b"jar")
    device = DumpDevice()
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        if args[:1] == ["push"]:
            return AdbResult(args=args, exit_code=0, stdout="pushed", stderr="")
        return AdbResult(args=args, exit_code=0, stdout=jar_output(), stderr="")

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.resolve_snapshot_helper", lambda path: None)

    capture = capture_snapshot(
        device,
        "emulator-5554",
        5000,
        SnapshotBackendOptions(backend="auto", snapshot_jar=str(snapshot_jar)),
        adb,
    )

    assert capture.metadata["backend"] == "android-uiautomator-jar"
    assert device.dumped is False
    assert calls[0][:1] == ["push"]
    assert calls[1][:3] == ["shell", "uiautomator", "runtest"]


def test_capture_snapshot_auto_falls_back_to_adb_when_jar_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = DumpDevice()
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        return AdbResult(args=args, exit_code=0, stdout=XML, stderr="")

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.resolve_snapshot_helper", lambda path: None)
    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.resolve_snapshot_jar", lambda path: None)

    capture = capture_snapshot(
        device,
        "emulator-5554",
        5000,
        SnapshotBackendOptions(backend="auto"),
        adb,
    )

    assert capture.metadata["backend"] == "adb-uiautomator-dump"
    assert capture.metadata["mode"] == "exec-out"
    assert device.dumped is False
    assert calls == [["exec-out", "uiautomator", "dump", "/dev/tty"]]


def test_capture_snapshot_auto_skips_stock_fallback_on_jar_timeout(tmp_path: Path) -> None:
    snapshot_jar = tmp_path / "snapshot.jar"
    snapshot_jar.write_bytes(b"jar")

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        if args[:1] == ["push"]:
            return AdbResult(args=args, exit_code=0, stdout="pushed", stderr="")
        return AdbResult(
            args=args,
            exit_code=1,
            stdout=jar_output(ok=False, error_type="java.util.concurrent.TimeoutException"),
            stderr="",
        )

    with pytest.raises(U2CliError) as exc:
        capture_snapshot(
            DumpDevice(),
            "emulator-5554",
            5000,
            SnapshotBackendOptions(backend="auto", snapshot_jar=str(snapshot_jar)),
            adb,
        )

    assert exc.value.code == ErrorCode.ACTION_FAILED
    assert exc.value.details["fallbackSkipped"] is True


def test_capture_snapshot_auto_skips_stock_fallback_on_helper_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = helper_artifact(tmp_path)

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        if args[:6] == ["shell", "cmd", "package", "list", "packages", "--show-versioncode"]:
            return AdbResult(args=args, exit_code=0, stdout="", stderr="")
        if args[:1] == ["install"]:
            return AdbResult(args=args, exit_code=0, stdout="Success", stderr="")
        return AdbResult(
            args=args,
            exit_code=1,
            stdout=helper_output(ok=False, error_type="java.util.concurrent.TimeoutException"),
            stderr="",
        )

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.resolve_snapshot_helper", lambda path: artifact)

    with pytest.raises(U2CliError) as exc:
        capture_snapshot(
            DumpDevice(),
            "emulator-5554",
            5000,
            SnapshotBackendOptions(backend="auto"),
            adb,
        )

    assert exc.value.code == ErrorCode.ACTION_FAILED
    assert exc.value.details["fallbackSkipped"] is True


def test_adb_dump_falls_back_to_file_read() -> None:
    calls: list[list[str]] = []

    def adb(serial: str | None, args: list[str], **kwargs: Any) -> AdbResult:
        calls.append(args)
        if args[:1] == ["exec-out"]:
            return AdbResult(args=args, exit_code=1, stdout="", stderr="")
        if args[:3] == ["shell", "uiautomator", "dump"]:
            return AdbResult(
                args=args,
                exit_code=0,
                stdout="UI dumped to: /sdcard/custom.xml",
                stderr="",
            )
        return AdbResult(args=args, exit_code=0, stdout=XML, stderr="")

    capture = capture_with_adb_dump("emulator-5554", adb)

    assert capture.xml == XML
    assert capture.metadata["mode"] == "file"
    assert calls[-1] == ["shell", "cat", "/sdcard/custom.xml"]


def test_helper_parser_error_branches() -> None:
    with pytest.raises(U2CliError):
        parse_helper_output("noise")
    with pytest.raises(U2CliError):
        parse_helper_output(helper_result({"ok": "false", "errorType": "Boom"}))
    with pytest.raises(U2CliError):
        decode_helper_xml([], {"backend": "helper"})
    with pytest.raises(U2CliError):
        decode_helper_xml(
            [{"index": 0, "count": 2, "payloadBase64": base64.b64encode(b"<hierarchy/>").decode()}],
            {},
        )
    with pytest.raises(U2CliError):
        decode_helper_xml([{"index": 2, "count": 1, "payloadBase64": "AAAA"}], {})
    with pytest.raises(U2CliError):
        decode_helper_xml(
            [
                {"index": 0, "count": 1, "payloadBase64": "AAAA"},
                {"index": 0, "count": 1, "payloadBase64": "AAAA"},
            ],
            {},
        )
    with pytest.raises(U2CliError):
        decode_helper_xml([{"index": 0, "count": 1, "payloadBase64": "not-base64"}], {})
    with pytest.raises(U2CliError):
        decode_helper_xml(
            [{"index": 0, "count": 1, "payloadBase64": base64.b64encode(b"no xml").decode()}],
            {},
        )

    records = parse_instrumentation_records(
        "INSTRUMENTATION_STATUS: androidtestcliiProtocol=androidtestclii-snapshot-helper-v1\n"
        "INSTRUMENTATION_RESULT: androidtestcliiProtocol=androidtestclii-snapshot-helper-v1\n"
    )
    assert records["status"][0]["androidtestcliiProtocol"] == "androidtestclii-snapshot-helper-v1"
    assert records["results"][0]["androidtestcliiProtocol"] == "androidtestclii-snapshot-helper-v1"


def test_jar_parser_error_branches() -> None:
    metadata = base64.b64encode(json.dumps({"protocol": "bad"}).encode()).decode()
    with pytest.raises(U2CliError):
        parse_jar_output("")
    with pytest.raises(U2CliError):
        parse_jar_output(f"{ANDROID_JAR_METADATA_PREFIX}{metadata}")
    good_meta = base64.b64encode(json.dumps({"protocol": "androidtestclii-android-snapshot-jar-v1"}).encode()).decode()
    bad_lines = [
        f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}\n{ANDROID_JAR_XML_CHUNK_PREFIX}bad",
        f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}\n{ANDROID_JAR_XML_CHUNK_PREFIX}x/1:AAAA",
        f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}\n{ANDROID_JAR_XML_CHUNK_PREFIX}2/1:AAAA",
        f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}\n{ANDROID_JAR_XML_CHUNK_PREFIX}0/2:AAAA",
        "\n".join(
            [
                f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}",
                f"{ANDROID_JAR_XML_CHUNK_PREFIX}0/1:AAAA",
                f"{ANDROID_JAR_XML_CHUNK_PREFIX}0/1:BBBB",
            ]
        ),
        f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}\n{ANDROID_JAR_XML_CHUNK_PREFIX}0/1:not-base64",
        f"{ANDROID_JAR_METADATA_PREFIX}{good_meta}\n{ANDROID_JAR_XML_CHUNK_PREFIX}0/1:{base64.b64encode(b'no xml').decode()}",
    ]
    for output in bad_lines:
        with pytest.raises(U2CliError):
            parse_jar_output(output)
    with pytest.raises(U2CliError):
        decode_jar_metadata("not-base64")
    with pytest.raises(U2CliError):
        decode_jar_metadata(base64.b64encode(json.dumps(["bad"]).encode()).decode())


def test_snapshot_backend_small_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = AdbResult(args=["x"], exit_code=1, stdout="out", stderr="err")
    err = adb_failure("failed", result)
    assert err.details["stderr"] == "err"
    assert is_snapshot_busy_timeout(
        U2CliError(ErrorCode.ACTION_FAILED, "timed out", {"helper": {"errorType": "TimeoutException"}})
    )
    assert is_install_update_incompatible(AdbResult([], 1, "", "INSTALL_FAILED_UPDATE_INCOMPATIBLE"))
    assert helper_install_reason("never", None, 1) == "skipped"
    assert helper_install_reason("always", 1, 2) == "forced"
    assert helper_install_reason("missing-or-outdated", 1, 2) == "outdated"
    assert read_int_value("7") == 7
    assert read_int_value(True) is None
    assert read_bool_value("true") is True
    assert read_optional_text(" null ".strip()) is None
    assert read_capture_mode("active-window") == "active-window"
    assert decode_optional_base64(base64.b64encode("Hi".encode()).decode()) == "Hi"
    assert decode_optional_base64("bad!!") is None
    assert extract_ui_dump_xml(f"prefix {XML} suffix", "") == XML
    assert extract_ui_dump_xml("no xml", "") is None
    assert resolve_dump_path("/sdcard/window.xml", "UI dumped to: /sdcard/custom.xml", "") == "/sdcard/custom.xml"

    with pytest.raises(U2CliError):
        read_helper_install_args({"installArgs": ["push"]})
    with pytest.raises(U2CliError):
        read_helper_install_args({"installArgs": ["install", "--bad"]})
    assert read_helper_install_args({"installArgs": ["install", "-r"]}) == ["install", "-r"]

    apk = tmp_path / "helper.apk"
    apk.write_bytes(b"apk")
    manifest = tmp_path / "helper.apk.manifest.json"
    manifest.write_text("{bad", encoding="utf-8")
    with pytest.raises(U2CliError):
        read_snapshot_helper_manifest(apk)
    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(U2CliError):
        read_snapshot_helper_manifest(apk)
    manifest.unlink()
    assert read_snapshot_helper_manifest(apk)["assetName"] == "helper.apk"


def test_run_adb_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.adb_path", lambda: None)
    with pytest.raises(U2CliError) as exc:
        run_adb(None, ["devices"])
    assert exc.value.code == ErrorCode.ADB_NOT_FOUND

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.adb_path", lambda: "/usr/bin/adb")

    def ok(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="out", stderr="")

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.subprocess.run", ok)
    result = run_adb("serial", ["devices"])
    assert result.stdout == "out"

    def fail(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="bad")

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.subprocess.run", fail)
    with pytest.raises(U2CliError):
        run_adb(None, ["devices"])
    assert run_adb(None, ["devices"], allow_failure=True).exit_code == 2

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=1)

    monkeypatch.setattr("androidtestclii.screen.snapshot_backend.subprocess.run", timeout)
    with pytest.raises(U2CliError) as exc:
        run_adb(None, ["devices"])
    assert exc.value.code == ErrorCode.ACTION_TIMEOUT
