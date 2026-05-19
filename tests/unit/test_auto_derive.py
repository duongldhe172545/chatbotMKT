"""Test auto_derive — LLM-driven main_category + brand_short + initials + slogan.

Refer:
- F2B.7 (LUAT_2B_llm) — auto-derive
- feedback_no_case_lock memory — KHÔNG substring keyword match
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.cache.data_loaders import clear_cache as clear_data_cache
from app.llm.auto_derive import (
    clear_cache as clear_derive_cache,
    derive_brand_short,
    derive_main_category,
    gen_initial_single,
    gen_initials_full,
    gen_slogans,
)


@pytest.fixture(autouse=True)
def _clear_all_caches():
    clear_data_cache()
    clear_derive_cache()
    yield
    clear_data_cache()
    clear_derive_cache()


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


# ============================================================
# Phase 5 R0: brand_short + initials + initial_single + slogans
# ============================================================


class TestGenInitialsFull:
    @pytest.mark.parametrize("name,expected", [
        ("Nhôm Kính Thanh Tùng", "TT"),     # NK lọc → còn Thanh + Tùng
        ("Cửa Cuốn Hùng Mạnh", "HM"),
        ("Tủ Bếp Vinh Quang", "VQ"),
        ("Cửa Hàng Anh Tâm", "AT"),
    ])
    def test_common_words_filtered(self, name, expected):
        assert gen_initials_full(name) == expected

    def test_fallback_all_common_words(self):
        """ADVERSARIAL: dealer_name toàn từ chung → fallback all tokens."""
        result = gen_initials_full("Nhôm Kính Cửa")
        # Filter sạch hết → fallback all 3 tokens
        assert result == "NKC"

    def test_max_length_truncated(self):
        """ADVERSARIAL: dealer_name dài → cắt ≤ 6 chữ."""
        long_name = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta"
        result = gen_initials_full(long_name)
        assert result is not None
        assert len(result) <= 6

    def test_none_input(self):
        assert gen_initials_full(None) is None
        assert gen_initials_full("") is None


class TestGenInitialSingle:
    def test_last_char(self):
        assert gen_initial_single("NKTT") == "T"
        assert gen_initial_single("HM") == "M"

    def test_lowercase_input_normalized(self):
        assert gen_initial_single("nktt") == "T"

    def test_none_input(self):
        assert gen_initial_single(None) is None
        assert gen_initial_single("") is None


class TestDeriveBrandShort:
    def test_llm_returns_short(self):
        client = MagicMock()
        client.extract_fast.return_value = {"brand_short": "Thanh Tùng"}
        result = derive_brand_short("Nhôm Kính Thanh Tùng", client)
        assert result == "Thanh Tùng"

    def test_llm_returns_null(self):
        client = MagicMock()
        client.extract_fast.return_value = {"brand_short": None}
        assert derive_brand_short("Test", client) is None

    def test_llm_fail(self):
        client = MagicMock()
        client.extract_fast.side_effect = Exception("API fail")
        assert derive_brand_short("Test", client) is None

    def test_empty_input(self):
        client = MagicMock()
        assert derive_brand_short("", client) is None
        assert derive_brand_short(None, client) is None
        client.extract_fast.assert_not_called()


class TestGenSlogans:
    def test_returns_list(self):
        client = MagicMock()
        client.extract_quality.return_value = {
            "slogans": [
                "Slogan 1",
                "Slogan 2",
                "Slogan 3",
                "Slogan 4",
                "Slogan 5",
            ],
        }
        result = gen_slogans("Test Shop", "cửa nhôm", client)
        assert len(result) == 5

    def test_dedupe(self):
        """ADVERSARIAL: LLM trả slogan trùng → dedupe."""
        client = MagicMock()
        client.extract_quality.return_value = {
            "slogans": ["A", "A", "B", "  a  ", "C"],
        }
        result = gen_slogans("Test", "cửa", client)
        # Case-insensitive dedupe
        assert len(result) == 3
        assert "A" in result and "B" in result and "C" in result

    def test_filter_empty_strings(self):
        client = MagicMock()
        client.extract_quality.return_value = {
            "slogans": ["A", "", "  ", "B"],
        }
        result = gen_slogans("Test", "cửa", client)
        assert result == ["A", "B"]

    def test_llm_fail_returns_empty(self):
        client = MagicMock()
        client.extract_quality.side_effect = Exception("API fail")
        result = gen_slogans("Test", "cửa", client)
        assert result == []

    def test_missing_required_inputs(self):
        """ADVERSARIAL: thiếu dealer_name hoặc main_product → return empty."""
        client = MagicMock()
        assert gen_slogans(None, "cửa", client) == []
        assert gen_slogans("Test", None, client) == []
        client.extract_quality.assert_not_called()

    def test_non_list_response(self):
        client = MagicMock()
        client.extract_quality.return_value = {"slogans": "not a list"}
        assert gen_slogans("Test", "cửa", client) == []
