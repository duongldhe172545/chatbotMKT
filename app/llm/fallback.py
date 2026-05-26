"""Fallback safe ack — dùng khi LLM call fail / timeout.

Refer F2C.4 (LUAT_2C_infra) timeout + retry policy + safe ack pattern.

Design: template Việt hóa, KHÔNG vocab cấm, KHÔNG promise specific.
Engine pick random để tự nhiên (không paste cứng 1 câu mỗi lần fail).
"""
from __future__ import annotations

import random


# ============================================================
# Safe ack templates — dùng khi LLM fail (timeout / API error)
# ============================================================

SAFE_ACK_TEMPLATES: list[str] = [
    "Dạ vâng anh.",
    "Dạ em hiểu rồi.",
    "Dạ được anh.",
    "Dạ vâng, mình tiếp nhé.",
    "Dạ vâng ạ.",
]


SAFE_RETRY_MESSAGES: list[str] = [
    "Dạ em xíu kết nối — anh chờ em chút nha.",
    "Dạ anh chờ em xíu ạ, em đang xử lý.",
    "Em đang xử lý nha anh, chờ em tí.",
]


SAFE_ERROR_MESSAGES: list[str] = [
    "Dạ em đang gặp xíu trục trặc, anh thử nhắn lại sau ít phút nhé ạ.",
    "Dạ em xin lỗi, hệ thống của em đang bận. Anh thử lại sau xíu giúp em nhé.",
]


def safe_ack(seed: int | None = None) -> str:
    """Trả về 1 ack template safe — dùng khi LLM gen fail.

    Args:
        seed: Random seed cho deterministic test. None = random thật.

    Returns:
        Safe ack string (always non-empty).
    """
    if seed is not None:
        rng = random.Random(seed)
        return rng.choice(SAFE_ACK_TEMPLATES)
    return random.choice(SAFE_ACK_TEMPLATES)


def safe_retry_message(seed: int | None = None) -> str:
    """Trả về 1 retry message safe khi LLM timeout."""
    if seed is not None:
        rng = random.Random(seed)
        return rng.choice(SAFE_RETRY_MESSAGES)
    return random.choice(SAFE_RETRY_MESSAGES)


def safe_error_message(seed: int | None = None) -> str:
    """Trả về 1 error message khi LLM fail hoàn toàn (sau hết retry)."""
    if seed is not None:
        rng = random.Random(seed)
        return rng.choice(SAFE_ERROR_MESSAGES)
    return random.choice(SAFE_ERROR_MESSAGES)
