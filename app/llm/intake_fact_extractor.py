"""Full-context fact extractor for the LLM-first intake engine."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.llm.client import LLMClient
from app.models.schema import DealerProfileRaw
from app.slots.definitions import OPTIONAL_SLOTS, SLOT_TO_ALL_FIELDS


DERIVED_FIELDS = {
    "province",
    "ward",
    "district",
    "main_category",
    "dealer_type",
    "brand_name_short",
    "initials_full",
    "initial_single",
    "contact_name",
    "contact_role",
    "hotline",
    "slogan_options",
}
BRANDING_PREFERENCE_FIELDS = {
    "logo_initials",
    "slogan_preference",
    "logo_style",
    "logo_existing_intent",
}
INTAKE_ALLOWED_FIELDS: set[str] = {
    field
    for fields in SLOT_TO_ALL_FIELDS.values()
    for field in fields
    if field not in DERIVED_FIELDS
} | BRANDING_PREFERENCE_FIELDS
Confidence = Literal["low", "medium", "high"]
OptionalResolution = Literal["not_applicable", "unknown", "declined"]
OPTIONAL_RESOLUTION_FIELDS: set[str] = {
    field
    for slot_id in OPTIONAL_SLOTS
    for field in SLOT_TO_ALL_FIELDS.get(slot_id, [])
}


class IntakeFact(BaseModel):
    """One dealer fact extracted from conversation evidence."""

    field: str
    value: Any
    evidence: str = ""
    confidence: Confidence = "medium"
    is_correction: bool = False

    @field_validator("field")
    @classmethod
    def field_must_be_allowed(cls, value: str) -> str:
        if value not in INTAKE_ALLOWED_FIELDS:
            raise ValueError(f"Unsupported intake field: {value}")
        return value


class IntakeFacts(BaseModel):
    facts: list[IntakeFact] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    resolved_optional_slots: list[str] = Field(default_factory=list)
    resolved_optional_fields: dict[str, OptionalResolution] = Field(default_factory=dict)
    
    # Gộp các trường Observation
    intent: str = "normal"
    dealer_type: str = "unknown"
    is_busy: bool = False
    is_emotional: bool = False
    is_skeptical: bool = False
    wants_brief: bool = False

    @field_validator("resolved_optional_slots")
    @classmethod
    def slots_must_be_optional(cls, values: list[str]) -> list[str]:
        invalid = [value for value in values if value not in OPTIONAL_SLOTS]
        if invalid:
            raise ValueError(f"Unsupported optional slot: {invalid}")
        return list(dict.fromkeys(values))

    @field_validator("resolved_optional_fields")
    @classmethod
    def fields_must_be_optional(
        cls,
        values: dict[str, OptionalResolution],
    ) -> dict[str, OptionalResolution]:
        invalid = [value for value in values if value not in OPTIONAL_RESOLUTION_FIELDS]
        if invalid:
            raise ValueError(f"Unsupported optional fields: {invalid}")
        return values


EXTRACTOR_TOOL_NAME = "extract_linh_intake_facts"
EXTRACTOR_TOOL_DESCRIPTION = (
    "Extract dealer profile facts and behavioral observations from the recent Em Linh MKT conversation. "
    "Only output facts supported by explicit evidence."
)
EXTRACTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string", "nullable": True},
                    "evidence": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "is_correction": {"type": "boolean"},
                },
                "required": ["field", "value", "evidence", "confidence"],
            },
        },
        "uncertainty_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "resolved_optional_slots": {
            "type": "array",
            "items": {"type": "string", "enum": OPTIONAL_SLOTS},
        },
        "resolved_optional_fields": {
            "type": "object",
            "additionalProperties": {
                "type": "string",
                "enum": ["not_applicable", "unknown", "declined"],
            },
        },
        "intent": {
            "type": "string",
            "enum": ["normal", "affirmative", "refusal", "khong_biet", "defensive", "tam_su", "edit", "confusion"],
        },
        "is_busy": {"type": "boolean"},
        "is_emotional": {"type": "boolean"},
        "is_skeptical": {"type": "boolean"},
        "wants_brief": {"type": "boolean"},
    },
    "required": ["facts", "intent", "is_busy", "is_emotional", "is_skeptical", "wants_brief"],
}


class FactExtractorError(RuntimeError):
    """Extractor output is invalid."""


def extract_intake_facts(
    *,
    history_text: str,
    current_profile: DealerProfileRaw,
    user_message: str,
    client: LLMClient,
    current_focus_slot: str | None = None,
    current_focus_field: str | None = None,
) -> IntakeFacts:
    """Extract profile facts from recent/full conversation context."""
    raw = client.extract_quality(
        system_prompt=build_fact_extractor_prompt(),
        conversation_text=build_fact_extractor_input(
            history_text=history_text,
            current_profile=current_profile,
            user_message=user_message,
            current_focus_slot=current_focus_slot,
            current_focus_field=current_focus_field,
        ),
        tool_name=EXTRACTOR_TOOL_NAME,
        tool_description=EXTRACTOR_TOOL_DESCRIPTION,
        input_schema=EXTRACTOR_SCHEMA,
    )
    try:
        return IntakeFacts.model_validate(raw)
    except ValidationError as exc:
        raise FactExtractorError(f"intake_fact_validation_failed: {exc}") from exc


def build_fact_extractor_prompt() -> str:
    from app.core.rules import get_extraction_principles, get_rules

    fields = ", ".join(sorted(INTAKE_ALLOWED_FIELDS))

    # Load extraction-only principles from rules.yaml (reply principles không liên quan)
    principles = get_extraction_principles()
    principles_text = "\n".join(f"- {p}" for p in principles)

    # Load slot-specific rules from rules.yaml
    rules = get_rules()
    dc = rules.get("data_collection", {})
    slots = dc.get("slots", [])
    slot_rules_text = ""
    for slot in slots:
        slot_rules = slot.get("rules", [])
        if slot_rules:
            slot_rules_text += f"\nSlot {slot['id']} ({slot.get('label', '')}):\n"
            for r in slot_rules:
                slot_rules_text += f"  - {r}\n"

    return f"""Bạn là bộ trích xuất dữ liệu hội thoại đồng thời là bộ nhận diện ý định/thái độ cho Em Linh MKT.

