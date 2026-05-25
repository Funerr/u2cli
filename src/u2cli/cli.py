from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import click
import typer

from u2cli.app import commands as app_commands
from u2cli.context import CommandContext, DEFAULT_MUTATION_TIMEOUT_MS, DEFAULT_TIMEOUT_MS
from u2cli.device import commands as device_commands
from u2cli.device import health
from u2cli.element import action as element_action
from u2cli.element import query as element_query
from u2cli.element.selector import Selector, selector_from_kwargs
from u2cli.errors import U2CliError, exit_code_for, normalize_exception
from u2cli.errors import ErrorCode
from u2cli.input import commands as input_commands
from u2cli.pi.tool_schema import tool_schema
from u2cli.result import CommandResult
from u2cli.screen import commands as screen_commands
from u2cli.screen import dump as screen_dump
from u2cli.screen import screenshot as screen_screenshot
from u2cli.screen import size as screen_size
from u2cli.session import commands as session_commands
from u2cli.toast import commands as toast_commands
from u2cli.watcher import commands as watcher_commands

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Agent-friendly Android CLI built on uiautomator2.",
)
device_app = typer.Typer(help="Inspect Android devices.")
app_app = typer.Typer(help="Manage app lifecycle.")
screen_app = typer.Typer(help="Observe screen state.")
element_app = typer.Typer(help="Find and operate UI elements.")
input_app = typer.Typer(help="Send input gestures.")
toast_app = typer.Typer(help="Read toast messages.")
pi_app = typer.Typer(help="Export Pi tool integration metadata.")
watcher_app = typer.Typer(help="Configure transient dialog watchers.")
session_app = typer.Typer(help="Inspect CLI session and sidecar mode.")

app.add_typer(device_app, name="device")
app.add_typer(app_app, name="app")
app.add_typer(screen_app, name="screen")
app.add_typer(element_app, name="element")
app.add_typer(input_app, name="input")
app.add_typer(toast_app, name="toast")
app.add_typer(pi_app, name="pi")
app.add_typer(watcher_app, name="watcher")
app.add_typer(session_app, name="session")

_ctx = CommandContext.start()
_exit_code = 0


@app.callback()
def global_options(
    json_output: bool = typer.Option(True, "--json", help="Emit a single JSON object on stdout."),
    serial: str | None = typer.Option(None, "--serial", help="Android device serial."),
    timeout_ms: int = typer.Option(
        DEFAULT_TIMEOUT_MS,
        "--timeout-ms",
        help="Command timeout budget in milliseconds.",
    ),
    verbose: bool = typer.Option(
        False, "-v", help="Increase stderr log verbosity; -vv is accepted."
    ),
) -> None:
    _ = (json_output, serial, timeout_ms, verbose)


def _emit(command: str, runner: Callable[[], Any]) -> None:
    global _exit_code
    try:
        value = runner()
        artifacts: list[dict[str, Any]] = []
        data = value
        if (
            isinstance(value, tuple)
            and len(value) == 2
            and isinstance(value[1], list)
            and isinstance(value[0], dict)
        ):
            data, artifacts = value
        result = CommandResult.ok(
            command=command,
            serial=_ctx.serial,
            duration_ms=_ctx.elapsed_ms(),
            data=data,
            artifacts=artifacts,
        )
        print(result.to_json())
        _exit_code = 0
    except BaseException as exc:
        error = normalize_exception(exc)
        result = CommandResult.failed(
            command=command,
            serial=_ctx.serial,
            duration_ms=_ctx.elapsed_ms(),
            error=error,
        )
        print(result.to_json())
        _exit_code = exit_code_for(error.code)


def _selector(
    *,
    text: str | None,
    text_contains: str | None,
    resource_id: str | None,
    description: str | None,
    description_contains: str | None,
    class_name: str | None,
    xpath: str | None,
    index: int | None,
) -> Selector:
    return selector_from_kwargs(
        text=text,
        text_contains=text_contains,
        resource_id=resource_id,
        description=description,
        description_contains=description_contains,
        class_name=class_name,
        xpath=xpath,
        index=index,
    )


def _parse_point(value: str, option: str) -> tuple[int, int]:
    try:
        left, right = value.split(",", 1)
        return int(left), int(right)
    except ValueError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            f"{option} must be formatted as x,y",
            {"argument": option, "value": value},
        ) from exc


