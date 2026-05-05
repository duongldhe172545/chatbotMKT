"""Source-of-truth cho mọi label hiển thị tiếng Việt.

Backend (card_renderer, conversation) import từ đây.
Frontend fetch qua endpoint GET /api/labels — admin.js không hardcode nữa.

Khi thêm category / priority mới, CHỈ sửa file này, frontend tự cập nhật.
"""
from __future__ import annotations

CATEGORY_LABEL: dict[str, str] = {
    "cua_cuon": "cửa cuốn",
    "cua_nhom_kinh": "cửa nhôm kính",
    "cua_thep": "cửa thép",
    "tu_bep": "tủ bếp",
    "solar": "solar / năng lượng mặt trời",
    "bao_tri_sua_chua": "bảo trì sửa chữa",
    "vlxd_tong_hop": "VLXD tổng hợp",
}

PRIORITY_LABEL: dict[str, str] = {
    "bo_mat_so": "bộ mặt số",
    "qr_khach_cu": "QR gửi khách cũ",
    "bai_dang": "bài đăng",
    "tro_ly_tu_van": "trợ lý tư vấn",
}

DEALER_TYPE_LABEL: dict[str, str] = {
    "dai_ly": "đại lý / cửa hàng bán lẻ",
    "chu_xuong": "chủ xưởng / xưởng sản xuất",
    "tho_doi": "thợ đội / thợ làm trực tiếp",
    "nha_thau_nho": "nhà thầu nhỏ",
    "s_dich_vu": "cơ sở dịch vụ",
    "khac": "khác",
}

# Tên field hiển thị trong message "đã cập nhật"
FIELD_LABEL: dict[str, str] = {
    "dealer_name": "Tên đại lý",
    "owner_name": "Người phụ trách",
    "phone_or_zalo": "Zalo/SĐT",
    "province": "Tỉnh/thành",
    "district": "Quận/huyện",
    "main_category": "Ngành chính",
    "dealer_type": "Loại dealer",
    "customer_base_estimate": "Khách cũ ước lượng",
    "pain_points": "Đau nhất",
    "dl0_priority": "Ưu tiên hỗ trợ",
}

# Label cho flag (admin UI hiển thị badge)
FLAG_LABEL: dict[str, dict] = {
    "phone_suspicious": {"text": "SĐT giả?", "cls": "flag-warn"},
    "name_suspicious": {"text": "Tên giả?", "cls": "flag-warn"},
    "abusive_language": {"text": "Chửi", "cls": "flag-bad"},
    "abusive_persistent": {"text": "Chửi nhiều", "cls": "flag-bad"},
    "prompt_injection_attempt": {"text": "Prompt inject", "cls": "flag-bad"},
    "escalation_requested": {"text": "Xin gặp người thật", "cls": "flag-info"},
    "garbage_input": {"text": "Nhập linh tinh", "cls": "flag-warn"},
    "spam_suspect": {"text": "Nghi spam", "cls": "flag-bad"},
    "dealer_paused": {"text": "Tạm dừng", "cls": "flag-info"},
}


def all_labels() -> dict:
    """Gom toàn bộ label cho endpoint /api/labels."""
    return {
        "category": CATEGORY_LABEL,
        "priority": PRIORITY_LABEL,
        "dealer_type": DEALER_TYPE_LABEL,
        "field": FIELD_LABEL,
        "flag": FLAG_LABEL,
    }
