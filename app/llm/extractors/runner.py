"""Extractor runner — gọi LLM với tool schema, validate, trả dict.

Refer F2B.2 (LUAT_2B_llm v0.1.2).

Flow:
    1. Get tool schema cho slot_id
    2. Build system prompt (F2B.1)
    3. Call LLM_FAST tier với extract_structured (JSON mode)
    4. Validate từng field qua validators.py
    5. Return dict {field_name: cleaned_value_or_none}
"""
from __future__ import annotations

import logging
from typing import Optional

from app.llm.client import LLMClient
from app.llm.extractors.schemas import SLOT_TOOL_SCHEMAS, get_tool_schema
from app.llm.extractors.validators import validate_field
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


def extract_slot(
    slot_id: str,
    user_message: str,
    client: LLMClient,
    dealer_type: Optional[DealerType] = None,
    address_form: AddressForm = AddressForm.ANH,
) -> dict:
    """Extract fields cho slot từ user message.

    Args:
        slot_id: vd "1.1", "1.2", "4.0" (Phase 1 chỉ 3 slot có schema)
        user_message: text từ dealer
        client: LLMClient (test có thể inject mock)
        dealer_type: Detected dealer type (UNKNOWN default Phase 1)
        address_form: anh / chị

    Returns:
        Dict {field_name: validated_value_or_none}.
        Empty dict nếu:
        - slot_id không có schema (Phase 2+ slot)
        - LLM fail / không extract được
        - Tất cả field invalid sau validate
    """
    tool = get_tool_schema(slot_id)
    if tool is None:
        logger.warning("Slot %s không có extractor schema (Phase 2+)", slot_id)
        return {}

    if not user_message or not user_message.strip():
        return {}

    # Build system prompt cho extractor
    system = build_system_prompt(
        dealer_type=dealer_type,
        address_form=address_form,
        current_slot=slot_id,
        task=(
            f"Extract field cho slot {slot_id} từ message của dealer. "
            f"Tuân thủ tool schema strict. Field dealer chưa cho → null."
        ),
    )

    # Call LLM_FAST với JSON mode (extract_structured)
    try:
        raw_output = client.extract_fast(
            system_prompt=system,
            conversation_text=user_message,
            tool_name=tool["name"],
            tool_description=tool["description"],
            input_schema=tool["input_schema"],
        )
    except Exception as e:
        logger.exception("LLM extract fail slot=%s: %s", slot_id, e)
        return {}

    if not isinstance(raw_output, dict):
        logger.warning("LLM extract slot=%s trả về non-dict: %r", slot_id, raw_output)
        return {}

    # Validate từng field
    validated: dict = {}
    field_names = tool["input_schema"]["properties"].keys()
    for field_name in field_names:
        raw_value = raw_output.get(field_name)
        if raw_value is None or raw_value == "":
            validated[field_name] = None
            continue
        ok, cleaned = validate_field(field_name, raw_value)
        validated[field_name] = cleaned if ok else None

    return validated
