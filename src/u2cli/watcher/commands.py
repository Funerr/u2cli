from __future__ import annotations

from typing import Any

from u2cli.context import CommandContext
from u2cli.device.connect import connect_device
from u2cli.errors import ErrorCode, U2CliError
from u2cli.timeouts import run_with_timeout


def _watcher_api(device: Any, name: str) -> Any:
    watcher = getattr(device, "watcher", None)
    if not callable(watcher):
        raise U2CliError(ErrorCode.ACTION_FAILED, "device does not expose watcher API")
    return watcher(name)


def add(
    ctx: CommandContext,
    name: str,
    text: str | None = None,
    resource_id: str | None = None,
    click_text: str | None = None,
) -> dict[str, Any]:
    if not any([text, resource_id]):
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "watcher add requires --text or --resource-id",
        )
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        api = _watcher_api(device, name)
        if text:
            api = api.when(text=text)
        if resource_id:
            api = api.when(resourceId=resource_id)
        if click_text:
            api.click(text=click_text)
        else:
            api.click()
        return {
            "name": name,
            "text": text,
            "resourceId": resource_id,
            "clickText": click_text,
            "added": True,
        }

    return run_with_timeout(_run, ctx.timeout_ms)


def run(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        watcher = getattr(device, "watchers", None) or getattr(device, "watcher", None)
        if watcher is None:
            raise U2CliError(ErrorCode.ACTION_FAILED, "device does not expose watcher API")
        runner = getattr(watcher, "run", None) or getattr(watcher, "run_watchers", None)
        if callable(runner):
            result = runner()
        else:
            result = device.watchers.run()
        return {"ran": True, "triggered": bool(result) if result is not None else None}

    return run_with_timeout(_run, ctx.timeout_ms)


def reset(ctx: CommandContext) -> dict[str, Any]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        watcher = getattr(device, "watchers", None) or getattr(device, "watcher", None)
        if watcher is None:
            raise U2CliError(ErrorCode.ACTION_FAILED, "device does not expose watcher API")
        remover = getattr(watcher, "remove", None) or getattr(watcher, "reset", None)
        if callable(remover):
            remover()
        return {"reset": True}

    return run_with_timeout(_run, ctx.timeout_ms)
