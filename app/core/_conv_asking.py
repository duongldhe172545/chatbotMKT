"""ASKING stage handler — Phase 6 R2 refactor.

Refer:
- F2A.1 stage ASKING
- F2A.4 state machine 6 action
- F2B.4b defensive / tâm sự handler (LLM_QUALITY)
- 1C § 4/5/10/11/12 — edge cases
- Phase 5 R1 Gap 6 — L2 threshold ≥3 từ
- Phase 5 R6 — state machine profile-aware
"""
from __future__ import annotations

import logging
from typing import Optional

from app.admin.queue import increment_flag_count
from app.core._conv_derive import merge_extracted
from app.core._conv_helpers import (
    gen_ack_safe,
    gen_partial_question,
    get_slot_question_for_attempt,
    phase_1_pause_fallback,
    summarize_history,
)
from app.core.abuse_detector import handle_address_blacklist_escalation
from app.core.address_blacklist import check_address_blacklist
from app.core.address_form import detect_address_form, detect_explicit_address
from app.core.brand_check import get_unknown_brands
from app.core.bridge_rotation import get_avoid_hint
from app.core.dealer_type import (
    detect_dealer_type,
    has_persistent_lua_lo_signal,
    has_strong_lua_lo_signal,
    should_detect_now,
    upgrade_to_lua_lo,
)
from app.core.edge_cases import (
    check_phone_retry_exhausted,
    handle_defensive_escalation,
    handle_tam_su_escalation,
    record_optional_refusal,
    record_tam_su,
    reset_optional_refusal,
    reset_tam_su,
)
from app.core.intent import (
    TECHNICAL_INQUIRY_ESCALATE_TEMPLATE,
    detect_intent,
    detect_technical_inquiry,
)
from app.core.session import mark_session_closed
from app.core.state_machine import decide_action
from app.guards import check_hallucinate
from app.llm.client import LLMClient
from app.llm.brand_correction import correct_brand
from app.llm.defensive_handler import handle_defensive as handle_defensive_llm
from app.llm.extractors import extract_slot
from app.llm.extractors.schemas import SLOT_TOOL_SCHEMAS
from app.llm.fallback import safe_ack
from app.llm.intent_classifier import classify_intent_layer2
from app.llm.tam_su_handler import handle_tam_su as handle_tam_su_llm
from app.models.enums import Action, AddressForm, DealerType, Flag, Intent, Stage
from app.models.schema import DealerProfileRaw, SessionState
from app.slots.definitions import is_optional
from app.slots.definitions import next_slot as get_next_slot
from app.slots.templates import get_question, get_retry_question

logger = logging.getLogger(__name__)


