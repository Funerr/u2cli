from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from u2cli.errors import ErrorCode, U2CliError, normalize_exception
from u2cli.timeouts import run_with_timeout


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str


def import_u2() -> Any:
    try:
        return importlib.import_module("uiautomator2")
    except ImportError as exc:
        raise U2CliError(
            ErrorCode.U2_IMPORT_FAILED,
            "uiautomator2 cannot be imported",
            {"error": str(exc)},
        ) from exc


def adb_path() -> str | None:
    return shutil.which("adb")


def adb_version() -> str | None:
    path = adb_path()
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path, "version"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (
        (proc.stdout or proc.stderr).strip().splitlines()[0]
        if (proc.stdout or proc.stderr)
        else None
    )


def list_adb_devices() -> list[AdbDevice]:
    path = adb_path()
    if not path:
        raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")
    try:
        proc = subprocess.run(
            [path, "devices"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found") from exc
    except subprocess.SubprocessError as exc:
        raise U2CliError(
            ErrorCode.ACTION_FAILED, "Failed to run adb devices", {"error": str(exc)}
        ) from exc

    devices: list[AdbDevice] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2:
            devices.append(AdbDevice(serial=parts[0], state=parts[1]))
    return devices


def ensure_device_online(serial: str | None = None) -> str | None:
    devices = list_adb_devices()
    if serial:
        for device in devices:
            if device.serial == serial:
                if device.state != "device":
                    raise U2CliError(
                        ErrorCode.DEVICE_OFFLINE,
                        "Android device is not online",
                        {"serial": serial, "state": device.state},
                    )
                return serial
        raise U2CliError(
            ErrorCode.DEVICE_NOT_FOUND, "Android device was not found", {"serial": serial}
        )
    online = [device for device in devices if device.state == "device"]
    if len(online) == 1:
        return online[0].serial
    if not online:
        return None
    raise U2CliError(
        ErrorCode.INVALID_ARGUMENT,
        "--serial is required when multiple devices are online",
        {"onlineDevices": [device.serial for device in online]},
    )


def connect_device(serial: str | None, timeout_ms: int) -> Any:
    def _connect() -> Any:
        try:
            u2 = import_u2()
            if serial:
                return u2.connect(serial)
            return u2.connect()
        except BaseException as exc:
            raise normalize_exception(exc) from exc

    return run_with_timeout(_connect, timeout_ms)


def python_health() -> dict[str, Any]:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return {"version": version, "ok": sys.version_info >= (3, 10)}
