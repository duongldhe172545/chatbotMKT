"""Detect xưng hô anh/chị từ tên + lời dealer.

Logic 3 tín hiệu (theo thứ tự ưu tiên):
1. Dealer tự xưng "chị" / "em là nữ" → "chị"
2. owner_name có dấu hiệu nữ rõ ràng → "chị"
3. Default → "anh" (~85% dealer ngành cửa/tủ/VLXD là nam)

Một khi chốt → giữ nhất quán suốt phiên (xem ConversationService).
Tên ambiguous (Hà, Linh, Anh, Sơn, Thanh) → giữ "anh" mặc định, KHÔNG
đoán bừa, để dealer correct nếu sai.
"""
from __future__ import annotations


# Tên nữ Việt Nam phổ biến — dùng để detect xưng hô.
# Chỉ những tên KHÁ rõ là nữ (không gồm Hà, Anh, Linh, Sơn, Thanh — ambiguous).
_FEMALE_NAMES = {
    "hương", "lan", "mai", "trang", "hoa", "hà", "nhung", "loan",
    "hằng", "vy", "phương", "thuỳ", "thùy", "diệu", "nga", "yến",
    "thảo", "vân", "quyên", "thuý", "thúy", "ngọc", "linh", "anh thư",
    "bảo châu", "bích", "hạnh", "tâm",
}


def detect_address_form(text: str, owner_name: str | None) -> str:
    """Detect xưng hô 'anh' hay 'chị'.

    Args:
        text: latest dealer message (để tìm tự xưng / correct)
        owner_name: tên đã extract (để check female name)

    Returns:
        "anh" hoặc "chị"
    """
    if text:
        low = text.lower()
        # Tự xưng nữ rõ ràng
        if "em là nữ" in low or "tôi là nữ" in low or "tao là nữ" in low:
            return "chị"
        # Dealer tự xưng "chị" trong câu (vd "chị tên...", "chị bán...")
        if low.startswith("chị ") or " chị " in low or low.startswith("chị,"):
            # Loại false positive: "đừng gọi chị là anh" (correct case riêng)
            if "đừng gọi" not in low:
                return "chị"
        # Correct case sau khi bot gọi nhầm
        if "đừng gọi" in low and "anh" in low and ("chị" in low or "nữ" in low):
            return "chị"

    # Detect by name (last word usually is given name in VN)
    if owner_name:
        parts = owner_name.lower().strip().split()
        if parts:
            last_name = parts[-1]
            if last_name in _FEMALE_NAMES:
                return "chị"

    return "anh"