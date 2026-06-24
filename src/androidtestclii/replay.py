from __future__ import annotations

import glob
import io
import json
import os
import shlex
import time
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from androidtestclii.branding import COMMAND_ALIAS, COMMAND_NAME, DISPLAY_NAME, LEGACY_COMMAND_NAMES
from androidtestclii.context import CommandContext
from androidtestclii.errors import ErrorCode, U2CliError, exit_code_for, normalize_exception
from androidtestclii.result import CommandResult
from androidtestclii.screen import visual as screen_visual
from androidtestclii.session.store import read_session


CommandRunner = Callable[[list[str]], tuple[int, dict[str, Any]]]


@dataclass
class ReplayScript:
    path: Path
    steps: list[list[str]]
    context: dict[str, str] = field(default_factory=dict)
    visual_expectations: list[dict[str, str]] = field(default_factory=list)


def replay(
    ctx: CommandContext,
    path: str,
    *,
    replay_update: bool = False,
    replay_env: list[str] | None = None,
    runner: CommandRunner | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    script_path = Path(path)
    if not script_path.exists():
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "replay script does not exist", {"path": path})
    parsed = parse_replay_script(script_path, ctx, replay_env or [])
    command_runner = runner or run_cli_command
    results = run_replay_steps(parsed.steps, parsed.context, command_runner)
    healed_steps: list[list[str]] = []
    for index, result in enumerate(results):
        healed = result.get("healedStep")
        healed_steps.append([str(item) for item in healed] if isinstance(healed, list) else parsed.steps[index])
    data: dict[str, Any] = {
        "path": str(script_path),
        "replayed": len(results),
        "healed": sum(1 for result in results if result.get("healed")),
        "updated": False,
        "context": parsed.context,
        "results": results,
    }
    artifacts: list[dict[str, Any]] = []
    if parsed.visual_expectations:
        visual_checks, visual_artifacts = run_replay_visual_checks(ctx, script_path, parsed.visual_expectations)
        data["visualChecks"] = visual_checks
        artifacts.extend(visual_artifacts)
    if replay_update:
        data.update(update_replay_script(script_path, healed_steps, parsed.context))
    return data, artifacts


def test(
    ctx: CommandContext,
    paths: list[str],
    *,
    report_junit: str | None = None,
    fail_fast: bool = False,
    replay_update: bool = False,
    replay_env: list[str] | None = None,
    runner: CommandRunner | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expanded_paths = expand_replay_test_paths(paths)
    results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    failed = 0
    for path in expanded_paths:
        started = time.perf_counter()
        try:
            data, replay_artifacts = replay(
                ctx,
                path,
                replay_update=replay_update,
                replay_env=replay_env,
                runner=runner,
            )
            artifacts.extend(replay_artifacts)
            replay_error = replay_test_error(data)
            ok = replay_error is None
            if not ok:
                failed += 1
            results.append(
                {
                    "path": path,
                    "ok": ok,
                    **data,
                    "durationMs": int((time.perf_counter() - started) * 1000),
                    **({"error": replay_error} if replay_error else {}),
                }
            )
        except BaseException as exc:
            normalized = normalize_exception(exc)
            failed += 1
            results.append(
                {
                    "path": path,
                    "ok": False,
                    "durationMs": int((time.perf_counter() - started) * 1000),
                    "error": {
                        "code": normalized.code.value,
                        "message": normalized.message,
                        **({"details": normalized.details} if normalized.details else {}),
                    },
                }
            )
        if results[-1].get("ok") is False and fail_fast:
            break
    total = len(results)
    data = {
        "paths": expanded_paths,
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "results": results,
    }
    if report_junit:
        artifact = write_junit_report(report_junit, results)
        artifacts.append(artifact)
        data["reportJunit"] = artifact["path"]
    return data, artifacts


def parse_replay_script(script_path: Path, ctx: CommandContext, replay_env: list[str]) -> ReplayScript:
    context: dict[str, str] = {}
    env: dict[str, str] = {}
    visual_expectations: list[dict[str, str]] = []
    raw_steps: list[tuple[int, list[str]]] = []
    script = script_path.read_text(encoding="utf-8")
    for line_number, raw in enumerate(script.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            visual = parse_replay_visual_expectation(stripped[1:].strip(), line_number=line_number)
            if visual is not None:
                visual_expectations.append(visual)
            continue
        try:
            tokens = shlex.split(stripped)
        except ValueError as exc:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "replay script line could not be parsed",
                {"path": str(script_path), "line": line_number, "error": str(exc)},
            ) from exc
        if not tokens:
            continue
        if tokens[0] == "context":
            context.update(parse_key_value_tokens(tokens[1:], line_number=line_number))
            continue
        if tokens[0] == "env":
            env.update(parse_key_value_tokens(tokens[1:], line_number=line_number))
            continue
        raw_steps.append((line_number, normalize_replay_step(tokens)))
    for entry in replay_env:
        if "=" not in entry:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "--replay-env entries must be KEY=VALUE",
                {"entry": entry},
            )
        key, value = entry.split("=", 1)
        env[key] = value
    if ctx.serial and not context.get("serial") and not context.get("device"):
        context["serial"] = ctx.serial
    if (
        ctx.timeout_ms_explicit
        and ctx.timeout_ms
        and not context.get("timeout")
        and not context.get("timeoutMs")
    ):
        context["timeoutMs"] = str(ctx.timeout_ms)
    platform = context.get("platform")
    if platform and platform != "android":
        raise U2CliError(
            ErrorCode.PLATFORM_UNSUPPORTED,
            f"replay currently supports {DISPLAY_NAME} Android context only",
            {
                "platform": platform,
                "unsupported": True,
                "recoveryHint": f"Use {COMMAND_NAME} with an Android device or add a dedicated platform adapter.",
            },
        )
    steps: list[list[str]] = []
    for line_number, tokens in raw_steps:
        try:
            steps.append([resolve_replay_vars(token, env) for token in tokens])
        except KeyError as exc:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "replay script variable was not provided",
                {"path": str(script_path), "line": line_number, "variable": str(exc).strip("'")},
            ) from exc
    return ReplayScript(
        path=script_path,
        steps=steps,
        context=context,
        visual_expectations=visual_expectations,
    )


