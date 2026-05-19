"""G1 — Prompt injection guard (regex Layer 1).

Refer LUAT_2B § F2B.8 G1.

Mục đích: dealer cố tình paste prompt nhằm jailbreak bot (đổi persona,
reveal system prompt, bypass rule).

Layer 1: regex match nhanh, không cần LLM.
Layer 2 (Phase 4): LLM input sanitize cho case tinh vi (paraphrase).

Action khi detect injection:
- Flag `prompt_injection` cho session
- KHÔNG forward raw message tới LLM extractor (strip injection part)
- Bot ack polite: "Dạ em không hiểu ý anh lắm, mình quay về phần em
  đang hỏi nhé?" (rồi tiếp tục slot hiện tại)
- ≥ 3 lần inject trong session → admin queue HIGH (refer F2C.8)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Refer F2B.8 G1 patterns + mở rộng VN
INJECTION_PATTERNS: list[str] = [
    # Classic jailbreak EN
    r"ignore (all |the )?(previous |above |prior )?instructions?",
    r"you are now (a |an )?",
    r"forget (your |the |all )?(previous |prior )?",
    r"disregard (all |the )?(previous |above )?",
    # System prompt reveal
    r"reveal (your |the )?system prompt",
    r"show (me |us )?(your |the )?(system )?prompt",
    r"print (out )?(your |the )?(system )?(prompt|instructions)",
    # Role-play injection
    r"system:?\s*[\r\n]",
    r"assistant:?\s*[\r\n]",
    r"user:?\s*[\r\n]",
    # Format markers
    r"\[INST\]|\[/INST\]",
    r"<\|im_start\|>|<\|im_end\|>",
    r"<\|system\|>|<\|user\|>|<\|assistant\|>",
    # Vietnamese injection attempts
    r"in ra (system |the )?prompt",
    r"đọc lại (system )?prompt",
    r"hi[eể]̂n thị (instructions?|prompt|hệ thống)",
    r"bỏ qua (mọi |tất cả )?(rule|luật|hướng dẫn)",
    r"quên (đi |hết )?(rule|luật|những gì)",
    r"từ giờ (em |anh )?(là|đóng vai)",
    r"đóng vai (làm )?(?!em)",  # đóng vai LÀM ai khác (không phải "em")
    r"em là (chatgpt|claude|gpt|gemini|bot|ai)\b",
    # Prompt extraction
    r"copy (out |the )?(your )?(prompt|instructions)",
    r"output (your |the )?system",
]

_COMPILED_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in INJECTION_PATTERNS
]


def check_prompt_injection(message: Optional[str]) -> Optional[str]:
    """Check message có chứa prompt injection không.

    Args:
        message: User raw message

    Returns:
        Pattern matched (str) nếu detect, None nếu clean.
    """
    if not message or not isinstance(message, str):
        return None
    for pattern in _COMPILED_INJECTION_PATTERNS:
        m = pattern.search(message)
        if m:
            matched = m.group(0)
            logger.warning(
                "Prompt injection detected: pattern=%r message=%r",
                pattern.pattern, message[:200],
            )
            return matched
    return None


def sanitize_injection(message: str) -> str:
    """Strip injection patterns khỏi message trước khi pass cho LLM.

    Args:
        message: User raw message (có thể chứa injection)

    Returns:
        Message đã strip pattern. Nếu message toàn injection → trả empty.
    """
    if not message or not isinstance(message, str):
        return ""
    result = message
    for pattern in _COMPILED_INJECTION_PATTERNS:
        result = pattern.sub("", result)
    # Collapse multi-space
    result = re.sub(r"\s+", " ", result).strip()
    return result


def is_clean(message: Optional[str]) -> bool:
    """True nếu message KHÔNG chứa injection."""
    return check_prompt_injection(message) is None
