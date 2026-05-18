"""Greeting render — Phase 1 1 biến thể MVP.

Refer:
- F2A.8 (LUAT_2A_core v0.2.4) — Greeting + Closing engine
- File 1A § 3 — 3 biến thể Greeting
- CORE § A.3 — bot KHÔNG render quà trực tiếp (qua Zalo)
"""
from __future__ import annotations

import hashlib


# Phase 1 — 3 biến thể, chọn theo hash(session_id) mod 3
_GREETING_VARIANTS: list[str] = [
    # Biến thể 1 (chuẩn — mẫu mặc định)
    (
        "Dạ em chào anh ạ! 🌷\n\n"
        "Em là Linh, chuyên gia hỗ trợ chiến lược kinh doanh trên nền tảng số "
        "cho các anh chị làm cửa, nhôm kính, tủ bếp trong Cộng Đồng Thợ 4.0.\n\n"
        "Để chào mừng anh tham gia cộng đồng của bên em, sau cuộc trò chuyện "
        "này em xin phép tặng anh một bộ thương hiệu hoàn toàn miễn phí, "
        "bao gồm:\n\n"
        "🎨 Logo riêng cho cửa hàng\n"
        "📇 Danh thiếp cá nhân hoá\n"
        "🎬 Video giới thiệu thương hiệu\n\n"
        "Bộ thương hiệu này em sẽ gửi anh **qua Zalo** ngay sau khi mình chốt "
        "thông tin xong (bên em chuẩn bị riêng cho từng cửa hàng).\n\n"
        "Vì món quà này mang màu sắc cá nhân của riêng anh, em xin phép trao "
        "đổi với anh khoảng 4-5 phút anh nhé. Còn về phần kế hoạch chiến lược "
        "phát triển nền tảng số đầy đủ, em sẽ gửi anh trong 3 ngày tới qua "
        "Zalo ạ.\n\n"
        "Anh có thể gõ chữ, hoặc bấm mic nói cũng được hết. Mình bắt đầu nhé anh?"
    ),
    # Biến thể 2 (gọn hơn — nếu muốn nhanh)
    (
        "Dạ em chào anh!\n\n"
        "Em là Linh, hỗ trợ chiến lược nền tảng số cho các anh chị làm cửa / "
        "nhôm kính / tủ bếp trong Cộng Đồng Thợ 4.0.\n\n"
        "Sau khi trò chuyện ngắn này (4-5 phút), em **gửi qua Zalo** cho anh "
        "một bộ thương hiệu gồm:\n"
        "🎨 Logo\n"
        "📇 Danh thiếp\n"
        "🎬 Video giới thiệu\n\n"
        "Và trong 3 ngày tới em gửi anh kế hoạch chiến lược nền tảng số đầy "
        "đủ qua Zalo.\n\n"
        "Anh sẵn sàng bắt đầu chưa ạ?"
    ),
    # Biến thể 3 (thân mật hơn — phù hợp dealer trẻ)
    (
        "Em chào anh ạ 🌷\n\n"
        "Em là Linh, em phụ trách hỗ trợ chiến lược nền tảng số bên Cộng Đồng "
        "Thợ 4.0 — chuyên cho các anh chị làm cửa, nhôm kính, tủ bếp.\n\n"
        "Sau 4-5 phút chuyện trò này, em **gửi qua Zalo** cho anh bộ thương "
        "hiệu riêng cho cửa hàng:\n"
        "🎨 Logo + 📇 Danh thiếp + 🎬 Video giới thiệu\n\n"
        "Trong 3 ngày tới em cũng gửi anh kế hoạch nền tảng số đầy đủ qua Zalo "
        "nữa nhé.\n\n"
        "Anh ok mình bắt đầu chưa ạ?"
    ),
]


def render_greeting(session_id: str) -> str:
    """Render greeting cho session.

    Refer 1A § 1.2 rotation: hash(session_id) mod 3 → biến thể cố định trong session.

    Args:
        session_id: UUID session

    Returns:
        Greeting text Việt thuần.
    """
    if not session_id:
        return _GREETING_VARIANTS[0]
    variant = _hash_to_variant(session_id, num_variants=len(_GREETING_VARIANTS))
    return _GREETING_VARIANTS[variant]


def _hash_to_variant(key: str, num_variants: int) -> int:
    """Hash deterministic → variant index. Refer 1A § 1.2."""
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h, 16) % num_variants


def get_num_variants() -> int:
    """Số biến thể greeting hiện có."""
    return len(_GREETING_VARIANTS)
