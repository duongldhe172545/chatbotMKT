"""Test auto_derive — LLM-driven main_category derive.

Refer:
- F2B.7 (LUAT_2B_llm) — auto-derive
- feedback_no_case_lock memory — KHÔNG substring keyword match
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.cache.data_loaders import clear_cache
from app.llm.auto_derive import derive_main_category


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


def _make_mock_client(return_value: dict | None = None) -> MagicMock:
    """Mock LLMClient.extract_fast trả về dict."""
    client = MagicMock()
    client.extract_fast = MagicMock(return_value=return_value or {})
    return client


class TestDeriveMainCategory:
    def test_empty_main_product_returns_none(self):
        client = _make_mock_client()
        assert derive_main_category("", client) is None
        assert derive_main_category(None, client) is None
        assert derive_main_category("   ", client) is None
        client.extract_fast.assert_not_called()

    def test_llm_returns_valid_code(self):
        client = _make_mock_client({"main_category": "cua_nhom_kinh"})
        result = derive_main_category("cửa nhôm kính hệ Xingfa", client)
        assert result == "cua_nhom_kinh"
        client.extract_fast.assert_called_once()

    def test_llm_returns_null(self):
        """LLM unsure → null → derive return None."""
        client = _make_mock_client({"main_category": None})
        assert derive_main_category("bán đủ thứ", client) is None

    def test_llm_returns_invalid_code(self):
        """LLM bịa code → reject."""
        client = _make_mock_client({"main_category": "khong_co_enum_nay"})
        assert derive_main_category("cửa cuốn", client) is None

    def test_llm_fail_returns_none(self):
        """LLM throw → return None gracefully."""
        client = MagicMock()
        client.extract_fast = MagicMock(side_effect=Exception("API timeout"))
        assert derive_main_category("cửa cuốn motor", client) is None

    def test_llm_returns_non_dict(self):
        """LLM trả non-dict (vd raw string) → return None."""
        client = _make_mock_client()
        client.extract_fast = MagicMock(return_value="cua_cuon")
        assert derive_main_category("cửa cuốn", client) is None

    def test_context_passed_in_user_text(self):
        """additional_context được gắn vào conversation_text."""
        client = _make_mock_client({"main_category": "cua_nhom_kinh"})
        derive_main_category(
            "cửa nhôm kính",
            client,
            additional_context="category_stack: cua_nhom_kinh, vlxd_tong_hop",
        )
        call_args = client.extract_fast.call_args
        conv_text = call_args.kwargs.get("conversation_text") or call_args.args[1]
        assert "category_stack" in conv_text
