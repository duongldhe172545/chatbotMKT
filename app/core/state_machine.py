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
    profile=None,
) -> tuple[Optional[str], Action]:
    """F2A.4 smart advance.

    Args:
        session: SessionState (mutated in-place)
        intent: detected intent (Layer 1 regex hoặc Layer 2 LLM)
        extracted: dict field từ extractor, None nếu chưa extract / không có field
        profile: DealerProfileRaw (Phase 5 R6 fix — check profile state cho
            multi-turn PARTIAL: dealer cho field A turn 1, field B turn 2 →
            cả 2 đều fill ở profile → ADVANCE).

    Returns:
        (next_slot_to_ask, action). next_slot = None → chuyển CONFIRMING.

    Side effects:
        - Mutate session.slot_attempts, session.flags, session.skipped_slots,
          session.deferred_slots, session.current_slot, session.paused_for
    """
    current = session.current_slot

    # Step 2.8: Re-check deferred slots
    # Phase 6 R+ fix v2: CHỈ re-check khi dealer KHÔNG cho data current turn
    # (extracted empty). Nếu dealer vừa fill slot hiện tại → ack + advance
    # bình thường, defer slot vẫn ở deferred_slots (sẽ recheck turn sau).
    # Lý do: nếu dealer fill data slot N + bot quay slot defer X → dealer
    # cảm thấy bot ignore câu trả lời vừa cho.
    no_new_data = not extracted or not any(v for v in extracted.values() if v is not None)
    if intent not in (Intent.REFUSAL, Intent.DEFENSIVE) and no_new_data:
        if _is_current_slot_done(current, profile, session):
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
        return _handle_refusal(session, current, profile=profile)

    # Step 2.6: PARTIAL fill cho multi-field slot (check profile-aware)
    if current and is_multi_field(current) and (extracted or profile):
        partial_result = _check_partial_fill(current, extracted or {}, session, profile)
        if partial_result:
            return partial_result

    # Step 2-3: Evaluate slot status (Phase 5 R6: check profile state nếu có,
    # fallback extracted — multi-turn fill: turn N fill field A, turn N+1 fill
    # field B → cả 2 đều ở profile → ADVANCE).
    fill_source = _merge_fill_source(extracted, profile, current)
    if fill_source and _slot_fully_filled(current, fill_source):
        # ADVANCE — reset consecutive
        if current:
            attempts = session.slot_attempts.setdefault(current, SlotAttempts())
            attempts.consecutive = 0
        # Phase 6 R+ fix: pass profile để next_slot skip slot đã fill (tránh
        # bot hỏi lại slot 2.1 'nội thất' đã fill khi recheck deferred làm loop).
        next_id = next_slot(current, session.skipped_slots, profile=profile) if current else None
        session.current_slot = next_id
        return (next_id, Action.ADVANCE)

    # Slot chưa fill (extracted=None hoặc thiếu required field, không phải partial)
    if current is None:
        # Edge case: không có current_slot → đi đầu list
        next_id = next_slot("", session.skipped_slots, profile=profile)
        session.current_slot = next_id
        return (next_id, Action.ADVANCE)

    if current in REQUIRED_SLOTS:
        return _handle_required_retry_defer_skip(session, current, profile=profile)
    if current in OPTIONAL_SLOTS:
        return _handle_optional_skip(session, current, profile=profile)

    # THÔNG BÁO (slot 4.1) — bot độc thoại, dealer ack "ok" là pass
    if intent == Intent.AFFIRMATIVE or intent == Intent.NORMAL:
        next_id = next_slot(current, session.skipped_slots, profile=profile)
        session.current_slot = next_id
        return (next_id, Action.ADVANCE)

    # Fallback
    return (current, Action.RETRY)


# ============================================================
# Helpers
# ============================================================


def _is_value_filled(value) -> bool:
    """True nếu value được coi là "đã fill" (không phải default empty).

    Phase 6 R+ fix bug: Pydantic list[str] default = [] (không None).
    `[] is not None` → True trước đây làm state machine nhầm slot 2.4
    (supplier_brands list) đã filled khi chưa có giá trị nào.
    """
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict, set, tuple)) and not value:
        return False
    return True


