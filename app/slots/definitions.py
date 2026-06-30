"""17 slot definitions cho Em Linh MKT v8.

Refer:
- F2A.5 (LUAT_2A_core v0.2.4) — slot priority + retry
- CORE § G.3 v3.0.5 — bảng 17 slot + field map
- File 1A § 4 v0.2.2 — Q&A templates per slot
- D9 STRATEGY — Phase 1 cut 3 REQUIRED
- GLOSSARY § 1 — 6 REQUIRED + 10 OPTIONAL + 1 THÔNG BÁO
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# Slot priority + classification
# Refer F2A.5 SLOT_PRIORITY_ORDER + REQUIRED_SLOTS
# ============================================================


# Trật tự ưu tiên 17 slot — forward-only (F2A.5)
SLOT_PRIORITY_ORDER: list[str] = [
    "1.1", "1.2", "1.3",                          # Chủ đề 1: danh thiếp (3)
    "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",     # Chủ đề 2: công việc + kênh (6)
    "3.1", "3.2", "3.3", "3.4", "3.5",            # Chủ đề 3: khách cũ + vướng (5)
    "4.0", "4.1", "4.2",                          # Chủ đề 4: bộ thương hiệu (3)
]

# 6 REQUIRED slot — retry max 3 tổng, 2 consecutive max (D11 STRATEGY)
REQUIRED_SLOTS: list[str] = ["1.1", "1.2", "1.3", "2.1", "2.2", "4.0"]

# 10 OPTIONAL slot — "không biết" → SKIP NGAY + flag dealer_declined
OPTIONAL_SLOTS: list[str] = [
    "2.3", "2.4", "2.5", "2.6",
    "3.1", "3.2", "3.3", "3.4", "3.5",
    "4.2",
]

# 1 THÔNG BÁO slot — bot độc thoại, không hỏi, không extractor (GLOSSARY § 1)
# Refer LUAT_2A F2A.5: rule "no_ask + no_retry + no_extractor + auto-advance".
THONG_BAO_SLOTS: list[str] = ["4.1"]
# Alias chính thức theo spec LUAT 2A v0.2.6 (English name) — same list,
# code có thể dùng tên này cho dev không quen tiếng Việt.
NOTIFICATION_SLOTS: list[str] = THONG_BAO_SLOTS

# Validation invariant — refer LUAT_2A F2A.5:
# REQUIRED ∪ OPTIONAL ∪ NOTIFICATION phải = SLOT_PRIORITY_ORDER (17 slot).
# Test unit: tests/unit/test_slot_definitions.py
assert (
    set(REQUIRED_SLOTS) | set(OPTIONAL_SLOTS) | set(NOTIFICATION_SLOTS)
    == set(SLOT_PRIORITY_ORDER)
), "Invariant fail: REQUIRED ∪ OPTIONAL ∪ NOTIFICATION ≠ 17 slot"
assert (
    len(REQUIRED_SLOTS) + len(OPTIONAL_SLOTS) + len(NOTIFICATION_SLOTS)
    == len(SLOT_PRIORITY_ORDER)
), "Invariant fail: slot overlap detected"

# 7 multi-field slot — refer 1A § 1.5 + F2A.4 step 2.6 (PARTIAL_RETRY)
MULTI_FIELD_SLOTS: list[str] = [
    "1.1", "1.2", "2.1", "2.4", "2.5", "2.6", "3.3",
]

# Phase 1 MVP scope — D9 STRATEGY (3 slot REQUIRED đơn giản nhất)
PHASE_1_REQUIRED_SLOTS: list[str] = ["1.1", "1.2", "4.0"]


# ============================================================
# SLOT_TO_REQUIRED_FIELDS — mapping slot → field bắt buộc
# Refer F2A.7 sanity check 5-point + F2A.4 step 2.6 PARTIAL detect
# ============================================================


SLOT_TO_REQUIRED_FIELDS: dict[str, list[str]] = {
    "1.1": ["owner_name", "dealer_name"],          # 2 field cùng REQUIRED
    "1.2": ["address"],                            # bán kính là OPTIONAL
    "1.3": ["phone_or_zalo"],
    "2.1": ["main_product"],                       # nhiều sản phẩm gom chung 1 trường
    "2.2": ["business_model_signal"],
    "4.0": ["brandkit_consent"],
}


# ============================================================
# SLOT_TO_ALL_FIELDS — mapping slot → tất cả field slot có thể fill
# Bao gồm cả OPTIONAL + RAW SIGNAL trong slot multi-field
# ============================================================


SLOT_TO_ALL_FIELDS: dict[str, list[str]] = {
    "1.1": ["owner_name", "dealer_name"],
    "1.2": ["address", "local_dominance_signal"],
    "1.3": ["phone_or_zalo"],                      # nhiều số → gom vào phone_or_zalo
    "2.1": ["main_product"],                       # nhiều sản phẩm → gom vào main_product
    "2.2": ["business_model_signal", "dealer_type"],
    "2.3": ["est_team_size", "team_stability_signal"],
    "2.4": ["supplier_brands", "supplier_negotiation_signal"],
    "2.5": ["primary_contact_channel"],
    "2.6": ["facebook", "fb_marketing_status", "community_network_signal"],
    "3.1": ["customer_old_percentage"],
    "3.2": ["customer_storage_method"],
    "3.3": ["customer_pain", "motivation_signal", "usp_signal"],
    "3.4": ["payment_terms_signal"],
    "3.5": ["warranty_responsibility_signal"],
    "4.0": ["brandkit_consent"],
    "4.1": [],                                     # THÔNG BÁO — không có field
    "4.2": ["color_accent", "feng_shui_signal"],
}


# ============================================================
# SlotDefinition — schema metadata cho 1 slot
# ============================================================


SlotKind = Literal["REQUIRED", "OPTIONAL", "THONG_BAO"]


class SlotDefinition(BaseModel):
    """Định nghĩa 1 slot — refer F2A.5 + 1A § 4."""
    slot_id: str
    topic: int                                     # 1-4 (chủ đề)
    purpose: str                                   # Mô tả ngắn
    kind: SlotKind
    required_fields: list[str] = Field(default_factory=list)
    all_fields: list[str] = Field(default_factory=list)
    is_multi_field: bool = False
    has_extractor: bool = True                     # False cho THONG_BAO


# Purpose + topic cho 17 slot — derive từ CORE § G.3
_SLOT_PURPOSES: dict[str, str] = {
    "1.1": "Tên người + tên cửa hàng",
    "1.2": "Địa chỉ + bán kính khách (C6)",
    "1.3": "SĐT / Zalo liên hệ",
    "2.1": "Danh mục + sản phẩm mạnh nhất",
    "2.2": "Mô hình kinh doanh",
    "2.3": "Đội thợ + độ ổn định (C3)",
    "2.4": "Hãng nhập + backup nguồn (C8)",
    "2.5": "Kênh khách liên hệ chính",
    "2.6": "Facebook + mạng lưới thợ/đối tác (C9)",
    "3.1": "Tỉ lệ khách cũ giới thiệu (C1)",
    "3.2": "Cách lưu danh sách khách (C7)",
    "3.3": "Vướng mắc khách cũ + động lực (C5)",
    "3.4": "Quy trình cọc + công nợ (C2)",
    "3.5": "Trách nhiệm bảo hành — ai chịu (C4)",
    "4.0": "Xin consent bộ thương hiệu",
    "4.1": "Logo (em chọn — thông báo)",
    "4.2": "Màu chủ đạo + phong thủy",
}


def _slot_topic(slot_id: str) -> int:
    """Derive topic từ slot_id (vd '2.3' → 2)."""
    return int(slot_id.split(".")[0])


def _build_slots() -> dict[str, SlotDefinition]:
    """Build 17 slot definitions từ constants trên."""
    slots: dict[str, SlotDefinition] = {}
    for slot_id in SLOT_PRIORITY_ORDER:
        if slot_id in REQUIRED_SLOTS:
            kind: SlotKind = "REQUIRED"
        elif slot_id in THONG_BAO_SLOTS:
            kind = "THONG_BAO"
        else:
            kind = "OPTIONAL"
        slots[slot_id] = SlotDefinition(
            slot_id=slot_id,
            topic=_slot_topic(slot_id),
            purpose=_SLOT_PURPOSES[slot_id],
            kind=kind,
            required_fields=SLOT_TO_REQUIRED_FIELDS.get(slot_id, []),
            all_fields=SLOT_TO_ALL_FIELDS[slot_id],
            is_multi_field=slot_id in MULTI_FIELD_SLOTS,
            has_extractor=kind != "THONG_BAO",
        )
    return slots


# Module-level dict — 17 slot definitions sẵn dùng
SLOTS: dict[str, SlotDefinition] = _build_slots()


# ============================================================
# Helper functions
# ============================================================


def get_slot(slot_id: str) -> SlotDefinition:
    """Lấy slot definition theo id. Raise KeyError nếu không tồn tại."""
    return SLOTS[slot_id]


def is_required(slot_id: str) -> bool:
    """True nếu slot REQUIRED (1.1/1.2/1.3/2.1/2.2/4.0)."""
    return slot_id in REQUIRED_SLOTS


def is_optional(slot_id: str) -> bool:
    """True nếu slot OPTIONAL."""
    return slot_id in OPTIONAL_SLOTS


def is_thong_bao(slot_id: str) -> bool:
    """True nếu slot THÔNG BÁO (4.1) — không có extractor."""
    return slot_id in THONG_BAO_SLOTS


def is_multi_field(slot_id: str) -> bool:
    """True nếu slot có nhiều field bắt buộc (PARTIAL_RETRY có thể trigger)."""
    return slot_id in MULTI_FIELD_SLOTS


def next_slot(
    current: str,
    skipped: Optional[list[str]] = None,
    profile=None,
) -> Optional[str]:
    """Trả slot tiếp theo trong SLOT_PRIORITY_ORDER, bỏ qua skipped + slot đã fill.

    Phase 6 R+ fix Lỗi 3+5: nếu profile passed → check slot.required_fields đã
    fill chưa. Slot REQUIRED fill rồi → skip (tránh hỏi lại slot 2.1 đã có
    main_product="nội thất" khi recheck deferred làm flow loop).

    Args:
        current: Slot hiện tại (vd "1.1"). Nếu không trong list → bắt đầu từ đầu.
        skipped: List slot đã skip (refer SessionState.skipped_slots).
        profile: Optional DealerProfileRaw — check fill state qua REQUIRED fields.

    Returns:
        Slot kế tiếp chưa fill, hoặc None nếu hết slot (chuyển CONFIRMING).
    """
    skipped = skipped or []
    try:
        idx = SLOT_PRIORITY_ORDER.index(current)
    except ValueError:
        idx = -1
    for next_id in SLOT_PRIORITY_ORDER[idx + 1:]:
        if next_id in skipped:
            continue
        # Phase 6 R+: skip slot đã fill (REQUIRED) — tránh hỏi lại
        if profile is not None and _is_slot_required_filled(next_id, profile):
            continue
        return next_id
    return None


def _is_slot_required_filled(slot_id: str, profile) -> bool:
    """True nếu slot REQUIRED fields đều fill trong profile.

    Helper cho `next_slot()` skip slot đã có data.
    """
    required = SLOT_TO_REQUIRED_FIELDS.get(slot_id, [])
    if not required:
        # Slot OPTIONAL/THONG_BAO: check tất cả fields có ít nhất 1 filled
        all_fields = SLOT_TO_ALL_FIELDS.get(slot_id, [])
        if not all_fields:
            return False  # THONG_BAO không có field — không skip
        return any(
            _field_filled(profile, f) for f in all_fields
        )
    # REQUIRED: tất cả required fields phải fill
    return all(_field_filled(profile, f) for f in required)


def _field_filled(profile, field: str) -> bool:
    """True nếu profile.field có giá trị non-empty."""
    v = getattr(profile, field, None)
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    if isinstance(v, list) and not v:
        return False
    return True
