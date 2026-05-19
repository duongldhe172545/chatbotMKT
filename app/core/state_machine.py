"""F2A.4 smart advance state machine — 6 action.

Refer:
- F2A.4 (LUAT_2A_core v0.2.4) — algorithm với 6 step (2.5/2.6/2.7/2.8)
- D11 STRATEGY — retry rule 3 total / 2 consecutive / DEFER
- 1A § 1.6 — quy ước retry kiên nhẫn (dealer turn đầu hay test/nghịch)
- D10 STRATEGY — slot 4.0 consent=no skip 4.1/4.2

Notes:
- Mutate session in-place (slot_attempts, flags, skipped_slots, deferred_slots,
  current_slot, paused_for) — đúng pattern Python state machine.
- Phase 1 simplified: defensive/tâm sự handler (LLM gen) là conversation
  orchestrator job, state machine chỉ return PAUSE.
"""
from __future__ import annotations

from typing import Optional

from app.models.enums import Action, Flag, Intent
from app.models.schema import DeferredSlot, SessionState, SlotAttempts
from app.slots.definitions import (
    OPTIONAL_SLOTS,
    REQUIRED_SLOTS,
    SLOT_TO_ALL_FIELDS,
    SLOT_TO_REQUIRED_FIELDS,
    is_multi_field,
    next_slot,
)


# ============================================================
# Config — refer F2A.4 tham số config
# ============================================================
MAX_RETRY_TOTAL = 3                    # Tổng max / slot REQUIRED / session
MAX_RETRY_CONSECUTIVE = 2              # Liên tiếp max (D11)
DEFER_RECHECK_AFTER_N_SLOTS = 2        # Re-check sau N slot khác
MAX_DEFER_PER_SLOT = 1                 # 1 slot defer max 1 lần


# ============================================================
# Main entry — F2A.4 decide_action
# ============================================================


def decide_action(
    session: SessionState,
    intent: Intent,
    extracted: Optional[dict] = None,
) -> tuple[Optional[str], Action]:
    """F2A.4 smart advance.

    Args:
        session: SessionState (mutated in-place)
        intent: detected intent (Layer 1 regex hoặc Layer 2 LLM)
        extracted: dict field từ extractor, None nếu chưa extract / không có field

    Returns:
        (next_slot_to_ask, action). next_slot = None → chuyển CONFIRMING.

    Side effects:
        - Mutate session.slot_attempts, session.flags, session.skipped_slots,
          session.deferred_slots, session.current_slot, session.paused_for
    """
    current = session.current_slot

    # Step 2.8: Re-check deferred slots TRƯỚC khi xử intent mới
    # (mood dealer ok → quay lại deferred slot)
    if intent not in (Intent.REFUSAL, Intent.DEFENSIVE):
        recheck_slot = _recheck_deferred(session)
        if recheck_slot:
            session.current_slot = recheck_slot
            return (recheck_slot, Action.RETRY)

    # Step 1: Intent branch — defensive/tâm sự → PAUSE
    if intent == Intent.DEFENSIVE:
        session.paused_for = "defensive"
        return (current, Action.PAUSE)
    if intent == Intent.TAM_SU:
        session.paused_for = "tam_su"
        return (current, Action.PAUSE)

    # Reset paused_for nếu intent thường
    if session.paused_for is not None:
        session.paused_for = None

    # Step 2.5: Branch slot 4.0 consent=no — refer D10 STRATEGY
    if current == "4.0" and extracted:
        consent = extracted.get("brandkit_consent")
        if consent == "no":
            for skip_slot in ("4.1", "4.2"):
                if skip_slot not in session.skipped_slots:
                    session.skipped_slots.append(skip_slot)
            session.current_slot = None
            return (None, Action.ADVANCE)

    # Step 1.x: REFUSAL handling (rõ ràng từ chối, không phải test/nghịch)
    if intent == Intent.REFUSAL:
        return _handle_refusal(session, current)

    # Step 2.6: PARTIAL fill cho multi-field slot
    if current and is_multi_field(current) and extracted:
        partial_result = _check_partial_fill(current, extracted)
        if partial_result:
            return partial_result

    # Step 2-3: Evaluate slot status
    if extracted and _slot_fully_filled(current, extracted):
        # ADVANCE — reset consecutive
        if current:
            attempts = session.slot_attempts.setdefault(current, SlotAttempts())
            attempts.consecutive = 0
        next_id = next_slot(current, session.skipped_slots) if current else None
        session.current_slot = next_id
        return (next_id, Action.ADVANCE)

    # Slot chưa fill (extracted=None hoặc thiếu required field, không phải partial)
    if current is None:
        # Edge case: không có current_slot → đi đầu list
        next_id = next_slot("", session.skipped_slots)
        session.current_slot = next_id
        return (next_id, Action.ADVANCE)

    if current in REQUIRED_SLOTS:
        return _handle_required_retry_defer_skip(session, current)
    if current in OPTIONAL_SLOTS:
        return _handle_optional_skip(session, current)

    # THÔNG BÁO (slot 4.1) — bot độc thoại, dealer ack "ok" là pass
    if intent == Intent.AFFIRMATIVE or intent == Intent.NORMAL:
        next_id = next_slot(current, session.skipped_slots)
        session.current_slot = next_id
        return (next_id, Action.ADVANCE)

    # Fallback
    return (current, Action.RETRY)


# ============================================================
# Helpers
# ============================================================