def parse_replay_visual_expectation(
    comment: str,
    *,
    line_number: int,
) -> dict[str, str] | None:
    if not comment.startswith("expect-screenshot"):
        return None
    try:
        tokens = shlex.split(comment)
    except ValueError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "expect-screenshot comment could not be parsed",
            {"line": line_number, "error": str(exc)},
        ) from exc
    if len(tokens) < 2:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "expect-screenshot requires a baseline PNG path",
            {"line": line_number},
        )
    visual = {"baseline": tokens[1], "threshold": "0", "line": str(line_number)}
    for token in tokens[2:]:
        if "=" in token:
            key, value = token.split("=", 1)
            if key in {"baseline", "threshold", "out"}:
                visual[key] = value
    return visual


def parse_key_value_tokens(tokens: list[str], *, line_number: int) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "replay context/env entries must be KEY=VALUE",
                {"line": line_number, "entry": token},
            )
        key, value = token.split("=", 1)
        if not key:
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "replay context/env key must not be empty",
                {"line": line_number, "entry": token},
            )
        values[key] = value
    return values


def normalize_replay_step(tokens: list[str]) -> list[str]:
    if tokens and tokens[0] in {COMMAND_NAME, COMMAND_ALIAS, *LEGACY_COMMAND_NAMES}:
        return tokens[1:]
    return tokens


