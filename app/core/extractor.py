"""Extractor — gọi LLM để bóc Dealer Profile RAW từ hội thoại."""
from __future__ import annotations

from app.llm.base import LLMProvider
from app.models.schema import ChatMessage, ChatRole, ExtractResult

from . import prompts


class Extractor:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def extract(self, messages: list[ChatMessage]) -> ExtractResult:
        conversation_text = self._format_conversation(messages)

        raw = self.llm.extract_structured(
            system_prompt=prompts.EXTRACTOR_SYSTEM_PROMPT,
            conversation_text=conversation_text,
            tool_name=prompts.EXTRACTION_TOOL_NAME,
            tool_description=prompts.EXTRACTION_TOOL_DESCRIPTION,
            input_schema=prompts.EXTRACTION_TOOL_SCHEMA,
        )

        result = ExtractResult(**raw)
        # Lớp raw_transcript theo spec mục 11: ghép tất cả tin nhắn dealer.
        # Không cho LLM tự sinh — đây là bản raw để trace, không qua xử lý.
        result.raw_transcript = "\n".join(
            m.content for m in messages if m.role == ChatRole.DEALER and m.content
        )
        return result

    @staticmethod
    def _format_conversation(messages: list[ChatMessage]) -> str:
        lines = ["Đây là hội thoại giữa Em Linh (bot) và dealer:\n"]
        for m in messages:
            speaker = "Em Linh" if m.role.value == "bot" else "Dealer"
            lines.append(f"{speaker}: {m.content}")
        lines.append(
            "\nHãy trích xuất Dealer Profile RAW theo schema. "
            "Gọi tool save_dealer_extraction với đầy đủ field."
        )
        return "\n".join(lines)
