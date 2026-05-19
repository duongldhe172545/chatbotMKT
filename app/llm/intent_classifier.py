"""Layer 2 intent classifier — LLM fallback khi regex Layer 1 không match.

Refer:
- F2B.3 (LUAT_2B_llm) — prompt template + 7 intent enum
- F2A.2 — 2-layer intent detection
- Phase 4 R3

Flow:
1. detect_intent_layer1() trả None hoặc Intent.NORMAL (fallback default)
2. Caller (conversation orchestrator) check: nếu message ≥ 4 từ + Layer 1
   trả NORMAL → gọi Layer 2 LLM classify
3. LLM trả enum value + confidence + reasoning
4. Engine merge: nếu LLM confidence ≥ MED → dùng LLM result

Cost: LLM_FAST ~$0.0003/call. Layer 2 chỉ gọi khi cần (≤ 5% turn).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.llm.client import LLMClient
from app.models.enums import Intent

logger = logging.getLogger(__name__)


# 7 intent label → Intent enum
_INTENT_LABELS: dict[str, Intent] = {
    "affirmative": Intent.AFFIRMATIVE,
    "refusal": Intent.REFUSAL,
    "khong_biet": Intent.KHONG_BIET,
    "defensive": Intent.DEFENSIVE,
    "tam_su": Intent.TAM_SU,
    "edit": Intent.EDIT,
    "normal": Intent.NORMAL,
}


_TOOL_SCHEMA = {
    "name": "classify_intent",
    "description": (
        "Phân loại MESSAGE từ dealer ngành cửa nhôm kính / VLXD vào "
        "1 trong 7 intent. Nếu ambiguous, áp priority: "
        "defensive > tam_su > refusal > khong_biet > edit > affirmative > normal."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": list(_INTENT_LABELS.keys()),
                "description": (
                    "affirmative=đồng ý/xác nhận, refusal=từ chối field, "
                    "khong_biet=không có thông tin, defensive=hỏi ngược/nghi, "
                    "tam_su=kể chuyện đời, edit=sửa field, normal=trả lời "
                    "thẳng câu hỏi slot."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["LOW", "MED", "HIGH"],
                "description": "Confidence level. LOW → caller có thể giữ Intent.NORMAL.",
            },
        },
        "required": ["intent", "confidence"],
        "additionalProperties": False,
    },
}


_SYSTEM_PROMPT = """\
Bạn là intent classifier Layer 2 cho chatbot Em Linh MKT (intake dealer
ngành cửa nhôm kính / cửa cuốn / tủ bếp Việt Nam).

7 intent enum (mô tả ngắn):
- affirmative: dealer đồng ý (ok, ừ, chuẩn, được, vâng)
- refusal: dealer từ chối field cụ thể (không cho, miễn, bỏ qua)
- khong_biet: dealer KHÔNG có thông tin (không biết, không nhớ, tùy em)
- defensive: dealer hỏi ngược/nghi ngờ bot (lừa đảo, phí gì, công ty nào)
- tam_su: dealer kể chuyện đời (gia đình, sức khoẻ, thời tiết, nhậu)
- edit: dealer sửa field đã ghi (sửa X thành Y, không phải...)
- normal: dealer trả lời thẳng câu hỏi slot (default)

Quy tắc:
1. Nếu ambiguous (match nhiều) → áp priority:
   defensive > tam_su > refusal > khong_biet > edit > affirmative > normal
2. CẤM trả intent không trong enum.
3. Trả JSON đúng schema.
"""


def classify_intent_layer2(
    message: str,
    client: LLMClient,
    stage: Optional[str] = None,
    current_slot: Optional[str] = None,
) -> tuple[Optional[Intent], str]:
    """Gọi LLM_FAST classify intent.

    Args:
        message: Dealer raw message
        client: LLMClient
        stage: Optional context — stage hiện tại (vd "ASKING")
        current_slot: Slot đang hỏi (vd "1.3")

    Returns:
        (intent_enum, confidence_str). intent=None nếu LLM fail.
        confidence_str ∈ {"LOW","MED","HIGH"} — caller check để decide
        có dùng kết quả LLM không.
    """
    if not message or not isinstance(message, str):
        return (None, "LOW")

    user_text = f"MESSAGE: {message}"
    if stage:
        user_text = f"Stage: {stage}\n" + user_text
    if current_slot:
        user_text = f"Slot đang hỏi: {current_slot}\n" + user_text

    try:
        result = client.extract_fast(
            system_prompt=_SYSTEM_PROMPT,
            conversation_text=user_text,
            tool_name=_TOOL_SCHEMA["name"],
            tool_description=_TOOL_SCHEMA["description"],
            input_schema=_TOOL_SCHEMA["input_schema"],
        )
    except Exception as e:
        logger.exception("Intent classifier L2 fail: %s", e)
        return (None, "LOW")

    if not isinstance(result, dict):
        return (None, "LOW")

    intent_str = result.get("intent")
    confidence = result.get("confidence", "LOW")

    if intent_str not in _INTENT_LABELS:
        logger.warning("L2 intent classifier trả enum lạ: %r", intent_str)
        return (None, "LOW")
    if confidence not in ("LOW", "MED", "HIGH"):
        confidence = "LOW"

    return (_INTENT_LABELS[intent_str], confidence)


# ============================================================
# PII leak guard — Phase 4 R3
# ============================================================


def check_pii_leak(
    bot_response: str,
    current_session_id: str,
    store,
    fields_to_check: Optional[list[str]] = None,
) -> list[str]:
    """Check bot_response có chứa PII của session khác không.

    Args:
        bot_response: Bot reply candidate
        current_session_id: Session ID hiện tại (skip khi compare)
        store: SQLiteStore
        fields_to_check: Field cần check (default: phone, address, dealer_name,
                         owner_name).

    Returns:
        List session_id mà PII xuất hiện trong response. Empty nếu clean.

    Note: load profile các session khác → memory cost O(N). Phase 4 R4
    Redis cache cho production scale (default in-memory OK cho dev).
    """
    if not bot_response or not current_session_id:
        return []
    if fields_to_check is None:
        fields_to_check = ["phone_or_zalo", "address", "dealer_name", "owner_name"]

    try:
        with store._connect() as conn:
            cursor = conn.execute(
                "SELECT session_id, phone_or_zalo, address, dealer_name, "
                "owner_name FROM dealer_profile_raw "
                "WHERE session_id != ?",
                (current_session_id,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.exception("PII leak DB scan fail: %s", e)
        return []

    leaked_sessions: list[str] = []
    for row in rows:
        sid = row["session_id"]
        for field in fields_to_check:
            value = row.get(field)
            if not value or not isinstance(value, str) or len(value) < 4:
                continue
            # Skip generic ngắn (vd owner_name "An" 2 char) — false positive
            if value in bot_response:
                logger.error(
                    "PII LEAK: response chứa %s=%r của session=%s (current=%s)",
                    field, value, sid, current_session_id,
                )
                if sid not in leaked_sessions:
                    leaked_sessions.append(sid)
                break  # 1 field/session đủ
    return leaked_sessions
