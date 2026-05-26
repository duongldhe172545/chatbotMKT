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

    # Extract field (Phase 2: 16 slot có extractor)
    extracted = _extract_and_merge(session, profile, message, client, current_slot)
    clarify_reply = _get_internal_reply(extracted)
    if clarify_reply:
        return clarify_reply

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
                raw_address = str(addr_to_check or "").strip()
                canonical = _canonical_address_guess(raw_address)
                session.pending_address_text = raw_address
                session.pending_address_canonical = canonical
                af = session.address_form.value
                return {"__internal_reply": f"Dạ {canonical} đúng không {af}?"}

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
    if current_slot == "1.1":
        explicit = detect_explicit_address(message)
        if explicit in ("chị", "anh"):
            session.address_form = (
                AddressForm.CHI if explicit == "chị" else AddressForm.ANH
            )
        elif extracted.get("owner_name"):
            detected = detect_address_form(message, extracted["owner_name"])
            session.address_form = (
                AddressForm.CHI if detected == "chị" else AddressForm.ANH
            )

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

    if slot_id == "2.4":
        if _normalize_supplier_brands(msg, extracted):
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


_DISTRICT_PROVINCE_GUESSES: dict[str, str] = {
    # Hà Nội
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
