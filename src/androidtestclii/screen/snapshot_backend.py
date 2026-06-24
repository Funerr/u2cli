from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Protocol

from androidtestclii.branding import (
    LEGACY_SNAPSHOT_HELPER_APK_ENV,
    LEGACY_SNAPSHOT_JAR_ENV,
    SNAPSHOT_HELPER_APK_ENV,
    SNAPSHOT_JAR_ENV,
)
from androidtestclii.device.connect import adb_path
from androidtestclii.errors import ErrorCode, U2CliError, normalize_exception


ANDROID_JAR_PROTOCOL = "androidtestclii-android-snapshot-jar-v1"
ANDROID_JAR_ENTRY_CLASS = "io.github.funerr.androidtestclii.snapshotjar.SnapshotDump"
ANDROID_JAR_REMOTE_PATH = "/data/local/tmp/androidtestclii-android-snapshot.jar"
ANDROID_JAR_METADATA_PREFIX = "ANDROIDTESTCLII_SNAPSHOT_METADATA_BASE64:"
ANDROID_JAR_XML_CHUNK_PREFIX = "ANDROIDTESTCLII_SNAPSHOT_XML_CHUNK:"

ANDROID_HELPER_PACKAGE = "com.callstack.androidtestclii.snapshothelper"
ANDROID_HELPER_RUNNER = f"{ANDROID_HELPER_PACKAGE}/.SnapshotInstrumentation"
ANDROID_HELPER_PROTOCOL = "androidtestclii-snapshot-helper-v1"
ANDROID_HELPER_OUTPUT_FORMAT = "uiautomator-xml"
ANDROID_HELPER_DEFAULT_INSTALL_ARGS = ["install", "-r", "-t"]
INSTALLED_SNAPSHOT_HELPERS: dict[tuple[str | None, str, int], int] = {}

DEFAULT_SNAPSHOT_WAIT_FOR_IDLE_TIMEOUT_MS = 500
DEFAULT_SNAPSHOT_TIMEOUT_MS = 8_000
DEFAULT_SNAPSHOT_COMMAND_OVERHEAD_MS = 5_000
DEFAULT_SNAPSHOT_MAX_DEPTH = 128
DEFAULT_SNAPSHOT_MAX_NODES = 5_000
DEFAULT_STOCK_DUMP_TIMEOUT_MS = 8_000

SnapshotBackendName = Literal["auto", "helper", "apk", "jar", "adb", "uiautomator2"]
SnapshotActualBackend = Literal[
    "android-snapshot-helper",
    "android-uiautomator-jar",
    "adb-uiautomator-dump",
    "uiautomator2",
]
SnapshotHelperInstallPolicy = Literal["missing-or-outdated", "always", "never"]
SnapshotHelperAction = Literal["snapshot", "toast-get", "toast-clear"]


class AdbRunner(Protocol):
    def __call__(
        self,
        serial: str | None,
        args: list[str],
        *,
        timeout_ms: int,
        allow_failure: bool,
    ) -> "AdbResult": ...


@dataclass(frozen=True)
class SnapshotBackendOptions:
    backend: SnapshotBackendName = "auto"
    helper_apk: str | None = None
    helper_install_policy: SnapshotHelperInstallPolicy = "missing-or-outdated"
    snapshot_jar: str | None = None
    wait_for_idle_timeout_ms: int = DEFAULT_SNAPSHOT_WAIT_FOR_IDLE_TIMEOUT_MS
    snapshot_timeout_ms: int = DEFAULT_SNAPSHOT_TIMEOUT_MS
    max_depth: int = DEFAULT_SNAPSHOT_MAX_DEPTH
    max_nodes: int = DEFAULT_SNAPSHOT_MAX_NODES


