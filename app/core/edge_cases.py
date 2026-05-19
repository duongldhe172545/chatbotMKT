"""Edge case handlers — Phase 3 R4 (refer File 1C).

Phase 3 R4 cover 4 edge case ưu tiên:
1. Defensive lặp 3 cấp (§ 2) — escalation L1 / L2 / L3
2. Refusal lặp OPTIONAL (§ 4) — 3 slot OPTIONAL refuse → rút gọn mode
3. Escalation L3 (§ 13) — soft-end + flag ESCALATION + queue HIGH
4. Phone invalid 3 lần (§ 12) — flag PHONE_INVALID_AFTER_RETRY + queue MED

API:
- handle_defensive_escalation(session) → (reply, should_close)
- handle_optional_refusal_streak(session) → tăng counter + flag nếu 3
- check_phone_retry_exhausted(session) → trigger flag nếu 3 retry fail
- raise_escalation(session, reason) → flag ESCALATION + flag liên quan
"""
from __future__ import annotations

import logging
from typing import Optional

from app.admin.queue import increment_flag_count
from app.models.enums import Flag
from app.models.schema import SessionState
from app.slots.definitions import REQUIRED_SLOTS, is_required

logger = logging.getLogger(__name__)


# ============================================================
# 1 + 3. Defensive lặp 3 cấp + Escalation L3
# ============================================================

DEFENSIVE_L1_TEMPLATE = (
    "Dạ anh yên tâm — em không thu phí gì đâu ạ, em chỉ thu thập thông "
    "tin để team bên em hỗ trợ anh tốt hơn. Dữ liệu em lưu nội bộ, không "
    "share ra ngoài. Mình tiếp tục được không ạ?"
)

DEFENSIVE_L2_TEMPLATE = (
    "Dạ em hiểu anh ngại — em chỉ cần vài thông tin cơ bản thôi ạ. Anh "
    "không trả lời câu nào cũng không sao, em ghi nhận và bỏ qua thôi."
)

DEFENSIVE_L3_TEMPLATE = (
    "Dạ vâng em hiểu anh ngại — em không hỏi thêm gì nữa nhé. Em ghi "
    "nhận thông tin anh đã chia sẻ và sẽ không spam anh đâu ạ. Cảm ơn "
    "anh đã dành thời gian, em chúc anh kinh doanh thuận lợi! 🌷"
)


def handle_defensive_escalation(session: SessionState) -> tuple[str, bool]:
    """Xử defensive theo cấp — refer 1C § 2.

    Args:
        session: SessionState (đã raise DEALER_TOO_DEFENSIVE flag bởi caller)

    Returns:
        (reply_text, should_close_session)

    Logic:
    - Lần 1: trả L1 template (đầy đủ + cam kết)
    - Lần 2: trả L2 template (ngắn + offer skip)
    - Lần 3+: trả L3 template + raise ESCALATION + close session
    """
    count = session.flag_counts.get(Flag.DEALER_TOO_DEFENSIVE.value, 0)

    if count <= 1:
        return (DEFENSIVE_L1_TEMPLATE, False)
    if count == 2:
        return (DEFENSIVE_L2_TEMPLATE, False)
    # count >= 3 → L3 escalation
    raise_escalation(session, reason="defensive_x3")
    return (DEFENSIVE_L3_TEMPLATE, True)


def raise_escalation(session: SessionState, reason: str) -> None:
    """Raise flag ESCALATION + log lý do. Caller responsable cho close session.

    Args:
        session: SessionState
        reason: Lí do escalate (vd "defensive_x3", "abuse_x2", "address_blacklist")
    """
    increment_flag_count(session, Flag.ESCALATION)
    logger.warning(
        "Escalation L3 raised: session=%s reason=%s",
        session.session_id, reason,
    )


# ============================================================
# 2. Refusal lặp OPTIONAL — refer 1C § 4
# ============================================================

RUSH_MODE_OFFER_TEMPLATE = (
    "Dạ vâng anh ơi, em hỏi xíu — anh có muốn em rút gọn phần thu thập "
    "không ạ? Em chỉ hỏi 1-2 ý quan trọng nhất rồi mình kết thúc nha, "
    "tiết kiệm thời gian cho anh."
)

# Threshold: 3 OPTIONAL refuse liên tiếp
OPTIONAL_REFUSAL_THRESHOLD = 3