def _extract_global_args(argv: list[str]) -> tuple[list[str], CommandContext]:
    json_output = True
    serial: str | None = None
    timeout_ms = DEFAULT_TIMEOUT_MS
    timeout_ms_explicit = False
    verbosity = 0
    passthrough: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            json_output = True
            i += 1
        elif arg == "--serial":
            if i + 1 >= len(argv):
                raise U2CliError(
                    ErrorCode.INVALID_ARGUMENT,
                    "--serial requires a value",
                    {"argument": "serial"},
                )
            serial = argv[i + 1]
            i += 2
        elif arg.startswith("--serial="):
            serial = arg.split("=", 1)[1]
            i += 1
        elif arg == "--timeout-ms":
            if i + 1 >= len(argv):
                raise U2CliError(
                    ErrorCode.INVALID_ARGUMENT,
                    "--timeout-ms requires a value",
                    {"argument": "timeout-ms"},
                )
            try:
                timeout_ms = int(argv[i + 1])
            except ValueError as exc:
                raise U2CliError(
                    ErrorCode.INVALID_ARGUMENT,
                    "--timeout-ms must be an integer",
                    {"argument": "timeout-ms", "value": argv[i + 1]},
                ) from exc
            timeout_ms_explicit = True
            i += 2
        elif arg.startswith("--timeout-ms="):
            raw = arg.split("=", 1)[1]
            try:
                timeout_ms = int(raw)
            except ValueError as exc:
                raise U2CliError(
                    ErrorCode.INVALID_ARGUMENT,
                    "--timeout-ms must be an integer",
                    {"argument": "timeout-ms", "value": raw},
                ) from exc
            timeout_ms_explicit = True
            i += 1
        elif arg in {"-v", "-vv"}:
            verbosity += len(arg) - 1
            i += 1
        else:
            passthrough.append(arg)
            i += 1
    return passthrough, CommandContext.start(
        json_output=json_output,
        serial=serial,
        timeout_ms=timeout_ms,
        timeout_ms_explicit=timeout_ms_explicit,
        verbosity=verbosity,
    )


def _mutation_ctx() -> CommandContext:
    if _ctx.timeout_ms_explicit:
        return _ctx
    return CommandContext.start(
        json_output=_ctx.json_output,
        serial=_ctx.serial,
        timeout_ms=DEFAULT_MUTATION_TIMEOUT_MS,
        timeout_ms_explicit=False,
        verbosity=_ctx.verbosity,
    )


def _require_explicit_timeout(command: str) -> None:
    if not _ctx.timeout_ms_explicit:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            f"{command} requires explicit --timeout-ms",
            {"argument": "timeout-ms"},
        )


@app.command()
def doctor() -> None:
    """Run local environment and optional target-device health checks."""
    _emit("doctor", lambda: health.doctor_data(_ctx))


@app.command()
def devices() -> None:
    """List attached Android devices."""
    _emit("devices", health.devices_data)


@device_app.command("info")
def device_info() -> None:
    """Return detailed information for the selected device."""
    _emit("device.info", lambda: health.device_info_data(_ctx))


@device_app.command("shell")
def device_shell(command: str = typer.Option(..., "--command")) -> None:
    _emit("device.shell", lambda: device_commands.shell(_ctx, command))


@device_app.command("push")
def device_push(
    local: str = typer.Option(..., "--local"),
    remote: str = typer.Option(..., "--remote"),
) -> None:
    _emit("device.push", lambda: device_commands.push(_mutation_ctx(), local, remote))


@device_app.command("pull")
def device_pull(
    remote: str = typer.Option(..., "--remote"),
    local: str = typer.Option(..., "--local"),
) -> None:
    _emit("device.pull", lambda: device_commands.pull(_mutation_ctx(), remote, local))


@device_app.command("clipboard-get")
def device_clipboard_get() -> None:
    _emit("device.clipboard-get", lambda: device_commands.clipboard_get(_ctx))


@device_app.command("clipboard-set")
def device_clipboard_set(text: str = typer.Option(..., "--text")) -> None:
    _emit("device.clipboard-set", lambda: device_commands.clipboard_set(_mutation_ctx(), text))


@device_app.command("logcat")
def device_logcat(
    lines: int = typer.Option(200, "--lines"),
    clear: bool = typer.Option(False, "--clear"),
) -> None:
    _emit("device.logcat", lambda: device_commands.logcat(_ctx, lines, clear))


@device_app.command("network")
def device_network() -> None:
    _emit("device.network", lambda: device_commands.network(_ctx))


