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
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional


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


# ============================================================
# 9.1 — Phát hiện cách xưng hô (anh/chị) từ cách khách TỰ XƯNG
# ============================================================
# High-precision: CHỈ đổi sang "chị" khi có dấu hiệu khách tự xưng chị rõ ràng;
# mặc định "anh". Đây là luật NGÔN NGỮ (đại từ), không khoá case nghiệp vụ.
_CHI_SELF_REF = [
    r"\bch[iị]\s+t[eê]n\b",                              # "chị tên ..."
    r"\b(tôi|toi|mình|minh)\s+l[aà]\s+ch[iị]\b",          # "tôi/mình là chị"
    r"\bem\s+l[aà]\s+ch[iị]\b",                           # "em là chị" (khách tự xưng)
    r"\bg[oọ]i\s+(em\s+)?(b[aằ]ng\s+)?(l[aà]\s+)?ch[iị]\b",  # "gọi (em là) chị"
    r"\bcho\s+ch[iị]\s+(xin|h[oỏ]i|g[uử]i|bi[eế]t)\b",   # "cho chị xin/hỏi"
    r"\bch[iị]\s+(mu[oố]n|c[âầ]n|đang|l[aà]\s+ch[uủ])\b", # "chị muốn/cần/là chủ"
]
_ANH_SELF_REF = [
    r"\banh\s+t[eê]n\b",
    r"\b(tôi|toi|mình|minh)\s+l[aà]\s+anh\b",
    r"\bg[oọ]i\s+(em\s+)?(b[aằ]ng\s+)?(l[aà]\s+)?anh\b",
    r"\bcho\s+anh\s+(xin|h[oỏ]i|g[uử]i|bi[eế]t)\b",
    r"\banh\s+(mu[oố]n|c[âầ]n|đang|l[aà]\s+ch[uủ])\b",
]


# ============================================================
# 9.4 — Tín hiệu "đủ rồi / chốt" lúc đang TƯ VẤN (C1-C9 bonus)
# ============================================================
# High-precision: chỉ bắt câu KẾT THÚC tư vấn rõ ràng. Dùng để bỏ qua nốt các câu
# tư vấn còn lại → ra thẳng thẻ hồ sơ (review). CHỈ áp dụng khi đang ở giai đoạn
# tư vấn (gate ở chat_service), nên "đủ rồi" lỡ là câu trả lời cũng ít hại.
# Match trên text ĐÃ BỎ DẤU (tránh địa ngục tổ hợp dấu tiếng Việt).
_WRAPUP_PATTERNS = [
    r"\bdu\s*(roi|nhe|thoi|day)\b",                  # "đủ rồi / đủ nhé / đủ thôi / đủ đây"
    r"\b(the|vay)\s*thoi\b",                          # "thế thôi / vậy thôi"
    r"\bchot\s*(luon|di|nhe|thoi|nha)\b",            # "chốt luôn/đi/nhé/thôi/nha"
    r"\bxong\s*(roi|nhe)\b",                          # "xong rồi"
    r"\bkhong\s*(can|muon)\s*(hoi\s*)?(them|nua)\b",  # "không cần/muốn hỏi thêm/nữa"
    r"\bdung\s*(lai|o\s*day)\b",                      # "dừng lại / dừng ở đây"
    r"\btam\s*du\b",                                  # "tạm đủ"
    r"\bbay\s*nhieu\s*(la\s*)?(du|duoc)\b",           # "bấy nhiêu là đủ/được"
]


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt + đ→d, về ASCII thường (cho match high-precision)."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def detect_wrapup(text: str) -> bool:
    """True nếu khách phát tín hiệu KẾT THÚC tư vấn ("đủ rồi / chốt / thế thôi…").

    Luật ngôn ngữ high-precision (không khoá case nghiệp vụ). Gọi có GATE ở
    chat_service: chỉ khi đang hỏi 1 field tư vấn C1-C9 (bonus)."""
    norm = _strip_accents(text or "")
    return any(re.search(p, norm) for p in _WRAPUP_PATTERNS)


def detect_address_form(messages: list[dict[str, Any]], default: str = "anh") -> str:
    """Suy cách GỌI khách ("anh" / "chi") từ cách khách tự xưng trong lịch sử.

    Quét tin nhắn của khách (source="user"). Ưu tiên "chi" nếu có dấu hiệu rõ
    (vì mặc định đã là "anh"). Sticky tự nhiên: cue nằm trong lịch sử nên tính lại
    mỗi lượt vẫn ra kết quả ổn định. Trả "anh"/"chi" (khớp guard hậu-lượt).
    """
    texts = [
        (m.get("text") or "").lower()
        for m in messages
        if (m.get("source") or "") == "user"
    ]
    if any(re.search(p, t) for t in texts for p in _CHI_SELF_REF):
        return "chi"
    if any(re.search(p, t) for t in texts for p in _ANH_SELF_REF):
        return "anh"
    return default


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
