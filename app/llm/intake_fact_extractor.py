"""Full-context fact extractor for the LLM-first intake engine."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.llm.client import LLMClient
from app.models.schema import DealerProfileRaw
from app.slots.definitions import OPTIONAL_SLOTS, SLOT_TO_ALL_FIELDS


DERIVED_FIELDS = {
    "province",
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
}
INTAKE_ALLOWED_FIELDS: set[str] = {
    field
    for fields in SLOT_TO_ALL_FIELDS.values()
    for field in fields
    if field not in DERIVED_FIELDS
} | BRANDING_PREFERENCE_FIELDS
Confidence = Literal["low", "medium", "high"]


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

    @field_validator("resolved_optional_slots")
    @classmethod
    def slots_must_be_optional(cls, values: list[str]) -> list[str]:
        invalid = [value for value in values if value not in OPTIONAL_SLOTS]
        if invalid:
            raise ValueError(f"Unsupported optional slot: {invalid}")
        return list(dict.fromkeys(values))


EXTRACTOR_TOOL_NAME = "extract_linh_intake_facts"
EXTRACTOR_TOOL_DESCRIPTION = (
    "Extract dealer profile facts from the recent Em Linh MKT conversation. "
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
    },
    "required": ["facts"],
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
) -> IntakeFacts:
    """Extract profile facts from recent/full conversation context."""
    raw = client.extract_quality(
        system_prompt=build_fact_extractor_prompt(),
        conversation_text=build_fact_extractor_input(
            history_text=history_text,
            current_profile=current_profile,
            user_message=user_message,
            current_focus_slot=current_focus_slot,
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
    fields = ", ".join(sorted(INTAKE_ALLOWED_FIELDS))
    return f"""Bạn là bộ trích xuất dữ liệu cho Em Linh MKT.

Nhiệm vụ:
- Đọc lịch sử hội thoại và tin nhắn mới nhất.
- Trích xuất TẤT CẢ thông tin đại lý có evidence rõ, kể cả ngoài thứ tự câu hỏi.
- Không ép theo slot hiện tại.
- Nếu người dùng sửa thông tin cũ, đặt is_correction=true.
- Nếu không chắc, không đoán cứng; bỏ qua fact hoặc ghi uncertainty_notes.
- Không xuất field derived như province, district, brand_name_short, hotline, slogan_options.
- Không hard-code địa danh. Nếu hiểu địa danh từ ngữ cảnh/STT thì value là cách hiểu tốt nhất và evidence phải ghi rõ.
- Với địa chỉ/tên hãng/tên riêng nghe chưa rõ do gõ sai hoặc STT, KHÔNG đánh confidence high. Nếu chỉ đoán được ứng viên, bỏ qua fact hoặc trả confidence="low" và ghi uncertainty_notes để bot hỏi xác nhận.
- Nếu bot vừa hỏi xác nhận một ứng viên cụ thể, ví dụ "Gia Lâm, Hà Nội đúng không anh?", và dealer trả lời "ừ, đúng, ok", khi đó mới xuất address/hãng với confidence high theo ứng viên đã được xác nhận.
- Nếu dealer chỉ nói tên quận/khu như "Gia Lâm", "Ocean Park" mà chưa có tỉnh/thành trong lịch sử, không coi là đủ địa chỉ; để bot hỏi xác nhận tỉnh/thành trước.
- Với field list như category_stack/supplier_brands, có thể trả value dạng text phân tách bằng dấu phẩy.
- Phải đọc câu bot ngay trước đó để hiểu tham chiếu. Ví dụ bot vừa gợi ý "Hòa Phát hay Việt Nhật", dealer nói "anh xài 2 hãng đó" hoặc "cả hai" thì supplier_brands phải là "Hòa Phát, Việt Nhật".
- Không bao giờ xuất placeholder như "2 hãng đó", "hai hãng đấy", "cả hai", "như trên" làm value. Nếu tham chiếu không đủ rõ để quy về giá trị cụ thể thì bỏ qua fact và ghi uncertainty_notes.
- Nếu dealer nói "Zalo giống số trên", "dùng số cá nhân luôn" khi profile đã có phone_or_zalo, hãy xuất zalo bằng đúng phone_or_zalo hiện có.
- Với các chủ đề nhiều field con của Linh, cố gắng extract đủ nếu có evidence: 2.4 gồm supplier_brands, customer_segment_signal, supplier_negotiation_signal; 2.6 gồm facebook, fb_marketing_status, community_network_signal; 3.3 gồm customer_pain, motivation_signal, usp_signal.
- Nếu câu bot ngay trước đang xin nhận bộ thương hiệu ở slot 4.0 và dealer trả lời "ok", "ừ", "đồng ý", hãy trích xuất brandkit_consent="yes".
- Ba preference logo được phép thu trực tiếp: logo_initials, slogan_preference, logo_style.
- Nếu bot đang hỏi màu, viết tắt, slogan hoặc phong cách logo và dealer nói "em chọn đi", "tùy em", "anh không rành", hãy xuất field tương ứng với value="auto". Không hỏi lặp.
- Nếu dealer tự đưa viết tắt, slogan hoặc phong cách cụ thể thì lưu đúng nội dung dealer chọn.
- Nếu dealer nói không biết, không có, bỏ qua hoặc không muốn trả lời một câu OPTIONAL đang hỏi, thêm slot đó vào resolved_optional_slots để bot không hỏi lặp. Không đánh dấu slot chỉ vì dealer chưa trả lời.

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
) -> str:
    return f"""Profile hiện tại:
{_profile_summary(current_profile)}

Slot đang được ưu tiên hỏi:
{current_focus_slot or "(chưa xác định)"}

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
