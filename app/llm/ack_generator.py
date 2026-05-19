"""Ack generator — LLM gen ack response per dealer_type.

Refer:
- F2B.4 (LUAT_2B_llm v0.1.2) — ack generator per dealer type
- 1B § 2 — tone matrix 4 nhóm
- D8 STRATEGY — LLM_FAST cho Bận/Lửa Lò, LLM_QUALITY cho Khoe/Lo
- F2C.4 — fallback safe ack khi LLM fail
"""
from __future__ import annotations

import logging
from typing import Optional

from app.llm.client import LLMClient
from app.llm.fallback import safe_ack
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


# Dealer type nào dùng LLM_QUALITY (insight cụ thể cần model mạnh)
_QUALITY_TIER_TYPES: set[DealerType] = {DealerType.KHOE, DealerType.LO}


def generate_ack(
    slot_id: str,
    extracted_data: dict,
    client: LLMClient,
    dealer_type: Optional[DealerType] = None,
    address_form: AddressForm = AddressForm.ANH,
    history_summary: str = "(chưa có)",
    use_fallback_on_error: bool = True,
) -> str:
    """Gen ack response cho dealer sau khi extract field.

    Args:
        slot_id: Slot vừa fill (vd "1.1")
        extracted_data: Field đã extract (cho LLM biết context). Vd:
            {"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"}
        client: LLMClient
        dealer_type: Detected dealer type. None → UNKNOWN (default tone Bận Phase 1).
        address_form: anh / chị
        history_summary: Tóm tắt history cho LLM context
        use_fallback_on_error: True → return safe_ack khi LLM fail.
            False → return empty string.

    Returns:
        Ack text từ LLM, hoặc safe_ack fallback nếu fail.
    """
    dealer_type = dealer_type or DealerType.UNKNOWN

    # Build user message cho LLM
    data_str = ", ".join(
        f"{k}={v}" for k, v in extracted_data.items() if v is not None
    ) or "(không có data extracted)"

    user_msg = (
        f"Dealer vừa cho data ở slot {slot_id}: {data_str}\n\n"
        f"Sinh 1 câu ACK ngắn theo tone {dealer_type.value}. "
        f"KHÔNG tự ask slot kế (engine sẽ append). "
        f"KHÔNG dùng vocab cấm (Tier, BRANDKIT, Scoring, etc.)."
    )

    system = build_system_prompt(
        dealer_type=dealer_type,
        address_form=address_form,
        current_slot=slot_id,
        history_summary=history_summary,
        task=f"Gen 1 câu ACK ngắn cho dealer type {dealer_type.value}.",
    )

    # Route tier per dealer_type (D8 STRATEGY)
    is_quality = dealer_type in _QUALITY_TIER_TYPES
    chat_fn = client.chat_quality if is_quality else client.chat_fast

    # Quality tier (Khoe/Lo) cần dài hơn — ack 15-30 từ + có insight cụ thể.
    # Gemini Pro thinking mode còn ăn budget → cần buffer rộng để không
    # empty text. Flash tier (Bận/Lửa) ngắn ≤ 12 từ → 128 token đủ.
    max_tokens = 768 if is_quality else 192

    try:
        response_text = chat_fn(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.exception("Ack gen fail slot=%s type=%s: %s", slot_id, dealer_type, e)
        if use_fallback_on_error:
            return safe_ack()
        return ""

    text = (response_text or "").strip()
    if not text:
        if use_fallback_on_error:
            return safe_ack()
        return ""

    return text


def is_quality_tier_type(dealer_type: DealerType) -> bool:
    """Returns True nếu dealer_type dùng LLM_QUALITY tier. Refer D8."""
    return dealer_type in _QUALITY_TIER_TYPES
