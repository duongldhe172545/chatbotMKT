"""Test LLMClient — tier routing. Refer STRATEGY D8 + GLOSSARY § 5."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.llm.client import (
    DEFAULT_LLM_FAST,
    DEFAULT_LLM_QUALITY,
    LLMClient,
    get_default_client,
    reset_default_client,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton trước + sau mỗi test."""
    reset_default_client()
    yield
    reset_default_client()


# ============================================================
# Routing: call_fast → fast_provider, call_quality → quality
# ============================================================


class TestRouting:
    def test_extract_fast_routes_to_fast_provider(self):
        fast = MagicMock()
        quality = MagicMock()
        client = LLMClient(fast_provider=fast, quality_provider=quality)

        fast.extract_structured.return_value = {"owner_name": "Tùng"}

        result = client.extract_fast(
            system_prompt="sys",
            conversation_text="hi",
            tool_name="extract",
            tool_description="desc",
            input_schema={"type": "object"},
        )

        assert result == {"owner_name": "Tùng"}
        fast.extract_structured.assert_called_once()
        quality.extract_structured.assert_not_called()

    def test_chat_fast_routes_to_fast(self):
        fast = MagicMock()
        quality = MagicMock()
        client = LLMClient(fast_provider=fast, quality_provider=quality)

        fast.chat.return_value = "Dạ em note."
        result = client.chat_fast(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == "Dạ em note."
        fast.chat.assert_called_once()
        quality.chat.assert_not_called()

    def test_chat_quality_routes_to_quality(self):
        fast = MagicMock()
        quality = MagicMock()
        client = LLMClient(fast_provider=fast, quality_provider=quality)

        quality.chat.return_value = "Khen cụ thể về số liệu của anh"
        result = client.chat_quality(
            system_prompt="sys",
            messages=[{"role": "user", "content": "anh có 50 khách"}],
        )
        assert result == "Khen cụ thể về số liệu của anh"
        quality.chat.assert_called_once()
        fast.chat.assert_not_called()

    def test_extract_quality_routes_to_quality(self):
        """LLM_QUALITY tier dùng cho slogan gen (F2B.7)."""
        fast = MagicMock()
        quality = MagicMock()
        client = LLMClient(fast_provider=fast, quality_provider=quality)

        quality.extract_structured.return_value = {"slogan_options": ["A", "B", "C"]}
        result = client.extract_quality(
            system_prompt="sys",
            conversation_text="dealer info",
            tool_name="slogan_gen",
            tool_description="gen 5 slogan",
            input_schema={"type": "object"},
        )
        assert result["slogan_options"] == ["A", "B", "C"]
        fast.extract_structured.assert_not_called()


# ============================================================
# Default config — env var mapping
# ============================================================


class TestDefaultConfig:
    def test_default_models_match_strategy_d8(self):
        """Phase 1 full Gemini — refer STRATEGY D8."""
        assert DEFAULT_LLM_FAST == "gemini-3.1-flash-lite"
        assert DEFAULT_LLM_QUALITY == "gemini-3.1-flash-lite"


# ============================================================
# Argument passing
# ============================================================


class TestArgumentPassing:
    def test_chat_fast_max_tokens_default(self):
        """call_fast_chat default max_tokens=256."""
        fast = MagicMock()
        client = LLMClient(fast_provider=fast, quality_provider=MagicMock())
        fast.chat.return_value = "ok"

        client.chat_fast(system_prompt="x", messages=[])
        call_kwargs = fast.chat.call_args.kwargs
        assert call_kwargs["max_tokens"] == 256

    def test_chat_quality_max_tokens_default(self):
        """chat_quality default max_tokens=512 (cần dài hơn fast cho insight)."""
        quality = MagicMock()
        client = LLMClient(fast_provider=MagicMock(), quality_provider=quality)
        quality.chat.return_value = "ok"

        client.chat_quality(system_prompt="x", messages=[])
        call_kwargs = quality.chat.call_args.kwargs
        assert call_kwargs["max_tokens"] == 512

    def test_extract_fast_passes_schema(self):
        fast = MagicMock()
        client = LLMClient(fast_provider=fast, quality_provider=MagicMock())
        fast.extract_structured.return_value = {}

        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        client.extract_fast(
            system_prompt="sys",
            conversation_text="txt",
            tool_name="t",
            tool_description="d",
            input_schema=schema,
        )
        call_kwargs = fast.extract_structured.call_args.kwargs
        assert call_kwargs["input_schema"] == schema
        assert call_kwargs["tool_name"] == "t"


# ============================================================
# Singleton accessor
# ============================================================


class TestSingleton:
    def test_get_default_client_returns_same_instance(self):
        """Singleton — multiple call return cùng instance."""
        # Set env GEMINI_API_KEY để không raise
        import os
        os.environ["GEMINI_API_KEY"] = "test-key"
        try:
            c1 = get_default_client()
            c2 = get_default_client()
            assert c1 is c2
        finally:
            del os.environ["GEMINI_API_KEY"]
            reset_default_client()

    def test_reset_default_client_clears_singleton(self):
        import os
        os.environ["GEMINI_API_KEY"] = "test-key"
        try:
            c1 = get_default_client()
            reset_default_client()
            c2 = get_default_client()
            assert c1 is not c2
        finally:
            del os.environ["GEMINI_API_KEY"]
            reset_default_client()
