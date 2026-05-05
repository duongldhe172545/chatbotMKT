"""ChatReplier — sinh phản hồi tự nhiên (không structured) cho stage DONE."""
from __future__ import annotations

from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.llm.base import LLMProvider
from app.models.schema import ChatMessage, ChatRole


class ChatReplier:
    """Wrapper quanh LLMProvider.chat() với persona em Linh đã set sẵn."""

    # Số message gần nhất truyền vào LLM — đủ context, không tốn token thừa
    HISTORY_WINDOW = 10

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def reply(self, messages: list[ChatMessage]) -> str:
        # Loại message rỗng (Anthropic API reject) + lấy N message gần nhất
        clean = [m for m in messages if (m.content or "").strip()]
        recent = clean[-self.HISTORY_WINDOW :]

        # Gộp các turn liên tiếp cùng role lại (Anthropic yêu cầu xen kẽ user/assistant)
        merged: list[dict] = []
        for m in recent:
            role = "user" if m.role == ChatRole.DEALER else "assistant"
            content = m.content.strip()
            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n" + content
            else:
                merged.append({"role": role, "content": content})

        # Đảm bảo bắt đầu bằng user
        if not merged or merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "Xin chào"})

        # Đảm bảo kết thúc bằng user (để LLM phản hồi)
        if merged[-1]["role"] != "user":
            merged.append({"role": "user", "content": "(anh chờ em phản hồi)"})

        return self.llm.chat(
            system_prompt=CHAT_SYSTEM_PROMPT,
            messages=merged,
            max_tokens=300,
        )