@app_app.command("current")
def app_current() -> None:
    _emit("app.current", lambda: app_commands.current(_ctx))


@app_app.command("list")
def app_list(kind: str = typer.Option("all", "--kind")) -> None:
    _emit("app.list", lambda: app_commands.list_apps(_ctx, kind))


@app_app.command("info")
def app_info(package: str = typer.Option(..., "--package")) -> None:
    _emit("app.info", lambda: app_commands.info(_ctx, package))


@app_app.command("start")
def app_start(package: str = typer.Option(..., "--package")) -> None:
    _emit("app.start", lambda: app_commands.start(_mutation_ctx(), package))


@app_app.command("launch")
def app_launch(
    package: str = typer.Option(..., "--package"),
    activity: str | None = typer.Option(None, "--activity"),
    wait: bool = typer.Option(False, "--wait"),
    stop_before_launch: bool = typer.Option(False, "--stop-before-launch"),
) -> None:
    _emit(
        "app.launch",
        lambda: app_commands.launch(_mutation_ctx(), package, activity, wait, stop_before_launch),
    )


@app_app.command("stop")
def app_stop(package: str = typer.Option(..., "--package")) -> None:
    _emit("app.stop", lambda: app_commands.stop(_mutation_ctx(), package))


@app_app.command("clear")
def app_clear(package: str = typer.Option(..., "--package")) -> None:
    _emit("app.clear", lambda: app_commands.clear(_mutation_ctx(), package))


@app_app.command("install")
def app_install(apk: str = typer.Option(..., "--apk")) -> None:
    _emit("app.install", lambda: app_commands.install(_mutation_ctx(), apk))


@app_app.command("uninstall")
def app_uninstall(package: str = typer.Option(..., "--package")) -> None:
    _emit("app.uninstall", lambda: app_commands.uninstall(_mutation_ctx(), package))


@app_app.command("stop-all")
def app_stop_all() -> None:
    _emit("app.stop-all", lambda: app_commands.stop_all(_mutation_ctx()))


@app_app.command("grant")
def app_grant(
    package: str = typer.Option(..., "--package"),
    permission: str = typer.Option(..., "--permission"),
) -> None:
    _emit("app.grant", lambda: app_commands.permission(_mutation_ctx(), package, permission, True))


@app_app.command("revoke")
def app_revoke(
    package: str = typer.Option(..., "--package"),
    permission: str = typer.Option(..., "--permission"),
) -> None:
    _emit(
        "app.revoke", lambda: app_commands.permission(_mutation_ctx(), package, permission, False)
    )


@app_app.command("intent")
def app_intent(
    package: str | None = typer.Option(None, "--package"),
    activity: str | None = typer.Option(None, "--activity"),
    action: str | None = typer.Option(None, "--action"),
    data_uri: str | None = typer.Option(None, "--data"),
    category: str | None = typer.Option(None, "--category"),
    extra: list[str] | None = typer.Option(None, "--extra"),
) -> None:
    _emit(
        "app.intent",
        lambda: app_commands.intent(
            _mutation_ctx(),
            package=package,
            activity=activity,
            action=action,
            data_uri=data_uri,
            category=category,
            extras=extra,
        ),
    )


@screen_app.command("dump")
def screen_dump_command(compact: bool = typer.Option(False, "--compact")) -> None:
    _emit("screen.dump", lambda: screen_dump.dump(_ctx, compact))


@screen_app.command("screenshot")
def screen_screenshot_command(out: str = typer.Option(..., "--out")) -> None:
    _emit("screen.screenshot", lambda: screen_screenshot.screenshot(_ctx, out))


@screen_app.command("size")
def screen_size_command() -> None:
    _emit("screen.size", lambda: screen_size.size(_ctx))


@screen_app.command("orientation")
def screen_orientation(value: str | None = typer.Option(None, "--set")) -> None:
    if value:
        _emit("screen.orientation", lambda: screen_commands.orientation_set(_mutation_ctx(), value))
    else:
        _emit("screen.orientation", lambda: screen_commands.orientation_get(_ctx))


@screen_app.command("wake")
def screen_wake() -> None:
    _emit("screen.wake", lambda: screen_commands.wake(_mutation_ctx()))


@screen_app.command("sleep")
def screen_sleep() -> None:
    _emit("screen.sleep", lambda: screen_commands.sleep(_mutation_ctx()))


@screen_app.command("unlock")
def screen_unlock() -> None:
    _emit("screen.unlock", lambda: screen_commands.unlock(_mutation_ctx()))


