"""Test local hook LLM gen — F2A.8 + feedback_no_case_lock.

Refer:
- F2A.8 (LUAT_2A_core v0.2.5) — Closing local hook LLM
- File 1A § 7.4 — quy ước local hook
- feedback_no_case_lock — KHÔNG hardcode tỉnh → đặc sản
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.cache.llm_cache import llm_cache_clear as clear_llm_cache
from app.core.closing import render_closing
from app.llm.local_hook import gen_local_hook
from app.models.enums import AddressForm, DealerType


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_llm_cache()
    yield
    clear_llm_cache()


def _client(chat_fast_return: str = "Bên Hà Nội mình khách quen thường ghé nhiều.") -> MagicMock:
    c = MagicMock()
    c.chat_fast = MagicMock(return_value=chat_fast_return)
    return c


class TestGenLocalHook:
    def test_returns_llm_response(self):
        custom = "Khu vực Hà Nội mình khách hay quan tâm chất lượng."
        client = _client(chat_fast_return=custom)
        result = gen_local_hook(
            province="Hà Nội",
            dealer_type=DealerType.KHOE,
            client=client,
            use_cache=False,
        )
        assert result == custom

    def test_empty_province_returns_empty(self):
        client = _client()
        assert gen_local_hook("", None, client) == ""
        assert gen_local_hook(None, None, client) == ""
        client.chat_fast.assert_not_called()

    def test_no_client_returns_empty(self):
        """Phase 1 fallback: không có client → rỗng."""
        result = gen_local_hook("Hà Nội", DealerType.BAN, client=None)
        assert result == ""

    def test_llm_returns_empty_string(self):
        """LLM được phép trả rỗng (không có gì đáng nói)."""
        client = _client(chat_fast_return="")
        result = gen_local_hook("Cao Bằng", DealerType.UNKNOWN, client, use_cache=False)
        assert result == ""

    def test_llm_too_long_filtered(self):
        """ADVERSARIAL: LLM trả > 200 char → reject (vi phạm ≤ 30 từ)."""
        long_text = "a" * 250
        client = _client(chat_fast_return=long_text)
        result = gen_local_hook("Hà Nội", DealerType.UNKNOWN, client, use_cache=False)
        assert result == ""

    def test_llm_exception_returns_empty(self):
        client = MagicMock()
        client.chat_fast = MagicMock(side_effect=Exception("API"))
        result = gen_local_hook("Hà Nội", DealerType.UNKNOWN, client, use_cache=False)
        assert result == ""

    def test_cache_hit_skips_llm(self):
        """Cache 7 ngày: lần 2 cùng province + dealer_type + session → KHÔNG gọi LLM.

        Phase 6 R+ 2026-05-22: cache key giờ có thêm variant_idx (hash từ
        session_id để đa dạng). Test truyền session_id cố định để verify
        cache hit logic (cùng key).
        """
        custom = "Sài Gòn nhộn nhịp lắm."
        client = _client(chat_fast_return=custom)
        sid = "test-session-fixed"
        # Call 1: miss → call LLM
        r1 = gen_local_hook("TP.HCM", DealerType.BAN, client, use_cache=True, session_id=sid)
        # Call 2: hit cache (cùng session_id → cùng variant_idx → cùng key)
        r2 = gen_local_hook("TP.HCM", DealerType.BAN, client, use_cache=True, session_id=sid)
        assert r1 == r2 == custom
        assert client.chat_fast.call_count == 1

    def test_cache_different_dealer_type_separate(self):
        """ADVERSARIAL: cùng province khác dealer_type → cache key khác."""
        client = MagicMock()
        client.chat_fast = MagicMock(
            side_effect=["hook for Khoe", "hook for Bận"]
        )
        r1 = gen_local_hook("Hà Nội", DealerType.KHOE, client, use_cache=True)
        r2 = gen_local_hook("Hà Nội", DealerType.BAN, client, use_cache=True)
        assert r1 != r2
        assert client.chat_fast.call_count == 2


class TestRenderClosingWithHook:
    def test_no_client_template_only(self):
        """Backward compat: không có client → template tổng quát."""
        result = render_closing(province="Hà Nội", consent="yes")
        assert "Em cảm ơn anh" in result
        # KHÔNG có hook (chưa LLM gen)
        assert not result.startswith("Khu vực")

    def test_with_client_prepends_hook(self):
        client = _client(chat_fast_return="Khu vực Hà Nội mình khách đông.")
        result = render_closing(
            province="Hà Nội",
            consent="yes",
            client=client,
            dealer_type=DealerType.KHOE,
        )
        assert result.startswith("Khu vực Hà Nội")
        assert "Em cảm ơn anh" in result

    def test_with_client_no_province_skip_hook(self):
        """ADVERSARIAL: có client nhưng không có province → KHÔNG gen hook."""
        client = _client()
        result = render_closing(
            province=None,
            consent="yes",
            client=client,
        )
        assert "Em cảm ơn anh" in result
        client.chat_fast.assert_not_called()

    def test_llm_empty_hook_no_prepend(self):
        """LLM trả rỗng → KHÔNG prepend, dùng template chỉ."""
        client = _client(chat_fast_return="")
        result = render_closing(
            province="Cao Bằng",
            consent="yes",
            client=client,
        )
        assert "Em cảm ơn anh" in result
        # Hook rỗng → không prefix newlines
        assert not result.startswith("\n")

    def test_consent_no_path_with_hook(self):
        client = _client(chat_fast_return="Bên Đà Nẵng mình khách ưa thương hiệu rõ ràng.")
        result = render_closing(
            province="Đà Nẵng",
            consent="no",
            client=client,
        )
        assert result.startswith("Bên Đà Nẵng")
        assert "không ép" in result  # consent=no template marker
