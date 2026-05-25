from __future__ import annotations

import traceback
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PYTHON_ENV_INVALID = "PYTHON_ENV_INVALID"
    U2_IMPORT_FAILED = "U2_IMPORT_FAILED"
    ADB_NOT_FOUND = "ADB_NOT_FOUND"
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    U2_CONNECT_FAILED = "U2_CONNECT_FAILED"
    APP_ACTION_FAILED = "APP_ACTION_FAILED"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ELEMENT_AMBIGUOUS = "ELEMENT_AMBIGUOUS"
    ACTION_TIMEOUT = "ACTION_TIMEOUT"
    ACTION_FAILED = "ACTION_FAILED"
    SCREENSHOT_FAILED = "SCREENSHOT_FAILED"
    TOAST_TIMEOUT = "TOAST_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


EXIT_CODES: dict[ErrorCode, int] = {
    ErrorCode.INVALID_ARGUMENT: 64,
    ErrorCode.INTERNAL_ERROR: 2,
}


class U2CliError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def exit_code_for(code: ErrorCode) -> int:
    return EXIT_CODES.get(code, 1)


def normalize_exception(exc: BaseException) -> U2CliError:
    if isinstance(exc, U2CliError):
        return exc

    name = type(exc).__name__
    text = str(exc)
    lower = text.lower()

    if isinstance(exc, FileNotFoundError) and (exc.filename == "adb" or "adb" in text):
        return U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")

    if name == "ValidationError":
        return U2CliError(ErrorCode.INVALID_ARGUMENT, "Invalid command arguments", {"error": text})

    if "adb" in lower and "not found" in lower:
        return U2CliError(ErrorCode.ADB_NOT_FOUND, "adb executable was not found")
    if "device offline" in lower or "offline" == lower:
        return U2CliError(ErrorCode.DEVICE_OFFLINE, "Android device is offline")
    if ("device" in lower and "not found" in lower) or "can't find any android device" in lower:
        return U2CliError(ErrorCode.DEVICE_NOT_FOUND, "Android device was not found")
    if "connect" in lower and ("uiautomator" in lower or "atx" in lower):
        return U2CliError(ErrorCode.U2_CONNECT_FAILED, "Failed to connect through uiautomator2")

    if name in {"UiObjectNotFoundError", "XPathElementNotFoundError"}:
        return U2CliError(ErrorCode.ELEMENT_NOT_FOUND, "No element matched selector")
    if name in {"TimeoutError", "FutureTimeoutError"}:
        return U2CliError(ErrorCode.ACTION_TIMEOUT, "Action timed out")
    if name in {"GatewayError", "SessionBrokenError", "RPCError"}:
        return U2CliError(ErrorCode.ACTION_FAILED, "uiautomator2 action failed", {"error": text})

    tb = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return U2CliError(
        ErrorCode.INTERNAL_ERROR,
        "Unhandled internal error",
        {"exceptionType": name, "traceback": tb},
    )