@screen_app.command("notification")
def screen_notification(action: str = typer.Option("open", "--action")) -> None:
    _emit("screen.notification", lambda: screen_commands.notification(_mutation_ctx(), action))


@screen_app.command("record")
def screen_record(
    out: str = typer.Option(..., "--out"),
    duration_sec: int = typer.Option(10, "--duration-sec"),
) -> None:
    _emit("screen.record", lambda: screen_commands.record(_mutation_ctx(), out, duration_sec))


def _selector_options(
    text: str | None,
    text_contains: str | None,
    resource_id: str | None,
    description: str | None,
    description_contains: str | None,
    class_name: str | None,
    xpath: str | None,
    index: int | None,
) -> Selector:
    return _selector(
        text=text,
        text_contains=text_contains,
        resource_id=resource_id,
        description=description,
        description_contains=description_contains,
        class_name=class_name,
        xpath=xpath,
        index=index,
    )


TextOpt = typer.Option(None, "--text")
TextContainsOpt = typer.Option(None, "--text-contains")
ResourceIdOpt = typer.Option(None, "--resource-id")
DescriptionOpt = typer.Option(None, "--description")
DescriptionContainsOpt = typer.Option(None, "--description-contains")
ClassNameOpt = typer.Option(None, "--class-name")
XPathOpt = typer.Option(None, "--xpath")
IndexOpt = typer.Option(None, "--index")


