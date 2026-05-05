"""Parse câu lệnh sửa profile bằng regex — tiết kiệm LLM call.

Pattern hỗ trợ:
- "sửa SĐT thành 0901234567"
- "đổi tên cửa hàng thành ABC"
- "tỉnh là Hà Nội"
- "không phải, tên là Vinh"

Trả (field_name, new_value) nếu match, None nếu không chắc → fallback LLM.
"""
from __future__ import annotations

import re

# Map keyword tiếng Việt → tên field thật trong DealerProfileRaw
FIELD_KEYWORDS: dict[str, str] = {
    # phone
    "sđt": "phone_or_zalo", "sdt": "phone_or_zalo",
    "số điện thoại": "phone_or_zalo", "so dien thoai": "phone_or_zalo",
    "số đt": "phone_or_zalo", "so dt": "phone_or_zalo",
    "zalo": "phone_or_zalo", "phone": "phone_or_zalo",
    "số phone": "phone_or_zalo",
    # dealer name
    "tên cửa hàng": "dealer_name", "ten cua hang": "dealer_name",
    "tên đại lý": "dealer_name", "ten dai ly": "dealer_name",
    "tên shop": "dealer_name",
    # owner
    "tên anh": "owner_name", "ten anh": "owner_name",
    "tên tôi": "owner_name", "ten toi": "owner_name",
    "tên em": "owner_name",
    # location
    "tỉnh": "province", "tinh": "province",
    "thành phố": "province", "thanh pho": "province",
    "huyện": "district", "huyen": "district",
    "quận": "district", "quan": "district",
    # category
    "ngành": "main_category", "nganh": "main_category",
    "mảng": "main_category", "mang": "main_category",
    # customer base
    "khách cũ": "customer_base_estimate", "khach cu": "customer_base_estimate",
    "số khách": "customer_base_estimate", "so khach": "customer_base_estimate",
    # pain points (note: edit qua regex chỉ set 1 item — list)
    "đau": "pain_points", "dau": "pain_points",
    "vướng": "pain_points", "vuong": "pain_points",
    "nỗi đau": "pain_points", "noi dau": "pain_points",
}

# Patterns nhận diện ý sửa: "sửa X thành Y", "đổi X thành Y", "X là Y", "không phải, X là Y"
EDIT_PATTERNS = [
    # "sửa <field> thành <value>"
    re.compile(r"(?:sửa|sua|đổi|doi|cập nhật|cap nhat|update)\s+(.+?)\s+(?:thành|thanh|là|la|sang)\s+(.+)", re.IGNORECASE),
    # "<field> là <value>" (chỉ khớp khi field được nhắc tới rõ ràng)
    re.compile(r"^\s*(?:không phải[,.\s]+|khong phai[,.\s]+|nhầm[,.\s]+|nham[,.\s]+)?(.+?)\s+(?:là|la)\s+(.+)$", re.IGNORECASE),
]


# Field nào là list — value cần wrap [value]
LIST_FIELDS = {"pain_points", "dl0_priority"}


def parse_edit_command(message: str) -> tuple[str, object] | None:
    """Trả (field_name, new_value) nếu parse được, None nếu không chắc.

    new_value là str cho field thường, list[str] cho LIST_FIELDS.
    """
    msg = message.strip()
    if not msg:
        return None

    for pattern in EDIT_PATTERNS:
        match = pattern.search(msg)
        if not match:
            continue

        field_keyword_raw, new_value_raw = match.group(1), match.group(2)
        field_keyword = field_keyword_raw.strip().lower()
        new_value: object = new_value_raw.strip().rstrip(".!?,").strip()

        if not new_value or len(str(new_value)) > 200:
            continue

        # Tìm field thật từ keyword — match dài nhất trước
        for kw in sorted(FIELD_KEYWORDS, key=len, reverse=True):
            if kw in field_keyword:
                field = FIELD_KEYWORDS[kw]
                # Special: phone phải là chữ số
                if field == "phone_or_zalo":
                    digits = re.sub(r"\D", "", str(new_value))
                    if len(digits) < 9 or len(digits) > 11:
                        return None
                    new_value = digits
                # Wrap thành list nếu cần
                if field in LIST_FIELDS:
                    new_value = [str(new_value)]
                return field, new_value

    return None