@dataclass(frozen=True)
class SnapshotCapture:
    xml: str
    backend: SnapshotActualBackend
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AdbResult:
    args: list[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SnapshotHelperArtifact:
    apk_path: str
    manifest: dict[str, Any]


def capture_snapshot(
    device: Any,
    serial: str | None,
    timeout_ms: int,
    options: SnapshotBackendOptions | None = None,
    adb_runner: AdbRunner | None = None,
) -> SnapshotCapture:
    resolved_options = options or SnapshotBackendOptions()
    errors: list[dict[str, str]] = []
    snapshot_timeout_ms = min(resolved_options.snapshot_timeout_ms, timeout_ms)
    resolved_options = SnapshotBackendOptions(
        backend=resolved_options.backend,
        helper_apk=resolved_options.helper_apk,
        helper_install_policy=resolved_options.helper_install_policy,
        snapshot_jar=resolved_options.snapshot_jar,
        wait_for_idle_timeout_ms=resolved_options.wait_for_idle_timeout_ms,
        snapshot_timeout_ms=snapshot_timeout_ms,
        max_depth=resolved_options.max_depth,
        max_nodes=resolved_options.max_nodes,
    )

    if resolved_options.backend in {"auto", "helper", "apk"}:
        artifact = resolve_snapshot_helper(resolved_options.helper_apk)
        if artifact:
            try:
                return capture_with_helper(serial, artifact, resolved_options, adb_runner)
            except U2CliError as exc:
                if resolved_options.backend in {"helper", "apk"}:
                    raise
                if is_snapshot_busy_timeout(exc):
                    raise U2CliError(
                        exc.code,
                        (
                            f"{exc.message}. Stock UIAutomator fallback was skipped because the "
                            "accessibility tree is busy or stalled."
                        ),
                        {
                            **exc.details,
                            "fallbackSkipped": True,
                            "hint": (
                                "Use screenshot as visual truth after this timeout, or retry once "
                                "the UI is idle."
                            ),
                        },
                    ) from exc
                errors.append({"backend": "android-snapshot-helper", "message": exc.message})
        elif resolved_options.backend in {"helper", "apk"}:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "Android snapshot helper APK was not found",
                {
                    "helperApk": resolved_options.helper_apk,
                    "env": SNAPSHOT_HELPER_APK_ENV,
                    "legacyEnv": LEGACY_SNAPSHOT_HELPER_APK_ENV,
                },
            )

    if resolved_options.backend in {"auto", "jar"}:
        snapshot_jar = resolve_snapshot_jar(resolved_options.snapshot_jar)
        if snapshot_jar:
            try:
                return capture_with_jar(serial, snapshot_jar, resolved_options, adb_runner)
            except U2CliError as exc:
                if resolved_options.backend == "jar":
                    raise
                if is_snapshot_busy_timeout(exc):
                    raise U2CliError(
                        exc.code,
                        (
                            f"{exc.message}. Stock UIAutomator fallback was skipped because the "
                            "accessibility tree is busy or stalled."
                        ),
                        {
                            **exc.details,
                            "fallbackSkipped": True,
                            "hint": (
                                "Use screenshot as visual truth after this timeout, or retry once "
                                "the UI is idle."
                            ),
                        },
                    ) from exc
                errors.append({"backend": "android-uiautomator-jar", "message": exc.message})
        elif resolved_options.backend == "jar":
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "Android snapshot JAR was not found",
                {
                    "snapshotJar": resolved_options.snapshot_jar,
                    "env": SNAPSHOT_JAR_ENV,
                    "legacyEnv": LEGACY_SNAPSHOT_JAR_ENV,
                },
            )

    if resolved_options.backend in {"auto", "adb"}:
        try:
            capture = capture_with_adb_dump(serial, adb_runner)
            if errors:
                capture.metadata["fallbackErrors"] = errors
            return capture
        except U2CliError as exc:
            if resolved_options.backend == "adb":
                raise
            errors.append({"backend": "adb-uiautomator-dump", "message": exc.message})

    if resolved_options.backend in {"auto", "uiautomator2"}:
        try:
            xml = device.dump_hierarchy()
        except BaseException as exc:
            raise normalize_exception(exc) from exc
        metadata: dict[str, Any] = {"backend": "uiautomator2"}
        if errors:
            metadata["fallbackErrors"] = errors
        return SnapshotCapture(xml=xml, backend="uiautomator2", metadata=metadata)

    raise U2CliError(
        ErrorCode.ACTION_FAILED,
        "No Android snapshot backend succeeded",
        {"errors": errors},
    )


def capture_with_helper(
    serial: str | None,
    artifact: SnapshotHelperArtifact,
    options: SnapshotBackendOptions,
    adb_runner: AdbRunner | None = None,
    action: SnapshotHelperAction = "snapshot",
) -> SnapshotCapture:
    install_result = ensure_snapshot_helper(serial, artifact, options, adb_runner)
    runner = str(artifact.manifest.get("instrumentationRunner") or ANDROID_HELPER_RUNNER)
    package_name = str(artifact.manifest.get("packageName") or ANDROID_HELPER_PACKAGE)
    command_timeout_ms = options.snapshot_timeout_ms + DEFAULT_SNAPSHOT_COMMAND_OVERHEAD_MS
    result = run_adb(
        serial,
        [
            "shell",
            "am",
            "instrument",
            "-w",
            "-e",
            "action",
            action,
            "-e",
            "waitForIdleTimeoutMs",
            str(options.wait_for_idle_timeout_ms),
            "-e",
            "timeoutMs",
            str(options.snapshot_timeout_ms),
            "-e",
            "maxDepth",
            str(options.max_depth),
            "-e",
            "maxNodes",
            str(options.max_nodes),
            runner,
        ],
        timeout_ms=command_timeout_ms,
        allow_failure=True,
        adb_runner=adb_runner,
    )
    output = f"{result.stdout}\n{result.stderr}"
    parsed: dict[str, Any] | None = None
    parse_error: U2CliError | None = None
    try:
        parsed = parse_helper_output(output)
    except U2CliError as exc:
        if result.exit_code == 0:
            raise
        parse_error = exc
    if result.exit_code != 0:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            parse_error.message if parse_error else "Android snapshot helper failed",
            {
                "exitCode": result.exit_code,
                "stderr": result.stderr,
                **(parse_error.details if parse_error else {}),
                **({"helper": parsed["metadata"]} if parsed else {}),
            },
        )
    if parsed is None:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot helper output could not be parsed",
            {"stdout": result.stdout, "stderr": result.stderr},
        )
    metadata = parsed["metadata"]
    if metadata.get("ok") is False:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            str(metadata.get("message") or metadata.get("errorType") or "Android snapshot helper failed"),
            {"helper": metadata},
        )
    return SnapshotCapture(
        xml=parsed["xml"],
        backend="android-snapshot-helper",
        metadata={
            "backend": "android-snapshot-helper",
            "helperApk": artifact.apk_path,
            "packageName": package_name,
            "instrumentationRunner": runner,
            "install": install_result,
            **metadata,
            **({"helperTruncated": metadata["truncated"]} if "truncated" in metadata else {}),
        },
    )