@element_app.command("find")
def element_find(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.find", lambda: element_query.find(_ctx, selector))


@element_app.command("exists")
def element_exists(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.exists", lambda: element_query.exists(_ctx, selector))


@element_app.command("count")
def element_count(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.count", lambda: element_query.count(_ctx, selector))


@element_app.command("bounds")
def element_bounds(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.bounds", lambda: element_query.bounds(_ctx, selector))


@element_app.command("wait")
def element_wait(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.wait", lambda: element_query.wait(_ctx, selector))


@element_app.command("click")
def element_click(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.click", lambda: element_action.click(_mutation_ctx(), selector))


@element_app.command("long-click")
def element_long_click(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.long-click", lambda: element_action.long_click(_mutation_ctx(), selector))


@element_app.command("set-text")
def element_set_text(
    value: str | None = typer.Option(None, "--value"),
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector_text = text
    if value is None:
        if text is None:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "element set-text requires --value, or legacy --text without selector text",
                {"argument": "value"},
            )
        value = text
        selector_text = None
    selector = _selector_options(
        selector_text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.set-text", lambda: element_action.set_text(_mutation_ctx(), selector, value))


@element_app.command("clear-text")
def element_clear_text(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.clear-text", lambda: element_action.clear_text(_mutation_ctx(), selector))


@element_app.command("get-text")
def element_get_text(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.get-text", lambda: element_action.get_text(_ctx, selector))


@element_app.command("swipe")
def element_swipe(
    direction: str = typer.Option(..., "--direction"),
    percent: float = typer.Option(0.6, "--percent"),
    steps: int = typer.Option(20, "--steps"),
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit(
        "element.swipe",
        lambda: element_action.swipe(_mutation_ctx(), selector, direction, percent, steps),
    )


@element_app.command("drag-to")
def element_drag_to(
    x: int = typer.Option(..., "--x"),
    y: int = typer.Option(..., "--y"),
    duration_ms: int = typer.Option(500, "--duration-ms"),
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit(
        "element.drag-to",
        lambda: element_action.drag_to(_mutation_ctx(), selector, x, y, duration_ms),
    )


@element_app.command("scroll-to")
def element_scroll_to(
    text: str | None = TextOpt,
    text_contains: str | None = TextContainsOpt,
    resource_id: str | None = ResourceIdOpt,
    description: str | None = DescriptionOpt,
    description_contains: str | None = DescriptionContainsOpt,
    class_name: str | None = ClassNameOpt,
    xpath: str | None = XPathOpt,
    index: int | None = IndexOpt,
) -> None:
    selector = _selector_options(
        text,
        text_contains,
        resource_id,
        description,
        description_contains,
        class_name,
        xpath,
        index,
    )
    _emit("element.scroll-to", lambda: element_action.scroll_to(_mutation_ctx(), selector))


@input_app.command("press")
def input_press(key: str = typer.Option(..., "--key")) -> None:
    _emit("input.press", lambda: input_commands.press(_mutation_ctx(), key))


@input_app.command("tap")
def input_tap(x: int = typer.Option(..., "--x"), y: int = typer.Option(..., "--y")) -> None:
    _emit("input.tap", lambda: input_commands.tap(_mutation_ctx(), x, y))


@input_app.command("swipe")
def input_swipe(
    from_: str = typer.Option(..., "--from"),
    to: str = typer.Option(..., "--to"),
    duration_ms: int = typer.Option(400, "--duration-ms"),
) -> None:
    from_point = _parse_point(from_, "--from")
    to_point = _parse_point(to, "--to")
    _emit(
        "input.swipe",
        lambda: input_commands.swipe(_mutation_ctx(), from_point, to_point, duration_ms),
    )


@input_app.command("text")
def input_text(value: str = typer.Option(..., "--text")) -> None:
    _emit("input.text", lambda: input_commands.text(_mutation_ctx(), value))


@input_app.command("drag")
def input_drag(
    from_: str = typer.Option(..., "--from"),
    to: str = typer.Option(..., "--to"),
    duration_ms: int = typer.Option(500, "--duration-ms"),
) -> None:
    from_point = _parse_point(from_, "--from")
    to_point = _parse_point(to, "--to")
    _emit(
        "input.drag",
        lambda: input_commands.drag(_mutation_ctx(), from_point, to_point, duration_ms),
    )


@input_app.command("keyevent")
def input_keyevent(code: int = typer.Option(..., "--code")) -> None:
    _emit("input.keyevent", lambda: input_commands.keyevent(_mutation_ctx(), code))


@toast_app.command("get")
def toast_get() -> None:
    def _run() -> dict[str, Any]:
        _require_explicit_timeout("toast.get")
        return toast_commands.get(_ctx)

    _emit("toast.get", _run)


@toast_app.command("reset")
def toast_reset() -> None:
    _emit("toast.reset", lambda: toast_commands.reset(_ctx))


@pi_app.command("schema")
def pi_schema() -> None:
    _emit("pi.schema", tool_schema)


@watcher_app.command("add")
def watcher_add(
    name: str = typer.Option(..., "--name"),
    text: str | None = typer.Option(None, "--text"),
    resource_id: str | None = typer.Option(None, "--resource-id"),
    click_text: str | None = typer.Option(None, "--click-text"),
) -> None:
    _emit(
        "watcher.add",
        lambda: watcher_commands.add(_ctx, name, text, resource_id, click_text),
    )


@watcher_app.command("run")
def watcher_run() -> None:
    _emit("watcher.run", lambda: watcher_commands.run(_ctx))


@watcher_app.command("reset")
def watcher_reset() -> None:
    _emit("watcher.reset", lambda: watcher_commands.reset(_ctx))


@session_app.command("info")
def session_info() -> None:
    _emit("session.info", lambda: session_commands.info(_ctx))


@session_app.command("sidecar-start")
def session_sidecar_start() -> None:
    _emit("session.sidecar-start", lambda: session_commands.sidecar_start(_ctx))


def main(argv: list[str] | None = None) -> None:
    global _ctx, _exit_code
    _exit_code = 0
    raw_args = list(sys.argv[1:] if argv is None else argv)
    try:
        args, parsed = _extract_global_args(raw_args)
    except BaseException as exc:
        parsed = CommandContext.start()
        error = normalize_exception(exc)
        result = CommandResult.failed(
            command="cli",
            serial=parsed.serial,
            duration_ms=parsed.elapsed_ms(),
            error=error,
        )
        print(result.to_json())
        raise SystemExit(exit_code_for(error.code))
    _ctx = parsed
    try:
        app(args=args, prog_name="u2cli", standalone_mode=False)
    except click.exceptions.Exit as exc:
        raise SystemExit(exc.exit_code) from exc
    except click.ClickException as exc:
        error = U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            exc.format_message(),
            {"argumentError": type(exc).__name__},
        )
        result = CommandResult.failed(
            command="cli",
            serial=_ctx.serial,
            duration_ms=_ctx.elapsed_ms(),
            error=error,
        )
        print(result.to_json())
        raise SystemExit(exit_code_for(error.code))
    except BaseException as exc:
        error = normalize_exception(exc)
        result = CommandResult.failed(
            command="cli",
            serial=_ctx.serial,
            duration_ms=_ctx.elapsed_ms(),
            error=error,
        )
        print(result.to_json())
        raise SystemExit(exit_code_for(error.code))
    raise SystemExit(_exit_code)
