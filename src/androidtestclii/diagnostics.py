from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from androidtestclii.context import CommandContext
from androidtestclii.device.connect import connect_device
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.session.store import read_session, update_session
from androidtestclii.timeouts import run_with_timeout


ANDROID_TRACE_CATEGORIES = ["gfx", "input", "view", "wm", "am", "sched", "freq", "idle", "disk"]
DEFAULT_TRACE_PATH = "artifacts/trace.html"
DEFAULT_PERF_PATH = "artifacts/perf.json"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
URL_RE = re.compile(r"https?://[^\s\"'<>),]+")
STATUS_RE = re.compile(r"(?:status[=:]\s*|<--\s*)([1-5][0-9]{2})\b", re.IGNORECASE)
DURATION_RE = re.compile(r"(?:duration[=:]\s*|\()([0-9]+)\s*ms\)?", re.IGNORECASE)


def trace_start(ctx: CommandContext, path: str | None = None) -> dict[str, Any]:
    target = str(Path(path or DEFAULT_TRACE_PATH))
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> dict[str, Any]:
        command = "atrace --async_start -b 16384 " + " ".join(ANDROID_TRACE_CATEGORIES)
        output = _shell_output(device.shell(command))
        return {
            "trace": "started",
            "available": True,
            "method": "android-atrace",
            "path": target,
            "categories": ANDROID_TRACE_CATEGORIES,
            "command": ["atrace", "--async_start", "-b", "16384", *ANDROID_TRACE_CATEGORIES],
            "output": output,
        }

    data = run_with_timeout(_run, ctx.timeout_ms)
    state = read_session()
    temporary = dict(state.temporary_automation)
    temporary["traceCapture"] = {
        "path": target,
        "method": "android-atrace",
        "categories": ANDROID_TRACE_CATEGORIES,
        "startedAt": time.time(),
    }
    update_session(serial=ctx.serial, timeout_ms=ctx.timeout_ms, temporary_automation=temporary)
    return data