def handle_asking(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> str:
    """Stage ASKING: extract + state machine + gen reply."""
    intent = detect_intent(message)
    current_slot = session.current_slot

    # CORE E.3: Technical inquiry detect — báo giá/bảo hành/kỹ thuật/
    # hợp tác/pháp lý/y tế/tài chính → escalate template, KHÔNG advance.
    # Check trước intent flow vì câu hỏi này có thể match TAM_SU
    # (vd "bệnh đau lưng nên đi viện không?") nhưng phải xử riêng.
    # Phase 6 R+ fix 2026-05-22 (user feedback bug slot 3.5): pass
    # current_slot để skip warranty pattern khi dealer trả lời slot 3.5.
    #
    # Phase 6 R+ fix 2026-05-25 (user feedback "session DONE quá dễ"):
    # KHÔNG count vào DEALER_TOO_DEFENSIVE — đó là flag cho dealer chửi/troll
    # 3 lần → escalate L3 close session. Technical inquiry chỉ là dealer
    # hỏi câu chuyên môn ngoài tầm, KHÔNG được trigger close session.
    if detect_technical_inquiry(message, current_slot=current_slot):
        logger.info(
            "Technical inquiry escalate: session=%s msg=%r",
            session.session_id, message[:80],
        )
        # Trả escalate template + question slot hiện tại để dealer
        # tiếp tục flow (không phải defensive cứng, không close session).
        followup_q = get_slot_question_for_attempt(current_slot, session)
        if followup_q:
            return f"{TECHNICAL_INQUIRY_ESCALATE_TEMPLATE}\n\n{followup_q}"
        return TECHNICAL_INQUIRY_ESCALATE_TEMPLATE

    # Intent Layer 2 LLM fallback (Phase 5 R1 Gap 6: threshold ≥3 từ)
    if intent == Intent.NORMAL and len(message.split()) >= 3:
        l2_intent, l2_confidence = classify_intent_layer2(
            message, client,
            stage=session.stage.value,
            current_slot=current_slot,
        )
        if l2_intent is not None and l2_confidence in ("MED", "HIGH"):
            if l2_intent != Intent.NORMAL:
                logger.info(
                    "Intent L2 override: L1=NORMAL → L2=%s (confidence=%s)",
                    l2_intent.value, l2_confidence,
                )
                intent = l2_intent

    # Detect dealer type tại turn 3/8/13 (F2A.6)
    if should_detect_now(session.turn_count):
        detect_dealer_type(session)

    # Phase 6 R+ fix: Lửa Lò detect chỉ trigger khi COMBINED signal (1B § 2.1):
    # - Strong: caps lock + profanity cùng turn (vd "ĐM CỬA HÀNG NÀO")
    # - Persistent: ≥ 2/3 turn gần có profanity (dealer chửi LẶP)
    # KHÔNG upgrade chỉ vì 1 lần "đéo cho" (dealer có thể bực 1 lần thôi).
    if has_strong_lua_lo_signal(message) or has_persistent_lua_lo_signal(session):
        if upgrade_to_lua_lo(session):
            logger.info(
                "Lửa Lò detect (combined/persistent): session=%s turn=%d msg=%r",
                session.session_id, session.turn_count, message[:60],
            )

    # 1C § 10: Address blacklist check RAW message TRƯỚC extract
    if current_slot == "1.2" and check_address_blacklist(message):
        increment_flag_count(session, Flag.ADDRESS_BLACKLIST)
        reply, should_close = handle_address_blacklist_escalation(session)
        if should_close:
            session.stage = Stage.DONE
            mark_session_closed(session)
        return reply

    repeat_reply = _handle_repeat_complaint(session, profile, message, current_slot)
    if repeat_reply:
        return repeat_reply

    flirt_reply = _handle_boundary_flirt(session, message, current_slot)
    if flirt_reply:
        return flirt_reply

    # CORE D.1: CONFUSION intent — dealer hỏi "là sao?/là gì?" → bot
    # CHỦ ĐỘNG GIẢI THÍCH, KHÔNG advance slot. Dùng defensive_handler
    # vì pattern 3-thành-phần (giải thích + bảo mật + bridge) phù hợp.
    # Phase 6 R+ fix 2026-05-22 (user feedback): "là sao?" trước đó fall
    # về NORMAL → bot skip slot, không trả lời câu hỏi dealer.
    if intent == Intent.CONFUSION:
        logger.info(
            "CONFUSION intent: session=%s msg=%r — bot giải thích (CORE D.1)",
            session.session_id, message[:60],
        )
        llm_reply = handle_defensive_llm(
            dealer_message=message,
            defensive_count=1,  # CONFUSION không count escalate L3
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            client=client,
            turn_count=session.turn_count,
            history_summary=summarize_history(session),
            current_slot=current_slot,
            bridge_avoid_hint=get_avoid_hint(session),
        )
        if llm_reply:
            return llm_reply
        # Fallback nếu LLM fail: ack rồi retry slot
        question = get_slot_question_for_attempt(current_slot, session)
        ack = "Dạ em hỏi lại — ý em là chia sẻ thêm chút thông tin để em hoàn thiện hồ sơ ạ."
        return f"{ack}\n\n{question}" if question else ack

    # ---------------------------------------------------------------
    # Mid-flow CORRECTION detect: dealer sửa thông tin đã fill trước đó
    # Vd: "ecopark chứ phố nối cái gì", "không phải 0912 mà 0987"
    # ---------------------------------------------------------------
    correction_reply = _handle_mid_correction(
        session, profile, message, client, current_slot
    )
    if correction_reply:
        return correction_reply

    suggestion_reply = _handle_slot_suggestion(
        session=session,
        profile=profile,
        message=message,
        current_slot=current_slot,
    )
    if suggestion_reply:
        return suggestion_reply

    # Extract field (Phase 2: 16 slot có extractor)
    extracted = _extract_and_merge(session, profile, message, client, current_slot)
    clarify_reply = _get_internal_reply(extracted)
    if clarify_reply:
        return clarify_reply

    if intent == Intent.TAM_SU and _has_slot_relevant_extracted_value(
        current_slot, extracted
    ):
        logger.info(
            "TAM_SU intent suppressed because current slot data was extracted: "
            "session=%s slot=%s extracted=%s",
            session.session_id,
            current_slot,
            extracted,
        )
        intent = Intent.NORMAL

    # State machine quyết action (Phase 5 R6: profile-aware)
    next_slot, action = decide_action(session, intent, extracted, profile=profile)

    # Reset tâm sự counter nếu intent KHÔNG phải TAM_SU
    if intent != Intent.TAM_SU:
        reset_tam_su(session)

    # PAUSE = defensive / tâm sự (F2B.4b)
    if action == Action.PAUSE:
        return _handle_pause(session, message, client, current_slot, profile=profile)

    # Track edge case: refusal lặp OPTIONAL (1C § 4)
    rush_offer: Optional[str] = None
    if action == Action.SKIP and current_slot and is_optional(current_slot):
        if record_optional_refusal(session):
            from app.core.edge_cases import RUSH_MODE_OFFER_TEMPLATE
            rush_offer = RUSH_MODE_OFFER_TEMPLATE
    elif action == Action.ADVANCE:
        reset_optional_refusal(session)

    # Phone retry exhausted (1C § 12)
    if action == Action.SKIP and current_slot == "1.3":
        check_phone_retry_exhausted(session)

    # Transition CONFIRMING (hết slot)
    if next_slot is None and action in (Action.ADVANCE, Action.SKIP, Action.DEFER):
        from app.core._conv_confirming import enter_confirming
        session.stage = Stage.CONFIRMING
        return enter_confirming(profile, session=session)

    # ADVANCE / SKIP / DEFER → ack + question for next slot
    if action in (Action.ADVANCE, Action.SKIP, Action.DEFER):
        # Phase 6 R+ fix bug 2: REFUSAL/DEFER cho REQUIRED → ack "không tiện
        # thì em hỏi sau" TRƯỚC khi chuyển slot (1A § 1.6 nuance).
        # Bug 3: Lửa Lò → ack ngắn ≤8 từ.
        defer_ack = _gen_defer_skip_ack(intent, action, current_slot, session)
        if defer_ack:
            ack = defer_ack
        elif (
            not _has_extracted_value(extracted)
            and (intent == Intent.AFFIRMATIVE or _is_ack_only(message))
        ):
            ack = "Dạ vâng."
        else:
            ack = gen_ack_safe(
                slot_id=current_slot or "",
                extracted_data=extracted or {},
                client=client,
                session=session,
            )
        question = get_slot_question_for_attempt(next_slot, session)
        if rush_offer:
            base = f"{ack}\n\n{rush_offer}" if ack else rush_offer
            if question:
                return f"{base}\n\n{question}"
            return base
        if question:
            return f"{ack}\n\n{question}" if ack else question
        return ack or "Dạ vâng ạ."

    # RETRY → variant rotate + retry tone (Phase 5 R1 Gap 7 + Phase 6 R+ fix)
    if action == Action.RETRY:
        # Phase 6 R+ fix: nếu state machine recheck_deferred → next_slot khác
        # current_slot. Phải dùng next_slot (slot deferred quay lại) để gen
        # initial question, không retry old slot.
        if next_slot and next_slot != current_slot:
            initial_q = get_slot_question_for_attempt(next_slot, session)
            return initial_q or "Anh cho em thêm thông tin nhé?"
        attempts = session.slot_attempts.get(current_slot)
        # Phase 6 R+ Fix D2 ROOT CAUSE: attempts.total = số lần dealer ĐÃ fail.
        # Lượt sắp ask = total + 1 (vd fail lần 1 → ask lượt 2 retry tone).
        attempt_num = (attempts.total + 1) if attempts else 1
        # PARTIAL_RETRY không count attempts → bump nếu đã PARTIAL.
        if current_slot in (session.partial_retried_slots or []):
            attempt_num = max(attempt_num + 1, 2)
        retry_q = get_retry_question(current_slot, attempt=attempt_num)
        return retry_q or (
            get_question(
                current_slot,
                session_id=session.session_id,
                attempt_offset=max(0, attempt_num - 1),
            )
            or "Anh cho em thêm thông tin nhé?"
        )

    # PARTIAL_RETRY → ack + hỏi field cụ thể (1A § 1.5)
    if action == Action.PARTIAL_RETRY:
        ack = gen_ack_safe(
            slot_id=current_slot or "",
            extracted_data=extracted or {},
            client=client,
            session=session,
        )
        partial_q = gen_partial_question(current_slot, profile)
        return f"{ack}\n\n{partial_q}" if ack else partial_q

    # Fallback
    return safe_ack()


# ============================================================
# Mid-flow correction handler
# ============================================================

import re as _re_corr

# Patterns that indicate dealer is correcting previously-filled data
_CORRECTION_PATTERNS = [
    # "ecopark chứ phố nối cái gì" / "X chứ Y gì"
    _re_corr.compile(r'(.+?)\s+chứ\s+(.+?)\s+(cái\s+)?gì', _re_corr.IGNORECASE),
    # "không phải X mà Y" / "không phải X, Y mới đúng"
    _re_corr.compile(r'không\s+phải\s+(.+?)\s*[,]\s*(.+?)(?:\s+mới\s+đúng)?$', _re_corr.IGNORECASE),
    # "X chứ không phải Y"
    _re_corr.compile(r'(.+?)\s+chứ\s+không\s+phải\s+(.+)', _re_corr.IGNORECASE),
    # "em ghi sai rồi, X chứ" / "sai rồi, X mới đúng"
    _re_corr.compile(r'(?:sai\s+rồi|ghi\s+sai)[,.]?\s*(.+?)(?:\s+mới\s+đúng|\s+chứ)', _re_corr.IGNORECASE),
]

_CORRECTION_MARKER_RE = _re_corr.compile(
    r"\b(nhầm|nham|sai\s+rồi|sai\s+roi|ghi\s+sai|không\s+phải|khong\s+phai|"
    r"chỉnh\s+lại|chinh\s+lai|sửa\s+lại|sua\s+lai|đổi\s+lại|doi\s+lai)\b",
    _re_corr.IGNORECASE,
)

_TRAILING_CORRECTION_WORDS_RE = _re_corr.compile(
    r"\s+(chứ|chu|mới\s+đúng|moi\s+dung|nhé|nhe|nha|ạ|a)\s*$",
    _re_corr.IGNORECASE,
)

_ADDRESS_CORRECTION_PATTERNS = [
    _re_corr.compile(
        r"(?:nhầm|nham|sai\s+rồi|sai\s+roi|ghi\s+sai)[,.\s]*(?:ở|o|địa\s+chỉ(?:\s+là)?|dia\s+chi(?:\s+la)?)\s+(.+)$",
        _re_corr.IGNORECASE,
    ),
    _re_corr.compile(
        r"(?:địa\s+chỉ|dia\s+chi)\s*(?:là|la|thành|thanh|sang)?\s+(.+)$",
        _re_corr.IGNORECASE,
    ),
    _re_corr.compile(
        r"(?:^|[,.\s])(?:ở|o)\s+(.+)$",
        _re_corr.IGNORECASE,
    ),
]

# Map profile field names → display labels for acknowledgment
_FIELD_DISPLAY = {
    "owner_name": "tên",
    "dealer_name": "tên cửa hàng",
    "address": "địa chỉ",
    "phone_or_zalo": "số điện thoại",
    "main_product": "sản phẩm chính",
    "supplier_brands": "hãng nhập",
    "brandkit_consent": "đồng ý nhận bộ thương hiệu",
}


def _handle_mid_correction(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
    current_slot: Optional[str],
) -> Optional[str]:
    """Detect and handle mid-flow corrections of previously filled data.

    When dealer says "ecopark chứ phố nối cái gì", we:
    1. Detect correction intent via regex
    2. Extract the correct value from the message
    3. Find which profile field the dealer is correcting
    4. Update profile
    5. Acknowledge + re-ask current slot
    """
    msg = (message or "").strip()
    if not msg or len(msg) < 5:
        return None

    direct = _parse_anytime_correction(msg, profile)
    if direct:
        target_field, correct_value = direct
        return _apply_mid_correction(
            session=session,
            profile=profile,
            client=client,
            current_slot=current_slot,
            target_field=target_field,
            correct_value=correct_value,
        )

    correct_value: Optional[str] = None
    wrong_value: Optional[str] = None

    for pattern in _CORRECTION_PATTERNS:
        m = pattern.search(msg)
        if m:
            groups = m.groups()
            if len(groups) >= 2:
                # First group = correct value, second = wrong value (for "X chứ Y gì")
                # OR first group = wrong value, second = correct value (for "không phải X mà Y")
                g1, g2 = groups[0].strip(), groups[1].strip()
                # Heuristic: check which group matches existing profile data
                match_field, matched_val = _find_matching_profile_field(profile, g1, g2)
                if match_field:
                    if matched_val == g1:
                        wrong_value = g1
                        correct_value = g2
                    else:
                        wrong_value = g2
                        correct_value = g1
                    break
                # If pattern is "X chứ Y gì" → X is correct, Y is wrong
                if "chứ" in msg and "không phải" not in msg.lower():
                    correct_value = g1
                    wrong_value = g2
                    match_field, _ = _find_matching_profile_field(profile, g2)
                    break

    if not correct_value:
        return None

    # Find which field to update
    target_field = None
    if wrong_value:
        target_field, _ = _find_matching_profile_field(profile, wrong_value)
    if not target_field and wrong_value:
        # Try harder: fuzzy match against profile values
        target_field = _fuzzy_find_field(profile, wrong_value)

    if not target_field:
        return None  # Can't determine which field → let normal flow handle

    return _apply_mid_correction(
        session=session,
        profile=profile,
        client=client,
        current_slot=current_slot,
        target_field=target_field,
        correct_value=correct_value,
    )


def _parse_anytime_correction(
    message: str,
    profile: DealerProfileRaw,
) -> Optional[tuple[str, object]]:
    """Parse corrections that can arrive while another slot is active."""
    msg = (message or "").strip()
    if not msg:
        return None

    supplier_update = _parse_supplier_brand_correction(msg, profile)
    if supplier_update:
        return "supplier_brands", supplier_update

    if not _CORRECTION_MARKER_RE.search(msg):
        return None

    try:
        from app.core.edit_parser import parse_edit_command

        parsed = parse_edit_command(msg)
    except Exception:
        parsed = None
    if parsed:
        field, value = parsed
        if _profile_has_value(profile, field):
            return field, value

    msg_fold = _fold_vn(msg)
    if _profile_has_value(profile, "address") and (
        " o " in f" {msg_fold} "
        or " dia chi" in msg_fold
        or " khu vuc" in msg_fold
    ):
        value = _extract_address_correction_value(msg)
        if value:
            return "address", value

    if _profile_has_value(profile, "phone_or_zalo"):
        digits = _re_corr.sub(r"\D", "", msg)
        if 9 <= len(digits) <= 11:
            return "phone_or_zalo", digits

    if _profile_has_value(profile, "dealer_name") and "cua hang" in msg_fold:
        value = _extract_after_field_hint(msg, ("cửa hàng", "cua hang", "tên cửa hàng", "ten cua hang"))
        if value:
            return "dealer_name", value

    if _profile_has_value(profile, "owner_name") and "ten" in msg_fold:
        value = _extract_after_field_hint(msg, ("tên anh", "ten anh", "tên tôi", "ten toi", "tên chị", "ten chi"))
        if value:
            return "owner_name", value

    return None


def _apply_mid_correction(
    *,
    session: SessionState,
    profile: DealerProfileRaw,
    client: LLMClient,
    current_slot: Optional[str],
    target_field: str,
    correct_value: object,
) -> str:
    """Apply correction, refresh derived fields, then continue current slot."""
    old_value = getattr(profile, target_field, None)
    if target_field == "address":
        profile.province = None
        profile.district = None
        session.pending_address_text = None
        session.pending_address_canonical = None
        if isinstance(correct_value, str) and _needs_address_province_confirmation(correct_value):
            correct_value = _canonical_address_guess(correct_value)
    extracted = {target_field: correct_value}
    merge_extracted(profile, extracted, client=client)
    display = _FIELD_DISPLAY.get(target_field, target_field)
    af = session.address_form.value

    logger.info(
        "Mid-flow correction: session=%s field=%s old=%r new=%r",
        session.session_id, target_field, old_value, correct_value,
    )

    # Acknowledge correction + re-ask current slot
    if isinstance(correct_value, list):
        value_text = ", ".join(str(v).strip() for v in correct_value if str(v).strip())
    else:
        value_text = str(correct_value)
    ack = f"Dạ em sửa lại {display} thành {value_text} rồi ạ."
    if target_field == "address":
        local_note = _local_address_note(value_text)
        if local_note:
            ack = f"{ack} {local_note}"
    if (
        target_field == "supplier_brands"
        and current_slot == "2.4"
        and not profile.customer_segment_signal
    ):
        question = gen_partial_question(current_slot, profile)
    else:
        question = get_slot_question_for_attempt(current_slot, session)
    if question:
        return f"{ack}\n\n{question}"
    return ack


def _profile_has_value(profile: DealerProfileRaw, field: str) -> bool:
    value = getattr(profile, field, None)
    return value is not None and value != "" and value != []


def _extract_address_correction_value(message: str) -> Optional[str]:
    for pattern in _ADDRESS_CORRECTION_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        value = _clean_correction_value(match.group(1))
        if value:
            return value
    return None


def _extract_after_field_hint(message: str, hints: tuple[str, ...]) -> Optional[str]:
    msg = message.strip()
    folded = _fold_vn(msg)
    for hint in hints:
        idx = folded.find(_fold_vn(hint))
        if idx < 0:
            continue
        value = msg[idx + len(hint):]
        value = _re_corr.sub(r"^\s*(là|la|thành|thanh|sang|:|-)\s*", "", value, flags=_re_corr.IGNORECASE)
        value = _clean_correction_value(value)
        if value:
            return value
    return None


def _parse_supplier_brand_correction(
    message: str,
    profile: DealerProfileRaw,
) -> Optional[list[str]]:
    existing = list(profile.supplier_brands or [])
    if not existing:
        return None

    msg = (message or "").strip()
    if not msg:
        return None

    patterns = (
        ("new_old", _re_corr.compile(r"(?:^|ý\s+là\s+|y\s+la\s+)(.+?)\s+chứ\s+không\s+phải\s+(.+)$", _re_corr.IGNORECASE)),
        ("old_new", _re_corr.compile(r"không\s+phải\s+(.+?)\s+(?:mà|,)\s*(.+)$", _re_corr.IGNORECASE)),
        ("new_old_ascii", _re_corr.compile(r"(?:^|y\s+la\s+)(.+?)\s+chu\s+khong\s+phai\s+(.+)$", _re_corr.IGNORECASE)),
        ("old_new_ascii", _re_corr.compile(r"khong\s+phai\s+(.+?)\s+(?:ma|,)\s*(.+)$", _re_corr.IGNORECASE)),
    )
    for direction, pattern in patterns:
        match = pattern.search(msg)
        if not match:
            continue
        first = _clean_brand_correction_value(match.group(1))
        second = _clean_brand_correction_value(match.group(2))
        if not first or not second:
            continue
        if direction.startswith("new_old"):
            updated = _replace_supplier_brand(existing, new_raw=first, old_raw=second)
        else:
            updated = _replace_supplier_brand(existing, new_raw=second, old_raw=first)
        if updated:
            return updated

    mentioned_brands = _extract_known_supplier_brands(msg)
    if mentioned_brands:
        return _merge_supplier_brand_updates(existing, mentioned_brands)

    # Bare follow-up after fuzzy extraction, e.g. "alumax em ơi" right after
    # the bot already stored "Alumac".
    candidate = _clean_brand_correction_value(msg)
    if candidate and len(candidate.split()) <= 3:
        return _replace_supplier_brand(existing, new_raw=candidate, old_raw=None)
    return None


def _clean_brand_correction_value(value: str) -> Optional[str]:
    cleaned = _clean_correction_value(value)
    if not cleaned:
        return None
    cleaned = _re_corr.sub(
        r"^(ý\s+là|y\s+la|là|la)\s+",
        "",
        cleaned.strip(),
        flags=_re_corr.IGNORECASE,
    )
    cleaned = _re_corr.sub(
        r"\s+(em\s+ơi|em\s+oi|em|anh\s+ơi|anh\s+oi|anh|chị\s+ơi|chi\s+oi|chị|chi|nhé|nhe|nha|ạ|a)$",
        "",
        cleaned.strip(),
        flags=_re_corr.IGNORECASE,
    )
    return cleaned.strip(" .,!?:;\"'") or None


def _canonical_brand_name(value: str) -> str:
    fixed = correct_brand(value).strip()
    known = {
        "alumax": "Alumax",
        "alumac": "Alumac",
        "koffman": "Koffman",
        "austdoor": "Austdoor",
        "titadoor": "Titadoor",
        "titado": "Titadoor",
        "tita do": "Titadoor",
        "mitadoor": "Mitadoor",
        "mitado": "Mitadoor",
        "mita do": "Mitadoor",
        "xingfa": "Xingfa",
    }
    key = _fold_vn(fixed)
    return known.get(key, fixed[:1].upper() + fixed[1:] if fixed.islower() else fixed)


def _extract_known_supplier_brands(message: str) -> list[str]:
    msg = _fold_vn(message or "")
    known_patterns = (
        ("Austdoor", ("austdoor", "aust door", "ot do", "ot door")),
        ("Titadoor", ("titadoor", "tita door", "tita do", "ti ta do", "titado")),
        ("Mitadoor", ("mitadoor", "mita door", "mita do", "mi ta do", "mitado")),
        ("Koffman", ("koffman", "cop man", "cop men", "kop men")),
        ("Alumax", ("alumax",)),
        ("Alumac", ("alumac",)),
    )
    result: list[str] = []
    seen: set[str] = set()
    for canonical, patterns in known_patterns:
        if any(p in msg for p in patterns):
            key = canonical.casefold()
            if key not in seen:
                seen.add(key)
                result.append(canonical)
    return result


def _merge_supplier_brand_updates(existing: list[str], updates: list[str]) -> list[str]:
    merged = [_canonical_brand_name(str(b)) for b in existing if str(b).strip()]
    for brand in updates:
        updated = _replace_supplier_brand(merged, new_raw=brand, old_raw=None)
        if updated:
            merged = updated
            continue
        canonical = _canonical_brand_name(brand)
        if _brand_compare_key(canonical) not in {_brand_compare_key(b) for b in merged}:
            merged.append(canonical)
    deduped: list[str] = []
    seen: set[str] = set()
    for brand in merged:
        key = _brand_compare_key(brand)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(brand)
    return deduped


def _replace_supplier_brand(
    existing: list[str],
    *,
    new_raw: str,
    old_raw: Optional[str],
) -> Optional[list[str]]:
    import difflib

    new_brand = _canonical_brand_name(new_raw)
    if not new_brand:
        return None
    existing_clean = [_canonical_brand_name(str(b)) for b in existing if str(b).strip()]
    if not existing_clean:
        return None

    new_key = _brand_compare_key(new_brand)
    old_key = _brand_compare_key(old_raw) if old_raw else ""
    best_idx: Optional[int] = None
    best_score = 0.0
    for idx, brand in enumerate(existing_clean):
        brand_key = _brand_compare_key(brand)
        if old_key and (old_key == brand_key or old_key in brand_key or brand_key in old_key):
            best_idx = idx
            best_score = 1.0
            break
        score = difflib.SequenceMatcher(None, new_key, brand_key).ratio()
        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx is None:
        return None
    if not old_key and best_score < 0.72:
        return None

    existing_clean[best_idx] = new_brand
    deduped: list[str] = []
    seen: set[str] = set()
    for brand in existing_clean:
        key = _brand_compare_key(brand)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(brand)
    return deduped


def _brand_compare_key(value: Optional[str]) -> str:
    return _re_corr.sub(r"[^a-z0-9]+", "", _fold_vn(value or ""))


def _clean_correction_value(value: str) -> Optional[str]:
    cleaned = (value or "").strip(" .,!?:;\"'")
    cleaned = _TRAILING_CORRECTION_WORDS_RE.sub("", cleaned).strip(" .,!?:;\"'")
    cleaned = _re_corr.sub(
        r"^(à|a|ờ|ơ|ừ|uh|ừm|um|nhầm|nham|sai\s+rồi|sai\s+roi|ghi\s+sai)[,.\s]+",
        "",
        cleaned,
        flags=_re_corr.IGNORECASE,
    ).strip(" .,!?:;\"'")
    if len(cleaned) < 2 or len(cleaned) > 200:
        return None
    return cleaned


def _find_matching_profile_field(
    profile: DealerProfileRaw,
    *candidates: str,
) -> tuple[Optional[str], Optional[str]]:
    """Find which profile field matches any of the candidate values.

    Returns (field_name, matched_candidate) or (None, None).
    """
    check_fields = ["address", "owner_name", "dealer_name", "phone_or_zalo", "main_product"]
    for field in check_fields:
        val = getattr(profile, field, None)
        if not val:
            continue
        val_lower = str(val).lower().strip()
        for c in candidates:
            c_lower = c.lower().strip()
            # Substring match (either direction)
            if c_lower in val_lower or val_lower in c_lower:
                return (field, c)
    return (None, None)


def _fuzzy_find_field(profile: DealerProfileRaw, wrong_text: str) -> Optional[str]:
    """Fuzzy-match wrong_text against profile values using partial overlap."""
    if not wrong_text:
        return None
    wrong_words = set(wrong_text.lower().split())
    if not wrong_words:
        return None
    check_fields = ["address", "owner_name", "dealer_name", "phone_or_zalo", "main_product"]
    best_field = None
    best_overlap = 0
    for field in check_fields:
        val = getattr(profile, field, None)
        if not val:
            continue
        val_words = set(str(val).lower().split())
        overlap = len(wrong_words & val_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_field = field
    return best_field if best_overlap > 0 else None


def _get_internal_reply(extracted: Optional[dict]) -> Optional[str]:
    """Return internal control reply from extractor helpers, if any."""
    if not extracted:
        return None
    reply = extracted.get("__internal_reply")
    return str(reply).strip() if reply else None


def _has_extracted_value(extracted: Optional[dict]) -> bool:
    if not extracted:
        return False
    return any(v is not None and v != "" and v != [] for v in extracted.values())


def _has_slot_relevant_extracted_value(
    slot_id: Optional[str],
    extracted: Optional[dict],
) -> bool:
    if not slot_id or not extracted:
        return False
    from app.slots.definitions import SLOT_TO_ALL_FIELDS, SLOT_TO_REQUIRED_FIELDS

    fields = set(SLOT_TO_ALL_FIELDS.get(slot_id, []))
    fields.update(SLOT_TO_REQUIRED_FIELDS.get(slot_id, []))
    for field in fields:
        value = extracted.get(field)
        if value is not None and value != "" and value != []:
            return True
    return False


def _extract_and_merge(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
    current_slot: Optional[str],
) -> Optional[dict]:
    """Extract slot + guards (hallucinate, brand whitelist) + merge profile."""
    if not current_slot or current_slot not in SLOT_TOOL_SCHEMAS:
        return None

    # Phase 6 R+ fix: pass profile context cho LLM hiểu reference
    # (vd "cùng tên anh" = dealer_name = owner_name đã biết)
    profile_context = _build_profile_context(profile, current_slot)
    extracted = extract_slot(
        slot_id=current_slot,
        user_message=message,
        client=client,
        dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
        address_form=session.address_form,
        profile_context=profile_context,
    )
    extracted = extracted or {}

    deterministic_fields = _apply_deterministic_slot_fixes(
        session, profile, message, current_slot, extracted
    )

    if current_slot == "1.2":
        pending = _resolve_pending_address_confirmation(session, message)
        if pending:
            extracted["address"] = pending
            deterministic_fields.add("address")
        else:
            # Check raw message first — LLM extractor may auto-add province
            raw_msg = (message or "").strip()
            addr_to_check = raw_msg if _needs_address_province_confirmation(raw_msg) else extracted.get("address")
            if _needs_address_province_confirmation(addr_to_check):
                # Known district → confirm with guessed province
                raw_address = str(addr_to_check or "").strip()
                canonical = _canonical_address_guess(raw_address)
                session.pending_address_text = raw_address
                session.pending_address_canonical = canonical
                af = session.address_form.value
                return {"__internal_reply": f"Dạ {canonical} đúng không {af}?"}

            # Unknown short address (1-3 words, no province keyword) → ask province
            addr_val = extracted.get("address") or raw_msg
            if addr_val and _is_short_address_without_province(addr_val):
                af = session.address_form.value
                return {"__internal_reply": (
                    f"Dạ {addr_val} thuộc tỉnh/thành nào {af} nhỉ? "
                    f"Em cần ghi rõ để hỗ trợ đúng khu vực ạ."
                )}

    # Phase 6 R+ fix: code-level reference resolver (LLM_FAST đôi khi miss)
    # Vd "cùng tên anh", "giống vậy" → fill dealer_name = owner_name từ profile.
    # Fix C: track field nào fill từ reference để ack explicit "cũng là X".
    fields_before = {k for k, v in extracted.items() if v is not None}
    _resolve_reference_fill(message, current_slot, profile, extracted)
    fields_after = {k for k, v in extracted.items() if v is not None}
    newly_ref_filled = sorted(fields_after - fields_before)
    # Fix C v3: cũng detect khi LLM TỰ fill dealer_name = owner_name từ ref
    # message (vd "cùng tên anh") — không phải resolver fire mới ref fill.
    if not newly_ref_filled and _is_reference_message(message):
        ref_inferred = _detect_llm_reference_fill(extracted, profile, current_slot)
        if ref_inferred:
            newly_ref_filled = ref_inferred
    if newly_ref_filled:
        session.last_ref_filled_fields = newly_ref_filled
    else:
        session.last_ref_filled_fields = []

    if not extracted:
        return extracted

    # G2: Hallucinate guard — null các field LLM bịa.
    # Phase 6 R+: skip hallucinate check cho field vừa fill từ reference
    # resolver (value KHÔNG ở message hiện tại — đến từ profile cũ).
    ref_filled = set(session.last_ref_filled_fields or [])
    ref_filled.update(_get_reference_filled_fields(message, current_slot, profile))
    hallucinated = check_hallucinate(extracted, message)
    if hallucinated:
        for field in hallucinated:
            if field in ref_filled or field in deterministic_fields:
                # Reference fill từ profile context — KHÔNG count hallucinate
                continue
            increment_flag_count(session, Flag.HALLUCINATE)
            extracted[field] = None

    # 1C § 11: Brand whitelist check
    if extracted.get("supplier_brands"):
        unknown = get_unknown_brands(extracted["supplier_brands"])
        if unknown:
            increment_flag_count(session, Flag.BRAND_NOT_IN_WHITELIST)
            logger.info(
                "Brand không trong whitelist: session=%s brands=%s",
                session.session_id, unknown,
            )

    # 1A § 2.1: Address form auto-detect sau slot 1.1
    # CRITICAL: chỉ set nếu CHƯA detect (vẫn là mặc định ANH).
    # Nếu đã detect CHI từ turn trước, KHÔNG ĐƯỢC overwrite lại ANH.
    if current_slot == "1.1":
        explicit = detect_explicit_address(message)
        if explicit == "chị":
            session.address_form = AddressForm.CHI
        elif explicit == "anh" and session.address_form == AddressForm.ANH:
            # Chỉ confirm ANH nếu chưa set CHI trước đó
            session.address_form = AddressForm.ANH
        elif session.address_form == AddressForm.ANH and extracted.get("owner_name"):
            # Chỉ auto-detect từ tên nếu chưa có signal rõ ràng
            detected = detect_address_form(message, extracted["owner_name"])
            if detected == "chị":
                session.address_form = AddressForm.CHI
            # KHÔNG set ANH ở đây — giữ nguyên giá trị hiện tại

    # Merge + auto-derive Scope 2
    merge_extracted(profile, extracted, client=client)
    return extracted


# Phase 6 R+ fix bug 2: ack template cho REFUSAL/DEFER REQUIRED slot
# Refer 1A § 1.6 + spec D11 — dealer từ chối → ack tôn trọng + chuyển slot.
# Bug 3: Lửa Lò → tone ngắn ≤8 từ (1B § 2.1)
_DEFER_REFUSAL_ACK_TEMPLATES: dict[str, str] = {
    "1.1": "Dạ vâng, không tiện chia sẻ tên thì em hỏi sau nhé.",
    "1.2": "Dạ vâng, chưa muốn cho địa chỉ thì em ghi nhận, mình tiếp tục nhé.",
    "1.3": "Dạ vâng, em hiểu — số liên hệ chưa tiện thì em hỏi sau ạ.",
    "2.1": "Dạ vâng, mình tiếp tục nhé.",
    "2.2": "Dạ vâng, mình tiếp tục nhé.",
    "4.0": "Dạ vâng, em tôn trọng — mình ghi nhận tới đây nhé.",
}

# Lửa Lò: tone cộc ≤8 từ — KHÔNG nịnh, KHÔNG giải thích dài
_DEFER_REFUSAL_ACK_LUA_LO: dict[str, str] = {
    "1.1": "Dạ vâng. Em hỏi sau.",
    "1.2": "Dạ vâng. Em note.",
    "1.3": "Dạ vâng. Em hỏi sau.",
    "2.1": "Dạ. Tiếp ạ.",
    "2.2": "Dạ. Tiếp ạ.",
    "4.0": "Dạ. Em ghi nhận.",
}

_DEFER_REFUSAL_ACK_DEFAULT = "Dạ vâng, mình tiếp tục nhé."
_DEFER_REFUSAL_ACK_LUA_LO_DEFAULT = "Dạ. Tiếp ạ."


def _gen_defer_skip_ack(
    intent: "Intent",
    action: "Action",
    slot_id: Optional[str],
    session: "SessionState" = None,
) -> Optional[str]:
    """Sinh ack tôn trọng khi DEFER/SKIP do dealer refuse REQUIRED slot.

    Phase 6 R+ fix bug 3: nếu dealer_type=LỬA_LÒ → dùng ack ngắn ≤8 từ.

    Returns None nếu KHÔNG cần defer ack (vd ADVANCE bình thường, REFUSAL
    với OPTIONAL slot có rush_offer riêng).
    """
    if intent != Intent.REFUSAL:
        return None
    if action not in (Action.DEFER, Action.SKIP):
        return None
    # Lửa Lò: tone ngắn
    if session is not None and session.detected_dealer_type == DealerType.LUA_LO:
        if not slot_id:
            return _DEFER_REFUSAL_ACK_LUA_LO_DEFAULT
        return _DEFER_REFUSAL_ACK_LUA_LO.get(slot_id, _DEFER_REFUSAL_ACK_LUA_LO_DEFAULT)
    # Default: trung tính
    if not slot_id:
        return _DEFER_REFUSAL_ACK_DEFAULT
    return _DEFER_REFUSAL_ACK_TEMPLATES.get(slot_id, _DEFER_REFUSAL_ACK_DEFAULT)


# Phase 6 R+ fix: regex patterns dealer reference tới field cũ.
# Vd "cùng tên anh", "giống vậy", "như trên", "trùng tên owner".
import re as _re

_REFERENCE_PATTERNS: list[_re.Pattern] = [
    _re.compile(r"\b(cùng|trùng)\s*(tên|với)\s*(anh|chị|chủ|owner)?\b", _re.IGNORECASE),
    _re.compile(r"\b(giống|y\s*như|như)\s*(vậy|trên|kia|anh|chị)\b", _re.IGNORECASE),
    _re.compile(r"\b(cũng|luôn)\s*(vậy|là\s*(vậy|tên|đó))\b", _re.IGNORECASE),
    _re.compile(r"\b(cùng|lấy)\s*tên\s*(anh|chị|chủ|owner)?\s*(luôn|nhé|ạ)?\b", _re.IGNORECASE),
    _re.compile(r"\b(theo|y\s*chang)\s*(anh|chị|tên\s*anh)\b", _re.IGNORECASE),
]


def _is_reference_message(message: str) -> bool:
    """Detect dealer message reference tới field cũ (vd 'cùng tên anh')."""
    if not message:
        return False
    folded = _fold_vn(message)
    reference_phrases = (
        "cung ten anh",
        "cung ten chi",
        "trung ten anh",
        "trung ten chi",
        "giong ten anh",
        "giong ten chi",
        "cung giong ten anh",
        "cung giong ten chi",
        "cung giong anh",
        "cung giong chi",
        "cung la ten anh",
        "cung la ten chi",
        "cung la anh",
        "cung la chi",
        "cung ten",
        "cung giong",
        "ten giong anh",
        "ten giong chi",
        "lay ten anh",
        "lay ten chi",
        "y chang ten anh",
        "y chang ten chi",
    )
    if any(phrase in folded for phrase in reference_phrases):
        return True
    for pat in _REFERENCE_PATTERNS:
        if pat.search(message):
            return True
    return False


def _resolve_reference_fill(
    message: str,
    slot_id: Optional[str],
    profile: DealerProfileRaw,
    extracted: dict,
) -> None:
    """Code-level reference resolver — fill field từ profile khi dealer
    reference (vd 'cùng tên anh luôn' → dealer_name = owner_name).

    Refer feedback_99_percent_edge — 99% case không phải happy path.
    LLM_FAST đôi khi miss reference → cần deterministic fill.

    Mutate `extracted` in-place.
    """
    if not slot_id or not _is_reference_message(message):
        return

    if slot_id == "1.1":
        # Slot 1.1: owner_name ↔ dealer_name reference
        owner = profile.owner_name or extracted.get("owner_name")
        dealer = profile.dealer_name or extracted.get("dealer_name")
        # Dealer nói "cùng tên anh" → fill field còn thiếu = field đã có
        if owner and not dealer and not extracted.get("dealer_name"):
            extracted["dealer_name"] = owner
            logger.info(
                "Reference resolver: dealer_name = owner_name=%r (msg=%r)",
                owner, message[:60],
            )
        elif dealer and not owner and not extracted.get("owner_name"):
            extracted["owner_name"] = dealer
            logger.info(
                "Reference resolver: owner_name = dealer_name=%r (msg=%r)",
                dealer, message[:60],
            )


def _detect_llm_reference_fill(
    extracted: dict,
    profile: DealerProfileRaw,
    slot_id: Optional[str],
) -> list[str]:
    """Phase 6 R+ Fix C v3: detect khi LLM TỰ fill ref (vd dealer_name = owner_name).

    Trigger nếu extracted field value match profile field khác.
    Vd: dealer_name="Dương Lê" + profile.owner_name="Dương Lê" → ref filled.
    """
    if slot_id != "1.1":
        return []
    ref_fields: list[str] = []
    # Check dealer_name vừa fill = owner_name cũ
    new_dealer = extracted.get("dealer_name")
    if new_dealer and profile.owner_name and str(new_dealer).strip() == str(profile.owner_name).strip():
        ref_fields.append("dealer_name")
    new_owner = extracted.get("owner_name")
    if new_owner and profile.dealer_name and str(new_owner).strip() == str(profile.dealer_name).strip():
        ref_fields.append("owner_name")
    return ref_fields


def _get_reference_filled_fields(
    message: str,
    slot_id: Optional[str],
    profile: DealerProfileRaw,
) -> set[str]:
    """Trả set fields đã fill từ reference (skip hallucinate check)."""
    if not slot_id or not _is_reference_message(message):
        return set()
    if slot_id == "1.1":
        filled: set[str] = set()
        if profile.owner_name and not profile.dealer_name:
            filled.add("dealer_name")
        if profile.dealer_name and not profile.owner_name:
            filled.add("owner_name")
        return filled
    return set()


def _build_profile_context(
    profile: DealerProfileRaw,
    slot_id: str,
) -> Optional[dict]:
    """Build profile context dict cho extractor (Phase 6 R+ fix reference).

    Trả về fields trong slot ALL_FIELDS đã có value (non-None) để LLM biết
    dealer đã cho gì rồi → hiểu reference "cùng tên anh"/"giống vậy".
    """
    from app.slots.definitions import SLOT_TO_ALL_FIELDS
    fields = SLOT_TO_ALL_FIELDS.get(slot_id, [])
    if not fields:
        return None
    ctx = {}
    for f in fields:
        v = getattr(profile, f, None)
        if v is None or v == "" or v == []:
            continue
        ctx[f] = v
    return ctx or None


def _apply_deterministic_slot_fixes(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    slot_id: Optional[str],
    extracted: dict,
) -> set[str]:
    """Patch high-confidence short answers before state-machine decision.

    These are not LLM replacements; they handle common Vietnamese shorthand
    that the extractor can miss and that caused loops in manual testing.
    """
    if not slot_id:
        return set()
    deterministic_fields: set[str] = set()
    msg = (message or "").strip()
    msg_fold = _fold_vn(msg)

    # FIX M2: deterministic extract 2 SĐT cho slot 1.3
    if slot_id == "1.3":
        import re as _re_phone
        phone_matches = _re_phone.findall(r'0\d{8,10}', msg)
        if len(phone_matches) >= 2 and not extracted.get("phone_secondary"):
            if not extracted.get("phone_or_zalo"):
                extracted["phone_or_zalo"] = phone_matches[0]
                deterministic_fields.add("phone_or_zalo")
            extracted["phone_secondary"] = phone_matches[1]
            deterministic_fields.add("phone_secondary")

    if slot_id == "4.0":
        if _is_brandkit_affirmative_after_soft_no(msg_fold):
            extracted["brandkit_consent"] = "yes"
            deterministic_fields.add("brandkit_consent")

    # FIX C1: deterministic fix cho slot 2.2 — business_model_signal
    # LLM extractor hay miss câu trả lời ngắn "phân phối thuần", "làm hết"...
    if slot_id == "2.2":
        current_biz_raw = _fold_vn(str(extracted.get("business_model_signal") or "")).strip(" .,!?:;")
        if not extracted.get("business_model_signal") or current_biz_raw in {"ban", "ban thoi", "chi ban"}:
            _biz_keywords = {
                "phan phoi": "phân phối thuần",
                "dai ly": "đại lý phân phối",
                "ban le": "bán lẻ",
                "ban hang": "bán hàng",
                "ban thoi": "bán thôi",
                "chi ban": "bán thôi",
                "thi cong": "thi công + lắp đặt",
                "lam het": "trọn gói (thi công + phân phối)",
                "xuong": "có xưởng sản xuất",
                "lap dat": "thi công lắp đặt",
                "lam tron": "trọn gói",
                "tron goi": "trọn gói",
            }
            for kw, val in _biz_keywords.items():
                if kw in msg_fold:
                    extracted["business_model_signal"] = val
                    deterministic_fields.add("business_model_signal")
                    break

    if slot_id == "2.4":
        supplier_update = _parse_supplier_brand_correction(msg, profile)
        if supplier_update:
            extracted["supplier_brands"] = supplier_update
            deterministic_fields.add("supplier_brands")
        elif _normalize_supplier_brands(msg, extracted):
            deterministic_fields.add("supplier_brands")
        if not extracted.get("customer_segment_signal"):
            if "nha dan" in msg_fold:
                extracted["customer_segment_signal"] = msg
                deterministic_fields.add("customer_segment_signal")
            elif "du an" in msg_fold or "thau" in msg_fold:
                extracted["customer_segment_signal"] = msg
                deterministic_fields.add("customer_segment_signal")

    if slot_id == "2.5":
        if (
            profile.phone_or_zalo
            and not extracted.get("zalo")
            and _is_same_as_previous_phone(msg_fold)
        ):
            extracted["zalo"] = profile.phone_or_zalo
            deterministic_fields.add("zalo")
        if not extracted.get("primary_contact_channel"):
            if _mentions_referral_source(msg_fold):
                extracted["primary_contact_channel"] = msg
                deterministic_fields.add("primary_contact_channel")
            elif _mentions_customer_self_source(msg_fold):
                extracted["primary_contact_channel"] = msg
                deterministic_fields.add("primary_contact_channel")
        if _says_no_online_channel(msg_fold):
            if not extracted.get("facebook"):
                extracted["facebook"] = "chưa có"
            if not extracted.get("fb_marketing_status"):
                extracted["fb_marketing_status"] = "chưa có kênh online"
            deterministic_fields.update({"facebook", "fb_marketing_status"})
        if _mentions_referral_source(msg_fold):
            if not extracted.get("customer_old_percentage"):
                extracted["customer_old_percentage"] = "chủ yếu khách quen giới thiệu"
            deterministic_fields.add("customer_old_percentage")

    if slot_id == "2.6":
        if _says_no_facebook(msg_fold):
            if not extracted.get("facebook"):
                extracted["facebook"] = "chưa có"
            if not extracted.get("fb_marketing_status"):
                extracted["fb_marketing_status"] = "chưa có Facebook"
            deterministic_fields.update({"facebook", "fb_marketing_status"})
        elif _says_light_network(msg_fold) and not extracted.get("community_network_signal"):
            extracted["community_network_signal"] = msg
            deterministic_fields.add("community_network_signal")
        elif _mentions_strong_network(msg_fold) and not extracted.get("community_network_signal"):
            extracted["community_network_signal"] = msg
            deterministic_fields.add("community_network_signal")
        elif msg_fold in {"chua co", "khong co"}:
            if profile.facebook or extracted.get("facebook"):
                extracted["community_network_signal"] = msg
                deterministic_fields.add("community_network_signal")
            else:
                extracted["facebook"] = "chưa có"
                extracted["fb_marketing_status"] = "chưa có Facebook"
                deterministic_fields.update({"facebook", "fb_marketing_status"})
        if _mentions_referral_source(msg_fold) or _mentions_strong_network(msg_fold):
            if not extracted.get("customer_old_percentage"):
                extracted["customer_old_percentage"] = "chủ yếu khách quen giới thiệu"
            deterministic_fields.add("customer_old_percentage")

    if slot_id == "3.1":
        if _mentions_referral_source(msg_fold) or _mentions_strong_network(msg_fold):
            if not extracted.get("customer_old_percentage"):
                extracted["customer_old_percentage"] = msg
            deterministic_fields.add("customer_old_percentage")

    if slot_id == "3.2":
        if _says_no_customer_storage(msg_fold):
            extracted["customer_storage_method"] = "không lưu"
            deterministic_fields.add("customer_storage_method")

    if slot_id == "3.3":
        if _says_no_customer_pain(msg_fold):
            extracted["customer_pain"] = "không có vướng mắc lớn"
            deterministic_fields.add("customer_pain")

    if slot_id == "3.5":
        if any(p in msg_fold for p in ("bao cho hang", "bao hang", "day ve hang", "nha cung cap", "hang xu ly")):
            extracted["warranty_responsibility_signal"] = msg
            deterministic_fields.add("warranty_responsibility_signal")
        elif any(p in msg_fold for p in ("tu lo", "tu xu ly", "anh xu ly", "ben anh xu ly", "cua hang xu ly", "lo het")):
            extracted["warranty_responsibility_signal"] = msg
            deterministic_fields.add("warranty_responsibility_signal")

    return deterministic_fields


def _normalize_supplier_brands(message: str, extracted: dict) -> bool:
    brands = extracted.get("supplier_brands") or []
    if isinstance(brands, str):
        brands = [brands]
    if not isinstance(brands, list):
        brands = []

    if "austdoor" in (message or "").lower():
        brands.append("Austdoor")

    normalized: list[str] = []
    seen: set[str] = set()
    for brand in brands:
        fixed = correct_brand(str(brand)).strip()
        if not fixed:
            continue
        key = fixed.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(fixed)
    if normalized:
        extracted["supplier_brands"] = normalized
        return True
    return False


def _fold_vn(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _is_same_as_previous_phone(msg_fold: str) -> bool:
    patterns = (
        "giong so tren",
        "nhu so tren",
        "so tren",
        "so cu",
        "so do",
        "dung so do",
        "so ca nhan",
        "dung so ca nhan",
        "lay so ca nhan",
        "giong so may",
        "giong voi so",
    )
    return any(p in msg_fold for p in patterns)


def _mentions_referral_source(msg_fold: str) -> bool:
    patterns = (
        "nguoi quen",
        "gioi thieu",
        "khach quen",
        "khach cu",
        "truyen mieng",
        "quen biet",
    )
    return any(p in msg_fold for p in patterns)


def _mentions_customer_self_source(msg_fold: str) -> bool:
    patterns = (
        "khach tu tim",
        "tu tim den",
        "khach tu den",
        "noi tieng",
        "uy tin nen khach",
        "khach tim den",
    )
    return any(p in msg_fold for p in patterns)


def _says_no_online_channel(msg_fold: str) -> bool:
    patterns = (
        "chua co kenh nao",
        "khong co kenh nao",
        "khong co facebook",
        "chua co facebook",
        "khong co fb",
        "chua co fb",
        "khong quang cao",
        "chua quang cao",
    )
    return any(p in msg_fold for p in patterns)


def _mentions_strong_network(msg_fold: str) -> bool:
    patterns = (
        "co nhieu",
        "chu yeu la the",
        "gioi thieu cho nhau",
        "chia se khach",
        "thay gioi thieu",
        "tho gioi thieu",
        "doi tac gioi thieu",
    )
    return any(p in msg_fold for p in patterns)


def _says_no_facebook(msg_fold: str) -> bool:
    patterns = (
        "lam gi co facebook",
        "lam gi co fb",
        "khong co facebook",
        "khong co fb",
        "chua co facebook",
        "chua co fb",
        "khong dung facebook",
        "khong dung fb",
    )
    return any(p in msg_fold for p in patterns)


def _says_light_network(msg_fold: str) -> bool:
    patterns = (
        "thinh thoang",
        "thi thoang",
        "it thoi",
        "it lam",
        "co chut",
        "doi khi",
        "lau lau",
    )
    return any(p in msg_fold for p in patterns)


def _says_no_customer_storage(msg_fold: str) -> bool:
    patterns = (
        "khong luu",
        "chua luu",
        "khong luu luon",
        "khong co luu",
        "khong co danh sach",
        "chua co danh sach",
        "khong ghi lai",
        "khong quan ly",
    )
    return any(p in msg_fold for p in patterns)


def _says_no_customer_pain(msg_fold: str) -> bool:
    patterns = (
        "khong kho",
        "khong vuong",
        "khong van de",
        "khong gap kho",
        "khong co gi kho",
        "khong kho ti nao",
        "khong kho ty nao",
        "on het",
    )
    return any(p in msg_fold for p in patterns)


def _is_brandkit_affirmative_after_soft_no(msg_fold: str) -> bool:
    msg = msg_fold.strip(" .,!?:;")
    yes_patterns = (
        "u roi",
        "uh roi",
        "um roi",
        "ok roi",
        "oke roi",
        "duoc roi",
        "the cung duoc",
        "lam di",
        "lam thu",
        "cu lam",
        "co",
        "dong y",
        "nhan",
    )
    no_patterns = ("khong", "thoi", "khong can", "khong them", "mien")
    if any(p in msg for p in no_patterns):
        return False
    return msg in yes_patterns or any(p in msg for p in yes_patterns)


def _is_ack_only(message: str) -> bool:
    msg = _fold_vn(message).strip(" .,!?:;")
    return msg in {"u", "uh", "ua", "uk", "o", "ok", "oke", "vang", "da", "duoc", "roi"}


def _handle_repeat_complaint(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    current_slot: Optional[str],
) -> Optional[str]:
    msg = _fold_vn(message)
    if not any(p in msg for p in ("vua hoi", "hoi xong", "tren bao", "noi roi", "bao roi")):
        return None
    if not any(p in msg for p in ("dit", "dm", "me", "lap", "hoi lai")):
        return None

    if current_slot and _slot_has_any_profile_value(current_slot, profile):
        next_id = get_next_slot(current_slot, session.skipped_slots, profile=profile)
        session.current_slot = next_id
        question = get_slot_question_for_attempt(next_id, session)
    else:
        question = get_slot_question_for_attempt(current_slot, session)
    apology = "Em xin lỗi, đoạn đó em hỏi lặp."
    return f"{apology}\n\n{question}" if question else apology


def _handle_boundary_flirt(
    session: SessionState,
    message: str,
    current_slot: Optional[str],
) -> Optional[str]:
    msg = _fold_vn(message)
    patterns = ("di choi voi anh", "di nhau voi anh", "hen ho", "di cafe voi anh")
    if not any(p in msg for p in patterns):
        return None
    question = get_slot_question_for_attempt(current_slot, session)
    bridge = "Em chỉ trao đổi công việc ở đây thôi ạ. Mình quay lại thông tin cửa hàng nhé."
    return f"{bridge}\n\n{question}" if question else bridge


def _handle_slot_suggestion(
    *,
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    current_slot: Optional[str],
) -> Optional[str]:
    if current_slot != "4.2":
        return None
    msg = _fold_vn(message)
    suggestion_markers = (
        "em goi y",
        "em chon",
        "tuy em",
        "em thich mau",
        "mau gi anh thich mau day",
        "mau gi cung duoc",
        "em thay mau nao",
    )
    if not any(p in msg for p in suggestion_markers):
        return None

    color = _suggest_brand_color(profile)
    profile.color_accent = color
    if not profile.feng_shui_signal:
        profile.feng_shui_signal = "để bot gợi ý theo ngành"

    product = (profile.main_product or "ngành mình").strip()
    return (
        f"Dạ, nếu để em gợi ý thì với mảng {product}, em chọn {color}; "
        "hướng này nhìn chắc thương hiệu mà vẫn dễ dùng trên logo, danh thiếp.\n\n"
        "Anh chốt hướng màu đó nhé?"
    )


def _suggest_brand_color(profile: DealerProfileRaw) -> str:
    folded = _fold_vn(" ".join([profile.main_category or "", profile.main_product or ""]))
    if "cua_thep" in folded or "cua thep" in folded or "thep" in folded:
        return "xanh đen phối ghi bạc"
    if "tu_bep" in folded or "tu bep" in folded or "bep" in folded:
        return "xanh rêu phối kem"
    if "nhom" in folded or "kinh" in folded or "cua cuon" in folded:
        return "xanh dương phối ghi bạc"
    return "xanh dương phối ghi bạc"


def _slot_has_any_profile_value(slot_id: str, profile: DealerProfileRaw) -> bool:
    from app.slots.definitions import SLOT_TO_ALL_FIELDS

    for field in SLOT_TO_ALL_FIELDS.get(slot_id, []):
        value = getattr(profile, field, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        return True
    return False


def _resolve_pending_address_confirmation(
    session: SessionState,
    message: str,
) -> Optional[str]:
    if not session.pending_address_canonical:
        return None
    msg_fold = _fold_vn(message)
    yes_words = {"u", "uh", "ua", "uk", "ok", "oke", "dung", "dung roi", "phai", "phai roi", "chuan"}
    no_words = {"khong", "khong phai", "sai", "chua dung"}
    if msg_fold in yes_words or any(msg_fold.startswith(w + " ") for w in yes_words):
        canonical = session.pending_address_canonical
        session.pending_address_text = None
        session.pending_address_canonical = None
        return canonical
    if msg_fold in no_words or any(msg_fold.startswith(w + " ") for w in no_words):
        session.pending_address_text = None
        session.pending_address_canonical = None
    return None


def _needs_address_province_confirmation(address: Optional[str]) -> bool:
    if not address:
        return False
    folded = _fold_vn(str(address)).strip(" .,!?:;")
    return folded in _DISTRICT_PROVINCE_GUESSES


def _canonical_address_guess(address: str) -> str:
    folded = _fold_vn(address).strip(" .,!?:;")
    if folded in _DISTRICT_PROVINCE_GUESSES:
        return _DISTRICT_PROVINCE_GUESSES[folded]
    return address.strip()


def _local_address_note(address: str) -> Optional[str]:
    folded = _fold_vn(address)
    if "ecopark" in folded:
        return "Khu Ecopark nhiều nhà ở hoàn thiện chỉn chu, hợp để mình làm thương hiệu nhìn gọn và tin cậy hơn."
    if "ocean park" in folded:
        return "Khu Ocean Park nhiều căn hộ và nhà phố mới, nhu cầu hoàn thiện cửa/nội thất thường khá rõ."
    return None


# Province keywords that indicate address already has province info
_PROVINCE_KEYWORDS = {
    "hà nội", "ha noi", "hcm", "tp hcm", "hồ chí minh", "ho chi minh",
    "đà nẵng", "da nang", "hải phòng", "hai phong", "cần thơ", "can tho",
    "tỉnh", "tinh", "thành phố", "thanh pho", "tp.",
    # Common province names
    "hải dương", "hai duong", "bắc ninh", "bac ninh", "bắc giang", "bac giang",
    "hưng yên", "hung yen", "thái bình", "thai binh", "nam định", "nam dinh",
    "nghệ an", "nghe an", "thanh hóa", "thanh hoa", "quảng ninh", "quang ninh",
    "đồng nai", "dong nai", "bình dương", "binh duong", "long an",
    "vĩnh phúc", "vinh phuc", "phú thọ", "phu tho", "thái nguyên", "thai nguyen",
    "lâm đồng", "lam dong", "đắk lắk", "dak lak", "gia lai", "khánh hòa", "khanh hoa",
    "bình thuận", "binh thuan", "bình định", "binh dinh", "quảng nam", "quang nam",
    "quảng ngãi", "quang ngai", "phú yên", "phu yen", "ninh bình", "ninh binh",
    "hà tĩnh", "ha tinh", "quảng bình", "quang binh", "quảng trị", "quang tri",
    "thừa thiên huế", "thua thien hue", "huế", "hue",
    "tiền giang", "tien giang", "bến tre", "ben tre", "vĩnh long", "vinh long",
    "đồng tháp", "dong thap", "an giang", "kiên giang", "kien giang",
    "cà mau", "ca mau", "bạc liêu", "bac lieu", "sóc trăng", "soc trang",
    "trà vinh", "tra vinh", "hậu giang", "hau giang",
    "lào cai", "lao cai", "yên bái", "yen bai", "sơn la", "son la",
    "điện biên", "dien bien", "lai châu", "lai chau", "hà giang", "ha giang",
    "cao bằng", "cao bang", "bắc kạn", "bac kan", "tuyên quang", "tuyen quang",
    "lạng sơn", "lang son",
    "tây ninh", "tay ninh", "bình phước", "binh phuoc", "bà rịa", "ba ria",
    "vũng tàu", "vung tau",
}


def _is_short_address_without_province(address: Optional[str]) -> bool:
    """True nếu address ngắn (1-3 từ) và KHÔNG chứa province keyword.

    Dùng để trigger hỏi dealer xác nhận tỉnh/thành.
    Ví dụ: "Gia Lộc" → True (ngắn, không có province)
           "Gia Lộc, Hải Dương" → False (đã có province)
           "quận Bình Thạnh tp HCM" → False (có province keyword)
    """
    if not address:
        return False
    addr = str(address).strip()
    # Strip common prefixes for counting
    addr_clean = addr.lower()
    for prefix in ("chị ở ", "anh ở ", "em ở ", "tôi ở ", "ở "):
        if addr_clean.startswith(prefix):
            addr = addr[len(prefix):].strip()
            break

    words = addr.split()
    if len(words) > 4 or len(words) == 0:
        return False  # Long enough → likely has province, or empty

    # Check if any province keyword is present
    addr_lower = addr.lower()
    for kw in _PROVINCE_KEYWORDS:
        if kw in addr_lower:
            return False  # Already has province info

    return True


_DISTRICT_PROVINCE_GUESSES: dict[str, str] = {
    # Hà Nội
    "ecopark": "Ecopark, Văn Giang, Hưng Yên",
    "ocean park": "Ocean Park, Gia Lâm, Hà Nội",
    "ha dong": "Hà Đông, Hà Nội",
    "quan ha dong": "Hà Đông, Hà Nội",
    "q ha dong": "Hà Đông, Hà Nội",
    "q. ha dong": "Hà Đông, Hà Nội",
    "thanh xuan": "Thanh Xuân, Hà Nội",
    "quan thanh xuan": "Thanh Xuân, Hà Nội",
    "q thanh xuan": "Thanh Xuân, Hà Nội",
    "q. thanh xuan": "Thanh Xuân, Hà Nội",
    "cau giay": "Cầu Giấy, Hà Nội",
    "dong da": "Đống Đa, Hà Nội",
    "hoang mai": "Hoàng Mai, Hà Nội",
    "ba dinh": "Ba Đình, Hà Nội",
    "long bien": "Long Biên, Hà Nội",
    "tay ho": "Tây Hồ, Hà Nội",
    "nam tu liem": "Nam Từ Liêm, Hà Nội",
    "bac tu liem": "Bắc Từ Liêm, Hà Nội",
    "hai ba trung": "Hai Bà Trưng, Hà Nội",
    "hoan kiem": "Hoàn Kiếm, Hà Nội",
    "thanh tri": "Thanh Trì, Hà Nội",
    "gia lam": "Gia Lâm, Hà Nội",
    "dong anh": "Đông Anh, Hà Nội",
    # TP.HCM
    "thu duc": "Thủ Đức, TP.HCM",
    "binh thanh": "Bình Thạnh, TP.HCM",
    "go vap": "Gò Vấp, TP.HCM",
    "tan binh": "Tân Bình, TP.HCM",
    "tan phu": "Tân Phú, TP.HCM",
    "phu nhuan": "Phú Nhuận, TP.HCM",
    "binh tan": "Bình Tân, TP.HCM",
    "nha be": "Nhà Bè, TP.HCM",
    "hoc mon": "Hóc Môn, TP.HCM",
    "cu chi": "Củ Chi, TP.HCM",
    "binh chanh": "Bình Chánh, TP.HCM",
    # Đà Nẵng
    "hai chau": "Hải Châu, Đà Nẵng",
    "thanh khe": "Thanh Khê, Đà Nẵng",
    "son tra": "Sơn Trà, Đà Nẵng",
    "lien chieu": "Liên Chiểu, Đà Nẵng",
    "cam le": "Cẩm Lệ, Đà Nẵng",
}


def _handle_pause(
    session: SessionState,
    message: str,
    client: LLMClient,
    current_slot: Optional[str],
    profile=None,
) -> str:
    """PAUSE = defensive / tâm sự — F2B.4b LLM handler."""
    if session.paused_for == "defensive":
        increment_flag_count(session, Flag.DEALER_TOO_DEFENSIVE)
        defensive_count = session.flag_counts.get(
            Flag.DEALER_TOO_DEFENSIVE.value, 1
        )
        llm_reply = handle_defensive_llm(
            dealer_message=message,
            defensive_count=defensive_count,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            client=client,
            turn_count=session.turn_count,
            history_summary=summarize_history(session),
            current_slot=current_slot,
            bridge_avoid_hint=get_avoid_hint(session),
        )
        if llm_reply:
            if defensive_count >= 3:
                from app.core.edge_cases import raise_escalation
                raise_escalation(session, reason=f"defensive_x{defensive_count}")
                session.stage = Stage.DONE
                mark_session_closed(session)
            return llm_reply
        reply, should_close = handle_defensive_escalation(session)
        if should_close:
            session.stage = Stage.DONE
            mark_session_closed(session)
        return reply

    if session.paused_for == "tam_su":
        record_tam_su(session)
        tam_su_count = session.consecutive_tam_su
        # Fix Lỗi 7: sau TAM_SU, advance slot nếu current slot đã có data
        # để tránh hỏi lại câu hỏi đã hỏi trước đó.
        advance_slot = current_slot
        if current_slot and _slot_has_any_profile_value(current_slot, profile):
            advance_slot = get_next_slot(
                current_slot, session.skipped_slots, profile=profile
            )
            if advance_slot:
                session.current_slot = advance_slot
        next_slot_hint = get_slot_question_for_attempt(
            advance_slot or current_slot, session
        )
        llm_reply = handle_tam_su_llm(
            dealer_message=message,
            tam_su_count=tam_su_count,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            client=client,
            history_summary=summarize_history(session),
            current_slot=advance_slot or current_slot,
            next_slot_hint=next_slot_hint,
            bridge_avoid_hint=get_avoid_hint(session),
        )
        if llm_reply:
            if tam_su_count >= 5:
                from app.core.edge_cases import raise_escalation
                raise_escalation(session, reason=f"tam_su_x{tam_su_count}")
                session.stage = Stage.DONE
                mark_session_closed(session)
            return _ensure_followup_question(llm_reply, next_slot_hint)
        reply, should_close = handle_tam_su_escalation(session)
        if should_close:
            session.stage = Stage.DONE
            mark_session_closed(session)
        return reply

    # Fallback (paused_for None hoặc lạ)
    return phase_1_pause_fallback(session.paused_for)


def _ensure_followup_question(reply: str, followup: Optional[str]) -> str:
    if not reply or not followup:
        return reply
    tail = reply.strip()[-120:]
    if "?" in tail:
        return reply
    return f"{reply.strip()}\n\n{followup}"