def ensure_snapshot_helper(
    serial: str | None,
    artifact: SnapshotHelperArtifact,
    options: SnapshotBackendOptions,
    adb_runner: AdbRunner | None = None,
) -> dict[str, Any]:
    manifest = artifact.manifest
    package_name = str(manifest.get("packageName") or ANDROID_HELPER_PACKAGE)
    version_code = read_int_value(manifest.get("versionCode")) or 1
    if options.helper_install_policy == "never":
        return {
            "packageName": package_name,
            "versionCode": version_code,
            "installed": False,
            "reason": "skipped",
        }
    cache_key = (serial, package_name, version_code)
    if (
        options.helper_install_policy != "always"
        and INSTALLED_SNAPSHOT_HELPERS.get(cache_key) == version_code
    ):
        return {
            "packageName": package_name,
            "versionCode": version_code,
            "installedVersionCode": version_code,
            "installed": False,
            "reason": "current",
            "cached": True,
        }

    installed_version_code = read_installed_version_code(
        serial,
        package_name,
        options.snapshot_timeout_ms,
        adb_runner,
    )
    reason = helper_install_reason(
        options.helper_install_policy,
        installed_version_code,
        version_code,
    )
    if reason == "current":
        INSTALLED_SNAPSHOT_HELPERS[cache_key] = version_code
        return {
            "packageName": package_name,
            "versionCode": version_code,
            "installedVersionCode": installed_version_code,
            "installed": False,
            "reason": "current",
        }

    verify_snapshot_helper_artifact(artifact)
    install_args = read_helper_install_args(manifest)
    install_timeout_ms = max(30_000, options.snapshot_timeout_ms + DEFAULT_SNAPSHOT_COMMAND_OVERHEAD_MS)
    result = run_adb(
        serial,
        [*install_args, artifact.apk_path],
        timeout_ms=install_timeout_ms,
        allow_failure=True,
        adb_runner=adb_runner,
    )
    if result.exit_code != 0 and is_install_update_incompatible(result):
        uninstall = run_adb(
            serial,
            ["uninstall", package_name],
            timeout_ms=install_timeout_ms,
            allow_failure=True,
            adb_runner=adb_runner,
        )
        result = run_adb(
            serial,
            [*install_args, artifact.apk_path],
            timeout_ms=install_timeout_ms,
            allow_failure=True,
            adb_runner=adb_runner,
        )
        if result.exit_code != 0 and uninstall.stderr:
            result = AdbResult(
                args=result.args,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=(
                    f"{result.stderr}\nPrevious uninstall stderr after "
                    f"INSTALL_FAILED_UPDATE_INCOMPATIBLE: {uninstall.stderr}"
                ).strip(),
            )
    if result.exit_code != 0:
        raise adb_failure("Failed to install Android snapshot helper", result)
    INSTALLED_SNAPSHOT_HELPERS[cache_key] = version_code
    return {
        "packageName": package_name,
        "versionCode": version_code,
        **({"installedVersionCode": installed_version_code} if installed_version_code is not None else {}),
        "installed": True,
        "reason": reason,
    }


def read_installed_version_code(
    serial: str | None,
    package_name: str,
    timeout_ms: int,
    adb_runner: AdbRunner | None = None,
) -> int | None:
    result = run_adb(
        serial,
        ["shell", "cmd", "package", "list", "packages", "--show-versioncode", package_name],
        timeout_ms=max(5_000, timeout_ms),
        allow_failure=True,
        adb_runner=adb_runner,
    )
    if result.exit_code != 0:
        return None
    package_prefix = f"package:{package_name}"
    for line in f"{result.stdout}\n{result.stderr}".splitlines():
        if not line.startswith(package_prefix):
            continue
        if len(line) > len(package_prefix) and not line[len(package_prefix)].isspace():
            continue
        match = re.search(r"(?:^|\s)versionCode:(\d+)(?:\s|$)", line)
        if match:
            return int(match.group(1))
    return None