def _merge_fill_source(
    extracted: Optional[dict],
    profile,
    slot_id: Optional[str],
) -> dict:
    """Merge extracted (turn này) + profile (accumulated) cho fill check.

    Phase 5 R6: PARTIAL multi-turn — dealer fill field A turn N, field B turn N+1.
    State machine cần thấy cả 2 đều có giá trị → ADVANCE thay vì lặp PARTIAL.

    Returns:
        Dict {field: value} hợp nhất. None / empty values từ profile loại bỏ.
    """
    merged: dict = {}
    if profile is not None and slot_id:
        all_fields = SLOT_TO_ALL_FIELDS.get(slot_id, [])
        for f in all_fields:
            value = getattr(profile, f, None)
            if _is_value_filled(value):
                merged[f] = value
    if extracted:
        for f, v in extracted.items():
            if _is_value_filled(v):
                merged[f] = v
    return merged


def _slot_fully_filled(slot_id: Optional[str], extracted: dict) -> bool:
    """True nếu slot đã đủ thông tin để ADVANCE.

    - REQUIRED slot: tất cả required_fields phải có value.
    - OPTIONAL slot: ít nhất 1 field trong SLOT_TO_ALL_FIELDS có value
      (dealer đã trả lời gì đó dù không cho hết).
    - THÔNG BÁO slot (4.1): không cần field, caller dùng AFFIRMATIVE intent.

    Phase 6 R+ fix bug: empty list/dict không tính filled (supplier_brands=[]).
    """
    if not slot_id:
        return False
    required = SLOT_TO_REQUIRED_FIELDS.get(slot_id, [])
    if required:
        return all(_is_value_filled(extracted.get(f)) for f in required)
    all_fields = SLOT_TO_ALL_FIELDS.get(slot_id, [])
    if not all_fields:
        return False
    return any(_is_value_filled(extracted.get(f)) for f in all_fields)


def _check_partial_fill(
    current: str,
    extracted: dict,
    session: SessionState,
    profile=None,
) -> Optional[tuple[Optional[str], Action]]:
    """Step 2.6: PARTIAL_RETRY nếu slot multi-field fill 1 phần.

    Phase 5 R3 Gap 11: cover cả OPTIONAL multi-field (2.4/2.5/2.6/3.3) —
    không chỉ REQUIRED. Spec 1A § 1.5 áp dụng cho 7 slot multi-field.

    Phase 5 R6 fix: check profile-aware. Nếu profile đã có field từ turn
    trước → KHÔNG fire PARTIAL nữa (đã đủ qua merge).

    Guard: track `session.partial_retried_slots` để mỗi slot PARTIAL_RETRY
    TỐI ĐA 1 lần (tránh loop OPTIONAL khi dealer không add thêm field).
    """
    from app.slots.definitions import SLOT_TO_ALL_FIELDS

    # Đã PARTIAL_RETRY slot này rồi → không trigger lại (tránh loop)
    if current in (session.partial_retried_slots or []):
        return None

    # Merge extracted + profile (phase 5 R6 — multi-turn fill check)
    merged = _merge_fill_source(extracted, profile, current)

    # Ưu tiên REQUIRED fields (slot 1.1, 1.2, 2.1, 2.2, 4.0 có REQUIRED).
    required = SLOT_TO_REQUIRED_FIELDS.get(current, [])
    if required:
        filled = [f for f in required if merged.get(f) is not None]
        missing = [f for f in required if f not in filled]
        if filled and missing:
            session.partial_retried_slots.append(current)
            return (current, Action.PARTIAL_RETRY)
        return None

    # OPTIONAL multi-field (2.4/2.5/2.6/3.3): ép PARTIAL nếu dealer chỉ
    # fill 1 trong ≥ 2 field (engine hỏi tiếp 1 lần — 1A § 1.5 ví dụ slot 2.4).
    all_fields = SLOT_TO_ALL_FIELDS.get(current, [])
    if len(all_fields) < 2:
        return None
    filled = [f for f in all_fields if merged.get(f) is not None]
    missing = [f for f in all_fields if merged.get(f) is None]
    if filled and len(missing) >= 1 and len(filled) < len(all_fields):
        session.partial_retried_slots.append(current)
        return (current, Action.PARTIAL_RETRY)
    return None


