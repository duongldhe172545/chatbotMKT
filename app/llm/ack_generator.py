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


def generate_unified_response(
    slot_id: str,
    extracted_data: dict,
    next_slot_id: str,
    next_slot_question: str,
    next_slot_why: str,
    client: LLMClient,
    dealer_type: Optional[DealerType] = None,
    address_form: AddressForm = AddressForm.ANH,
    history_summary: str = "(chưa có)",
    use_fallback_on_error: bool = True,
    bridge_avoid_hint: str = "",
    recently_acked_name: Optional[str] = None,
    ref_filled_fields: Optional[list[str]] = None,
) -> str:
    """Sinh câu thoại hợp nhất phản hồi thông tin cũ + nêu lý do + hỏi thông tin mới.

    Args:
        slot_id: Slot vừa fill (vd "1.1")
        extracted_data: Field đã extract (cho LLM biết context). Vd:
            {"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"}
        next_slot_id: Slot tiếp theo chuẩn bị hỏi
        next_slot_question: Câu hỏi mẫu của slot tiếp theo để tham khảo
        next_slot_why: Lý do kinh doanh (Business Why) tại sao cần hỏi câu tiếp
        client: LLMClient
        dealer_type: Detected dealer type. None → UNKNOWN (default tone Bận Phase 1).
        address_form: anh / chị
        history_summary: Tóm tắt history cho LLM context
        use_fallback_on_error: True → return safe_ack khi LLM fail.
            False → return empty string.

    Returns:
        Câu thoại hợp nhất từ LLM, hoặc safe_ack fallback nếu fail.
    """
    dealer_type = dealer_type or DealerType.UNKNOWN

    # Build user message cho LLM
    data_str = ", ".join(
        f"{k}={v}" for k, v in extracted_data.items() if v is not None
    ) or "(không có data extracted)"

    user_msg = f"Dữ liệu dealer vừa cung cấp ở slot {slot_id}: {data_str}\n\n"
    
    if next_slot_id:
        user_msg += (
            f"Mục tiêu tiếp theo là hỏi thông tin cho slot {next_slot_id}.\n"
            f"Lý do cần thông tin này (Business Why): {next_slot_why}\n"
            f"Câu hỏi mẫu tham khảo làm ý tưởng: '{next_slot_question}'\n\n"
            f"Nhiệm vụ: Hãy tạo phản hồi hợp nhất mượt mà và ấm áp theo tone {dealer_type.value}.\n"
            f"1. Phản hồi thông cảm/khen nhẹ dựa trên thông tin vừa nhận ({data_str}).\n"
            f"2. Nêu lý do ngắn gọn tại sao cần hỏi câu tiếp theo (dựa trên Business Why).\n"
            f"3. Hỏi tự nhiên để lấy thông tin mới cho slot {next_slot_id} (hãy sáng tạo dựa trên câu hỏi mẫu trên).\n"
            f"Hãy viết thành 1-2 đoạn văn ngắn hoàn chỉnh, tự nhiên như tư vấn trực tiếp."
        )
    else:
        user_msg += (
            f"Sinh 1 câu phản hồi ngắn theo tone {dealer_type.value}.\n"
            f"KHÔNG dùng các từ cấm (Tier, Scoring, C1-C9, etc.)."
        )

    # Phase 6 R+ Fix B: tránh lặp ack tên dealer turn N+1
    if recently_acked_name:
        user_msg += (
            f"\n\n⚠️ ĐÃ ack '{recently_acked_name}' turn trước — turn này "
            f"KHÔNG nhắc lại tên này. Ack data khác (vd dealer_name, address) "
            f"hoặc cảm thán mở chung."
        )
    # Phase 6 R+ Fix C: ack explicit khi field fill từ reference dealer
    # nói ("cùng tên anh luôn" → dealer_name = owner_name).
    if ref_filled_fields:
        ref_list = ", ".join(ref_filled_fields)
        user_msg += (
            f"\n\n⚠️ Field {ref_list} được fill từ DEALER REFERENCE "
            f"(dealer nói 'cùng tên anh' / 'giống vậy'). Ack phải EXPLICIT "
            f"để dealer biết bot hiểu đúng, vd 'Dạ tên cửa hàng cũng là "
            f"{{value}} ạ'. KHÔNG ack chung chung."
        )

    system = build_system_prompt(
        dealer_type=dealer_type,
        address_form=address_form,
        current_slot=slot_id,
        history_summary=history_summary,
        task=f"Tạo phản hồi hợp nhất tự nhiên cho dealer type {dealer_type.value}.",
        bridge_avoid_hint=bridge_avoid_hint,
    )

    # Route tier per dealer_type (D8 STRATEGY)
    is_quality = dealer_type in _QUALITY_TIER_TYPES
    chat_fn = client.chat_quality if is_quality else client.chat_fast

    # Quality tier (Khoe/Lo) cần dài hơn — ack 15-30 từ + có insight cụ thể.
    # Gemini Pro thinking mode còn ăn budget → cần buffer rộng để không
    # empty text. Flash tier (Bận/Lửa) ngắn ≤ 12 từ → 128 token đủ.
    max_tokens = 768 if is_quality else 384

    try:
        response_text = chat_fn(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.exception("Unified response gen fail slot=%s next=%s type=%s: %s", slot_id, next_slot_id, dealer_type, e)
        if use_fallback_on_error:
            return safe_ack()
        return ""

    text = (response_text or "").strip()
    if not text:
        if use_fallback_on_error:
            return safe_ack()
        return ""

    # Phase 6 R+ fix 2026-05-22 (user feedback Lỗi 1): hard post-process
    # cấm formula "cái tên ... nghe rất [adj]" — LLM stubborn dùng dù prompt
    # CẤM. Replace bằng phrase tự nhiên hơn.
    text = _scrub_repeated_ack_pattern(text)

    return text


def generate_ack(
    slot_id: str,
    extracted_data: dict,
    client: LLMClient,
    dealer_type: Optional[DealerType] = None,
    address_form: AddressForm = AddressForm.ANH,
    history_summary: str = "(chưa có)",
    use_fallback_on_error: bool = True,
    bridge_avoid_hint: str = "",
    recently_acked_name: Optional[str] = None,
    ref_filled_fields: Optional[list[str]] = None,
) -> str:
    """Gen ack response cho dealer sau khi extract field (legacy compatibility)."""
    return generate_unified_response(
        slot_id=slot_id,
        extracted_data=extracted_data,
        next_slot_id="",
        next_slot_question="",
        next_slot_why="",
        client=client,
        dealer_type=dealer_type,
        address_form=address_form,
        history_summary=history_summary,
        use_fallback_on_error=use_fallback_on_error,
        bridge_avoid_hint=bridge_avoid_hint,
        recently_acked_name=recently_acked_name,
        ref_filled_fields=ref_filled_fields,
    )


# ============================================================
# Phase 6 R+ fix 2026-05-22: post-process cấm formula khen tên lặp
# ============================================================

import re as _re

# Pattern: "cái tên [X] nghe rất [adj] [optional và tạo cảm giác Y]"
# Greedy match phần tail "và/cũng tạo/gợi/cho cảm giác/sự/niềm [Z]" để
# scrub clean hơn (không để lại trailing words "và X").
_CLICHE_NAME_PRAISE_PATTERN = _re.compile(
    r"cái\s*tên\s*(['\"]?[\w\sÀ-ỹ]+?['\"]?)?\s*"
    r"(nghe\s*rất|nghe\s*thật|nghe\s*thấy|nghe\s*có\s*vẻ)\s+"
    r"[\w\sÀ-ỹ]+?"  # adjective + 1-3 từ tiếp
    r"(\s*(và|cũng|kèm|với)\s+(tạo|gợi|cho|mang|khẳng\s*định)\s+"
    r"(được\s+)?(cảm\s*giác|sự|niềm|thương\s*hiệu|uy\s*tín)\s+"
    r"[\w\sÀ-ỹ]+?)?"
    r"(?=[,.!?]|\s+(em|cho|anh|chị|mình)\s)",  # stop at punctuation OR pronoun start
    _re.IGNORECASE,
)

# Replacement đơn giản: "anh [X] — em note rồi ạ" (giữ trung tính)
_CLICHE_REPLACEMENT_VARIANTS = [
    "em đã ghi nhận thông tin",
    "em note rồi",
    "em lưu vào hồ sơ rồi",
    "em đã lưu vào hồ sơ rồi",
    "em ghi nhận thông tin này rồi",
]


def _scrub_repeated_ack_pattern(text: str) -> str:
    """Detect formula 'cái tên ... nghe rất [adj]' — chỉ FLAG warning,
    KHÔNG tự rewrite (risk phá câu).

    CORE B.2 + B.4 #2: KHÔNG dùng cliche khen tên này.

    Phase 6 R+ 2026-05-22: ban đầu em dùng regex replace nhưng gây ra
    sentence awkward (vd "em note rồi cho khách hàng" — duplicate).
    Trade-off: flag + log → admin biết LLM dùng cliche → prompt cải tiến
    qua iterate. Không auto-replace để giữ ack tự nhiên.
    """
    if not text or not isinstance(text, str):
        return text
    if _CLICHE_NAME_PRAISE_PATTERN.search(text):
        logger.warning(
            "Ack uses cliche 'cái tên nghe rất X': %r — system_prompt rule "
            "violated, consider strengthening prompt OR add more few-shot examples.",
            text[:120],
        )
    return text


def is_quality_tier_type(dealer_type: DealerType) -> bool:
    """Returns True nếu dealer_type dùng LLM_QUALITY tier. Refer D8."""
    return dealer_type in _QUALITY_TIER_TYPES