def helper_install_reason(
    policy: SnapshotHelperInstallPolicy,
    installed_version_code: int | None,
    required_version_code: int,
) -> str:
    if policy == "never":
        return "skipped"
    if policy == "always":
        return "forced"
    if installed_version_code is None:
        return "missing"
    return "outdated" if installed_version_code < required_version_code else "current"


def verify_snapshot_helper_artifact(artifact: SnapshotHelperArtifact) -> None:
    apk_path = Path(artifact.apk_path)
    if not apk_path.is_file():
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "Android snapshot helper APK does not exist",
            {"helperApk": str(apk_path)},
        )
    expected_sha = artifact.manifest.get("sha256")
    if isinstance(expected_sha, str) and expected_sha:
        actual_sha = hashlib.sha256(apk_path.read_bytes()).hexdigest()
        if actual_sha.lower() != expected_sha.lower():
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "Android snapshot helper APK checksum mismatch",
                {"helperApk": str(apk_path), "expectedSha256": expected_sha, "actualSha256": actual_sha},
            )


def read_helper_install_args(manifest: dict[str, Any]) -> list[str]:
    raw_args = manifest.get("installArgs")
    if raw_args is None:
        return list(ANDROID_HELPER_DEFAULT_INSTALL_ARGS)
    if not isinstance(raw_args, list) or not all(isinstance(arg, str) for arg in raw_args):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "Android snapshot helper manifest installArgs must be a string array",
            {"installArgs": raw_args},
        )
    if not raw_args or raw_args[0] != "install":
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            'Android snapshot helper manifest installArgs must start with "install"',
            {"installArgs": raw_args},
        )
    allowed_flags = {"-r", "-t", "-d", "-g"}
    unsupported = [arg for arg in raw_args[1:] if arg not in allowed_flags]
    if unsupported:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            f'Android snapshot helper manifest installArgs contains unsupported flag "{unsupported[0]}"',
            {"installArgs": raw_args},
        )
    return list(raw_args)


def is_install_update_incompatible(result: AdbResult) -> bool:
    return "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in f"{result.stdout}\n{result.stderr}"


def capture_with_jar(
    serial: str | None,
    snapshot_jar: str,
    options: SnapshotBackendOptions,
    adb_runner: AdbRunner | None = None,
) -> SnapshotCapture:
    jar_path = Path(snapshot_jar)
    if not jar_path.is_file():
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "Android snapshot JAR does not exist",
            {"snapshotJar": str(jar_path)},
        )

    push_result = run_adb(
        serial,
        ["push", str(jar_path), ANDROID_JAR_REMOTE_PATH],
        timeout_ms=max(
            10_000,
            options.snapshot_timeout_ms + DEFAULT_SNAPSHOT_COMMAND_OVERHEAD_MS,
        ),
        allow_failure=True,
        adb_runner=adb_runner,
    )
    if push_result.exit_code != 0:
        raise adb_failure("Failed to push Android snapshot JAR", push_result)

    command_timeout_ms = options.snapshot_timeout_ms + DEFAULT_SNAPSHOT_COMMAND_OVERHEAD_MS
    result = run_adb(
        serial,
        [
            "shell",
            "uiautomator",
            "runtest",
            ANDROID_JAR_REMOTE_PATH,
            "-c",
            ANDROID_JAR_ENTRY_CLASS,
            "-e",
            "waitForIdleTimeoutMs",
            str(options.wait_for_idle_timeout_ms),
            "-e",
            "timeoutMs",
            str(options.snapshot_timeout_ms),
            "-e",
            "maxDepth",
            str(options.max_depth),
            "-e",
            "maxNodes",
            str(options.max_nodes),
        ],
        timeout_ms=command_timeout_ms,
        allow_failure=True,
        adb_runner=adb_runner,
    )
    output = f"{result.stdout}\n{result.stderr}"
    parsed: dict[str, Any] | None = None
    parse_error: U2CliError | None = None
    try:
        parsed = parse_jar_output(output)
    except U2CliError as exc:
        if result.exit_code == 0:
            raise
        parse_error = exc
    if result.exit_code != 0:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            parse_error.message if parse_error else "Android snapshot JAR failed",
            {
                "exitCode": result.exit_code,
                "stderr": result.stderr,
                **(parse_error.details if parse_error else {}),
                **({"jar": parsed["metadata"]} if parsed else {}),
            },
        )
    if parsed is None:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR output could not be parsed",
            {"stdout": result.stdout, "stderr": result.stderr},
        )
    metadata = parsed["metadata"]
    if metadata.get("ok") is False:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            str(metadata.get("message") or metadata.get("errorType") or "Android snapshot JAR failed"),
            {"jar": metadata},
        )
    return SnapshotCapture(
        xml=parsed["xml"],
        backend="android-uiautomator-jar",
        metadata={
            "backend": "android-uiautomator-jar",
            "snapshotJar": str(jar_path),
            "remotePath": ANDROID_JAR_REMOTE_PATH,
            **metadata,
            **({"helperTruncated": metadata["truncated"]} if "truncated" in metadata else {}),
        },
    )


