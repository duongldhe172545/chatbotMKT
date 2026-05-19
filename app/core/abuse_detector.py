"""Personal abuse detector — refer KICH_BAN_1C § 5.

Phân biệt 2 loại "chửi":
- Lửa Lò chửi chung ("đm em hỏi nhiều thế") → tone marker, KHÔNG flag abuse
- Personal abuse ("đm con bot này ngu") → tấn công bot/em → flag ABUSIVE_LANGUAGE
  + 3 cấp escalation tương tự defensive (L1/L2/L3).

3 cấp pattern (1C § 5):
- L1: bot polite "Dạ em xin lỗi nếu làm phiền, em tiếp tục phần hỏi"
- L2: offer dừng "Nếu phần này anh không muốn tiếp, em dừng lại cũng được"
- L3: soft-end "Dạ vâng, em ngừng tại đây. Em ghi nhận thông tin..."
       → flag ESCALATION + queue HIGH

API:
- is_personal_abuse(message) → bool (regex Layer 1)
- handle_abuse_escalation(session) → (reply, should_close)
"""
from __future__ import annotations

import logging
import re

from app.admin.queue import increment_flag_count
from app.core.edge_cases import raise_escalation
from app.core.regex_markers import PERSONAL_ABUSE_PATTERNS
from app.models.enums import Flag
from app.models.schema import SessionState

logger = logging.getLogger(__name__)


_COMPILED_ABUSE = [
    re.compile(p, re.IGNORECASE | re.UNICODE) for p in PERSONAL_ABUSE_PATTERNS
]


def is_personal_abuse(message: str | None) -> bool:
    """True nếu message chứa pattern abuse cá nhân bot/em.

    Args:
        message: User raw message

    Returns:
        True nếu match ≥ 1 pattern PERSONAL_ABUSE.
    """
    if not message or not isinstance(message, str):
        return False
    for pattern in _COMPILED_ABUSE:
        if pattern.search(message):
            logger.warning(
                "Personal abuse detected: pattern=%r message=%r",
                pattern.pattern, message[:150],
            )
            return True
    return False


# ============================================================
# Abuse escalation 3 cấp (1C § 5)
# ============================================================

ABUSE_L1_TEMPLATE = (
    "Dạ em xin lỗi nếu làm phiền anh ạ. Em tiếp tục phần hỏi nhé."
)

ABUSE_L2_TEMPLATE = (
    "Dạ anh ơi, nếu phần này anh không muốn tiếp, em dừng lại cũng "
    "được ạ. Em không muốn làm phiền anh đâu."
)

ABUSE_L3_TEMPLATE = (
    "Dạ vâng, em ngừng tại đây ạ. Em ghi nhận thông tin anh đã chia "
    "sẻ, cảm ơn anh nhiều ạ."
)


def handle_abuse_escalation(session: SessionState) -> tuple[str, bool]:
    """Xử abuse theo cấp — refer 1C § 5.

    Caller PHẢI increment_flag_count(ABUSIVE_LANGUAGE) TRƯỚC khi gọi
    hàm này (để count count chính xác).

    Args:
        session: SessionState

    Returns:
        (reply_text, should_close_session)

    Logic:
    - count=1 (L1): bot polite tiếp slot
    - count=2 (L2): bot offer dừng (chưa close)
    - count≥3 (L3): bot soft-end + raise ESCALATION
    """
    count = session.flag_counts.get(Flag.ABUSIVE_LANGUAGE.value, 0)

    if count <= 1:
        return (ABUSE_L1_TEMPLATE, False)
    if count == 2:
        return (ABUSE_L2_TEMPLATE, False)
    # count >= 3 → L3
    raise_escalation(session, reason=f"abuse_x{count}")
    return (ABUSE_L3_TEMPLATE, True)


# ============================================================
# Address blacklist 3 cấp (1C § 10)
# ============================================================

ADDRESS_BL_L1_TEMPLATE = (
    "Dạ em xin lại địa chỉ chính xác giúp em ạ — em chỉ cần tỉnh + "
    "quận thôi cũng được."
)

ADDRESS_BL_L2_TEMPLATE = (
    "Dạ vâng em ghi nhận. Em không cần địa chỉ cụ thể, anh chỉ cần "
    "cho em tỉnh thôi nhé."
)

ADDRESS_BL_L3_TEMPLATE = (
    "Dạ vâng em ghi nhận. Em tạm dừng phần này, có gì team người "
    "thật sẽ liên hệ anh sau ạ."
)


def handle_address_blacklist_escalation(session: SessionState) -> tuple[str, bool]:
    """Xử address blacklist theo cấp — refer 1C § 10.

    Caller đã increment_flag_count(ADDRESS_BLACKLIST) TRƯỚC khi gọi.

    Returns:
        (reply_text, should_close_session)
    """
    count = session.flag_counts.get(Flag.ADDRESS_BLACKLIST.value, 0)
    if count <= 1:
        return (ADDRESS_BL_L1_TEMPLATE, False)
    if count == 2:
        return (ADDRESS_BL_L2_TEMPLATE, False)
    # count >= 3 → L3
    raise_escalation(session, reason=f"address_blacklist_x{count}")
    return (ADDRESS_BL_L3_TEMPLATE, True)
