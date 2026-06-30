"""Extractor tool schemas — 1 tool / slot.

Refer:
- F2B.2 (LUAT_2B_llm v0.1.2) — extractor schema strict
- D6 STRATEGY — 1 tool / slot (tổng 16 tool, slot 4.1 không có)
- C-B3 batch 4 — "16 tool" (đã fix từ "17 tool")

Phase 1: 3 slot REQUIRED (1.1, 1.2, 4.0). Phase 2+ mở rộng 13 slot.

Schema design:
- Strict input_schema (type + maxLength) — chống prompt injection bằng input dài
- Field optional (required=[]) — LLM có thể trả null nếu dealer chưa cho
- Sanitize ở validators.py sau khi LLM trả về
"""
from __future__ import annotations


# ============================================================
# Slot 1.1 — Tên người + tên cửa hàng (multi-field)
# ============================================================

TOOL_SLOT_1_1: dict = {
    "name": "extract_slot_1_1",
    "description": (
        "Extract tên cá nhân (owner_name) + tên cửa hàng (dealer_name) từ "
        "message dealer. Đây là slot multi-field: dealer có thể trả lời 1 "
        "hoặc cả 2 trong 1 câu. Field nào dealer chưa cho → null. "
        "Bỏ tiền tố anh/chị/bác khỏi owner_name. GIỮ FULL họ + tên đệm + "
        "tên gọi (vd 'Lê Dương' KHÔNG cắt thành 'Dương')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "owner_name": {
                "type": ["string", "null"],
                "description": (
                    "Tên ĐẦY ĐỦ chủ cửa hàng (họ + tên đệm + tên gọi). "
                    "Vd: 'Nguyễn Quốc Vinh' (KHÔNG chỉ 'Vinh'), 'Lê Dương' "
                    "(KHÔNG chỉ 'Dương'), 'Trần Thị Lan' (KHÔNG chỉ 'Lan'). "
                    "Nếu dealer cho 1 từ thì giữ 1 từ. KHÔNG kèm 'anh'/"
                    "'chị'/'bác'/'em' tiền tố. Null nếu dealer chưa cho."
                ),
                "maxLength": 100,
            },
            "dealer_name": {
                "type": ["string", "null"],
                "description": (
                    "Tên cửa hàng / business name. Vd: 'Nhôm Kính Thanh "
                    "Tùng', 'Cửa Cuốn Phú Cường', 'Tủ Bếp Quốc Vinh'. "
                    "Null nếu dealer chỉ cho tên cá nhân."
                ),
                "maxLength": 200,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 1.2 — Địa chỉ + bán kính khách (multi-field, RAW signal C6)
# ============================================================

TOOL_SLOT_1_2: dict = {
    "name": "extract_slot_1_2",
    "description": (
        "Extract địa chỉ cửa hàng (address) + bán kính khách hàng "
        "(local_dominance_signal — RAW text cho C6). Address là REQUIRED, "
        "bán kính là OPTIONAL. Dealer có thể trả 1 hoặc cả 2."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": ["string", "null"],
                "description": (
                    "Địa chỉ cửa hàng. Capitalize, giữ nguyên tỉnh/quận. "
                    "Có thể ngắn ('Quận 1, TP.HCM') hoặc đầy đủ "
                    "('123 Lê Lợi, P. Bến Nghé, Quận 1, TP.HCM'). "
                    "Null nếu dealer chưa cho."
                ),
                "maxLength": 500,
            },
            "local_dominance_signal": {
                "type": ["string", "null"],
                "description": (
                    "Raw text về bán kính / địa bàn khách. Vd: 'khách đến "
                    "từ 5km xung quanh', 'phường lân cận', 'toàn quận'. "
                    "Null nếu dealer không kể."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 4.0 — Brandkit consent
# ============================================================

TOOL_SLOT_4_0: dict = {
    "name": "extract_slot_4_0",
    "description": (
        "Extract đồng ý/từ chối nhận bộ thương hiệu (brandkit_consent). "
        "Dealer nói 'yes'/'OK'/'có'/'đồng ý'/'cho' → 'yes'. Nói 'không "
        "cần'/'thôi'/'từ chối'/'không' → 'no'. Không rõ → null."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "brandkit_consent": {
                "type": ["string", "null"],
                "enum": ["yes", "no", None],
                "description": (
                    "'yes' nếu dealer đồng ý nhận quà bộ thương hiệu, "
                    "'no' nếu từ chối, null nếu dealer chưa rõ ràng."
                ),
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 1.3 — Phone / Zalo
# ============================================================

TOOL_SLOT_1_3: dict = {
    "name": "extract_slot_1_3",
    "description": (
        "Extract số điện thoại / Zalo (phone_or_zalo) từ message. "
        "Giữ NGUYÊN digits + dấu chấm/space/dash. Validator sẽ clean "
        "thành digits-only sau. Null nếu dealer chưa cho hoặc từ chối."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "phone_or_zalo": {
                "type": ["string", "null"],
                "description": (
                    "Số điện thoại / Zalo. Vd '0912345678', '0912 345 678', "
                    "'0912-345-678'. Null nếu dealer chưa cho hoặc nói 'không'."
                ),
                "maxLength": 30,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 2.1 — Sản phẩm chủ lực
# ============================================================

TOOL_SLOT_2_1: dict = {
    "name": "extract_slot_2_1",
    "description": (
        "Extract sản phẩm dealer làm (main_product). Dealer có thể kể NHIỀU "
        "mặt hàng — gom HẾT vào main_product, phân cách dấu phẩy "
        "(vd 'cửa nhôm kính, cửa cuốn, tủ bếp')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "main_product": {
                "type": ["string", "null"],
                "description": (
                    "Sản phẩm dealer làm, raw text. Nếu NHIỀU mặt hàng → liệt "
                    "kê hết, phân cách dấu phẩy (vd 'cửa nhôm kính hệ Xingfa, "
                    "cửa cuốn motor, tủ bếp acrylic'). Null nếu chưa cho."
                ),
                "maxLength": 300,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 2.2 — Mô hình kinh doanh
# ============================================================

TOOL_SLOT_2_2: dict = {
    "name": "extract_slot_2_2",
    "description": (
        "Extract mô hình kinh doanh (business_model_signal — raw text). "
        "Phase 6 R+ enrich: HIỂU RỘNG — bất kỳ tín hiệu nào về cách dealer "
        "làm việc đều fill (vd 'lắp đặt', 'thi công', 'làm thợ', 'có xưởng', "
        "'bán lẻ', 'gia công', 'đại lý')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "business_model_signal": {
                "type": ["string", "null"],
                "description": (
                    "Mô hình KD raw text. Bất kỳ tín hiệu cách làm việc:\n"
                    "- 'phân phối thuần' / 'bán lẻ' / 'đại lý' → bán lại hàng\n"
                    "- 'có xưởng' / 'tự sản xuất' / 'gia công' → sản xuất riêng\n"
                    "- 'lắp đặt' / 'thi công' / 'làm thợ' → đội thi công riêng\n"
                    "- 'kết hợp' / 'bán + thi công' / 'cả hai' → mô hình hybrid\n"
                    "GIỮ NGUYÊN văn từ dealer cho, KHÔNG diễn dịch lại. "
                    "Null CHỈ KHI dealer không đề cập gì về mô hình kinh doanh."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 2.3 — Đội thợ
# ============================================================

TOOL_SLOT_2_3: dict = {
    "name": "extract_slot_2_3",
    "description": (
        "Extract số thợ (est_team_size: int) + tín hiệu ổn định đội "
        "(team_stability_signal: raw text). Phase 6 R+ update 2026-05-22: "
        "HIỂU colloquial number (dealer Việt hay nói 'tầm chục', 'vài "
        "chục', 'mươi mấy người') — KHÔNG được trả null khi rõ ràng có "
        "ước lượng số."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "est_team_size": {
                "type": ["integer", "null"],
                "description": (
                    "Số thợ chính (int). HIỂU colloquial Vietnamese:\n"
                    "- '1 mình' / 'một mình' → 1\n"
                    "- 'tầm chục' / 'khoảng chục' / 'chục thằng' / 'chục đứa' / 'chục người' → 10\n"
                    "- 'vài chục' / 'hai chục' → 20\n"
                    "- 'nửa chục' / 'năm sáu người' → 5\n"
                    "- 'mươi mấy' / 'hơn mười' / 'mười mấy' → 12 (mid-estimate)\n"
                    "- 'vài người' / 'mấy người' → 3 (mid-estimate)\n"
                    "- 'đôi ba thợ' / 'hai ba thợ' → 3\n"
                    "- '8-9 người' / '5 đến 7' → mid-estimate 8 / 6\n"
                    "- 'đông lắm' / 'cả tá' → 12\n"
                    "- 'một xưởng to' / 'mấy chục' → 30\n"
                    "Null CHỈ khi dealer KHÔNG đề cập số nào (vd 'chưa nhớ', "
                    "'để xem lại'). Luôn ưu tiên estimate trung bình thay "
                    "vì null nếu có hint số."
                ),
                "minimum": 0,
                "maximum": 200,
            },
            "team_stability_signal": {
                "type": ["string", "null"],
                "description": (
                    "Tín hiệu ổn định đội raw, GIỮ NGUYÊN cách dealer nói. "
                    "Vd '2 thợ chính gắn bó 4-5 năm', 'thợ vụ theo dự án', "
                    "'mới thuê 6 tháng', 'tầm chục thằng làm lâu rồi', "
                    "'đội cũ hết', 'thuê thêm khi có dự án'."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 2.4 — Hãng nhập + backup
# ============================================================

TOOL_SLOT_2_4: dict = {
    "name": "extract_slot_2_4",
    "description": (
        "Extract hãng nhập (supplier_brands: list) + tín hiệu negotiation "
        "(supplier_negotiation_signal: raw — backup nguồn, NPP quen). "
        "Brand names giữ NGUYÊN cách viết hoa (Xingfa, PMA, Schüco)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "supplier_brands": {
                "type": ["array", "null"],
                "description": (
                    "List tên hãng nhập. Vd ['Xingfa', 'PMA'], ['Schüco']."
                ),
                "items": {"type": "string", "maxLength": 50},
                "maxItems": 10,
            },
            "supplier_negotiation_signal": {
                "type": ["string", "null"],
                "description": (
                    "Tín hiệu chủ động nguồn raw. Vd '2 NPP quen thân', "
                    "'có backup nếu đứt', 'chỉ 1 nguồn duy nhất'."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 2.5 — Kênh khách liên hệ
# ============================================================

TOOL_SLOT_2_5: dict = {
    "name": "extract_slot_2_5",
    "description": (
        "Extract kênh khách liên hệ chính (primary_contact_channel). "
        "Vd 'Zalo', 'điện thoại', 'Facebook', 'khách cũ giới thiệu', 'mixed'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_contact_channel": {
                "type": ["string", "null"],
                "description": (
                    "Kênh chính raw. Vd 'Zalo', 'khách cũ giới thiệu', "
                    "'mixed' (đa kênh)."
                ),
                "maxLength": 100,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 2.6 — Facebook + network
# ============================================================

TOOL_SLOT_2_6: dict = {
    "name": "extract_slot_2_6",
    "description": (
        "Extract trang Facebook (facebook) + trạng thái dùng FB "
        "(fb_marketing_status) + tín hiệu network thợ/đối tác "
        "(community_network_signal — raw cho C9)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "facebook": {
                "type": ["string", "null"],
                "description": (
                    "FB link / tên trang / 'chung cá nhân' / 'chưa có'. "
                    "Null nếu dealer không nói tới FB."
                ),
                "maxLength": 200,
            },
            "fb_marketing_status": {
                "type": ["string", "null"],
                "description": (
                    "Tình trạng dùng FB. Vd 'ít chăm', 'có post hàng "
                    "tuần', 'chưa biết bắt đầu', 'lười'."
                ),
                "maxLength": 200,
            },
            "community_network_signal": {
                "type": ["string", "null"],
                "description": (
                    "Mạng lưới thợ/đối tác raw (C9). Vd 'có mạng lưới "
                    "thợ trao đổi khách 2 chiều', 'hoạt động đơn lẻ'."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 3.1 — Tỉ lệ khách cũ
# ============================================================

TOOL_SLOT_3_1: dict = {
    "name": "extract_slot_3_1",
    "description": (
        "Extract tỉ lệ khách cũ giới thiệu (customer_old_percentage). "
        "Giữ raw text: '60-70%', 'gần như hết', 'khoảng 80%'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_old_percentage": {
                "type": ["string", "null"],
                "description": (
                    "Raw text tỉ lệ. Vd '60-70%', 'gần như hết', 'khoảng "
                    "80%', '1/2'. Null nếu dealer không cho."
                ),
                "maxLength": 100,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 3.2 — Cách lưu danh sách khách
# ============================================================

TOOL_SLOT_3_2: dict = {
    "name": "extract_slot_3_2",
    "description": (
        "Extract cách lưu danh sách khách (customer_storage_method). "
        "Raw text: 'Zalo', 'sổ tay', 'Excel', 'CRM', 'sổ + Zalo', "
        "'không lưu / nhớ trong đầu'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_storage_method": {
                "type": ["string", "null"],
                "description": (
                    "Cách lưu raw. Vd 'sổ + Zalo', 'Excel', 'không lưu'."
                ),
                "maxLength": 200,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 3.3 — Vướng mắc khách cũ (OPEN — DÀI, mining nhiều)
# ============================================================

TOOL_SLOT_3_3: dict = {
    "name": "extract_slot_3_3",
    "description": (
        "Extract pain point khách cũ (customer_pain — DÀI, raw, không "
        "cắt) + tín hiệu động lực (motivation_signal C5) + USP nếu có "
        "(usp_signal). Đây là turn mining quan trọng nhất."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_pain": {
                "type": ["string", "null"],
                "description": (
                    "Pain point raw, GIỮ NGUYÊN VĂN dealer kể. Vd 'khó "
                    "nhớ lịch sử khách cũ sau >1 năm', 'khách quay lại "
                    "kỳ kèo giá'."
                ),
                "maxLength": 2000,
            },
            "motivation_signal": {
                "type": ["string", "null"],
                "description": (
                    "Động lực (C5) raw. Vd 'muốn có công cụ tra cứu "
                    "nhanh', 'muốn giữ chân khách lâu hơn'."
                ),
                "maxLength": 500,
            },
            "usp_signal": {
                "type": ["string", "null"],
                "description": (
                    "Lợi thế cạnh tranh ngầm dealer hé ra. Vd 'làm chất "
                    "lượng nên khách giới thiệu nhiều'. Null nếu chưa rõ."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 3.4 — Cọc + công nợ
# ============================================================

TOOL_SLOT_3_4: dict = {
    "name": "extract_slot_3_4",
    "description": (
        "Extract tín hiệu thanh toán (payment_terms_signal — raw cọc % "
        "+ DSO + nợ kéo dài). Dealer thường nói chung chung như '50% "
        "cọc', 'thanh toán hết khi bàn giao'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "payment_terms_signal": {
                "type": ["string", "null"],
                "description": (
                    "Raw text về cọc + thanh toán. Vd '50% cọc, hết khi "
                    "bàn giao', 'cọc 30%, nợ 30 ngày'."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 3.5 — Bảo hành — ai chịu
# ============================================================

TOOL_SLOT_3_5: dict = {
    "name": "extract_slot_3_5",
    "description": (
        "Extract trách nhiệm bảo hành (warranty_responsibility_signal). "
        "Vd 'cửa hàng đứng ra ký', 'đẩy về nhà cung cấp', 'tùy lỗi'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "warranty_responsibility_signal": {
                "type": ["string", "null"],
                "description": (
                    "Raw text ai chịu bảo hành. Vd 'cửa hàng đứng ra', "
                    "'đẩy nhà SX', 'tùy lỗi'."
                ),
                "maxLength": 500,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Slot 4.2 — Màu + phong thủy
# ============================================================

TOOL_SLOT_4_2: dict = {
    "name": "extract_slot_4_2",
    "description": (
        "Extract màu chủ đạo (color_accent) + tín hiệu phong thủy "
        "(feng_shui_signal — mệnh hoặc lý do chọn màu)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "color_accent": {
                "type": ["string", "null"],
                "description": (
                    "Màu chủ đạo raw. Vd 'xanh dương', 'đỏ', 'vàng + "
                    "đen', 'em chọn cho hợp ngành' (null nếu để bot chọn)."
                ),
                "maxLength": 100,
            },
            "feng_shui_signal": {
                "type": ["string", "null"],
                "description": (
                    "Phong thủy raw. Vd 'mệnh Hỏa hợp đỏ', 'không quan "
                    "tâm phong thủy', 'tuổi Mão'."
                ),
                "maxLength": 200,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


# ============================================================
# Master dict — slot_id → tool schema (Phase 2: 16 slot có extractor)
# Slot 4.1 là THÔNG BÁO, không có extractor.
# ============================================================

SLOT_TOOL_SCHEMAS: dict[str, dict] = {
    "1.1": TOOL_SLOT_1_1,
    "1.2": TOOL_SLOT_1_2,
    "1.3": TOOL_SLOT_1_3,
    "2.1": TOOL_SLOT_2_1,
    "2.2": TOOL_SLOT_2_2,
    "2.3": TOOL_SLOT_2_3,
    "2.4": TOOL_SLOT_2_4,
    "2.5": TOOL_SLOT_2_5,
    "2.6": TOOL_SLOT_2_6,
    "3.1": TOOL_SLOT_3_1,
    "3.2": TOOL_SLOT_3_2,
    "3.3": TOOL_SLOT_3_3,
    "3.4": TOOL_SLOT_3_4,
    "3.5": TOOL_SLOT_3_5,
    "4.0": TOOL_SLOT_4_0,
    "4.2": TOOL_SLOT_4_2,
}


def get_tool_schema(slot_id: str) -> dict | None:
    """Lấy tool schema cho slot_id. None nếu slot không có extractor."""
    return SLOT_TOOL_SCHEMAS.get(slot_id)


def list_phase_1_slot_ids() -> list[str]:
    """Slot_id list có extractor Phase 1 (giữ tên BC, thực tế là 16 slot Phase 2)."""
    return list(SLOT_TOOL_SCHEMAS.keys())