def capture_with_adb_dump(
    serial: str | None,
    adb_runner: AdbRunner | None = None,
) -> SnapshotCapture:
    streamed = run_adb(
        serial,
        ["exec-out", "uiautomator", "dump", "/dev/tty"],
        timeout_ms=DEFAULT_STOCK_DUMP_TIMEOUT_MS,
        allow_failure=True,
        adb_runner=adb_runner,
    )
    xml = extract_ui_dump_xml(streamed.stdout, streamed.stderr)
    if xml:
        return SnapshotCapture(
            xml=xml,
            backend="adb-uiautomator-dump",
            metadata={"backend": "adb-uiautomator-dump", "mode": "exec-out"},
        )

    dump_path = "/sdcard/window_dump.xml"
    dumped = run_adb(
        serial,
        ["shell", "uiautomator", "dump", dump_path],
        timeout_ms=DEFAULT_STOCK_DUMP_TIMEOUT_MS,
        allow_failure=True,
        adb_runner=adb_runner,
    )
    if dumped.exit_code != 0:
        raise adb_failure("adb uiautomator dump failed", dumped)
    actual_path = resolve_dump_path(dump_path, dumped.stdout, dumped.stderr)
    cat = run_adb(serial, ["shell", "cat", actual_path], allow_failure=True, adb_runner=adb_runner)
    xml = extract_ui_dump_xml(cat.stdout, cat.stderr)
    if not xml:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "adb uiautomator dump did not return XML",
            {
                "dumpStdout": dumped.stdout,
                "dumpStderr": dumped.stderr,
                "catStdout": cat.stdout,
                "catStderr": cat.stderr,
            },
        )
    return SnapshotCapture(
        xml=xml,
        backend="adb-uiautomator-dump",
        metadata={"backend": "adb-uiautomator-dump", "mode": "file", "path": actual_path},
    )


def parse_helper_output(output: str) -> dict[str, Any]:
    records = parse_instrumentation_records(output)
    final_result = next(
        (
            record
            for record in records["results"]
            if record.get("androidtestcliiProtocol") == ANDROID_HELPER_PROTOCOL
        ),
        None,
    )
    if final_result is None:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot helper did not return a final result",
            {"output": output},
        )
    metadata = read_helper_metadata(final_result)
    if final_result.get("ok") != "true":
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            read_helper_error_message(final_result),
            {"helper": metadata, "errorType": final_result.get("errorType")},
        )
    if final_result.get("action") in {"toast-get", "toast-clear"}:
        return {"xml": "", "metadata": metadata}
    xml = decode_helper_xml(collect_helper_chunks(records["status"]), metadata)
    return {"xml": xml, "metadata": metadata}


def parse_instrumentation_records(output: str) -> dict[str, list[dict[str, str]]]:
    status: list[dict[str, str]] = []
    results: list[dict[str, str]] = []
    current_status: dict[str, str] | None = None
    current_result: dict[str, str] | None = None

    for line in output.splitlines():
        if line.startswith("INSTRUMENTATION_STATUS: "):
            if current_status is None:
                current_status = {}
            read_key_value(line.removeprefix("INSTRUMENTATION_STATUS: "), current_status)
            continue
        if line.startswith("INSTRUMENTATION_STATUS_CODE: "):
            if current_status is not None:
                status.append(current_status)
                current_status = None
            continue
        if line.startswith("INSTRUMENTATION_RESULT: "):
            if current_result is None:
                current_result = {}
            read_key_value(line.removeprefix("INSTRUMENTATION_RESULT: "), current_result)
            continue
        if line.startswith("INSTRUMENTATION_CODE: "):
            if current_result is not None:
                results.append(current_result)
                current_result = None

    if current_status is not None:
        status.append(current_status)
    if current_result is not None:
        results.append(current_result)
    return {"status": status, "results": results}


def read_key_value(line: str, target: dict[str, str]) -> None:
    separator = line.find("=")
    if separator < 0:
        return
    target[line[:separator]] = line[separator + 1 :]


