"""LLM client unified — tier routing LLM_FAST / LLM_QUALITY.

Refer:
- STRATEGY D8 — 2-tier abstraction (LLM_FAST + LLM_QUALITY)
- GLOSSARY § 5 — tier mapping
- KE_HOACH § 0.9 — routing table
- F2B.1 (LUAT_2B_llm) — system prompt builder

Phase 1: full Gemini (LLM_FAST=gemini-2.5-flash, LLM_QUALITY=gemini-2.5-pro).
Claude adapter giữ trong app/llm/claude.py (Phase 2+ nếu cần fallback).
"""
from __future__ import annotations

import os
from typing import Optional

from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider


# Default model — refer .env.example
DEFAULT_LLM_FAST = "gemini-2.5-flash"
DEFAULT_LLM_QUALITY = "gemini-2.5-pro"


class LLMClient:
    """Unified LLM client với 2-tier routing.

    FAST: intent classify, extractor, STT brand correct, address parser,
          auto-derive brand_short/initials, ack Bận/Lửa Lò.
    QUALITY: ack Khoe/Lo (insight cụ thể), slogan options, defensive/tâm sự handler.

    Phase 1 chỉ implement Gemini. Test mock LLMProvider để không cần API key.
    """

    def __init__(
        self,
        fast_provider: Optional[LLMProvider] = None,
        quality_provider: Optional[LLMProvider] = None,
    ):
        """Khởi tạo LLMClient.

        Args:
            fast_provider: Provider cho LLM_FAST tier. None → tạo GeminiProvider
                với LLM_FAST model từ env.
            quality_provider: Provider cho LLM_QUALITY tier. None → tạo GeminiProvider
                với LLM_QUALITY model từ env.
        """
        self.fast_provider = fast_provider or self._build_default_fast()
        self.quality_provider = quality_provider or self._build_default_quality()

    @staticmethod
    def _build_default_fast() -> LLMProvider:
        """Build provider từ Pydantic Settings (đã load .env qua pydantic-settings).

        Note: dùng get_settings() thay vì os.environ trực tiếp vì pydantic-settings
        load .env vào Settings model nhưng KHÔNG mutate os.environ.
        """
        from app.config import get_settings
        settings = get_settings()
        return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.LLM_FAST)

    @staticmethod
    def _build_default_quality() -> LLMProvider:
        from app.config import get_settings
        settings = get_settings()
        return GeminiProvider(
            api_key=settings.GEMINI_API_KEY, model=settings.LLM_QUALITY
        )

    # ============================================================
    # LLM_FAST tier
    # ============================================================

    def extract_fast(
        self,
        system_prompt: str,
        conversation_text: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        """Extract structured output với LLM_FAST (cheap, deterministic).

        Dùng cho: extractor 17 slot, intent classify, STT brand, address parser,
        auto-derive brand_short/initials.

        Returns:
            Dict JSON parsed theo schema. Empty dict nếu LLM fail (defensive).
        """
        return self.fast_provider.extract_structured(
            system_prompt=system_prompt,
            conversation_text=conversation_text,
            tool_name=tool_name,
            tool_description=tool_description,
            input_schema=input_schema,
        )

    def chat_fast(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 256,
    ) -> str:
        """Chat reply với LLM_FAST. Dùng cho: ack Bận / Lửa Lò.

        Args:
            system_prompt: System prompt (refer F2B.1 build_system_prompt)
            messages: List [{"role": "user"|"assistant", "content": str}]
            max_tokens: Max output tokens (default 256 cho ack ngắn)

        Returns:
            Text reply. Empty string nếu LLM fail.
        """
        return self.fast_provider.chat(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
        )

    # ============================================================
    # LLM_QUALITY tier
    # ============================================================

    def chat_quality(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 512,
    ) -> str:
        """Chat reply với LLM_QUALITY. Dùng cho: ack Khoe/Lo, slogan,
        defensive/tâm sự handler (refer F2B.4b).

        Phase 1 chưa implement defensive handler — sẵn sàng cho Phase 2+.
        """
        return self.quality_provider.chat(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
        )

    def extract_quality(
        self,
        system_prompt: str,
        conversation_text: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        """Extract structured với LLM_QUALITY. Dùng cho slogan gen 5 phương án
        sáng tạo (F2B.7).
        """
        return self.quality_provider.extract_structured(
            system_prompt=system_prompt,
            conversation_text=conversation_text,
            tool_name=tool_name,
            tool_description=tool_description,
            input_schema=input_schema,
        )


# ============================================================
# Singleton accessor (Phase 1 đơn giản — Phase 2+ DI container)
# ============================================================


_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    """Get singleton LLMClient. Lazy init từ env vars."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def reset_default_client() -> None:
    """Reset singleton (chủ yếu cho test)."""
    global _default_client
    _default_client = None
