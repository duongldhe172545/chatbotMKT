"""Main conversation orchestrator — F2A.1 stage dispatcher.

Refer:
- F2A.1 (LUAT_2A_core v0.2.4) — stage transitions
- F2A.4 — state machine decide_action
- CORE § G — khung chạy 4 stage
- KE_HOACH § action 20 — orchestrator ≤ 300 dòng

Phase 1 design:
- handle_message: pure function (session + profile + message + client → reply)
- Storage adapter inject Round 6 (API layer)
- Defensive/tâm sự handler: Phase 1 dùng safe fallback (LLM_QUALITY handler Phase 2+)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.card_renderer import render_card
from app.core.closing import render_closing, render_soft_end_closing
from app.core.greeting import render_greeting
from app.core.intent import detect_intent
from app.core.sanity import check_sanity
from app.core.session import is_session_timeout, mark_session_closed, touch_session
from app.core.state_machine import decide_action
from app.llm.ack_generator import generate_ack
from app.llm.client import LLMClient
from app.llm.extractors import extract_slot
from app.llm.extractors.schemas import SLOT_TOOL_SCHEMAS
from app.llm.fallback import safe_ack
from app.models.enums import (
    Action,
    ConfirmationStatus,
    DealerType,
    Flag,
    Intent,
    Stage,
)
from app.models.schema import (
    DealerProfileRaw,
    HistoryMessage,
    SessionState,
)
from app.slots.definitions import is_thong_bao
from app.slots.templates import get_question, get_retry_question

logger = logging.getLogger(__name__)


# ============================================================
# Main entry
# ============================================================


def handle_message(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> tuple[str, SessionState, DealerProfileRaw]:
    """Process 1 dealer message. Stage-based dispatch.

    Args:
        session: SessionState hiện tại (mutated in-place)
        profile: DealerProfileRaw hiện tại (mutated in-place)
        message: Text từ dealer
        client: LLMClient (test inject mock)

    Returns:
        (reply_text, updated_session, updated_profile).

    Side effects:
        - Mutate session: turn_count, history, current_slot, stage, flags, ...
        - Mutate profile: extracted fields từ message
    """
    # Lazy timeout check (Phase 1-3, refer KE_HOACH § 0.4)
    if is_session_timeout(session):
        mark_session_closed(session)
        return (render_soft_end_closing(), session, profile)

    # Touch session timestamp + increment turn
    touch_session(session)
    session.turn_count += 1

    # Add dealer message to history
    now = datetime.now(timezone.utc)
    session.history.append(HistoryMessage(role="dealer", content=message, ts=now))

    # Stage-based dispatch
    if session.stage == Stage.GREETING:
        reply = _handle_greeting(session, message)
    elif session.stage == Stage.ASKING:
        reply = _handle_asking(session, profile, message, client)
    elif session.stage == Stage.CONFIRMING:
        reply = _handle_confirming(session, profile, message)
    else:  # Stage.DONE
        reply = _handle_done()

    # Add bot reply to history
    session.history.append(HistoryMessage(role="bot", content=reply, ts=now))

    return (reply, session, profile)


def start_session(session: SessionState) -> str:
    """Render greeting cho session mới. Gọi 1 lần khi session bắt đầu.

    Args:
        session: SessionState mới tạo (stage=GREETING)

    Returns:
        Greeting text. Caller add vào history.
    """
    return render_greeting(session.session_id)


# ============================================================
# Stage handlers
# ============================================================


def _handle_greeting(session: SessionState, message: str) -> str:
    """Stage GREETING: dealer ack greeting → chuyển ASKING + hỏi slot 1.1."""
    intent = detect_intent(message)

    if intent == Intent.AFFIRMATIVE or intent == Intent.NORMAL:
        # Chuyển ASKING + ask slot 1.1
        session.stage = Stage.ASKING
        session.current_slot = "1.1"
        return get_question("1.1", variant=0) or "Anh cho em xin tên và tên cửa hàng nhé."

    if intent == Intent.REFUSAL:
        # Dealer từ chối ngay greeting → soft-close
        mark_session_closed(session)
        return render_soft_end_closing()

    # Defensive/khong_biet/khác → re-prompt
    return "Dạ anh sẵn sàng chưa ạ? Mình bắt đầu được không?"


def _handle_asking(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> str:
    """Stage ASKING: extract + state machine + gen reply."""
    intent = detect_intent(message)
    current_slot = session.current_slot

    # Extract field (chỉ nếu slot có extractor — Phase 1: 3 slot)
    extracted: Optional[dict] = None
    if current_slot and current_slot in SLOT_TOOL_SCHEMAS:
        extracted = extract_slot(
            slot_id=current_slot,
            user_message=message,
            client=client,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
        )
        # Merge extracted vào profile
        if extracted:
            _merge_extracted(profile, extracted)

    # State machine quyết action
    next_slot, action = decide_action(session, intent, extracted)

    # Gen reply theo action
    if action == Action.PAUSE:
        # Phase 1 simplified: safe fallback. Phase 2+ dùng F2B.4b defensive/tâm sự handler.
        return _phase_1_pause_fallback(session.paused_for)

    # Check transition tới CONFIRMING (hết slot)
    if next_slot is None and action == Action.ADVANCE:
        session.stage = Stage.CONFIRMING
        return _enter_confirming(profile)

    if action in (Action.ADVANCE, Action.SKIP, Action.DEFER):
        # Ack + question for next slot
        ack = _gen_ack_safe(
            slot_id=current_slot or "",
            extracted_data=extracted or {},
            client=client,
            session=session,
        )
        question = _get_slot_question_for_attempt(next_slot, session)
        if question:
            return f"{ack}\n\n{question}" if ack else question
        return ack or "Dạ vâng ạ."

    if action == Action.RETRY:
        # Stay current slot, retry tone
        attempts = session.slot_attempts.get(current_slot)
        attempt_num = attempts.total if attempts else 1
        retry_q = get_retry_question(current_slot, attempt=attempt_num)
        return retry_q or (get_question(current_slot, variant=0) or "Anh cho em thêm thông tin nhé?")

    if action == Action.PARTIAL_RETRY:
        # Ack phần đã cho + hỏi field còn thiếu
        ack = _gen_ack_safe(
            slot_id=current_slot or "",
            extracted_data=extracted or {},
            client=client,
            session=session,
        )
        # Phase 1 simplified: hỏi lại slot. Phase 2+ ask field cụ thể.
        return f"{ack}\n\nAnh cho em thêm thông tin còn thiếu nha?" if ack else "Anh cho em thêm thông tin còn thiếu nha?"

    # Fallback
    return safe_ack()


def _handle_confirming(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
) -> str:
    """Stage CONFIRMING: dealer xác nhận card."""
    intent = detect_intent(message)

    if intent == Intent.AFFIRMATIVE:
        # Sanity check 5-point trước khi CONFIRMED
        passed, failed = check_sanity(session, profile)
        if not passed:
            logger.warning("Sanity check fail: %s", failed)
            if Flag.SANITY_CHECK_FAILED not in session.flags:
                session.flags.append(Flag.SANITY_CHECK_FAILED)
            # Vẫn cho confirm — admin queue sẽ review (refer F2A.7)

        session.confirmation_status = ConfirmationStatus.CONFIRMED
        session.stage = Stage.DONE
        mark_session_closed(session)
        return render_closing(
            province=profile.province,
            consent=profile.brandkit_consent,
        )

    if intent == Intent.EDIT:
        # Phase 2+ edit_parser. Phase 1 simplified.
        return (
            "Dạ anh ghi rõ giúp em — sửa phần nào, thành gì ạ? "
            "(Edit chi tiết em sẽ hỗ trợ kỹ hơn ở phiên bản sau.)"
        )

    if intent == Intent.REFUSAL:
        # Dealer từ chối confirm — soft-close
        session.confirmation_status = ConfirmationStatus.PENDING
        session.stage = Stage.DONE
        mark_session_closed(session)
        return render_soft_end_closing()

    # Re-prompt
    return "Anh duyệt OK / sửa gì giúp em ạ?"


def _handle_done() -> str:
    """Stage DONE: session đóng, chỉ trả message thông báo."""
    return (
        "Em đã chốt thông tin của anh rồi ạ. Em hẹn anh trên Zalo nhé — "
        "bộ thương hiệu + kế hoạch nền tảng số em gửi trong ít giờ tới."
    )


# ============================================================
# Helpers
# ============================================================


def _enter_confirming(profile: DealerProfileRaw) -> str:
    """Render card khi vào CONFIRMING."""
    return (
        "Em đã ghi nhận đủ thông tin rồi ạ. Anh xem giúp em qua card này nhé:\n\n"
        + render_card(profile)
    )


def _merge_extracted(profile: DealerProfileRaw, extracted: dict) -> None:
    """Merge extracted dict vào profile (chỉ field non-None)."""
    for field, value in extracted.items():
        if value is None:
            continue
        if not hasattr(profile, field):
            logger.warning("Extracted field %s không có trong DealerProfileRaw", field)
            continue
        setattr(profile, field, value)


def _gen_ack_safe(
    slot_id: str,
    extracted_data: dict,
    client: LLMClient,
    session: SessionState,
) -> str:
    """Gen ack với fallback safe."""
    if not slot_id or not extracted_data:
        return safe_ack()
    try:
        return generate_ack(
            slot_id=slot_id,
            extracted_data=extracted_data,
            client=client,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            use_fallback_on_error=True,
        )
    except Exception as e:
        logger.exception("Ack gen fail: %s", e)
        return safe_ack()


def _get_slot_question_for_attempt(
    slot_id: Optional[str],
    session: SessionState,
) -> Optional[str]:
    """Lấy câu hỏi slot phù hợp attempt (retry tone giảm dần)."""
    if not slot_id:
        return None
    # Slot THÔNG BÁO (4.1) — get_question lấy "câu thông báo"
    if is_thong_bao(slot_id):
        return get_question(slot_id, variant=0)
    # Slot có retry → check attempts
    attempts = session.slot_attempts.get(slot_id)
    attempt_num = attempts.total + 1 if attempts else 1
    if attempt_num <= 1:
        return get_question(slot_id, variant=0)
    # Retry tone giảm dần
    return get_retry_question(slot_id, attempt=attempt_num) or get_question(slot_id, variant=0)


def _phase_1_pause_fallback(paused_for: Optional[str]) -> str:
    """Safe response cho PAUSE (defensive/tâm sự). Phase 2+ dùng F2B.4b handler."""
    if paused_for == "defensive":
        return (
            "Dạ anh yên tâm — em không thu phí gì đâu ạ, em chỉ thu thập "
            "thông tin để team bên em hỗ trợ anh tốt hơn. Dữ liệu em lưu nội "
            "bộ, không share ra ngoài. Mình tiếp tục được không ạ?"
        )
    if paused_for == "tam_su":
        return (
            "Dạ em hiểu mà ạ. Anh chia sẻ em rất quý. À cho em hỏi tiếp xíu nhé?"
        )
    return "Dạ em hiểu ạ. Mình tiếp tục được không anh?"
