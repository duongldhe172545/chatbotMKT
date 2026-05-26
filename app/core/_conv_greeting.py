"""GREETING stage handler — Phase 6 R2 refactor.

Refer:
- F2A.1 stage GREETING
- 1A § 3.3 — tone mặc định (chưa biết nhóm dealer)
- 1C § 2 + § 3 + F2B.4b — defensive / tâm sự handler ngay greeting
- Phase 5 R1 Gap 5 — L2 verify khi L1=AFFIRMATIVE dài
"""
from __future__ import annotations

import logging

from app.admin.queue import increment_flag_count
from app.core._conv_helpers import summarize_history
from app.core.bridge_rotation import get_avoid_hint
from app.core.closing import render_soft_end_closing
from app.core.edge_cases import (
    handle_defensive_escalation,
    handle_tam_su_escalation,
    record_tam_su,
)
from app.core.garbage_detector import is_garbage, is_meaningful_short
from app.core.greeting import render_greeting
from app.core.intent import detect_intent
from app.core.session import mark_session_closed
from app.llm.client import LLMClient
from app.llm.defensive_handler import handle_defensive as handle_defensive_llm
from app.llm.intent_classifier import classify_intent_layer2
from app.llm.tam_su_handler import handle_tam_su as handle_tam_su_llm
from app.models.enums import DealerType, Flag, Intent, Stage
from app.models.schema import SessionState
from app.slots.templates import get_question

logger = logging.getLogger(__name__)


_GREETING_GARBAGE_REPROMPT = (
    "Dạ em chưa rõ ý anh lắm ạ. Mình bắt đầu chứ anh? Em chỉ cần "
    "trò chuyện 4-5 phút thôi nhé."
)


_GREETING_FALLBACK_REPROMPT = (
    "Dạ anh sẵn sàng chưa ạ? Mình bắt đầu được không?"
)


def start_session(session: SessionState) -> str:
    """Render greeting cho session mới. Caller add vào history."""
    return render_greeting(session.session_id)


def handle_greeting(
    session: SessionState,
    message: str,
    client: LLMClient,
    profile=None,
) -> str:
    """Stage GREETING dispatcher.

    Xử các edge case ngay tại greeting (refer 1A § 3.3 + 1C § 2/3):
    - DEFENSIVE → LLM defensive handler 3-component (F2B.4b), KHÔNG advance
    - TAM_SU → LLM tâm sự handler, KHÔNG advance
    - Garbage → re-prompt nhẹ, KHÔNG advance
    - REFUSAL → soft-close
    - AFFIRMATIVE/NORMAL → advance ASKING + hỏi slot 1.1
    """
    intent = detect_intent(message)
    word_count = len(message.split())

    # L2 verify nếu L1=AFFIRMATIVE nhưng message dài (>5 từ) — catch jumbled
    # defensive/tâm sự ẩn sau "ờ" / "ok" đầu câu.
    if intent == Intent.AFFIRMATIVE and word_count > 5:
        intent = _l2_verify(message, client, session, intent)

    # L2 fallback nếu L1=NORMAL — bắt defensive/tâm sự ẩn (vd "dùng như nào").
    if intent == Intent.NORMAL and word_count >= 3:
        intent = _l2_verify(message, client, session, intent)

    # Garbage detect tại greeting (1C § 7)
    if not is_meaningful_short(message) and is_garbage(message):
        increment_flag_count(session, Flag.GARBAGE_INPUT)
        return _GREETING_GARBAGE_REPROMPT

    if intent == Intent.DEFENSIVE:
        return _handle_greeting_defensive(session, message, client)

    if intent == Intent.TAM_SU:
        return _handle_greeting_tam_su(session, message, client)

    if intent == Intent.REFUSAL:
        mark_session_closed(session)
        session.stage = Stage.DONE
        return render_soft_end_closing()

    if intent == Intent.AFFIRMATIVE or intent == Intent.NORMAL:
        # Phase 6 R+ Fix BUG UX: dealer gõ data ngay (vd "Lê Dương") thay vì
        # "ok" → KHÔNG advance trống slot 1.1. Forward bridge.
        # NOTE: chỉ kích hoạt bridge khi message KHÔNG chứa BẤT KỲ ack token —
        # "ờ tiếp đi", "ok làm đi", "ừ làm tiếp" đều có token AFFIRMATIVE rõ
        # → advance bình thường + ask slot 1.1 initial.
        session.stage = Stage.ASKING
        session.current_slot = "1.1"
        msg_lower = message.strip().lower()
        # Token AFFIRMATIVE rõ ràng (mở rộng để bắt "tiếp", "làm", "đi")
        ack_tokens = {
            "ok", "okay", "oke", "okê", "vâng", "dạ", "ờ", "ừ", "ờm", "uh",
            "có", "được", "đúng", "rồi", "chuẩn", "yes", "yeah",
            "tiếp", "làm", "đi", "bắt", "đầu", "bắt đầu", "go",
        }
        tokens = [t.strip() for t in msg_lower.split() if t.strip()]
        # is_pure_ack: TẤT CẢ tokens đều là ack token (cho phép "ờ tiếp đi",
        # "ok làm đi", "ừ ok") HOẶC message ≤ 4 từ + có ≥ 1 ack token.
        has_any_ack = any(t in ack_tokens for t in tokens)
        all_ack = bool(tokens) and all(t in ack_tokens for t in tokens)
        is_pure_ack = (
            all_ack
            or (has_any_ack and len(tokens) <= 4)
            or word_count <= 1
        )
        if not is_pure_ack:
            # Phase 6 R+ Fix G4: dealer gõ DATA lẫn (vd "ok anh Tùng Hà Nội")
            # → FORWARD sang asking handler để EXTRACT data, KHÔNG bắt gõ lại.
            if profile is not None:
                from app.core._conv_asking import handle_asking
                return handle_asking(session, profile, message, client)
            # Fallback nếu profile None (test/edge)
            return (
                "Dạ em ghi nhận ạ. Để chính xác từ đầu — anh cho em xin "
                "lại tên anh và tên cửa hàng mình nhé?"
            )
        return (
            get_question("1.1", session_id=session.session_id)
            or "Anh cho em xin tên và tên cửa hàng nhé."
        )

    # KHONG_BIET / EDIT / khác → re-prompt rõ hơn
    return _GREETING_FALLBACK_REPROMPT


