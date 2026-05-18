"""Intent detection Layer 1 (regex). Refer F2A.2.

Layer 2 LLM fallback ở `app/llm/intent_classifier.py` — Phase 2+.

Priority order (F2A.2):
    defensive > tam_su > refusal > khong_biet > edit > affirmative > normal
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.regex_markers import (
    AFFIRMATIVE_PATTERNS,
    DEFENSIVE_PATTERNS,
    EDIT_PATTERNS,
    KHONG_BIET_PATTERNS,
    REFUSAL_PATTERNS,
    TAM_SU_PATTERNS,
)
from app.models.enums import Intent


# Priority list — order quyết định kết quả nếu message match nhiều intent
_INTENT_PRIORITY: list[tuple[Intent, list[str]]] = [
    (Intent.DEFENSIVE, DEFENSIVE_PATTERNS),
    (Intent.TAM_SU, TAM_SU_PATTERNS),
    (Intent.REFUSAL, REFUSAL_PATTERNS),
    (Intent.KHONG_BIET, KHONG_BIET_PATTERNS),
    (Intent.EDIT, EDIT_PATTERNS),
    (Intent.AFFIRMATIVE, AFFIRMATIVE_PATTERNS),
]


_RE_FLAGS = re.IGNORECASE | re.UNICODE

# Precompile patterns (1 lần module-level — perf)
_COMPILED: list[tuple[Intent, list[re.Pattern]]] = [
    (intent, [re.compile(p, _RE_FLAGS) for p in patterns])
    for intent, patterns in _INTENT_PRIORITY
]


def detect_intent_layer1(message: str) -> Optional[Intent]:
    """Layer 1 regex detection.

    Args:
        message: text dealer gửi

    Returns:
        Intent nếu match, None nếu không match marker nào.
        Caller (Phase 1) treat None = Intent.NORMAL.
        Caller (Phase 2+) dispatch Layer 2 LLM nếu None.
    """
    if not message or not message.strip():
        return None

    msg_lower = message.strip().lower()
    for intent, patterns in _COMPILED:
        for pattern in patterns:
            if pattern.search(msg_lower):
                return intent
    return None


def detect_intent(message: str) -> Intent:
    """Combined Layer 1 + fallback to NORMAL. Phase 1 wrapper.

    Args:
        message: text dealer gửi

    Returns:
        Intent (luôn có value, không None).
    """
    return detect_intent_layer1(message) or Intent.NORMAL