NGUYÊN TẮC CHUNG THU THẬP DỮ LIỆU:
{principles_text}

QUY TẮC RIÊNG THEO SLOT:
{slot_rules_text}

QUY TẮC PHÂN TÍCH Ý ĐỊNH & THÁI ĐỘ (OBSERVATION):
- intent: Phân loại TIN NHẮN MỚI NHẤT của dealer vào 1 trong các nhóm sau:
  * affirmative: dealer đồng ý (ok, ừ, chuẩn, được, vâng)
  * refusal: dealer từ chối cung cấp thông tin (không cho, miễn, bỏ qua)
  * khong_biet: dealer không có thông tin/tùy bot (không biết, không nhớ, tùy em, em chọn đi)
  * defensive: dealer hỏi ngược/nghi ngờ/vặn vẹo bot (lừa đảo à, có mất phí không, công ty nào)
  * tam_su: dealer kể chuyện đời/tâm sự (về thời tiết, gia đình, sức khỏe, khó khăn nghề nghiệp)
  * edit: dealer sửa thông tin đã cung cấp trước đó (sửa X thành Y, không phải...)
  * confusion: dealer hỏi lại vì không hiểu ý bot (là sao, ý em là sao, chưa rõ)
  * normal: dealer trả lời thẳng câu hỏi slot (mặc định)
  Nếu tin nhắn có nhiều ý định chồng chéo, hãy ưu tiên theo thứ tự: defensive > confusion > tam_su > refusal > khong_biet > edit > affirmative > normal.
- is_busy: true nếu tin nhắn ngắn gọn (<= 3 từ) hoặc dealer thể hiện sự vội vàng, bận rộn.
- is_emotional: true nếu tin nhắn dài (> 15 từ) hoặc dealer đang chia sẻ cảm xúc/tâm sự.
- is_skeptical: true nếu intent là defensive hoặc thể hiện sự nghi ngờ rõ ràng.
- wants_brief: true nếu dealer yêu cầu hoặc đã từng yêu cầu nhắn ngắn gọn trong lịch sử trò chuyện, VÀ dealer chưa từng yêu cầu nói dài/chi tiết/bình thường trở lại sau yêu cầu đó.


QUY TẮC KỸ THUẬT EXTRACTION:
- Đọc lịch sử hội thoại và tin nhắn mới nhất.
- Trích xuất TẤT CẢ thông tin đại lý có evidence rõ, kể cả ngoài thứ tự câu hỏi.
- Nếu người dùng sửa thông tin cũ, đặt is_correction=true.
- Nếu không chắc, không đoán cứng; bỏ qua fact hoặc ghi uncertainty_notes.
- Không xuất field derived: province, ward, district, brand_name_short, hotline, slogan_options.
- `current_focus_field` là field bot vừa hỏi — DÙNG để HIỂU ngữ cảnh câu trả lời, TUYỆT ĐỐI KHÔNG ép mọi tin nhắn thành value của field đó (xem luật KHỚP NGỮ NGHĨA ở trên).
- Với field list (category_stack, supplier_brands): trả value dạng text phân tách dấu phẩy.
- Phải đọc câu bot ngay trước đó để hiểu tham chiếu (vd "2 hãng đó" → quy về tên cụ thể).
- Không bao giờ xuất placeholder làm value: "cả hai", "như trên", và TUYỆT ĐỐI không xuất token tiếng Anh "none"/"null"/"n/a"/"undefined".
- Với dữ liệu OPTIONAL, resolve riêng từng field trong resolved_optional_fields.

Field được phép:
{fields}

Chỉ trả JSON đúng schema, không markdown, không text ngoài JSON.
"""



def build_fact_extractor_input(
    *,
    history_text: str,
    current_profile: DealerProfileRaw,
    user_message: str,
    current_focus_slot: str | None = None,
    current_focus_field: str | None = None,
) -> str:
    return f"""Profile hiện tại:
{_profile_summary(current_profile)}

Slot đang được ưu tiên hỏi:
{current_focus_slot or "(chưa xác định)"}

Field chính xác bot vừa hỏi:
{current_focus_field or "(chưa xác định)"}

Lịch sử gần đây:
{history_text}

Tin nhắn mới nhất:
{user_message}
"""


def _profile_summary(profile: DealerProfileRaw) -> str:
    parts: list[str] = []
    for key, value in profile.model_dump().items():
        if _has_value(value):
            parts.append(f"{key}={value}")
    return "; ".join(parts) if parts else "(chưa có)"


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True
