from __future__ import annotations

import time

import pytest

from androidtestclii.context import CommandContext
from androidtestclii.errors import U2CliError
from androidtestclii.input.commands import press
from androidtestclii.locks import serial_lock
from androidtestclii.timeouts import run_with_timeout


def test_run_with_timeout_raises_action_timeout() -> None:
    with pytest.raises(U2CliError) as exc:
        run_with_timeout(lambda: time.sleep(0.2), 10)

    assert exc.value.code.value == "ACTION_TIMEOUT"


def test_serial_lock_busy() -> None:
    with serial_lock("test-serial", 100):
        with pytest.raises(U2CliError) as exc:
            with serial_lock("test-serial", 10):
                pass

    assert exc.value.code.value == "ACTION_TIMEOUT"


def test_mutation_lock_wraps_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def connect_device(serial: str | None, timeout_ms: int) -> object:
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr("androidtestclii.input.commands.connect_device", connect_device)
    ctx = CommandContext.start(serial="test-serial", timeout_ms=10)

    with serial_lock("test-serial", 100):
        with pytest.raises(U2CliError) as exc:
            press(ctx, "back")

    assert exc.value.code.value == "ACTION_TIMEOUT"
    assert called is False
