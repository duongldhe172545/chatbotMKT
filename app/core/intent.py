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
    CONFUSION_PATTERNS,
    DEFENSIVE_PATTERNS,
    EDIT_PATTERNS,
    KHONG_BIET_PATTERNS,
    REFUSAL_PATTERNS,
    TAM_SU_PATTERNS,
    TECHNICAL_INQUIRY_PATTERNS,
)
from app.models.enums import Intent


# Priority list — order quyết định kết quả nếu message match nhiều intent
# CONFUSION priority TRƯỚC DEFENSIVE/TAM_SU: "là sao?" có thể match nhiều
# pattern nhưng confusion là intent dealer cần giải thích (CORE D.1).
_INTENT_PRIORITY: list[tuple[Intent, list[str]]] = [
    (Intent.CONFUSION, CONFUSION_PATTERNS),  # CORE D.1 — chủ động giải thích
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

    Note: KHONG_BIET/REFUSAL pattern chỉ áp dụng cho message NGẮN
    (≤ 25 từ). Message dài là dealer KỂ chứ không phải refuse — tránh
    false positive như "anh không nhớ ra đã làm gì cho họ" (dealer kể
    pain, không phải nói "không biết").
    """
    if not message or not message.strip():
        return None

    msg_lower = message.strip().lower()
    word_count = len(msg_lower.split())
    skip_short_intents = word_count > 25

    for intent, patterns in _COMPILED:
        # Bỏ qua KHONG_BIET / REFUSAL cho message dài
        if skip_short_intents and intent in (Intent.KHONG_BIET, Intent.REFUSAL):
            continue
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


# Pre-compile TECHNICAL_INQUIRY patterns (module-level perf)
_TECHNICAL_INQUIRY_COMPILED: list[re.Pattern] = [
    re.compile(p, _RE_FLAGS) for p in TECHNICAL_INQUIRY_PATTERNS
]

# Phase 6 R+ fix 2026-05-22 (user feedback bug slot 3.5):
# Pattern index theo TECHNICAL_INQUIRY_PATTERNS thứ tự định nghĩa:
#   0. Báo giá
#   1. Bảo hành / khiếu nại / sửa chữa  ← slot 3.5 reply data
#   2. Tư vấn kỹ thuật chuyên sâu
#   3. Hợp tác / phân phối
#   4. Pháp lý / thuế
#   5. Y tế
#   6. Tài chính cá nhân
_WARRANTY_PATTERN_INDEX = 1
_COOPERATION_PATTERN_INDEX = 3  # "hợp tác / phân phối" pattern
_BUSINESS_MODEL_DATA_RE = re.compile(
    r"\b(sản\s*xuất|lắp\s*đặt|thi\s*công|gia\s*công|bán\s*lẻ|"
    r"phân\s*phối|có\s*xưởng|đội\s*thợ|làm\s*hết|trọn\s*gói)\b",
    _RE_FLAGS,
)
_REQUEST_OR_QUESTION_RE = re.compile(
    r"\?|"
    r"\b(ai|sao|thế\s*nào|như\s*nào|bao\s*nhiêu|có\s+.*\s+không|"
    r"muốn|cần|xin|tư\s*vấn|cho\s+anh|giúp\s+anh|đăng\s*ký)\b",
    _RE_FLAGS,
)
_WARRANTY_DATA_RE = re.compile(
    r"\b(anh|bên\s+anh|team\s+(?:anh|em)|nhà\s+cung\s+cấp|bên\s+lắp\s+đặt|"
    r"thợ|đại\s+lý).{0,100}\b(bảo\s*hành|sửa\s+chữa|đổi\s+trả)\b|"
    r"\b(bảo\s+hành|sửa\s+chữa|đổi\s+trả).{0,100}\b"
    r"(anh|bên\s+anh|team\s+(?:anh|em)|nhà\s+cung\s+cấp|bên\s+lắp\s+đặt|thợ|đại\s+lý)\b",
    _RE_FLAGS,
)
_COOPERATION_DATA_RE = re.compile(
    r"\b(sản\s*xuất|gia\s*công|thi\s*công|lắp\s*đặt|bán|cung\s*cấp|"
    r"chuyên|làm|có\s+làm|vừa).{0,120}\b(phân\s*phối|đại\s*lý)\b|"
    r"\b(phân\s*phối|đại\s*lý).{0,120}\b(khác|khách|bên\s+anh|của\s+anh)\b",
    _RE_FLAGS,
)

# Map slot_id → set pattern indexes cần SKIP (vì dealer expected reply
# về topic đó, KHÔNG phải technical inquiry).
_SLOT_TECHNICAL_SKIP_MAP: dict[str, set[int]] = {
    "3.5": {_WARRANTY_PATTERN_INDEX},  # slot 3.5 hỏi warranty_responsibility
    "2.2": {_COOPERATION_PATTERN_INDEX},  # FIX C2: slot 2.2 hỏi mô hình → "phân phối" là DATA
}


def detect_technical_inquiry(
    message: str,
    current_slot: Optional[str] = None,
) -> bool:
    """CORE E.3: detect dealer hỏi câu chuyên môn ngoài tầm bot.

    7 nhóm pattern:
    1. Báo giá (giá bao nhiêu, chiết khấu)
    2. Bảo hành / khiếu nại / sửa chữa
    3. Tư vấn kỹ thuật chuyên sâu (loại nhôm/kính nào tốt, hợp biển)
    4. Hợp tác / đối tác / phân phối / nhượng quyền
    5. Pháp lý / thuế / hợp đồng
    6. Y tế (HỎI advice, không phải tâm sự)
    7. Tài chính cá nhân (vay, đầu tư)

    Phase 6 R+ fix 2026-05-22: skip pattern theo current_slot context.
    Vd slot 3.5 hỏi "bảo hành ai chịu?" → dealer reply "anh chịu bảo hành"
    là valid DATA, KHÔNG phải technical inquiry → skip pattern #2.

    Args:
        message: dealer text
        current_slot: slot đang hỏi. Nếu trong _SLOT_TECHNICAL_SKIP_MAP →
            skip pattern tương ứng (avoid false positive).

    Returns: True nếu match 1+ pattern (sau khi loại skip).
    """
    if not message or not message.strip():
        return False
    msg_lower = message.strip().lower()

    skip_indexes = _SLOT_TECHNICAL_SKIP_MAP.get(current_slot or "", set())
    for idx, pattern in enumerate(_TECHNICAL_INQUIRY_COMPILED):
        if idx in skip_indexes:
            continue
        # A description such as "anh chịu bảo hành" or "anh sản xuất và
        # phân phối cho đại lý khác" is intake data, not a request for advice.
        # This check is slot-independent because the LLM-first engine may have
        # already advanced its debug focus before the reply pipeline runs.
        if (
            idx == _WARRANTY_PATTERN_INDEX
            and _WARRANTY_DATA_RE.search(msg_lower)
            and not _REQUEST_OR_QUESTION_RE.search(msg_lower)
        ):
            continue
        if (
            idx == _COOPERATION_PATTERN_INDEX
            and (_COOPERATION_DATA_RE.search(msg_lower) or _BUSINESS_MODEL_DATA_RE.search(msg_lower))
            and not _REQUEST_OR_QUESTION_RE.search(msg_lower)
        ):
            continue
        # Slot 2.2 asks for the business model. A dealer can naturally answer
        # "vừa sản xuất vừa lắp đặt thi công bảo hành" without asking for
        # technical support. Keep a real warranty question eligible.
        if (
            idx == _WARRANTY_PATTERN_INDEX
            and current_slot == "2.2"
            and "?" not in msg_lower
            and _BUSINESS_MODEL_DATA_RE.search(msg_lower)
        ):
            continue
        if pattern.search(msg_lower):
            return True
    return False


# Reply template cho technical inquiry escalation.
# Refer CORE § E.3 + KICH_BAN_1C § 13 escalation L2.
TECHNICAL_INQUIRY_ESCALATE_TEMPLATE = (
    "Dạ cái này anh để em chuyển team chuyên môn liên hệ nhé — "
    "họ sẽ tư vấn anh kỹ hơn em nhiều ạ. Mình tiếp tục phần em "
    "đang hỏi luôn được không anh?"
)