def run_replay_steps(
    steps: list[list[str]],
    context: dict[str, str],
    runner: CommandRunner,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        argv = context_flags(context) + step
        exit_code, payload = runner(argv)
        healed_step = None
        if not payload.get("success"):
            healed = heal_replay_step(step, payload)
            if healed is None:
                raise replay_step_error(index, step, payload, exit_code)
            healed_step = healed
            exit_code, payload = runner(context_flags(context) + healed)
            if not payload.get("success"):
                raise replay_step_error(index, healed, payload, exit_code)
        results.append(
            {
                "index": index,
                "command": str(payload.get("command") or (healed_step or step)[0]),
                "ok": True,
                "healed": healed_step is not None,
                "healedStep": healed_step,
                "data": payload.get("data", {}),
                "artifacts": payload.get("artifacts", []),
                "durationMs": payload.get("durationMs"),
            }
        )
    return results


def test_failed_error(data: dict[str, Any], artifacts: list[dict[str, Any]]) -> U2CliError:
    return U2CliError(
        ErrorCode.BATCH_STEP_FAILED,
        "test replay failed",
        {**data, "artifacts": artifacts},
    )


def run_replay_visual_checks(
    ctx: CommandContext,
    script_path: Path,
    expectations: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from androidtestclii.screen import screenshot as screen_screenshot

    current_path = script_path.with_name(f"{script_path.stem}-current.png")
    screenshot_data, _ = screen_screenshot.screenshot(ctx, str(current_path))
    raw_current = screenshot_data.get("path")
    if not isinstance(raw_current, str) or not raw_current:
        raise U2CliError(
            ErrorCode.SCREENSHOT_FAILED,
            "replay visual check could not capture a screenshot path",
            {"failureStage": "replay-visual"},
        )
    visual_checks: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for index, expectation in enumerate(expectations, start=1):
        baseline = resolve_replay_path(script_path, expectation["baseline"])
        out = expectation.get("out")
        out_path = resolve_replay_path(script_path, out) if out else script_path.with_name(f"{script_path.stem}-diff.png")
        diff, diff_artifacts = screen_visual.diff_screenshot(
            baseline=str(baseline),
            current=raw_current,
            threshold=expectation.get("threshold"),
            out=str(out_path),
        )
        visual_checks.append(
            {
                "index": index,
                "line": int(expectation["line"]),
                "baseline": str(baseline),
                "current": raw_current,
                "diff": str(out_path),
                "passed": diff["passed"],
                "diffRatio": diff["diffRatio"],
                "thresholdRatio": diff["thresholdRatio"],
                "changedPixels": diff["changedPixels"],
            }
        )
        for artifact in diff_artifacts:
            artifacts.append(
                {
                    **artifact,
                    "description": "replay screenshot diff",
                }
            )
    return visual_checks, artifacts


def replay_test_error(data: dict[str, Any]) -> dict[str, Any] | None:
    visual_checks = data.get("visualChecks")
    if not isinstance(visual_checks, list):
        return None
    failed_checks = [
        check
        for check in visual_checks
        if isinstance(check, dict) and check.get("passed") is False
    ]
    if not failed_checks:
        return None
    return {
        "code": "REPLAY_VISUAL_ASSERTION_FAILED",
        "message": "replay visual assertion failed",
        "details": {"failedVisualChecks": failed_checks},
    }


def write_junit_report(report_path: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    target = Path(report_path)
    if target.exists() and target.is_dir():
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "JUnit report path must not be a directory",
            {"path": str(target)},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    failures = sum(1 for result in results if not result.get("ok"))
    duration_ms = sum(int(result.get("durationMs") or 0) for result in results)
    suite = ET.Element(
        "testsuite",
        {
            "name": "androidtestclii.ad",
            "tests": str(len(results)),
            "failures": str(failures),
            "errors": "0",
            "skipped": "0",
            "time": junit_seconds(duration_ms),
        },
    )
    for result in results:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "androidtestclii.replay",
                "name": str(result.get("path") or "unknown"),
                "file": str(result.get("path") or ""),
                "time": junit_seconds(int(result.get("durationMs") or 0)),
            },
        )
        if not result.get("ok"):
            raw_error = result.get("error")
            error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
            failure = ET.SubElement(
                case,
                "failure",
                {
                    "message": str(error.get("message") or "replay test failed"),
                    "type": str(error.get("code") or "REPLAY_TEST_FAILED"),
                },
            )
            failure.text = json.dumps(
                {"path": result.get("path"), "error": error},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
    ET.indent(suite, space="  ")
    ET.ElementTree(suite).write(target, encoding="utf-8", xml_declaration=True)
    return {"type": "junit", "path": str(target), "description": ".ad test suite JUnit XML"}


def expand_replay_test_paths(patterns: list[str]) -> list[str]:
    expanded: list[str] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            expanded.extend(matches)
        else:
            expanded.append(pattern)
    return expanded


def update_replay_script(
    path: Path,
    steps: list[list[str]],
    context: dict[str, str],
) -> dict[str, Any]:
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    lines = [f"# updated by {DISPLAY_NAME} replay --replay-update"]
    context_items = [
        (key, context[key])
        for key in ("platform", "serial", "device", "timeout", "timeoutMs")
        if context.get(key)
    ]
    if context_items:
        lines.append(
            "context "
            + " ".join(f"{key}={quote_replay_token(value)}" for key, value in context_items)
        )
    lines.extend(" ".join(quote_replay_token(token) for token in step) for step in steps)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "updated": True,
        "normalizedSteps": len(steps),
        "backupPath": str(backup),
        "updateMethod": "normalize-script",
    }


def heal_replay_step(step: list[str], payload: dict[str, Any]) -> list[str] | None:
    error = payload.get("error")
    error_code = error.get("code") if isinstance(error, dict) else None
    if error_code not in {"ELEMENT_NOT_FOUND", "SNAPSHOT_REF_NOT_FOUND"}:
        return None
    if not step:
        return None
    command = step[0]
    if command not in {"click", "press", "longpress", "fill", "get", "find", "is"}:
        return None
    target_index = 1
    if command == "get" and len(step) > 2:
        target_index = 2
    if len(step) <= target_index:
        return None
    healed_ref = replay_ref_for_target(step[target_index])
    if healed_ref is None:
        return None
    healed = list(step)
    healed[target_index] = healed_ref
    return healed


def replay_ref_for_target(target: str) -> str | None:
    wanted = target_value_for_replay_heal(target)
    if not wanted:
        return None
    session = read_session()
    last = session.last_snapshot
    if last is None:
        return None
    for ref, entry in last.ref_map.items():
        public = entry.public_dict()
        candidates = [
            public.get("text"),
            public.get("description"),
            public.get("resourceId"),
            public.get("className"),
        ]
        selector = public.get("selector")
        if isinstance(selector, dict):
            candidates.extend(
                selector.get(key)
                for key in [
                    "text",
                    "description",
                    "resourceId",
                    "resource_id",
                    "className",
                    "class_name",
                ]
            )
        if any(isinstance(candidate, str) and candidate == wanted for candidate in candidates):
            return ref if ref.startswith("@") else f"@{ref}"
    return None


def target_value_for_replay_heal(target: str) -> str | None:
    text = target.strip()
    if not text or text.startswith("@"):
        return None
    if "=" in text:
        _, value = text.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return text


def replay_step_error(
    index: int,
    step: list[str],
    payload: dict[str, Any],
    exit_code: int,
) -> U2CliError:
    raw_error = payload.get("error")
    error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
    code = ErrorCode.BATCH_STEP_FAILED
    return U2CliError(
        code,
        str(error.get("message") or "replay step failed"),
        {
            "index": index,
            "step": step,
            "exitCode": exit_code,
            "error": error,
            "payload": payload,
        },
    )


def run_cli_command(argv: list[str]) -> tuple[int, dict[str, Any]]:
    from androidtestclii import cli as cli_module

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            cli_module.main(argv)
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    output = stdout.getvalue().strip()
    if not output:
        payload = CommandResult.failed(
            command=argv[0] if argv else "replay.step",
            serial=None,
            duration_ms=0,
            error=U2CliError(
                ErrorCode.INTERNAL_ERROR,
                "replay step did not emit JSON",
                {"argv": argv, "stderr": stderr.getvalue()},
            ),
        ).to_dict()
        return 2, payload
    try:
        payload = json.loads(output.splitlines()[-1])
    except json.JSONDecodeError as exc:
        payload = CommandResult.failed(
            command=argv[0] if argv else "replay.step",
            serial=None,
            duration_ms=0,
            error=U2CliError(
                ErrorCode.INTERNAL_ERROR,
                "replay step emitted invalid JSON",
                {"argv": argv, "stdout": output, "stderr": stderr.getvalue(), "error": str(exc)},
            ),
        ).to_dict()
        return 2, payload
    return code, payload


def emit_test_result(
    ctx: CommandContext,
    command: str,
    runner: Callable[[], tuple[dict[str, Any], list[dict[str, Any]]]],
) -> int:
    started = time.perf_counter()
    exit_code = 0
    try:
        data, artifacts = runner()
        if int(data.get("failed") or 0) > 0:
            raise test_failed_error(data, artifacts)
        result = CommandResult.ok(
            command=command,
            serial=ctx.serial,
            duration_ms=int((time.perf_counter() - started) * 1000),
            data=data,
            artifacts=artifacts,
        )
        payload = result.to_json()
    except U2CliError as exc:
        if exc.code == ErrorCode.BATCH_STEP_FAILED:
            artifacts = exc.details.get("artifacts", [])
            data = {key: value for key, value in exc.details.items() if key != "artifacts"}
            result = CommandResult.ok(
                command=command,
                serial=ctx.serial,
                duration_ms=int((time.perf_counter() - started) * 1000),
                data=data,
                artifacts=artifacts if isinstance(artifacts, list) else [],
            )
            payload = result.to_json()
            exit_code = 1
        else:
            result = CommandResult.failed(
                command=command,
                serial=ctx.serial,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=exc,
            )
            payload = result.to_json()
            exit_code = exit_code_for(exc.code)
    print(payload)
    return exit_code


def context_flags(context: dict[str, str]) -> list[str]:
    flags: list[str] = []
    serial = context.get("serial") or context.get("device")
    if serial:
        flags.extend(["--serial", serial])
    timeout = context.get("timeoutMs") or context.get("timeout")
    if timeout:
        flags.extend(["--timeout-ms", timeout])
    return flags


def resolve_replay_vars(token: str, env: dict[str, str]) -> str:
    result = token
    for _ in range(20):
        start = result.find("${")
        if start < 0:
            return result
        end = result.find("}", start + 2)
        if end < 0:
            return result
        key = result[start + 2:end]
        value = env.get(key, os.environ.get(key))
        if value is None:
            raise KeyError(key)
        result = result[:start] + value + result[end + 1:]
    return result


def quote_replay_token(value: Any) -> str:
    text = str(value)
    if text == "":
        return '""'
    if all(not char.isspace() and char not in {'"', "'", "\\"} for char in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def resolve_replay_path(script_path: Path, value: str | None) -> Path:
    if not value:
        return script_path.parent
    path = Path(value)
    return path if path.is_absolute() else script_path.parent / path


def junit_seconds(duration_ms: int) -> str:
    return f"{max(duration_ms, 0) / 1000:.3f}"