def record_optional_refusal(session: SessionState) -> bool:
    """Tăng counter optional refusal. Reset nếu dealer trả lời ok ở slot khác.

    Args:
        session: SessionState

    Returns:
        True nếu vừa đạt threshold (cần offer rush_mode), False nếu chưa.
    """
    session.consecutive_optional_refusal += 1
    if session.consecutive_optional_refusal >= OPTIONAL_REFUSAL_THRESHOLD:
        if Flag.MULTIPLE_REFUSAL_IN_ROW not in session.flags:
            increment_flag_count(session, Flag.MULTIPLE_REFUSAL_IN_ROW)
            logger.info(
                "Multiple refusal threshold reached: session=%s count=%d",
                session.session_id, session.consecutive_optional_refusal,
            )
            return True
    return False


def reset_optional_refusal(session: SessionState) -> None:
    """Reset counter khi dealer ADVANCE (cho slot)."""
    session.consecutive_optional_refusal = 0


def enter_rush_mode(session: SessionState) -> None:
    """Bật rush_mode — engine chỉ hỏi REQUIRED còn lại."""
    session.rush_mode = True
    logger.info("Rush mode enabled: session=%s", session.session_id)


def should_skip_in_rush_mode(session: SessionState, slot_id: str) -> bool:
    """True nếu đang rush_mode + slot là OPTIONAL → skip.

    REQUIRED slot vẫn phải hỏi (rush_mode chỉ skip OPTIONAL).
    """
    if not session.rush_mode:
        return False
    return not is_required(slot_id)


# ============================================================
# 4. Phone invalid 3 lần — refer 1C § 12
# ============================================================

PHONE_RETRY_THRESHOLD = 3


def check_phone_retry_exhausted(session: SessionState) -> bool:
    """Check slot 1.3 đã retry ≥ 3 lần fail chưa.

    Caller gọi sau khi extract slot 1.3 fail (phone validator reject).

    Returns:
        True nếu vừa đạt threshold (caller flag + SKIP slot).
    """
    attempts = session.slot_attempts.get("1.3")
    if attempts is None:
        return False
    if attempts.total >= PHONE_RETRY_THRESHOLD:
        if Flag.PHONE_INVALID_AFTER_RETRY not in session.flags:
            increment_flag_count(session, Flag.PHONE_INVALID_AFTER_RETRY)
            logger.warning(
                "Phone retry exhausted: session=%s attempts=%d",
                session.session_id, attempts.total,
            )
            return True
    return False


# ============================================================
# Helpers
# ============================================================


def is_session_escalated(session: SessionState) -> bool:
    """True nếu session đã raise ESCALATION → caller close + Closing rút gọn."""
    return Flag.ESCALATION in session.flags


# ============================================================
# 5. Tâm sự kéo dài — refer 1C § 3
# ============================================================

TAM_SU_L1_TEMPLATE = (
    "Dạ em hiểu mà ạ. Anh chia sẻ em rất quý. À cho em hỏi tiếp xíu nhé?"
)

TAM_SU_L2_TEMPLATE = (
    "Em nghe mà thấy thương anh thật ạ. Phần này em ghi lại để team người "
    "thật bên em có dịp trò chuyện kỹ hơn với anh sau. Mình tiếp tục phần "
    "thu thập xíu được không anh?"
)

TAM_SU_L3_TEMPLATE = (
    "Dạ em hiểu mà anh — em ghi nhận hết những gì anh chia sẻ. Em note "
    "lại để team người thật sau có dịp chuyện trò kỹ hơn ạ. Mình ngừng "
    "tại đây nhé, cảm ơn anh đã dành thời gian 🌷"
)


def handle_tam_su_escalation(session: SessionState) -> tuple[str, bool]:
    """Xử tâm sự theo cấp — refer 1C § 3.

    Caller tăng `session.consecutive_tam_su` TRƯỚC khi gọi.
    Reset counter khi intent ≠ TAM_SU.

    Returns:
        (reply, should_close)

    Logic:
    - count=1: L1 nhẹ (engage 1 nhịp)
    - count=2: L1 (engage nhịp 2)
    - count=3-4: L2 (polite cut + offer quay slot)
    - count≥5: L3 (soft-end + raise ESCALATION)
    """
    count = session.consecutive_tam_su
    if count <= 2:
        return (TAM_SU_L1_TEMPLATE, False)
    if count <= 4:
        return (TAM_SU_L2_TEMPLATE, False)
    # count ≥ 5 → L3
    raise_escalation(session, reason=f"tam_su_x{count}")
    return (TAM_SU_L3_TEMPLATE, True)


def record_tam_su(session: SessionState) -> int:
    """Tăng counter tâm sự. Return new count."""
    session.consecutive_tam_su += 1
    return session.consecutive_tam_su


def reset_tam_su(session: SessionState) -> None:
    """Reset counter khi dealer ngừng tâm sự."""
    session.consecutive_tam_su = 0