def collect_helper_chunks(records: list[dict[str, str]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for record in records:
        if record.get("androidtestcliiProtocol") != ANDROID_HELPER_PROTOCOL:
            continue
        if record.get("outputFormat") != ANDROID_HELPER_OUTPUT_FORMAT:
            continue
        if "payloadBase64" not in record:
            continue
        chunks.append(
            {
                "index": read_int_value(record.get("chunkIndex")),
                "count": read_int_value(record.get("chunkCount")),
                "payloadBase64": record["payloadBase64"],
            }
        )
    return chunks


def decode_helper_xml(chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    if not chunks:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot helper did not return XML chunks",
            {"helper": metadata},
        )
    expected_count = chunks[0].get("count") or len(chunks)
    if (
        not isinstance(expected_count, int)
        or expected_count < 1
        or len(chunks) != expected_count
        or any(chunk.get("count") != expected_count for chunk in chunks)
    ):
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot helper returned incomplete XML chunks",
            {"expectedChunks": expected_count, "actualChunks": len(chunks)},
        )

    indexed: dict[int, str] = {}
    for chunk in chunks:
        index = chunk.get("index")
        if not isinstance(index, int) or index < 0 or index >= expected_count:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot helper returned invalid chunk index",
                {"chunkIndex": index, "expectedChunks": expected_count},
            )
        if index in indexed:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot helper returned duplicate XML chunks",
                {"chunkIndex": index},
            )
        indexed[index] = str(chunk.get("payloadBase64") or "")

    payloads: list[bytes] = []
    for index in range(expected_count):
        payload = indexed.get(index)
        if payload is None:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot helper returned incomplete XML chunks",
                {"missingChunkIndex": index, "expectedChunks": expected_count},
            )
        try:
            payloads.append(base64.b64decode(payload, validate=True))
        except ValueError as exc:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot helper returned invalid base64 XML chunk",
                {"chunkIndex": index},
            ) from exc
    xml = b"".join(payloads).decode("utf-8", errors="replace")
    if "<hierarchy" not in xml or "</hierarchy>" not in xml:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot helper output did not contain XML",
            {"xml": xml},
        )
    return xml


