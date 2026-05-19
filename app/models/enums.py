"""Em Linh MKT v8 — enum definitions.

Refer:
- F2A.1 (Stage), F2A.2 (Intent), F2A.4 (Action), F2A.6 (DealerType)
- F2A.3 (Flag enum 15) — STRATEGY D12
- F2C.8 (Priority, QueueStatus)
- GLOSSARY § Action, § Flag, § Intent
"""
from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    """4 stage forward-only. Refer F2A.1 + D2 STRATEGY."""
    GREETING = "GREETING"
    ASKING = "ASKING"
    CONFIRMING = "CONFIRMING"
    DONE = "DONE"


class Action(str, Enum):
    """6 action state machine. Refer F2A.4 + GLOSSARY § Action + D11 STRATEGY."""
    ADVANCE = "ADVANCE"                  # Slot fill HIGH → chuyển slot kế
    RETRY = "RETRY"                      # Slot REQUIRED empty, consecutive < 2 và total < 3 → hỏi lại
    PARTIAL_RETRY = "PARTIAL_RETRY"      # Slot multi-field fill 1 phần — KHÔNG count attempts
    DEFER = "DEFER"                      # REQUIRED đã 2 consecutive → tạm gác, đi slot khác
    SKIP = "SKIP"                        # OPTIONAL "không biết" / REQUIRED hết 3 total
    PAUSE = "PAUSE"                      # Defensive / tâm sự — không advance slot


class Intent(str, Enum):
    """7 intent. Refer F2A.2 + GLOSSARY § Intent."""
    AFFIRMATIVE = "affirmative"          # ok / ừ / chuẩn / được
    REFUSAL = "refusal"                  # đéo cho / không nói / miễn cho tôi
    KHONG_BIET = "khong_biet"            # không biết / không nhớ / tùy em
    DEFENSIVE = "defensive"              # lừa đảo à / phí gì / em là ai
    TAM_SU = "tam_su"                    # vợ / nhậu / golf / stress
    EDIT = "edit"                        # sửa X thành Y (chỉ valid stage CONFIRMING)
    NORMAL = "normal"                    # default — không match marker nào


class DealerType(str, Enum):
    """4 nhóm dealer + unknown (default 'ban' khi confidence thấp).

    Refer F2A.6 detect turn 3/8/13 + 1B § 2 tone matrix.
    """
    LUA_LO = "lua_lo"                    # Cộc, caps, chửi bậy
    KHOE = "khoe"                        # Kể thành tích, số liệu
    LO = "lo"                            # Nghi ngờ, hỏi ngược
    BAN = "ban"                          # 1-2 chữ, đi thẳng (default)
    UNKNOWN = "unknown"                  # Chưa đủ data — fallback "ban"


class ConfirmationStatus(str, Enum):
    """Trạng thái xác nhận card. Refer F2A.7 sanity check."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EDITED = "EDITED"


class ReviewStatus(str, Enum):
    """Trạng thái review admin. Refer F2C.8."""
    RAW = "RAW"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Flag(str, Enum):
    """15 flag chia 4 nhóm.

    Refer F2A.3 enum + GLOSSARY § 4 + KE_HOACH § 2.3 + STRATEGY D12.
    """
    # ----- Behavior (4) — dealer chủ động từ chối / skip -----
    DEALER_DECLINED = "dealer_declined"
    REQUIRED_MISSING = "required_missing"
    CONSENT_UNCLEAR = "consent_unclear"
    MULTIPLE_REFUSAL_IN_ROW = "multiple_refusal_in_row"

    # ----- Abuse (5) — dealer vi phạm / data nguy hiểm -----
    PROMPT_INJECTION = "prompt_injection"
    ABUSIVE_LANGUAGE = "abusive_language"
    GARBAGE_INPUT = "garbage_input"
    DEALER_TOO_DEFENSIVE = "dealer_too_defensive"
    ADDRESS_BLACKLIST = "address_blacklist"

    # ----- Escalation (1) — Phase 3 R4 (refer 1C § 13) -----
    # Tổng hợp khi bot quyết soft-end session (defensive 3 lần, abuse 2 lần,
    # address blacklist, prompt_injection 3 lần). Trigger admin queue HIGH.
    ESCALATION = "escalation"

    # ----- Data quality (4) — lỗi format / data chưa whitelist -----
    SANITY_CHECK_FAILED = "sanity_check_failed"
    PHONE_INVALID_AFTER_RETRY = "phone_invalid_after_retry"
    VOICE_QUALITY_POOR = "voice_quality_poor"
    BRAND_NOT_IN_WHITELIST = "brand_not_in_whitelist"

    # ----- LLM guard (2) — bot lỗi -----
    HALLUCINATE = "hallucinate"
    PII_LEAK = "pii_leak"


class AddressForm(str, Enum):
    """Cách xưng hô. Refer 1A § 2.1."""
    ANH = "anh"
    CHI = "chị"


class Priority(str, Enum):
    """Admin queue priority. Refer F2C.8."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class QueueStatus(str, Enum):
    """Admin queue status. Refer F2C.8."""
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Channel(str, Enum):
    """Source channel của session."""
    WEB = "web"
    ZALO = "zalo"
    FB = "fb"
    VOICE = "voice"   # Phase 4 R2 — STT voice channel (refer 1C § 8)
