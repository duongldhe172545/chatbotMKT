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
        "Bỏ tiền tố anh/chị/bác khỏi owner_name."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "owner_name": {
                "type": ["string", "null"],
                "description": (
                    "Tên cá nhân chủ cửa hàng. Vd: 'Tùng', 'Quốc Vinh', "
                    "'Lan'. KHÔNG kèm 'anh'/'chị'/'bác'/'em'. Null nếu "
                    "dealer chưa cho hoặc chỉ cho tên cửa hàng."
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
# Master dict — slot_id → tool schema (Phase 1: 3 slot)
# ============================================================

SLOT_TOOL_SCHEMAS: dict[str, dict] = {
    "1.1": TOOL_SLOT_1_1,
    "1.2": TOOL_SLOT_1_2,
    "4.0": TOOL_SLOT_4_0,
}


def get_tool_schema(slot_id: str) -> dict | None:
    """Lấy tool schema cho slot_id. None nếu Phase 1 chưa có."""
    return SLOT_TOOL_SCHEMAS.get(slot_id)


def list_phase_1_slot_ids() -> list[str]:
    """Slot_id list có extractor Phase 1."""
    return list(SLOT_TOOL_SCHEMAS.keys())
