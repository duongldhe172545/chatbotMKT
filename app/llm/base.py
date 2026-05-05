"""LLM provider interface — đổi provider chỉ bằng config."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def extract_structured(
        self,
        system_prompt: str,
        conversation_text: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        """Gọi LLM và ép output theo JSON schema. Trả dict đã parse."""
        ...

    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 512,
    ) -> str:
        """Trả text reply tự nhiên (không structured).

        messages: list[{"role": "user"|"assistant", "content": str}]
        """
        ...
