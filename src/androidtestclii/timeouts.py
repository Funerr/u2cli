from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

from .errors import ErrorCode, U2CliError

T = TypeVar("T")


def run_with_timeout(fn: Callable[[], T], timeout_ms: int) -> T:
    if timeout_ms <= 0:
        raise U2CliError(ErrorCode.INVALID_ARGUMENT, "timeout-ms must be greater than 0")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout_ms / 1000)
    except FutureTimeoutError as exc:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise U2CliError(ErrorCode.ACTION_TIMEOUT, "Action timed out") from exc
    finally:
        if future.done():
            executor.shutdown(wait=True)
