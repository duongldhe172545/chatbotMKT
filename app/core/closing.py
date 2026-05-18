"""Closing render — Phase 1.

Refer:
- F2A.8 (LUAT_2A_core v0.2.5) — Closing engine (KHÔNG khoá case đặc sản)
- File 1A § 7 — Closing templates + consent=no path
- CORE § H.3 + § A.3 — bot KHÔNG render trực tiếp, chỉ dẫn Zalo
- D10 STRATEGY — consent=no skip path

Nguyên tắc "không khoá case":
- Bỏ lookup table "province → đặc sản" (vd HN → phở) — ép câu robot.
- Closing chỉ truyền province làm context, để Phase 2 LLM tự gen hook
  địa phương đa dạng (không ép template).
- Phase 1: closing không có hook địa phương — template tổng quát.
"""
from __future__ import annotations

from typing import Optional


# ============================================================
# Closing templates — consent=yes path
# ============================================================


_CLOSING_CONSENT_YES_TEMPLATE = (
    "Em cảm ơn anh rất nhiều đã dành thời gian chia sẻ với em ạ! 🌷\n\n"
    "Em đã ghi nhận đầy đủ thông tin của cửa hàng mình rồi. Anh bấm vào "
    "[link ứng dụng nhỏ] — bên em **đang chuẩn bị** bộ thương hiệu "
    "(logo + danh thiếp + video) và sẽ gửi anh qua Zalo trong ít giờ tới.\n\n"
    "Nhóm Cộng Đồng Thợ 4.0 phù hợp với anh em cũng sẽ giới thiệu kèm. "
    "Trong 3 ngày tới em sẽ gửi anh kế hoạch chiến lược nền tảng số đầy "
    "đủ qua Zalo nữa nhé.\n\n"
    "Em cảm ơn anh rất nhiều! Chúc cửa hàng mình ngày càng phát đạt ạ 🌷"
)


# ============================================================
# Closing templates — consent=no path (refer D10 STRATEGY)
# ============================================================


_CLOSING_CONSENT_NO_TEMPLATE = (
    "Dạ em hiểu anh chưa cần bộ thương hiệu, em không ép đâu ạ.\n\n"
    "Em vẫn ghi nhận thông tin của cửa hàng mình. Nếu sau này anh đổi ý "
    "muốn nhận bộ thương hiệu, anh nhắn lại em nhé — bên em luôn sẵn sàng.\n\n"
    "Nhóm Cộng Đồng Thợ 4.0 phù hợp với khu vực + ngành mình em cũng sẽ "
    "giới thiệu qua Zalo trong 3 ngày tới ạ.\n\n"
    "Em cảm ơn anh rất nhiều đã dành thời gian!"
)


# ============================================================
# Soft-end templates — escalation L3 / timeout
# ============================================================


_CLOSING_SOFT_END_TEMPLATE = (
    "Dạ vâng, em ngừng tại đây ạ. Em ghi nhận thông tin anh đã chia sẻ. "
    "Team người thật bên em có thể sẽ liên hệ anh sau nếu cần hỗ trợ thêm. "
    "Em cảm ơn anh nhiều ạ 🌷"
)


# ============================================================
# Render functions
# ============================================================


def render_closing(
    province: Optional[str] = None,
    consent: Optional[str] = None,
) -> str:
    """Render closing dựa trên consent.

    Args:
        province: Reserved cho Phase 2 (LLM gen hook địa phương dựa context).
            Phase 1 không dùng — bỏ lookup table đặc sản.
        consent: brandkit_consent value ("yes"/"no"/None).

    Returns:
        Closing text Việt thuần.
    """
    del province  # Phase 1: chưa dùng. Phase 2: LLM-driven hook.

    if consent == "no":
        return _CLOSING_CONSENT_NO_TEMPLATE
    # Default: consent=yes path (cũng dùng cho consent=null nhưng pass sanity)
    return _CLOSING_CONSENT_YES_TEMPLATE


def render_soft_end_closing() -> str:
    """Render closing rút gọn cho escalation L3 / timeout.

    Refer 1C § 13 escalation script.
    """
    return _CLOSING_SOFT_END_TEMPLATE