def _l2_verify(
    message: str,
    client: LLMClient,
    session: SessionState,
    current_intent: Intent,
) -> Intent:
    """L2 LLM verify — override intent nếu detect DEFENSIVE/TAM_SU/REFUSAL ẩn."""
    try:
        l2_intent, l2_confidence = classify_intent_layer2(
            message, client,
            stage=session.stage.value,
            current_slot=None,
        )
    except Exception:
        return current_intent
    if l2_intent in (Intent.DEFENSIVE, Intent.TAM_SU, Intent.REFUSAL) \
       and l2_confidence in ("MED", "HIGH"):
        logger.info(
            "Greeting L2 override: %s → %s (confidence=%s)",
            current_intent.value, l2_intent.value, l2_confidence,
        )
        return l2_intent
    return current_intent


def _handle_greeting_defensive(
    session: SessionState,
    message: str,
    client: LLMClient,
) -> str:
    """F2B.4b: LLM_QUALITY 3-component, KHÔNG advance ASKING."""
    increment_flag_count(session, Flag.DEALER_TOO_DEFENSIVE)
    defensive_count = session.flag_counts.get(
        Flag.DEALER_TOO_DEFENSIVE.value, 1
    )
    llm_reply = handle_defensive_llm(
        dealer_message=message,
        defensive_count=defensive_count,
        dealer_type=DealerType.UNKNOWN,
        address_form=session.address_form,
        client=client,
        turn_count=session.turn_count,
        history_summary=summarize_history(session),
        current_slot=None,
        bridge_avoid_hint=get_avoid_hint(session),
    )
    if llm_reply:
        if defensive_count >= 3:
            from app.core.edge_cases import raise_escalation
            raise_escalation(session, reason=f"defensive_greeting_x{defensive_count}")
            session.stage = Stage.DONE
            mark_session_closed(session)
        return llm_reply
    # Fallback template
    reply, should_close = handle_defensive_escalation(session)
    if should_close:
        session.stage = Stage.DONE
        mark_session_closed(session)
    return reply


def _handle_greeting_tam_su(
    session: SessionState,
    message: str,
    client: LLMClient,
) -> str:
    """LLM tâm sự handler — engage 1-2 nhịp + bridge 'mình bắt đầu nhé?'."""
    record_tam_su(session)
    tam_su_count = session.consecutive_tam_su
    llm_reply = handle_tam_su_llm(
        dealer_message=message,
        tam_su_count=tam_su_count,
        dealer_type=DealerType.UNKNOWN,
        address_form=session.address_form,
        client=client,
        history_summary=summarize_history(session),
        current_slot=None,
        next_slot_hint="Anh sẵn sàng bắt đầu cuộc trò chuyện chưa ạ?",
        bridge_avoid_hint=get_avoid_hint(session),
    )
    if llm_reply:
        return llm_reply
    reply, _ = handle_tam_su_escalation(session)
    return reply