def read_helper_metadata(final_result: dict[str, str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "protocol": final_result.get("androidtestcliiProtocol"),
        "ok": read_bool_value(final_result.get("ok")),
        "action": read_optional_text(final_result.get("action")),
        "helperApiVersion": read_optional_text(final_result.get("helperApiVersion")),
        "outputFormat": ANDROID_HELPER_OUTPUT_FORMAT,
        "waitForIdleTimeoutMs": read_int_value(final_result.get("waitForIdleTimeoutMs")),
        "timeoutMs": read_int_value(final_result.get("timeoutMs")),
        "maxDepth": read_int_value(final_result.get("maxDepth")),
        "maxNodes": read_int_value(final_result.get("maxNodes")),
        "rootPresent": read_bool_value(final_result.get("rootPresent")),
        "captureMode": read_capture_mode(final_result.get("captureMode")),
        "windowCount": read_int_value(final_result.get("windowCount")),
        "nodeCount": read_int_value(final_result.get("nodeCount")),
        "truncated": read_bool_value(final_result.get("truncated")),
        "elapsedMs": read_int_value(final_result.get("elapsedMs")),
    }
    if final_result.get("errorType"):
        metadata["errorType"] = final_result["errorType"]
    if final_result.get("message"):
        metadata["message"] = final_result["message"]
    toast_capture = read_toast_capture(final_result)
    if toast_capture is not None:
        metadata["toastCapture"] = toast_capture
    return {key: value for key, value in metadata.items() if value is not None}


def read_toast_capture(final_result: dict[str, str]) -> dict[str, Any] | None:
    if "toastStatus" not in final_result:
        return None
    status = read_toast_status(final_result.get("toastStatus"))
    latest_text = decode_optional_base64(final_result.get("toastLatestTextBase64"))
    latest_id = read_optional_text(final_result.get("toastLatestId"))
    latest_package = read_optional_text(final_result.get("toastLatestPackage"))
    latest_captured_at_ms = read_int_value(final_result.get("toastLatestCapturedAtMs"))
    latest: dict[str, Any] | None = None
    if latest_text and status == "captured":
        latest = {
            **({"id": latest_id} if latest_id else {}),
            "text": latest_text,
            **({"packageName": latest_package} if latest_package else {}),
            **(
                {"capturedAtMs": latest_captured_at_ms}
                if latest_captured_at_ms is not None
                else {}
            ),
            "source": "toast",
        }
    max_history_size = read_int_value(final_result.get("toastMaxHistorySize"))
    return {
        "status": status,
        "reason": read_optional_text(final_result.get("toastReason")),
        "message": read_optional_text(final_result.get("toastMessage")),
        "latest": latest,
        "historySize": read_int_value(final_result.get("toastHistorySize")),
        "maxHistorySize": max_history_size if max_history_size is not None else 20,
    }


def read_toast_status(value: str | None) -> str:
    if value in {"captured", "empty", "disabled", "unavailable", "timeout", "error"}:
        return value
    return "error"


def read_helper_error_message(final_result: dict[str, str]) -> str:
    message = final_result.get("message")
    if message and message != "null":
        return message
    return final_result.get("errorType") or "Android snapshot helper returned an error"


def parse_jar_output(output: str) -> dict[str, Any]:
    metadata: dict[str, Any] | None = None
    chunks: dict[int, str] = {}
    expected_count: int | None = None

    for line in output.splitlines():
        if line.startswith(ANDROID_JAR_METADATA_PREFIX):
            metadata = decode_jar_metadata(line.removeprefix(ANDROID_JAR_METADATA_PREFIX))
            continue
        if not line.startswith(ANDROID_JAR_XML_CHUNK_PREFIX):
            continue
        rest = line.removeprefix(ANDROID_JAR_XML_CHUNK_PREFIX)
        parts = rest.split(":", 1)
        if len(parts) != 2:
            raise U2CliError(ErrorCode.ACTION_FAILED, "Android snapshot JAR returned bad XML chunk")
        index_count, payload = parts
        index_parts = index_count.split("/", 1)
        if len(index_parts) != 2:
            raise U2CliError(ErrorCode.ACTION_FAILED, "Android snapshot JAR returned bad chunk index")
        try:
            index = int(index_parts[0])
            chunk_count = int(index_parts[1])
        except ValueError as exc:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot JAR returned non-numeric chunk index",
            ) from exc
        if index < 0 or chunk_count < 1 or index >= chunk_count:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot JAR returned invalid chunk index",
                {"chunkIndex": index, "chunkCount": chunk_count},
            )
        if expected_count is None:
            expected_count = chunk_count
        elif expected_count != chunk_count:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot JAR returned inconsistent chunk counts",
                {"expectedChunks": expected_count, "actualChunks": chunk_count},
            )
        if index in chunks:
            raise U2CliError(
                ErrorCode.ACTION_FAILED,
                "Android snapshot JAR returned duplicate XML chunks",
                {"chunkIndex": index},
            )
        chunks[index] = payload

    if metadata is None:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR did not return metadata",
            {"output": output},
        )
    if metadata.get("protocol") != ANDROID_JAR_PROTOCOL:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR returned an unexpected protocol",
            {"protocol": metadata.get("protocol")},
        )
    if not chunks or expected_count is None:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR did not return XML chunks",
            {"metadata": metadata},
        )
    if len(chunks) != expected_count:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR returned incomplete XML chunks",
            {"expectedChunks": expected_count, "actualChunks": len(chunks)},
        )

    payload = "".join(chunks[index] for index in range(expected_count))
    try:
        xml = base64.b64decode(payload, validate=True).decode("utf-8", errors="replace")
    except ValueError as exc:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR returned invalid base64 XML",
        ) from exc
    if "<hierarchy" not in xml or "</hierarchy>" not in xml:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR output did not contain XML",
            {"xml": xml},
        )
    return {"xml": xml, "metadata": metadata}


def decode_jar_metadata(payload: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(payload, validate=True).decode("utf-8", errors="replace")
        metadata = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR returned invalid metadata",
        ) from exc
    if not isinstance(metadata, dict):
        raise U2CliError(
            ErrorCode.ACTION_FAILED,
            "Android snapshot JAR metadata was not an object",
            {"metadata": metadata},
        )
    return metadata


