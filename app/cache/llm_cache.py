"""LLM result cache — Phase 4 R4.

Refer F2C.5 (LUAT_2C_infra) — cache LLM intent/STT/address/slogan.

In-memory TTL cache. Phase 5 migrate Redis cho multi-instance prod.

Used by:
- Intent classifier Layer 2 — cache (message + stage + slot) hash → Intent
- Address parser Layer 2 LLM (Phase 4+) — cache (raw_address) hash → parsed
- Slogan gen — cache (dealer_name + main_product) → list[str]

API:
- llm_cache_get(key) → value | None
- llm_cache_set(key, value, ttl_s)
- llm_cache_clear()
"""
from __future__ import annotations

import hashlib
import logging
import time
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


# {key: (value, expires_at_monotonic)}
_cache: dict[str, tuple[Any, float]] = {}
_lock = Lock()

# Cleanup threshold
_MAX_ENTRIES = 10000


def make_key(*parts: Any) -> str:
    """Build cache key từ multiple parts (hash để fix length)."""
    raw = "|".join(str(p) for p in parts if p is not None)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def llm_cache_get(key: str) -> Any | None:
    """Get value if not expired, else None."""
    if not key:
        return None
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at < now:
            del _cache[key]
            return None
        return value


def llm_cache_set(key: str, value: Any, ttl_s: int = 3600) -> None:
    """Set value với TTL.

    Args:
        key: Cache key
        value: Bất kỳ JSON-serializable value
        ttl_s: TTL seconds (default 1h)
    """
    if not key:
        return
    now = time.monotonic()
    with _lock:
        # Simple eviction nếu quá MAX
        if len(_cache) >= _MAX_ENTRIES:
            # Evict 10% oldest
            sorted_keys = sorted(_cache.keys(), key=lambda k: _cache[k][1])
            for k in sorted_keys[: _MAX_ENTRIES // 10]:
                del _cache[k]
        _cache[key] = (value, now + ttl_s)


def llm_cache_clear() -> None:
    """Clear all (test helper)."""
    with _lock:
        _cache.clear()


def llm_cache_size() -> int:
    """Số entry hiện tại (debug)."""
    return len(_cache)