def _slot_fully_filled(slot_id: Optional[str], extracted: dict) -> bool:
    """True nếu slot đã đủ thông tin để ADVANCE.

    - REQUIRED slot: tất cả required_fields phải có value.
    - OPTIONAL slot: ít nhất 1 field trong SLOT_TO_ALL_FIELDS có value
      (dealer đã trả lời gì đó dù không cho hết).
    - THÔNG BÁO slot (4.1): không cần field, caller dùng AFFIRMATIVE intent.
    """
    if not slot_id:
        return False
    required = SLOT_TO_REQUIRED_FIELDS.get(slot_id, [])
    if required:
        # REQUIRED slot — cần all required_fields
        return all(extracted.get(f) is not None for f in required)
    # OPTIONAL slot — cần ít nhất 1 field non-None
    all_fields = SLOT_TO_ALL_FIELDS.get(slot_id, [])
    if not all_fields:
        return False
    return any(extracted.get(f) is not None for f in all_fields)


def _check_partial_fill(
    current: str,
    extracted: dict,
) -> Optional[tuple[Optional[str], Action]]:
    """Step 2.6: PARTIAL_RETRY nếu slot multi-field fill 1 phần.

    Returns (current, PARTIAL_RETRY) nếu detect partial. None nếu full hoặc empty.
    """
    required = SLOT_TO_REQUIRED_FIELDS.get(current, [])
    if not required:
        return None
    filled = [f for f in required if extracted.get(f) is not None]
    missing = [f for f in required if f not in filled]
    if filled and missing:
        # PARTIAL — KHÔNG count attempts
        return (current, Action.PARTIAL_RETRY)
    return None


def _handle_refusal(
    session: SessionState,
    current: Optional[str],
) -> tuple[Optional[str], Action]:
    """Refusal rõ ràng: OPTIONAL → SKIP ngay, REQUIRED → DEFER hoặc SKIP."""
    if current is None:
        return (None, Action.ADVANCE)
    if current in OPTIONAL_SLOTS:
        return _handle_optional_skip(session, current)
    if current in REQUIRED_SLOTS:
        return _handle_required_retry_defer_skip(
            session, current, is_explicit_refusal=True
        )
    # THÔNG BÁO — không có refusal logic
    next_id = next_slot(current, session.skipped_slots)
    session.current_slot = next_id
    return (next_id, Action.ADVANCE)


def _handle_required_retry_defer_skip(
    session: SessionState,
    current: str,
    is_explicit_refusal: bool = False,
) -> tuple[Optional[str], Action]:
    """Step 2.7: RETRY / DEFER / SKIP cho slot REQUIRED chưa fill.

    Args:
        is_explicit_refusal: True nếu intent=REFUSAL — bỏ qua check consecutive,
            đi thẳng DEFER (hoặc SKIP nếu hết total). Refer D11 STRATEGY note.
    """
    attempts = session.slot_attempts.setdefault(current, SlotAttempts())
    attempts.consecutive += 1
    attempts.total += 1

    # Hết total → SKIP + flag required_missing
    if attempts.total >= MAX_RETRY_TOTAL:
        if current not in session.skipped_slots:
            session.skipped_slots.append(current)
        if Flag.REQUIRED_MISSING not in session.flags:
            session.flags.append(Flag.REQUIRED_MISSING)
        next_id = next_slot(current, session.skipped_slots)
        session.current_slot = next_id
        return (next_id, Action.SKIP)

    # Explicit refusal OR consecutive >= MAX → DEFER
    if is_explicit_refusal or attempts.consecutive >= MAX_RETRY_CONSECUTIVE:
        # Check max defer cùng slot
        already_deferred = current in session.deferred_slots
        if already_deferred:
            # Đã defer 1 lần rồi mà vẫn refusal → SKIP
            if current not in session.skipped_slots:
                session.skipped_slots.append(current)
            if Flag.REQUIRED_MISSING not in session.flags:
                session.flags.append(Flag.REQUIRED_MISSING)
            # Xóa deferred (đã bỏ slot)
            del session.deferred_slots[current]
            next_id = next_slot(current, session.skipped_slots)
            session.current_slot = next_id
            return (next_id, Action.SKIP)

        session.deferred_slots[current] = DeferredSlot(
            defer_at_turn=session.turn_count,
            recheck_after_n_slots=DEFER_RECHECK_AFTER_N_SLOTS,
        )
        attempts.consecutive = 0  # Reset cho lần re-check sau
        # Advance qua slot kế — deferred slot bị skip tạm
        skipped_for_now = list(set(session.skipped_slots) | set(session.deferred_slots.keys()))
        next_id = next_slot(current, skipped_for_now)
        session.current_slot = next_id
        return (next_id, Action.DEFER)

    # consecutive < 2 và total < 3 → RETRY (hỏi lại tone giảm dần)
    return (current, Action.RETRY)


def _handle_optional_skip(
    session: SessionState,
    current: str,
) -> tuple[Optional[str], Action]:
    """Slot OPTIONAL không fill / refusal → SKIP NGAY + flag dealer_declined."""
    if current not in session.skipped_slots:
        session.skipped_slots.append(current)
    if Flag.DEALER_DECLINED not in session.flags:
        session.flags.append(Flag.DEALER_DECLINED)
    next_id = next_slot(current, session.skipped_slots)
    session.current_slot = next_id
    return (next_id, Action.SKIP)


def _recheck_deferred(session: SessionState) -> Optional[str]:
    """Step 2.8: re-check deferred slots khi gap turn đủ.

    Returns slot_id để re-ask, hoặc None.

    Logic:
    - Slot deferred + (turn_count - defer_at_turn >= recheck_after_n_slots)
    - Phase 1 simplified: chỉ check turn gap (không check mood detail).
      Refer F2A.4 step 2.8 — Phase 2+ thêm intent recent check.
    """
    for slot_id, deferred in list(session.deferred_slots.items()):
        gap = session.turn_count - deferred.defer_at_turn
        if gap >= deferred.recheck_after_n_slots:
            del session.deferred_slots[slot_id]
            return slot_id
    return None