def _handle_refusal(
    session: SessionState,
    current: Optional[str],
    profile=None,
) -> tuple[Optional[str], Action]:
    """Refusal rõ ràng: OPTIONAL → SKIP ngay, REQUIRED → DEFER hoặc SKIP."""
    if current is None:
        return (None, Action.ADVANCE)
    if current in OPTIONAL_SLOTS:
        return _handle_optional_skip(session, current, profile=profile)
    if current in REQUIRED_SLOTS:
        return _handle_required_retry_defer_skip(
            session, current, is_explicit_refusal=True, profile=profile,
        )
    next_id = next_slot(current, session.skipped_slots, profile=profile)
    session.current_slot = next_id
    return (next_id, Action.ADVANCE)


def _handle_required_retry_defer_skip(
    session: SessionState,
    current: str,
    is_explicit_refusal: bool = False,
    profile=None,
) -> tuple[Optional[str], Action]:
    """Step 2.7: RETRY / DEFER / SKIP cho slot REQUIRED chưa fill.

    Args:
        is_explicit_refusal: True nếu intent=REFUSAL — bỏ qua check consecutive,
            đi thẳng DEFER (hoặc SKIP nếu hết total). Refer D11 STRATEGY note.
        profile: pass cho next_slot skip slot đã fill (Phase 6 R+ fix).
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
        next_id = next_slot(current, session.skipped_slots, profile=profile)
        session.current_slot = next_id
        return (next_id, Action.SKIP)

    # Explicit refusal OR consecutive >= MAX → DEFER
    if is_explicit_refusal or attempts.consecutive >= MAX_RETRY_CONSECUTIVE:
        already_deferred = current in session.deferred_slots
        if already_deferred:
            if current not in session.skipped_slots:
                session.skipped_slots.append(current)
            if Flag.REQUIRED_MISSING not in session.flags:
                session.flags.append(Flag.REQUIRED_MISSING)
            del session.deferred_slots[current]
            next_id = next_slot(current, session.skipped_slots, profile=profile)
            session.current_slot = next_id
            return (next_id, Action.SKIP)

        session.deferred_slots[current] = DeferredSlot(
            defer_at_turn=session.turn_count,
            recheck_after_n_slots=DEFER_RECHECK_AFTER_N_SLOTS,
        )
        attempts.consecutive = 0
        skipped_for_now = list(set(session.skipped_slots) | set(session.deferred_slots.keys()))
        next_id = next_slot(current, skipped_for_now, profile=profile)
        session.current_slot = next_id
        return (next_id, Action.DEFER)

    return (current, Action.RETRY)


def _handle_optional_skip(
    session: SessionState,
    current: str,
    profile=None,
) -> tuple[Optional[str], Action]:
    """Slot OPTIONAL không fill / refusal → SKIP NGAY + flag dealer_declined."""
    if current not in session.skipped_slots:
        session.skipped_slots.append(current)
    if Flag.DEALER_DECLINED not in session.flags:
        session.flags.append(Flag.DEALER_DECLINED)
    next_id = next_slot(current, session.skipped_slots, profile=profile)
    session.current_slot = next_id
    return (next_id, Action.SKIP)


def _is_current_slot_done(
    current: Optional[str],
    profile,
    session: SessionState,
) -> bool:
    """Phase 6 R+ fix BUG E: True nếu current_slot đã có thể chuyển sang slot khác.

    Điều kiện done:
    - current=None (chưa bắt đầu / vừa transition)
    - current trong skipped_slots
    - current là REQUIRED + đủ required_fields (profile-aware)
    - current là OPTIONAL multi-field + đã có ≥ 1 field
    - current là THÔNG BÁO (slot 4.1)

    KHÔNG done nếu dealer đang fill multi-field PARTIAL hoặc REQUIRED còn thiếu.
    """
    if not current:
        return True
    if current in session.skipped_slots:
        return True
    # THÔNG BÁO không có field — luôn done sau ack
    from app.slots.definitions import THONG_BAO_SLOTS
    if current in THONG_BAO_SLOTS:
        return True
    # Check fully_filled qua profile state (Phase 6 R+ fix bug: empty list/str
    # không tính filled — Pydantic list[str] default=[] làm nhầm).
    required = SLOT_TO_REQUIRED_FIELDS.get(current, [])
    if required:
        if profile is None:
            return False
        return all(_is_value_filled(getattr(profile, f, None)) for f in required)
    all_fields = SLOT_TO_ALL_FIELDS.get(current, [])
    if profile is not None and all_fields:
        any_filled = any(
            _is_value_filled(getattr(profile, f, None)) for f in all_fields
        )
        if any_filled:
            return True
    return False


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