def run_adb(
    serial: str | None,
    args: list[str],
    *,
    timeout_ms: int = DEFAULT_STOCK_DUMP_TIMEOUT_MS,
    allow_failure: bool = False,
    adb_runner: AdbRunner | None = None,
) -> AdbResult:
    if adb_runner is not None:
        return adb_runner(serial, args, timeout_ms=timeout_ms, allow_failure=allow_failure)

    executable = adb_path()
    if executable is None:
        raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")
    command = [executable]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    try:
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_ms / 1000,
        )
    except FileNotFoundError as exc:
        raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise U2CliError(
            ErrorCode.ACTION_TIMEOUT,
            "adb command timed out",
            {"args": args, "timeoutMs": timeout_ms},
        ) from exc
    result = AdbResult(args=args, exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    if proc.returncode != 0 and not allow_failure:
        raise adb_failure("adb command failed", result)
    return result


def adb_failure(message: str, result: AdbResult) -> U2CliError:
    return U2CliError(
        ErrorCode.ACTION_FAILED,
        message,
        {
            "args": result.args,
            "exitCode": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )


def is_snapshot_busy_timeout(error: U2CliError) -> bool:
    payload = error.details.get("helper") or error.details.get("jar")
    error_text = ""
    if isinstance(payload, dict):
        error_text = " ".join(
            str(payload.get(key, "")) for key in ("errorType", "message") if payload.get(key)
        )
    text = f"{error.message} {error_text}".lower()
    return "timeoutexception" in text or "timed out" in text


def resolve_snapshot_helper(explicit_path: str | None) -> SnapshotHelperArtifact | None:
    candidates = [
        explicit_path,
        os.environ.get(SNAPSHOT_HELPER_APK_ENV),
        os.environ.get(LEGACY_SNAPSHOT_HELPER_APK_ENV),
        package_snapshot_helper_apk(),
        repository_snapshot_helper_apk(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return SnapshotHelperArtifact(str(path), read_snapshot_helper_manifest(path))
    return None


def read_snapshot_helper_manifest(apk_path: Path) -> dict[str, Any]:
    manifest_path = Path(f"{apk_path}.manifest.json")
    if manifest_path.is_file():
        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "Android snapshot helper manifest is invalid JSON",
                {"manifest": str(manifest_path)},
            ) from exc
        if not isinstance(raw_manifest, dict):
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "Android snapshot helper manifest must be an object",
                {"manifest": str(manifest_path)},
            )
        return raw_manifest
    return {
        "name": "android-snapshot-helper",
        "assetName": apk_path.name,
        "sha256": "",
        "packageName": ANDROID_HELPER_PACKAGE,
        "versionCode": 1,
        "instrumentationRunner": ANDROID_HELPER_RUNNER,
        "minSdk": 23,
        "outputFormat": ANDROID_HELPER_OUTPUT_FORMAT,
        "statusProtocol": ANDROID_HELPER_PROTOCOL,
        "installArgs": ANDROID_HELPER_DEFAULT_INSTALL_ARGS,
    }


def package_snapshot_helper_apk() -> str | None:
    try:
        files = resources.files("androidtestclii").joinpath("android-snapshot-helper")
    except (ModuleNotFoundError, AttributeError):
        return None
    try:
        apks = sorted(str(path) for path in files.iterdir() if path.name.endswith(".apk"))
    except (FileNotFoundError, NotADirectoryError):
        return None
    return apks[-1] if apks else None


def repository_snapshot_helper_apk() -> str | None:
    root = Path(__file__).resolve().parents[3]
    helper_dir = root / "android-snapshot-helper" / "dist"
    if not helper_dir.is_dir():
        return None
    apks = sorted(helper_dir.glob("*.apk"))
    return str(apks[-1]) if apks else None


def resolve_snapshot_jar(explicit_path: str | None) -> str | None:
    candidates = [
        explicit_path,
        os.environ.get(SNAPSHOT_JAR_ENV),
        os.environ.get(LEGACY_SNAPSHOT_JAR_ENV),
        package_snapshot_jar(),
        repository_snapshot_jar(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    return None


def package_snapshot_jar() -> str | None:
    try:
        files = resources.files("androidtestclii").joinpath("android-snapshot-jar")
    except (ModuleNotFoundError, AttributeError):
        return None
    try:
        jars = sorted(str(path) for path in files.iterdir() if path.name.endswith(".jar"))
    except (FileNotFoundError, NotADirectoryError):
        return None
    return jars[-1] if jars else None


def repository_snapshot_jar() -> str | None:
    root = Path(__file__).resolve().parents[3]
    jar_dir = root / "android-snapshot-jar" / "dist"
    if not jar_dir.is_dir():
        return None
    jars = sorted(jar_dir.glob("*.jar"))
    return str(jars[-1]) if jars else None


def extract_ui_dump_xml(stdout: str, stderr: str) -> str | None:
    text = f"{stdout}\n{stderr}"
    xml_start = text.find("<?xml")
    hierarchy_start = xml_start if xml_start >= 0 else text.find("<hierarchy")
    if hierarchy_start < 0:
        return None
    end = text.rfind("</hierarchy>")
    if end < 0 or end < hierarchy_start:
        return None
    xml = text[hierarchy_start : end + len("</hierarchy>")].strip()
    return xml or None


def resolve_dump_path(default_path: str, stdout: str, stderr: str) -> str:
    match = re.search(r"dumped to:\s*(\S+)", f"{stdout}\n{stderr}", flags=re.IGNORECASE)
    return match.group(1) if match else default_path


def read_int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def read_bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def read_optional_text(value: str | None) -> str | None:
    if value is None or value == "null":
        return None
    trimmed = value.strip()
    return trimmed or None


def read_capture_mode(value: str | None) -> str | None:
    if value in {"interactive-windows", "active-window"}:
        return value
    return None


def decode_optional_base64(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if not re.fullmatch(r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?", trimmed):
        return None
    try:
        return base64.b64decode(trimmed, validate=True).decode("utf-8", errors="replace")
    except ValueError:
        return None
