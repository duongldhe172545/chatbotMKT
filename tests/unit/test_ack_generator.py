"""Test ack generator. Refer F2B.4 + D8 STRATEGY tier routing."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.llm.ack_generator import (
    generate_ack,
    is_quality_tier_type,
)
from app.llm.fallback import SAFE_ACK_TEMPLATES
from app.models.enums import AddressForm, DealerType


def _make_client(
    fast_response: str = "Dạ em note.",
    quality_response: str = "Khen anh cụ thể về số liệu.",
):
    """Build mock LLMClient với chat_fast + chat_quality return mock text."""
    client = MagicMock()
    client.chat_fast.return_value = fast_response
    client.chat_quality.return_value = quality_response
    return client


# ============================================================
# Tier routing (D8 STRATEGY)
# ============================================================


class TestTierRouting:
    def test_ban_uses_fast_tier(self):
        """Bận → LLM_FAST."""
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.BAN,
        )
        client.chat_fast.assert_called_once()
        client.chat_quality.assert_not_called()

    def test_lua_lo_uses_fast_tier(self):
        """Lửa Lò → LLM_FAST."""
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Vinh"}, client,
            dealer_type=DealerType.LUA_LO,
        )
        client.chat_fast.assert_called_once()
        client.chat_quality.assert_not_called()

    def test_khoe_uses_quality_tier(self):
        """Khoe → LLM_QUALITY (cần insight cụ thể)."""
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.KHOE,
        )
        client.chat_quality.assert_called_once()
        client.chat_fast.assert_not_called()

    def test_lo_uses_quality_tier(self):
        """Lo → LLM_QUALITY (cần cam kết bảo mật cụ thể)."""
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.LO,
        )
        client.chat_quality.assert_called_once()
        client.chat_fast.assert_not_called()

    def test_unknown_uses_fast_tier(self):
        """UNKNOWN (default 3 turn đầu) → LLM_FAST (tone Bận)."""
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.UNKNOWN,
        )
        client.chat_fast.assert_called_once()

    def test_none_dealer_type_defaults_to_unknown(self):
        """None dealer_type → UNKNOWN → FAST."""
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=None,
        )
        client.chat_fast.assert_called_once()


class TestQualityTierHelper:
    def test_is_quality_tier_type(self):
        assert is_quality_tier_type(DealerType.KHOE) is True
        assert is_quality_tier_type(DealerType.LO) is True
        assert is_quality_tier_type(DealerType.BAN) is False
        assert is_quality_tier_type(DealerType.LUA_LO) is False
        assert is_quality_tier_type(DealerType.UNKNOWN) is False


# ============================================================
# Return value
# ============================================================


class TestReturnValue:
    def test_returns_llm_text(self):
        client = _make_client(fast_response="Dạ em note rồi anh Tùng.")
        result = generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.BAN,
        )
        assert result == "Dạ em note rồi anh Tùng."

    def test_strips_whitespace(self):
        client = _make_client(fast_response="  Dạ em note.\n\n")
        result = generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.BAN,
        )
        assert result == "Dạ em note."


# ============================================================
# Fallback on error
# ============================================================


class TestFallback:
    def test_llm_exception_returns_safe_ack(self):
        """LLM raise → return safe_ack."""
        client = MagicMock()
        client.chat_fast.side_effect = ConnectionError("LLM down")
        result = generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.BAN,
            use_fallback_on_error=True,
        )
        assert result in SAFE_ACK_TEMPLATES

    def test_llm_empty_response_returns_safe_ack(self):
        """LLM trả empty → fallback safe."""
        client = _make_client(fast_response="")
        result = generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.BAN,
        )
        assert result in SAFE_ACK_TEMPLATES

    def test_no_fallback_returns_empty_on_error(self):
        """use_fallback_on_error=False → return '' khi LLM fail."""
        client = MagicMock()
        client.chat_fast.side_effect = ConnectionError("LLM down")
        result = generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.BAN,
            use_fallback_on_error=False,
        )
        assert result == ""


# ============================================================
# Prompt context — extracted_data + dealer_type pass đúng
# ============================================================


class TestPromptContext:
    def test_extracted_data_in_user_message(self):
        client = _make_client()
        generate_ack(
            "1.1",
            {"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"},
            client,
            dealer_type=DealerType.BAN,
        )
        call_kwargs = client.chat_fast.call_args.kwargs
        # User message phải chứa data extracted
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        user_content = messages[0]["content"]
        assert "Tùng" in user_content
        assert "Nhôm Kính Thanh Tùng" in user_content

    def test_system_prompt_contains_dealer_type(self):
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Tùng"}, client,
            dealer_type=DealerType.KHOE,
        )
        call_kwargs = client.chat_quality.call_args.kwargs
        system = call_kwargs["system_prompt"]
        assert "khoe" in system
        assert "Khen CỤ THỂ" in system or "khen" in system.lower()

    def test_address_form_propagates(self):
        client = _make_client()
        generate_ack(
            "1.1", {"owner_name": "Lan"}, client,
            dealer_type=DealerType.BAN,
            address_form=AddressForm.CHI,
        )
        call_kwargs = client.chat_fast.call_args.kwargs
        assert "chị" in call_kwargs["system_prompt"]
