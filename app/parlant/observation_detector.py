"""Observation detector — detect dealer behavioral signals from messages.

Parlant concept: Observations are facts about the dealer derived from
their messages. Unlike extracted profile data, observations are
behavioral/conversational signals used to adjust tone and approach.

Observations detected:
- dealer_type: lua_lo / khoe / lo / ban / unknown
- intent: affirmative / refusal / defensive / tam_su / confusion / etc.
- is_busy: dealer seems rushed (short messages, caps)
- is_emotional: dealer is venting / telling stories
- is_skeptical: dealer is suspicious / asking about scams
- message_length: short / medium / long
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Observations:
    """Behavioral signals detected from a single user message."""

    dealer_type: str = "unknown"
    intent: str = "normal"
    is_busy: bool = False
    is_emotional: bool = False
    is_skeptical: bool = False
    message_length: str = "medium"  # short / medium / long
    wants_brief: bool = False
    raw_signals: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dealer_type": self.dealer_type,
            "intent": self.intent,
            "is_busy": self.is_busy,
            "is_emotional": self.is_emotional,
            "is_skeptical": self.is_skeptical,
            "message_length": self.message_length,
            "wants_brief": self.wants_brief,
            "raw_signals": self.raw_signals or [],
        }

    def signal_list(self) -> list[str]:
        """Return list of active signal names for trace logging."""
        signals = []
        if self.is_busy:
            signals.append("user_is_busy")
        if self.is_emotional:
            signals.append("user_is_emotional")
        if self.is_skeptical:
            signals.append("user_is_skeptical")
        if self.wants_brief:
            signals.append("user_wants_brief")
        if self.intent != "normal":
            signals.append(f"intent_{self.intent}")
        if self.dealer_type != "unknown":
            signals.append(f"dealer_{self.dealer_type}")
        return signals


def detect_observations(
    message: str,
    history_length: int = 0,
    llm_client: Optional[Any] = None,
    stage: Optional[str] = None,
    current_slot: Optional[str] = None,
) -> Observations:
    """Detect behavioral observations from a user message.

    Args:
        message: Current user message text
        history_length: Number of messages in history (for dealer_type heuristic)
        llm_client: Optional LLMClient to run Layer 2 intent classification
        stage: Optional stage context
        current_slot: Optional current slot context

    Returns:
        Observations with detected signals
    """
    if not message:
        return Observations()

    msg_lower = message.lower().strip()
    signals: list[str] = []

    # Message length classification
    word_count = len(msg_lower.split())
    if word_count <= 3:
        msg_length = "short"
    elif word_count <= 15:
        msg_length = "medium"
    else:
        msg_length = "long"

    # Intent detection via core.intent (robust regex patterns + Layer 2 LLM fallback)
    from app.core.intent import detect_intent
    intent_enum = detect_intent(
        message,
        llm_client=llm_client,
        stage=stage,
        current_slot=current_slot
    )
    intent = intent_enum.value
    if intent != "normal":
        signals.append(f"{intent}_marker")

    # Wants brief detection
    wants_brief = False
    wants_brief_patterns = [
        r"\b(ngắn\s*gọn|ngắn\s*thôi|vào\s*thẳng|vào\s*việc|nhanh\s*lên|nói\s*nhanh|gọn\s*lẹ|nhanh\s*gọn)\b",
        r"\b(nói\s*ít|bớt\s*lời|đừng\s*dài\s*dòng|ngắn\s*tí|ngắn\s*nữa)\b",
    ]
    for p in wants_brief_patterns:
        if re.search(p, msg_lower):
            wants_brief = True
            signals.append("wants_brief_signal")
            break

    # Busy detection
    is_busy = False
    has_caps = bool(re.search(r"[A-Z]{3,}", message))
    if msg_length == "short" or has_caps or wants_brief:
        is_busy = True
        signals.append("busy_signal")

    # Skeptical detection
    is_skeptical = intent == "defensive"
    if is_skeptical:
        signals.append("skeptical_signal")

    # Emotional detection
    is_emotional = intent == "tam_su" or msg_length == "long"
    if is_emotional:
        signals.append("emotional_signal")

    return Observations(
        dealer_type="unknown",
        intent=intent,
        is_busy=is_busy,
        is_emotional=is_emotional,
        is_skeptical=is_skeptical,
        message_length=msg_length,
        wants_brief=wants_brief,
        raw_signals=signals,
    )