def trace_stop(ctx: CommandContext, path: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = read_session()
    capture = state.temporary_automation.get("traceCapture")
    target = Path(path or (capture.get("path") if isinstance(capture, dict) else None) or DEFAULT_TRACE_PATH)
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        output = _shell_output(device.shell("atrace --async_stop -z"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        temporary = dict(state.temporary_automation)
        temporary.pop("traceCapture", None)
        update_session(serial=ctx.serial, timeout_ms=ctx.timeout_ms, temporary_automation=temporary)
        data = {
            "trace": "stopped",
            "available": True,
            "method": "android-atrace",
            "path": str(target),
            "bytes": target.stat().st_size,
        }
        artifacts = [{"type": "trace", "path": str(target), "description": "device trace"}]
        return data, artifacts

    return run_with_timeout(_run, ctx.timeout_ms)


def perf_collect(
    ctx: CommandContext,
    app_id: str | None = None,
    out: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    device = connect_device(ctx.serial, ctx.timeout_ms)

    def _run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        meminfo = _shell_output(device.shell("cat /proc/meminfo"))
        stat = _shell_output(device.shell("cat /proc/stat"))
        ps = _shell_output(device.shell("ps -A"))
        data = {
            "available": True,
            "method": "android-procfs",
            "appId": app_id or "foreground",
            "memory": parse_meminfo(meminfo),
            "cpu": parse_proc_stat(stat),
            "processes": parse_ps(ps, app_id),
            "rawLineCount": len(meminfo.splitlines()) + len(stat.splitlines()) + len(ps.splitlines()),
        }
        artifacts: list[dict[str, Any]] = []
        if out:
            import json

            target = Path(out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            artifacts.append({"type": "perf", "path": str(target), "description": "procfs perf snapshot"})
            data["path"] = str(target)
            data["bytes"] = target.stat().st_size
        return data, artifacts

    return run_with_timeout(_run, ctx.timeout_ms)


def network_summary(
    ctx: CommandContext,
    include: str = "summary",
    limit: int = 50,
    log_path: str | None = None,
) -> dict[str, Any]:
    if include not in {"summary", "all"}:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--include must be summary or all",
            {"argument": "include", "value": include},
        )
    if limit <= 0 or limit > 1000:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "--limit must be between 1 and 1000",
            {"argument": "limit", "value": limit},
        )

    def _read() -> dict[str, Any]:
        if log_path:
            raw = Path(log_path).read_text(encoding="utf-8")
            source = "logs-artifact"
        else:
            device = connect_device(ctx.serial, ctx.timeout_ms)
            raw = _shell_output(device.shell("logcat -d -v brief"))
            source = "android-logcat"
        traffic = format_network_traffic(parse_network_log_lines(raw, limit=limit), include)
        return {
            "action": "summary",
            "available": True,
            "source": source,
            "include": include,
            "limit": limit,
            "count": len(traffic),
            "traffic": traffic,
            "note": "Parsed HTTP and URL clues visible in logcat; this is not a full packet capture.",
        }

    return run_with_timeout(_read, ctx.timeout_ms)


def parse_meminfo(raw: str) -> dict[str, int]:
    fields: dict[str, int] = {}
    key_map = {
        "MemTotal": "totalKb",
        "MemFree": "freeKb",
        "MemAvailable": "availableKb",
        "Buffers": "buffersKb",
        "Cached": "cachedKb",
        "SwapTotal": "swapTotalKb",
        "SwapFree": "swapFreeKb",
    }
    for line in raw.splitlines():
        parts = line.replace(":", "").split()
        if len(parts) >= 2 and parts[0] in key_map:
            fields[key_map[parts[0]]] = _safe_int(parts[1])
    return fields


def parse_proc_stat(raw: str) -> dict[str, Any]:
    for line in raw.splitlines():
        if line.startswith("cpu "):
            values = [_safe_int(part) for part in line.split()[1:]]
            total = sum(values)
            idle = values[3] if len(values) > 3 else 0
            return {"totalJiffies": total, "idleJiffies": idle, "busyJiffies": max(0, total - idle)}
    return {}


def parse_ps(raw: str, app_id: str | None = None) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    lines = raw.splitlines()
    for line in lines[1:] if lines and "PID" in lines[0] else lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[-1]
        if app_id and app_id not in {"foreground", name} and app_id not in name:
            continue
        pid_index = 1 if not parts[0].isdigit() and len(parts) > 1 else 0
        processes.append({"pid": _safe_int(parts[pid_index]), "name": name, "raw": line[-1000:]})
        if len(processes) >= 20:
            break
    return processes


def parse_network_log_lines(raw: str, *, limit: int) -> list[dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    traffic: list[dict[str, Any]] = []
    for line in raw.splitlines():
        url_match = URL_RE.search(line)
        if not url_match:
            continue
        url = url_match.group(0)
        method = _extract_http_method(line)
        status = _extract_int(STATUS_RE.search(line))
        duration_ms = _extract_int(DURATION_RE.search(line))
        entry = {
            "method": method,
            "url": url,
            "status": status,
            "durationMs": duration_ms,
            "raw": line[-1000:],
        }
        if status is None and method:
            requests[url] = entry
            continue
        if status is not None and not method and url in requests:
            entry["method"] = requests[url].get("method")
        traffic.append(entry)
        if len(traffic) >= limit:
            break
    return traffic


def format_network_traffic(traffic: list[dict[str, Any]], include: str) -> list[dict[str, Any]]:
    if include != "summary":
        return traffic
    return [{key: value for key, value in entry.items() if key != "raw"} for entry in traffic]


def _extract_http_method(line: str) -> str | None:
    for token in re.split(r"[^A-Z]+", line.upper()):
        if token in HTTP_METHODS:
            return token
    return None


def _extract_int(match: re.Match[str] | None) -> int | None:
    if not match:
        return None
    return _safe_int(match.group(1))


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _shell_output(result: Any) -> str:
    return str(getattr(result, "output", result)).strip()
