"""Test rate limit + LLM cache — Phase 4 R4."""
from __future__ import annotations

import time

import pytest

from app.cache.llm_cache import (
    llm_cache_clear,
    llm_cache_get,
    llm_cache_set,
    llm_cache_size,
    make_key,
)
from app.guards.rate_limit import (
    check_rate_limit,
    get_bucket_size,
    reset_all,
    reset_for_key,
)


@pytest.fixture(autouse=True)
def clean_state():
    reset_all()
    llm_cache_clear()
    yield
    reset_all()
    llm_cache_clear()


# ============================================================
# Rate limit
# ============================================================


class TestRateLimit:
    def test_under_limit_allowed(self):
        for i in range(5):
            allowed, _ = check_rate_limit("user:1", max_requests=10, window_seconds=60)
            assert allowed is True

    def test_exact_limit_allowed(self):
        for i in range(10):
            allowed, _ = check_rate_limit("user:1", max_requests=10, window_seconds=60)
            assert allowed is True

    def test_over_limit_blocked(self):
        for _ in range(10):
            check_rate_limit("user:1", max_requests=10, window_seconds=60)
        allowed, retry = check_rate_limit("user:1", max_requests=10, window_seconds=60)
        assert allowed is False
        assert retry > 0

    def test_different_keys_independent(self):
        """ADVERSARIAL: 2 user khác nhau — không bị share bucket."""
        for _ in range(10):
            check_rate_limit("user:A", max_requests=10, window_seconds=60)
        # user:B vẫn allowed
        allowed, _ = check_rate_limit("user:B", max_requests=10, window_seconds=60)
        assert allowed is True

    def test_empty_key_always_allowed(self):
        """ADVERSARIAL: key rỗng → bypass (không track)."""
        for _ in range(100):
            allowed, _ = check_rate_limit("", max_requests=5, window_seconds=60)
            assert allowed is True

    def test_reset_for_key(self):
        for _ in range(10):
            check_rate_limit("user:1", max_requests=10, window_seconds=60)
        # Blocked
        assert check_rate_limit("user:1", max_requests=10, window_seconds=60)[0] is False
        reset_for_key("user:1")
        # Sau reset
        allowed, _ = check_rate_limit("user:1", max_requests=10, window_seconds=60)
        assert allowed is True

    def test_bucket_size_tracks_requests(self):
        for i in range(3):
            check_rate_limit("user:1", max_requests=10, window_seconds=60)
        assert get_bucket_size("user:1") == 3


# ============================================================
# LLM cache
# ============================================================


class TestLlmCache:
    def test_get_returns_none_for_miss(self):
        assert llm_cache_get("nokey") is None

    def test_set_and_get(self):
        llm_cache_set("key1", "value1", ttl_s=10)
        assert llm_cache_get("key1") == "value1"

    def test_ttl_expires(self):
        """ADVERSARIAL: TTL 0 → ngay lập tức expire."""
        llm_cache_set("key1", "value1", ttl_s=0)
        time.sleep(0.001)
        assert llm_cache_get("key1") is None

    def test_overwrite(self):
        llm_cache_set("key1", "v1", ttl_s=10)
        llm_cache_set("key1", "v2", ttl_s=10)
        assert llm_cache_get("key1") == "v2"

    def test_complex_value(self):
        llm_cache_set("key1", {"intent": "defensive", "conf": "HIGH"}, ttl_s=10)
        result = llm_cache_get("key1")
        assert result["intent"] == "defensive"

    def test_make_key_deterministic(self):
        k1 = make_key("intent_l2", "hello", "ASKING", "1.1")
        k2 = make_key("intent_l2", "hello", "ASKING", "1.1")
        assert k1 == k2
        # Different parts → different key
        k3 = make_key("intent_l2", "hello", "ASKING", "1.2")
        assert k1 != k3

    def test_make_key_handles_none(self):
        k = make_key("part1", None, "part2")
        assert isinstance(k, str)
        assert len(k) == 32  # sha256 prefix

    def test_clear(self):
        llm_cache_set("key1", "v", ttl_s=10)
        llm_cache_set("key2", "v", ttl_s=10)
        assert llm_cache_size() == 2
        llm_cache_clear()
        assert llm_cache_size() == 0

    def test_empty_key_ignored(self):
        llm_cache_set("", "v", ttl_s=10)
        # Empty key bypass
        assert llm_cache_get("") is None
