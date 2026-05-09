"""Concurrency utilities — per-session lock + idempotency cache.

Triết lý:
- IN-MEMORY thuần Python — 0 cost, 0 latency thêm cho khác session
- Per-session lock: 2 request CÙNG session_id sẽ serialize. Khác session
  → song song, không block nhau.
- Idempotency cache: TTL 5 phút, max 1000 entry. Lookup O(1).

Khi nào cần restart cleanup:
- Lock dict tích lũy theo session mới. Mỗi Lock ~16 bytes. 10K session/năm
  ≈ 160KB → bỏ qua. Restart server là reset.
- Idempotency cache có maxsize → tự evict LRU khi full.

Khi scale (>1 worker / multi-process): nâng cấp sang Redis. Hiện tại
single-worker uvicorn (Railway free tier) → in-memory đủ.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

# ============================================================
# PER-SESSION LOCK
# ============================================================
# Mục đích: chống race condition khi 2 request cùng session_id đến đồng
# thời (vd dealer gửi 2 lần do mạng yếu, hoặc multi-tab cùng session).
# Lock dict global, key = session_id, value = threading.Lock instance.

_session_locks: dict[str, threading.Lock] = {}
_locks_dict_lock = threading.Lock()  # bảo vệ thao tác trên _session_locks


def get_session_lock(session_id: str) -> threading.Lock:
    """Lấy (hoặc tạo mới) Lock cho session_id.

    Caller dùng `with lock:` để serialize logic xử request. Khác session
    KHÔNG block nhau (vì mỗi session 1 Lock riêng).
    """
    # Fast path: lock đã tồn tại → trả luôn (lookup atomic trong CPython)
    lock = _session_locks.get(session_id)
    if lock is not None:
        return lock
    # Slow path: cần tạo mới — bảo vệ bằng dict-level lock
    with _locks_dict_lock:
        # Re-check sau khi acquire (có thể request khác đã tạo trong lúc đợi)
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


# ============================================================
# IDEMPOTENCY CACHE
# ============================================================
# Mục đích: chống double-submit từ network retry / multi-tab. Frontend
# tạo msg_id (UUID) cho mỗi gửi. Backend cache `{msg_id: response}` 5 phút.
# Duplicate request → trả cached response, KHÔNG gọi LLM.

_IDEM_TTL_SECONDS = 300  # 5 phút
_IDEM_MAX_ENTRIES = 1000

# OrderedDict để tự LRU evict. Value = (response, expire_at_timestamp).
_idem_cache: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
_idem_lock = threading.Lock()


def idem_get(msg_id: str) -> Any | None:
    """Tra response đã cache cho msg_id. None nếu chưa có hoặc đã hết TTL."""
    if not msg_id:
        return None
    with _idem_lock:
        entry = _idem_cache.get(msg_id)
        if entry is None:
            return None
        response, expire_at = entry
        if time.monotonic() > expire_at:
            # Expired → evict
            _idem_cache.pop(msg_id, None)
            return None
        # Hit → move to end (LRU "recently used")
        _idem_cache.move_to_end(msg_id)
        return response


def idem_set(msg_id: str, response: Any) -> None:
    """Cache response cho msg_id. Evict LRU nếu cache full."""
    if not msg_id:
        return
    with _idem_lock:
        expire_at = time.monotonic() + _IDEM_TTL_SECONDS
        _idem_cache[msg_id] = (response, expire_at)
        _idem_cache.move_to_end(msg_id)
        # Evict LRU nếu vượt max
        while len(_idem_cache) > _IDEM_MAX_ENTRIES:
            _idem_cache.popitem(last=False)


def reset_caches() -> None:
    """Reset cho test/maintenance. Production thì restart server."""
    with _locks_dict_lock:
        _session_locks.clear()
    with _idem_lock:
        _idem_cache.clear()
