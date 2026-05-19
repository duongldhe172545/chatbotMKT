"""Rate limit guard — Phase 4 R4.

Refer F2C.2 (LUAT_2C_infra) — spam guard 4 layer.

In-memory token bucket per IP/session. Phase 5 sẽ migrate Redis.

API:
- check_rate_limit(key, max_per_minute) → (allowed: bool, retry_after_s)
- reset_for_key(key) — test helper
"""
from __future__ import annotations

import logging
import time
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


# Sliding window: {key: deque[timestamp]}
_buckets: dict[str, deque[float]] = {}
_lock = Lock()


def check_rate_limit(
    key: str,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> tuple[bool, float]:
    """Sliding window rate limit.

    Args:
        key: Identifier (vd "ip:1.2.3.4" hoặc "session:abc")
        max_requests: Max request trong window
        window_seconds: Window size (default 60s)

    Returns:
        (allowed, retry_after_s):
        - allowed=True nếu request OK
        - retry_after_s = seconds đến request tiếp theo allowed (0 nếu OK)
    """
    if not key:
        return (True, 0.0)

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = _buckets.setdefault(key, deque())
        # Prune old timestamps
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            # Compute retry-after: earliest entry + window
            retry_after = (bucket[0] + window_seconds) - now
            return (False, max(0.0, retry_after))

        bucket.append(now)
        return (True, 0.0)


def reset_for_key(key: str) -> None:
    """Clear bucket for 1 key (test helper)."""
    with _lock:
        _buckets.pop(key, None)


def reset_all() -> None:
    """Clear tất cả buckets (test helper)."""
    with _lock:
        _buckets.clear()


def get_bucket_size(key: str) -> int:
    """Số request trong window hiện tại (debug)."""
    with _lock:
        return len(_buckets.get(key, []))
