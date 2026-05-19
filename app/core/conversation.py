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

from app.admin.queue import increment_flag_count
from app.core.abuse_detector import (
    handle_abuse_escalation,
    handle_address_blacklist_escalation,
    is_personal_abuse,
)
from app.core.address_blacklist import check_address_blacklist
from app.core.address_parser import parse_address
from app.core.brand_check import get_unknown_brands
from app.core.card_renderer import render_card
from app.core.closing import render_closing, render_soft_end_closing
from app.core.dealer_type import detect_dealer_type, should_detect_now
from app.core.edge_cases import (
    check_phone_retry_exhausted,
    handle_defensive_escalation,
    record_optional_refusal,
    reset_optional_refusal,
    should_skip_in_rush_mode,
)
from app.core.garbage_detector import is_garbage, is_meaningful_short
from app.core.greeting import render_greeting
from app.core.intent import detect_intent
from app.core.sanity import check_sanity
from app.core.session import is_session_timeout, mark_session_closed, touch_session
from app.core.state_machine import decide_action
from app.slots.definitions import is_optional, is_required
from app.guards import (
    auto_rewrite,
    check_hallucinate,
    check_prompt_injection,
    has_forbidden_scoring_vocab,
    sanitize_injection,
)
from app.llm.ack_generator import generate_ack
from app.llm.auto_derive import derive_main_category
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
        - Mutate session: turn_count, history, current_slot, stage, flags,
          flag_counts (qua guards + state machine)
        - Mutate profile: extracted fields từ message

    Note: admin queue trigger được caller (API layer) gọi SAU khi
    save_session — vì FK constraint cần session row trong DB trước.
    """
    # Lazy timeout check (Phase 1-3, refer KE_HOACH § 0.4)
    if is_session_timeout(session):
        mark_session_closed(session)
        return (render_soft_end_closing(), session, profile)

    # Touch session timestamp + increment turn
    touch_session(session)
    session.turn_count += 1

    # G1: Prompt injection guard (Layer 1 regex)
    injection_match = check_prompt_injection(message)
    if injection_match:
        increment_flag_count(session, Flag.PROMPT_INJECTION)
        # Sanitize message trước khi pass cho LLM
        message = sanitize_injection(message) or message

    # Garbage input detect (1C § 7) — flag nếu lặp 2 lần cùng slot.
    # Short "ok"/"có" KHÔNG phải garbage (whitelist).
    if (
        not is_meaningful_short(message)
        and is_garbage(message)
        and session.stage == Stage.ASKING
    ):
        count = increment_flag_count(session, Flag.GARBAGE_INPUT)
        if count >= 2:
            logger.warning(
                "Garbage input lặp ≥ 2 lần: session=%s msg=%r",
                session.session_id, message[:80],
            )

    # Personal abuse detect (1C § 5) — short-circuit khỏi flow normal
    abuse_reply: Optional[str] = None
    if is_personal_abuse(message) and session.stage == Stage.ASKING:
        increment_flag_count(session, Flag.ABUSIVE_LANGUAGE)
        abuse_reply, should_close = handle_abuse_escalation(session)
        if should_close:
            session.stage = Stage.DONE
            mark_session_closed(session)

    # Add dealer message to history (giữ raw message — admin sẽ thấy attack pattern)
    now = datetime.now(timezone.utc)
    session.history.append(HistoryMessage(role="dealer", content=message, ts=now))

    # Nếu abuse handled, short-circuit return (KHÔNG xử slot)
    if abuse_reply is not None:
        # Auto-rewrite + add bot history (giữ pattern guard cuối)
        abuse_reply = auto_rewrite(abuse_reply)
        session.history.append(HistoryMessage(role="bot", content=abuse_reply, ts=now))
        return (abuse_reply, session, profile)

    # Stage-based dispatch
    if session.stage == Stage.GREETING:
        reply = _handle_greeting(session, message)
    elif session.stage == Stage.ASKING:
        reply = _handle_asking(session, profile, message, client)
    elif session.stage == Stage.CONFIRMING:
        reply = _handle_confirming(session, profile, message)
    else:  # Stage.DONE
        reply = _handle_done()

    # G3: Drift guard — auto-rewrite vocab cấm trong bot reply
    # Note: drift là lỗi NỘI BỘ bot (LLM lệch), không flag session.
    # Scoring vocab leak nghiêm trọng → log warning để admin biết.
    if reply:
        if has_forbidden_scoring_vocab(reply):
            logger.error(
                "Scoring vocab LEAK trong bot reply session=%s reply=%r",
                session.session_id, reply[:200],
            )
        reply = auto_rewrite(reply)

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

    # Detect dealer type tại turn 3/8/13 (refer F2A.6)
    if should_detect_now(session.turn_count):
        detect_dealer_type(session)

    # 1C § 10: Address blacklist 3 cấp — check RAW message TRƯỚC extract
    # (vì LLM có thể strip blacklist khỏi extracted address → validator pass nhầm)
    if current_slot == "1.2" and check_address_blacklist(message):
        increment_flag_count(session, Flag.ADDRESS_BLACKLIST)
        reply, should_close = handle_address_blacklist_escalation(session)
        if should_close:
            session.stage = Stage.DONE
            mark_session_closed(session)
        return reply

    # Extract field (Phase 2: 16 slot có extractor)
    extracted: Optional[dict] = None
    if current_slot and current_slot in SLOT_TOOL_SCHEMAS:
        extracted = extract_slot(
            slot_id=current_slot,
            user_message=message,
            client=client,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
        )
        # G2: Hallucinate guard — null các field LLM bịa (không có trong message)
        if extracted:
            hallucinated = check_hallucinate(extracted, message)
            if hallucinated:
                # Mỗi field hallucinate = 1 lần raise (count tăng theo)
                for field in hallucinated:
                    increment_flag_count(session, Flag.HALLUCINATE)
                    extracted[field] = None
        # Note: 1C § 10 address blacklist check moved BEFORE extract
        # (refer block trên — vì LLM strip blacklist khỏi address)
        # 1C § 11: Brand whitelist check — flag nếu có brand lạ
        if extracted and extracted.get("supplier_brands"):
            unknown = get_unknown_brands(extracted["supplier_brands"])
            if unknown:
                increment_flag_count(session, Flag.BRAND_NOT_IN_WHITELIST)
                logger.info(
                    "Brand không trong whitelist: session=%s brands=%s",
                    session.session_id, unknown,
                )
        # Merge extracted vào profile + auto-derive Scope 2 fields
        if extracted:
            _merge_extracted(profile, extracted, client=client)

    # State machine quyết action
    next_slot, action = decide_action(session, intent, extracted)

    # Gen reply theo action
    if action == Action.PAUSE:
        # PAUSE = defensive / tâm sự — refer state_machine.decide_action
        if session.paused_for == "defensive":
            # Raise flag DEALER_TOO_DEFENSIVE + xử theo cấp 1C § 2
            increment_flag_count(session, Flag.DEALER_TOO_DEFENSIVE)
            reply, should_close = handle_defensive_escalation(session)
            if should_close:
                # Escalation L3 → soft-end session
                session.stage = Stage.DONE
                mark_session_closed(session)
            return reply
        # Tâm sự (Phase 3+ sẽ có dedicated handler) — fallback nhẹ
        return _phase_1_pause_fallback(session.paused_for)

    # Track edge case: refusal lặp OPTIONAL (1C § 4) — count + flag
    rush_offer: Optional[str] = None
    if action == Action.SKIP and current_slot and is_optional(current_slot):
        if record_optional_refusal(session):
            # Vừa đạt 3 OPTIONAL refuse liên tiếp → flag + offer message
            # (rush_mode logic đầy đủ defer Phase 4 — Phase 3 R4 chỉ flag + offer text)
            from app.core.edge_cases import RUSH_MODE_OFFER_TEMPLATE
            rush_offer = RUSH_MODE_OFFER_TEMPLATE
    elif action == Action.ADVANCE:
        # Dealer fill OK → reset counter
        reset_optional_refusal(session)

    # Edge case: phone invalid 3 retry exhausted (1C § 12)
    # State machine SKIP slot 1.3 khi total >= MAX_RETRY_TOTAL (3) →
    # raise PHONE_INVALID_AFTER_RETRY thay required_missing generic.
    if action == Action.SKIP and current_slot == "1.3":
        check_phone_retry_exhausted(session)

    # Check transition tới CONFIRMING (hết slot — bất kỳ action nào trừ RETRY/PAUSE)
    if next_slot is None and action in (Action.ADVANCE, Action.SKIP, Action.DEFER):
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
        # Nếu vừa offer rush_mode, prepend offer (dealer trả lời ok/không ở turn sau)
        if rush_offer:
            base = f"{ack}\n\n{rush_offer}" if ack else rush_offer
            if question:
                return f"{base}\n\n{question}"
            return base
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


def _merge_extracted(
    profile: DealerProfileRaw,
    extracted: dict,
    client: Optional[LLMClient] = None,
) -> None:
    """Merge extracted dict vào profile (chỉ field non-None).

    Auto-derive Scope 2 fields sau khi merge:
    - address → province + district (qua address_parser Layer 1 regex)
    - main_product → main_category (LLM_FAST, không substring match)
    """
    for field, value in extracted.items():
        if value is None:
            continue
        if not hasattr(profile, field):
            logger.warning("Extracted field %s không có trong DealerProfileRaw", field)
            continue
        setattr(profile, field, value)

    # Auto-derive province + district sau khi address fill (Scope 2)
    if "address" in extracted and extracted.get("address") and not profile.province:
        province, district = parse_address(profile.address)
        if province:
            profile.province = province
        if district:
            profile.district = district

    # Auto-derive main_category từ main_product (LLM_FAST)
    if (
        client is not None
        and "main_product" in extracted
        and extracted.get("main_product")
        and not profile.main_category
    ):
        context = ""
        if profile.category_stack:
            context = f"category_stack: {', '.join(profile.category_stack)}"
        derived = derive_main_category(profile.main_product, client, context)
        if derived:
            profile.main_category = derived
            logger.info(
                "Auto-derive main_category: %r → %s",
                profile.main_product, derived,
            )
        else:
            logger.warning(
                "Auto-derive main_category fail/null cho main_product=%r",
                profile.main_product,
            )


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
