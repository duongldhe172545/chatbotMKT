"""Greeting render — Phase 6 R+ 1 biến thể duy nhất.

Refer:
- F2A.8 (LUAT_2A_core v0.2.4) — Greeting + Closing engine
- File 1A § 3 — Greeting (1 biến thể chính thức, user-approved 2026-05-22)
- CORE § A.3 — bot KHÔNG render quà trực tiếp (qua Zalo)
"""
from __future__ import annotations


# Phase 6 R+ 2026-05-22 (user feedback): bỏ rotation 3 variant, chốt 1
# variant duy nhất (variant chuẩn user-approved).
_GREETING_TEXT: str = (
    "Dạ em chào anh ạ! 🌷\n\n"
    "Em là Linh, chuyên gia hỗ trợ chiến lược kinh doanh trên nền tảng số "
    "cho các anh chị làm cửa, nhôm kính, tủ bếp, điện mặt trời trong Cộng Đồng Thợ 4.0.\n\n"
    "Để chào mừng anh tham gia cộng đồng của bên em, sau cuộc trò chuyện "
    "này em xin phép tặng anh một bộ thương hiệu hoàn toàn miễn phí, "
    "bao gồm:\n\n"
    "🎁 Logo riêng cho cửa hàng\n"
    "🎁 Danh thiếp cá nhân hoá\n"
    "🎁 Video giới thiệu thương hiệu\n\n"
    "Vì món quà này mang màu sắc cá nhân của riêng anh, em xin phép trao "
    "đổi với anh khoảng 4-5 phút anh nhé. Bộ thương hiệu và kế hoạch chi "
    "tiết về chiến lược phát triển nền tảng số em sẽ gửi anh qua Zalo "
    "trong thời gian sớm nhất sau đó ạ.\n\n"
    "Anh có thể gõ chữ, hoặc bấm mic nói cũng được hết. Mình bắt đầu nhé anh?"
)


def render_greeting(session_id: str) -> str:  # noqa: ARG001
    """Render greeting cho session.

    Phase 6 R+: 1 biến thể duy nhất — trả thẳng _GREETING_TEXT, không cần
    hash rotation. session_id giữ lại trong signature để backward-compat
    với caller (start_session, tests).

    Args:
        session_id: UUID session (không dùng, giữ cho backward-compat)

    Returns:
        Greeting text Việt thuần.
    """
    return _GREETING_TEXT


def get_num_variants() -> int:
    """Số biến thể greeting hiện có (Phase 6 R+: luôn = 1)."""
    return 1
