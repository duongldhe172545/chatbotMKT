"""Tâm sự handler — LLM_QUALITY gen empathy CỤ THỂ + bridge phrase.

Refer:
- F2B.4b (LUAT_2B_llm) — tâm sự handler spec
- File 1C § 3 — tâm sự kéo dài escalation
- File 1B § 5.2 — tâm sự engage CỤ THỂ
- CORE § D.4 — engage 1-2 nhịp trước quay slot
- STRATEGY D8 — tâm sự dùng LLM_QUALITY

Pattern:
- Empathy CỤ THỂ với chuyện dealer kể (KHÔNG generic "khổ thân anh")
- KHÔNG khuyên y tế / pháp lý / tài chính cá nhân
- Sau 1-2 nhịp engage → bridge phrase quay slot
- Nếu tâm sự ≥ 3 turn liên tiếp → polite cut

Sub-task topic detect — LLM_FAST (6 topic: work_stress/family/health/hobby/financial/other).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.llm.client import LLMClient
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


TAM_SU_POLITE_CUT_AT = 3  # ≥ N turn → polite cut

# Topic enum cho sub-task topic detect (F2B.4b TAM_SU_TOPIC_ENUM)
TAM_SU_TOPICS = (
    "work_stress",
    "family",
    "health",
    "hobby",
    "financial",
    "other",
)


def _build_topic_task() -> str:
    """Task instruction cho LLM_FAST topic classifier."""
    return (
        "Phân loại topic tâm sự dealer vừa kể vào 1 trong 6 nhãn:\n"
        "- work_stress: stress nghề, dự án cháy, thợ bỏ việc, deadline gấp\n"
        "- family: vợ con, gia đình, hôn nhân\n"
        "- health: sức khoẻ, ốm, bệnh, mệt mỏi thể chất\n"
        "- hobby: golf, cầu lông, bóng đá, du lịch, sở thích\n"
        "- financial: nợ nần, kinh tế khó khăn, tài chính cá nhân\n"
        "- other: không thuộc 5 nhóm trên\n\n"
        "Trả về JSON với schema topic, severity (1 nhẹ → 3 nặng)."
    )


_TOPIC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "enum": list(TAM_SU_TOPICS)},
        "severity": {"type": "integer", "minimum": 1, "maximum": 3},
    },
    "required": ["topic"],
}


def detect_topic(
    dealer_message: str,
    client: LLMClient,
) -> tuple[str, int]:
    """Detect topic + severity của tâm sự message. LLM_FAST.

    Returns:
        (topic, severity). Default ("other", 1) nếu LLM fail.
    """
    if not dealer_message or not isinstance(dealer_message, str):
        return ("other", 1)

    system = build_system_prompt(
        dealer_type=DealerType.UNKNOWN,
        address_form=AddressForm.ANH,
        task=_build_topic_task(),
    )
    try:
        result = client.extract_fast(
            system_prompt=system,
            conversation_text=f"Dealer: {dealer_message}",
            tool_name="classify_tam_su_topic",
            tool_description="Phân loại topic tâm sự + mức độ nặng/nhẹ.",
            input_schema=_TOPIC_SCHEMA,
        )
    except Exception as e:
        logger.exception("Topic detect fail: %s", e)
        return ("other", 1)

    if not isinstance(result, dict):
        return ("other", 1)
    topic = result.get("topic")
    if topic not in TAM_SU_TOPICS:
        topic = "other"
    severity_raw = result.get("severity", 1)
    try:
        severity = max(1, min(3, int(severity_raw)))
    except (TypeError, ValueError):
        severity = 1
    return (topic, severity)


def _build_tam_su_task(
    dealer_message: str,
    tam_su_count: int,
    topic: str,
    severity: int,
    dealer_type: DealerType,
    next_slot_hint: Optional[str],
) -> str:
    """Build task instruction cho LLM_QUALITY tâm sự handler."""
    is_polite_cut = tam_su_count >= TAM_SU_POLITE_CUT_AT
    is_heavy = severity >= 3

    base = (
        f'Đại lý vừa kể tâm sự: "{dealer_message}"\n\n'
        f"Context:\n"
        f"- Tâm sự lần thứ {tam_su_count} trong session\n"
        f"- Topic: {topic}\n"
        f"- Severity (1 nhẹ → 3 nặng): {severity}\n"
        f"- Dealer type: {dealer_type.value}\n"
    )
    if next_slot_hint:
        base += f"- Slot kế tiếp engine sẽ hỏi: {next_slot_hint}\n"

    base += (
        f"\nSinh 1 response engage 1-2 nhịp:\n"
        f"- Empathy CỤ THỂ với chuyện dealer kể (KHÔNG generic 'khổ thân anh')\n"
        f"- KHÔNG khuyên y tế / pháp lý / tài chính / thuế\n"
        f"- KHÔNG bơ → hỏi slot ngay\n"
        f"- Sau 1-2 nhịp engage → dẫn về flow bằng bridge phrase tự nhiên "
        f'(vd "À cho em hỏi tiếp anh xíu, ...")\n\n'
        f"Yêu cầu:\n"
        f"- 30-60 từ\n"
        f"- KHÔNG promise tiền / ưu đãi / job\n"
        f"- KHÔNG vocab cấm (Tier, BRANDKIT, Scoring, ...)\n"
    )

    if is_heavy:
        base += (
            f"\n⚠️ Tâm sự NẶNG (severity {severity}) — ví dụ ly hôn / bệnh hiểm / "
            f"phá sản → KHÔNG khuyên gì cụ thể, gợi cộng đồng kết nối: "
            f'"Bên em có nhóm anh em ngành, anh muốn em giới thiệu để có người '
            f'chia sẻ không?"'
        )
    if is_polite_cut:
        base += (
            f"\n⚠️ Tâm sự đã ≥ {TAM_SU_POLITE_CUT_AT} turn liên tiếp → POLITE CUT: "
            f'"Team người thật bên em có thể trò chuyện kỹ hơn em — em ghi nhận '
            f'câu chuyện anh chia sẻ rồi ạ. Mình quay lại phần thông tin nhé?"'
        )
    return base


def handle_tam_su(
    dealer_message: str,
    tam_su_count: int,
    dealer_type: DealerType,
    address_form: AddressForm,
    client: LLMClient,
    history_summary: str = "(chưa có)",
    current_slot: Optional[str] = None,
    next_slot_hint: Optional[str] = None,
    topic: Optional[str] = None,
    severity: Optional[int] = None,
    bridge_avoid_hint: str = "",
) -> Optional[str]:
    """Gen LLM_QUALITY response cho intent=TAM_SU.

    Args:
        dealer_message: Raw dealer message tâm sự
        tam_su_count: Số lần tâm sự liên tiếp trong session (≥ 1)
        dealer_type: Detected dealer type
        address_form: anh / chị
        client: LLMClient
        history_summary: Tóm tắt 3 turn gần
        current_slot: Slot đang hỏi
        next_slot_hint: Text câu hỏi slot kế (cho LLM bridge tự nhiên)
        topic: Optional override topic (nếu caller đã detect)
        severity: Optional override severity

    Returns:
        Response text, hoặc None nếu LLM fail (caller fallback template).
    """
    if not dealer_message or not isinstance(dealer_message, str):
        return None

    dealer_type = dealer_type or DealerType.UNKNOWN

    # Auto detect topic nếu caller không cung cấp
    if topic is None or severity is None:
        topic_detected, severity_detected = detect_topic(dealer_message, client)
        topic = topic or topic_detected
        severity = severity or severity_detected

    task = _build_tam_su_task(
        dealer_message=dealer_message,
        tam_su_count=max(1, tam_su_count),
        topic=topic,
        severity=severity,
        dealer_type=dealer_type,
        next_slot_hint=next_slot_hint,
    )

    system_prompt = build_system_prompt(
        dealer_type=dealer_type,
        address_form=address_form,
        current_slot=current_slot,
        history_summary=history_summary,
        task=task,
        bridge_avoid_hint=bridge_avoid_hint,
    )

    try:
        response = client.chat_quality(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": dealer_message}],
            max_tokens=768,
        )
    except Exception as e:
        logger.exception(
            "Tâm sự handler LLM fail: count=%d msg=%r err=%s",
            tam_su_count, dealer_message[:80], e,
        )
        return None

    text = (response or "").strip()
    if not text:
        logger.warning(
            "Tâm sự handler LLM returned empty: count=%d msg=%r",
            tam_su_count, dealer_message[:80],
        )
        return None
    return text
