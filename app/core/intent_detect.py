"""Intent classification — detect 3 loại message dealer bằng keyword.

ConversationService dùng các function ở đây để chọn Goal cho Replier:
- TÂM SỰ → ENGAGE_TAM_SU (engage chuyện đời thường)
- DEFENSIVE → ANSWER_DEFENSIVE (trả lời nghi ngờ)
- REFUSAL → HANDLE_REFUSAL (respect skip + chuyển field)

Loại "thông thường" (A — cho data) và "trêu/cộc" (D) không cần detect riêng —
Replier tự xử dựa trên prompt principles.

Triết lý: keyword match RỘNG (capture đa số) thay vì regex CHÍT (miss nhiều).
False positive (vd: dealer kể chuyện công trình mà bị flag tâm sự) chấp nhận
được vì Replier vẫn engage tự nhiên.
"""
from __future__ import annotations


# ============================================================
# (C) TÂM SỰ — dealer kể chuyện đời thường
# ============================================================
# Khi detect → KHÔNG inject target_field hint, để Replier tự engage chuyện đó
# trước rồi mới dẫn về field.
_TAM_SU_KEYWORDS = (
    "vợ", "chồng", "bạn gái", "bạn trai", "ny", "gấu",
    "con", "gia đình", "ba mẹ", "bố mẹ", "bố", "mẹ",
    "nhậu", "say", "đau đầu", "mệt", "ốm", "bệnh", "viện", "đau",
    "golf", "bóng", "đá bóng", "tennis", "bida", "gym", "tập",
    "buồn", "chán", "stress", "căng thẳng", "đời", "tâm sự",
    "cãi nhau", "cãi cọ", "hết tiền", "kẹt tiền", "dịch bệnh",
    "công trình", "lắp đặt", "đi khách", "khách hàng khó",
)


def is_tam_su_message(text: str) -> bool:
    """Detect message dealer là tâm sự / off-topic / đời thường.

    Khi True → inject ENGAGE_TAM_SU hint cho Replier để engage 1-2 nhịp
    về chính chuyện đó trước, rồi mới dẫn về field.
    """
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in _TAM_SU_KEYWORDS)


# ============================================================
# (B) DEFENSIVE — dealer hỏi ngược / nghi ngờ
# ============================================================
# Khi detect → BẮT BUỘC trả lời câu hỏi của dealer TRƯỚC, rồi mới dẫn field.
_DEFENSIVE_KEYWORDS = (
    # Benefit/lợi ích
    "được lợi", "được gì", "lợi gì", "có gì hay", "có ích gì", "có lợi gì",
    # Fraud/lừa đảo
    "lừa đảo", "lừa", "đa cấp", "scam", "tổ chức gì",
    # Cost/phí
    "miễn phí thật", "có phí", "tốn tiền", "thu phí", "trả phí", "miễn phí không",
    "tiền không", "đắt không", "rẻ không",
    # Privacy/data
    "spam", "lấy data", "lấy thông tin", "lấy số", "bán data", "bán thông tin",
    "lấy data ở đâu", "data ở đâu", "data từ đâu", "ai cấp", "ai cho",
    "có quyền xoá", "xoá dữ liệu", "xoá data", "gdpr", "bảo mật",
    "thông tin của tao có ai biết", "ai biết về tao",
    # Identity/legitimacy
    "ai làm", "em là ai", "mày là ai", "bot à", "có thật",
    "thật không", "có chuẩn", "uy tín",
    "tin được không", "tin tưởng được",
    "công ty nào", "ai chủ", "thuộc công ty", "của công ty nào",
    "có hợp pháp", "hợp pháp không", "có giấy phép",
    "chính chủ", "có chính chủ",
    # Time/availability
    "tao bận", "không có thời gian", "rảnh đâu",
)


def is_defensive_message(text: str) -> bool:
    """Detect dealer đang hỏi ngược / dò xét / nghi ngờ (Loại B).

    Khi True:
    - KHÔNG inject target_field hint (tránh LLM bơ câu hỏi để hỏi field).
    - Inject directive ANSWER_DEFENSIVE — bắt buộc trả lời câu hỏi dealer trước.
    """
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in _DEFENSIVE_KEYWORDS)


# ============================================================
# REFUSAL — dealer từ chối cung cấp 1 field cụ thể
# ============================================================
# Khi detect → bot ack respect + skip field đó, không spam câu hỏi cũ.
# Re-ask logic: skipped field có thể được hỏi lại sau khi dealer fill ≥2 field
# khác (xem ConversationService._weak_required_fields).
_REFUSAL_KEYWORDS = (
    "đéo cho", "deo cho", "không cho", "khong cho",
    "không tiện", "khong tien", "ko tiện", "ko cho",
    "không nói", "khong noi", "đéo nói", "deo noi",
    # "miễn" alone overlap với "miễn phí thật?" (defensive). Bó cụm cụ thể:
    "thôi miễn", "thoi mien", "xin miễn", "xin mien",
    "miễn cho tôi", "miễn cho em", "miễn cho anh",
    "thôi không", "thoi khong", "không có",
    "bỏ qua", "bo qua", "skip",
)


def is_refusal_message(text: str) -> bool:
    """Detect dealer từ chối cung cấp field hiện tại.

    Khi True → REFUSAL handler:
    - Mark skipped + ghi nhận filled_count tại thời điểm skip
    - Bot ack tôn trọng + chuyển sang field khác (qua Replier HANDLE_REFUSAL)

    Lọc false positive: "không có thời gian" thuộc busy không phải refusal,
    "không có vốn" là pain không phải refusal.
    """
    if not text:
        return False
    low = text.lower().strip()
    if "thời gian" in low or "không có vốn" in low:
        return False
    return any(kw in low for kw in _REFUSAL_KEYWORDS)