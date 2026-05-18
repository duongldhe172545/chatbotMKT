"""Retry helper với exponential backoff. Refer F2C.4 timeout + retry policy.

Phase 1: sync retry (F2C.4 LLM = 30s timeout, retry 2 lần với delay 1s/2s).
"""
from __future__ import annotations

import time
from typing import Callable, Optional, TypeVar


T = TypeVar("T")


class RetryExhaustedError(Exception):
    """Raised khi hết retry attempts vẫn fail."""


def call_with_retry(
    func: Callable[[], T],
    max_attempts: int = 3,
    base_delay_s: float = 1.0,
    timeout_s: float = 30.0,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call func với exponential backoff retry. Refer F2C.4.

    Args:
        func: Callable không args (dùng functools.partial nếu cần bind args).
        max_attempts: Tổng số attempt (1 = no retry, 3 = original + 2 retry).
        base_delay_s: Delay đầu (sẽ × 2 mỗi lần).
        timeout_s: Total timeout — raise TimeoutError nếu vượt.
        retryable_exceptions: Tuple exception types được retry. Exception
            ngoài tuple → raise ngay (không retry, vd ValueError, TypeError).

    Returns:
        Result của func.

    Raises:
        RetryExhaustedError: hết retry vẫn fail (last exception attached qua __cause__).
        TimeoutError: vượt total timeout_s.
        Original exception type: nếu exception KHÔNG trong retryable_exceptions.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts >= 1, got {max_attempts}")

    start = time.monotonic()
    last_error: Optional[BaseException] = None

    for attempt in range(max_attempts):
        # Check timeout TRƯỚC mỗi attempt
        elapsed = time.monotonic() - start
        if elapsed >= timeout_s:
            raise TimeoutError(
                f"Total timeout {timeout_s}s exceeded after {attempt} attempts"
            )

        try:
            return func()
        except retryable_exceptions as e:
            last_error = e
            # Nếu còn attempt → sleep + continue
            if attempt + 1 < max_attempts:
                delay = base_delay_s * (2 ** attempt)
                remaining = timeout_s - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError(
                        f"Total timeout {timeout_s}s exceeded during backoff"
                    )
                time.sleep(min(delay, remaining))

    # Hết attempt
    raise RetryExhaustedError(
        f"Hết {max_attempts} attempt. Last error: {last_error}"
    ) from last_error
