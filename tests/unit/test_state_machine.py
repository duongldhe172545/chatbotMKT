"""Test F2A.4 state machine — 6 action.

Refer:
- F2A.4 (LUAT_2A_core v0.2.4) — algorithm 6 step
- D11 STRATEGY — retry rule 3 total / 2 consecutive / DEFER
- D10 STRATEGY — slot 4.0 consent=no skip 4.1/4.2
"""
from __future__ import annotations

import pytest

from app.core.session import create_session
from app.core.state_machine import (
    MAX_DEFER_PER_SLOT,
    MAX_RETRY_CONSECUTIVE,
    MAX_RETRY_TOTAL,
    decide_action,
)
from app.models.enums import Action, Flag, Intent


# ============================================================
# Happy path — ADVANCE
# ============================================================


class TestAdvance:
    def test_advance_on_full_fill(self):
        """Slot REQUIRED full fill → ADVANCE."""
        s = create_session()
        s.current_slot = "1.1"
        extracted = {"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.ADVANCE
        assert next_slot == "1.2"
        assert s.current_slot == "1.2"

    def test_advance_resets_consecutive(self):
        """Sau ADVANCE, consecutive_attempts reset = 0."""
        s = create_session()
        s.current_slot = "1.1"
        # Simulate consecutive=1 từ retry trước
        from app.models.schema import SlotAttempts
        s.slot_attempts["1.1"] = SlotAttempts(consecutive=1, total=1)

        extracted = {"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"}
        decide_action(s, Intent.NORMAL, extracted)
        assert s.slot_attempts["1.1"].consecutive == 0


# ============================================================
# RETRY — REQUIRED, attempt 1
# ============================================================


class TestRetry:
    def test_retry_required_first_attempt(self):
        """Slot REQUIRED + empty extracted + intent normal → RETRY."""
        s = create_session()
        s.current_slot = "1.1"
        next_slot, action = decide_action(s, Intent.NORMAL, extracted=None)
        assert action == Action.RETRY
        assert next_slot == "1.1"
        # Stay on current slot
        assert s.current_slot == "1.1"
        # consecutive=1, total=1
        assert s.slot_attempts["1.1"].consecutive == 1
        assert s.slot_attempts["1.1"].total == 1

    def test_retry_increments_attempts(self):
        s = create_session()
        s.current_slot = "1.1"
        # First retry
        decide_action(s, Intent.NORMAL, extracted=None)
        assert s.slot_attempts["1.1"].consecutive == 1
        assert s.slot_attempts["1.1"].total == 1


# ============================================================
# DEFER — REQUIRED, 2 consecutive
# ============================================================


class TestDefer:
    def test_defer_after_2_consecutive(self):
        """Sau 2 lần consecutive RETRY chưa fill → DEFER."""
        s = create_session()
        s.current_slot = "1.1"
        # Retry 1
        decide_action(s, Intent.NORMAL, None)
        assert s.slot_attempts["1.1"].consecutive == 1
        # Retry 2 → consecutive=2 → DEFER
        next_slot, action = decide_action(s, Intent.NORMAL, None)
        assert action == Action.DEFER
        # Slot 1.1 trong deferred, current_slot chuyển sang slot kế
        assert "1.1" in s.deferred_slots
        assert s.current_slot == "1.2"
        # consecutive reset, total = 2 (giữ)
        assert s.slot_attempts["1.1"].consecutive == 0
        assert s.slot_attempts["1.1"].total == 2

    def test_explicit_refusal_immediate_defer(self):
        """REQUIRED + intent=REFUSAL → DEFER ngay (bỏ check consecutive)."""
        s = create_session()
        s.current_slot = "1.1"
        next_slot, action = decide_action(s, Intent.REFUSAL, None)
        assert action == Action.DEFER
        assert "1.1" in s.deferred_slots
        # Total = 1, consecutive reset = 0
        assert s.slot_attempts["1.1"].total == 1

    def test_recheck_deferred_re_asks(self):
        """Sau N slot khác + current slot done → deferred slot re-check + RETRY.

        Phase 6 R+ fix BUG E: chỉ re-check khi current_slot đã fully_filled.
        """
        from app.models.schema import DealerProfileRaw, DeferredSlot
        s = create_session()
        s.current_slot = "1.1"

        # Defer slot 1.1 ở turn 0
        s.deferred_slots["1.1"] = DeferredSlot(defer_at_turn=0, recheck_after_n_slots=2)
        s.current_slot = "1.2"
        # Slot 1.2 đã fill xong (REQUIRED address)
        profile = DealerProfileRaw(address="Hà Nội")

        # Tăng turn_count → mood ok, re-check
        s.turn_count = 3  # gap = 3 >= 2 → re-check
        next_slot, action = decide_action(s, Intent.NORMAL, None, profile=profile)
        # Re-check trigger → return slot 1.1 với RETRY
        assert next_slot == "1.1"
        assert action == Action.RETRY
        assert "1.1" not in s.deferred_slots  # cleared

    def test_recheck_deferred_NOT_trigger_if_current_slot_unfilled(self):
        """Phase 6 R+ fix BUG E: current slot chưa fill → KHÔNG re-check deferred.

        Dealer đang dở slot 2.2 mà bot lờ đi để quay slot 1.3 deferred → SAI.
        """
        from app.models.schema import DealerProfileRaw, DeferredSlot
        s = create_session()
        # Defer slot 1.3 ở turn 0
        s.deferred_slots["1.3"] = DeferredSlot(defer_at_turn=0, recheck_after_n_slots=2)
        # Đang dở slot 2.2 (REQUIRED business_model_signal chưa fill)
        s.current_slot = "2.2"
        s.turn_count = 3  # gap đủ re-check
        profile = DealerProfileRaw()  # business_model_signal=None

        next_slot, action = decide_action(s, Intent.NORMAL, None, profile=profile)
        # KHÔNG re-check 1.3 — phải xử slot 2.2 trước
        assert "1.3" in s.deferred_slots  # KHÔNG cleared
        assert next_slot != "1.3"


# ============================================================
# SKIP — REQUIRED hết total
# ============================================================


class TestSkipRequired:
    def test_skip_after_3_total_attempts(self):
        """Slot REQUIRED hết MAX_RETRY_TOTAL (3) → SKIP + flag required_missing."""
        s = create_session()
        s.current_slot = "1.1"
        # Simulate đã retry 2 lần (consecutive=2 → DEFER lần đầu)
        from app.models.schema import SlotAttempts
        s.slot_attempts["1.1"] = SlotAttempts(consecutive=0, total=2)
        # Lần 3 retry → total=3 → SKIP
        next_slot, action = decide_action(s, Intent.NORMAL, None)
        assert action == Action.SKIP
        assert "1.1" in s.skipped_slots
        assert Flag.REQUIRED_MISSING in s.flags
        assert next_slot == "1.2"


# ============================================================
# SKIP — OPTIONAL
# ============================================================


class TestSkipOptional:
    def test_optional_skip_immediately_on_khong_biet(self):
        """OPTIONAL + intent=KHONG_BIET → SKIP NGAY + flag dealer_declined."""
        s = create_session()
        s.current_slot = "2.3"  # OPTIONAL
        next_slot, action = decide_action(s, Intent.KHONG_BIET, None)
        # Note: KHONG_BIET không match REFUSAL path. Slot 2.3 empty extracted
        # → vào _handle_optional_skip
        assert action == Action.SKIP
        assert "2.3" in s.skipped_slots
        assert Flag.DEALER_DECLINED in s.flags

    def test_optional_skip_on_refusal(self):
        """OPTIONAL + REFUSAL → SKIP."""
        s = create_session()
        s.current_slot = "3.1"  # OPTIONAL
        next_slot, action = decide_action(s, Intent.REFUSAL, None)
        assert action == Action.SKIP
        assert "3.1" in s.skipped_slots

    def test_optional_no_retry_no_defer(self):
        """OPTIONAL không retry, không defer — SKIP ngay 1 phát."""
        s = create_session()
        s.current_slot = "2.4"  # OPTIONAL
        next_slot, action = decide_action(s, Intent.NORMAL, None)
        assert action == Action.SKIP
        # Không count attempts cho OPTIONAL
        assert "2.4" not in s.slot_attempts or s.slot_attempts["2.4"].total == 0


# ============================================================
# PARTIAL_RETRY — multi-field slot
# ============================================================


class TestPartialRetry:
    def test_partial_fill_slot_1_1(self):
        """Slot 1.1 fill 1/2 field → PARTIAL_RETRY (KHÔNG count attempts)."""
        s = create_session()
        s.current_slot = "1.1"
        extracted = {"owner_name": "Tùng"}  # thiếu dealer_name
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.PARTIAL_RETRY
        assert next_slot == "1.1"
        # KHÔNG count attempts
        assert "1.1" not in s.slot_attempts or s.slot_attempts["1.1"].total == 0

    def test_partial_fill_dealer_name_only(self):
        s = create_session()
        s.current_slot = "1.1"
        extracted = {"dealer_name": "Nhôm Kính Thanh Tùng"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.PARTIAL_RETRY

    def test_full_fill_no_partial(self):
        """Full fill 2/2 → ADVANCE, không PARTIAL_RETRY."""
        s = create_session()
        s.current_slot = "1.1"
        extracted = {"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.ADVANCE

    # Phase 5 R3 Gap 11: OPTIONAL multi-field PARTIAL
    def test_partial_fill_optional_slot_2_4(self):
        """Slot 2.4 (OPTIONAL multi-field 3 fields) fill 1/3 → PARTIAL_RETRY."""
        s = create_session()
        s.current_slot = "2.4"
        extracted = {"supplier_brands": ["Xingfa"]}  # thiếu segment + backup
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.PARTIAL_RETRY
        assert next_slot == "2.4"
        assert "2.4" in s.partial_retried_slots

    def test_partial_fill_slot_3_3_one_field(self):
        """Slot 3.3 (3 OPTIONAL fields: customer_pain + motivation + usp) fill 1/3."""
        s = create_session()
        s.current_slot = "3.3"
        extracted = {"customer_pain": "khó nhớ khách cũ"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.PARTIAL_RETRY
        assert "3.3" in s.partial_retried_slots

    def test_partial_optional_only_fires_once(self):
        """ADVERSARIAL: PARTIAL OPTIONAL chỉ fire 1 lần (tránh loop)."""
        s = create_session()
        s.current_slot = "2.4"
        # Lần 1: PARTIAL fire
        extracted = {"supplier_brands": ["Xingfa"]}
        _, action1 = decide_action(s, Intent.NORMAL, extracted)
        assert action1 == Action.PARTIAL_RETRY

        # Lần 2: cùng slot, dealer KHÔNG add → PARTIAL không fire lại
        extracted2 = {"supplier_brands": ["Xingfa"]}  # vẫn 1 field
        _, action2 = decide_action(s, Intent.NORMAL, extracted2)
        # Sau khi đã PARTIAL 1 lần, không quay lại PARTIAL — phải ADVANCE/SKIP/RETRY
        assert action2 != Action.PARTIAL_RETRY

    def test_partial_optional_all_fields_filled_no_partial(self):
        """Full fill 3/3 OPTIONAL → ADVANCE, không PARTIAL."""
        s = create_session()
        s.current_slot = "2.4"
        extracted = {
            "supplier_brands": ["Xingfa"],
            "customer_segment_signal": "nhà dân",
            "supplier_negotiation_signal": "có 2 NPP backup",
        }
        _, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.ADVANCE


# ============================================================
# PAUSE — defensive / tâm sự
# ============================================================


class TestPause:
    def test_pause_on_defensive(self):
        s = create_session()
        s.current_slot = "1.1"
        next_slot, action = decide_action(s, Intent.DEFENSIVE, None)
        assert action == Action.PAUSE
        assert next_slot == "1.1"  # stay
        assert s.paused_for == "defensive"

    def test_pause_on_tam_su(self):
        s = create_session()
        s.current_slot = "2.3"
        next_slot, action = decide_action(s, Intent.TAM_SU, None)
        assert action == Action.PAUSE
        assert s.paused_for == "tam_su"

    def test_pause_resets_on_normal(self):
        """Sau pause, intent thường → paused_for reset."""
        s = create_session()
        s.current_slot = "1.1"
        s.paused_for = "defensive"
        extracted = {"owner_name": "Tùng", "dealer_name": "X"}
        decide_action(s, Intent.NORMAL, extracted)
        assert s.paused_for is None


# ============================================================
# Slot 4.0 consent=no — D10 STRATEGY
# ============================================================


class TestConsentNo:
    def test_consent_no_skips_4_1_4_2(self):
        """Slot 4.0 + brandkit_consent=no → skip 4.1, 4.2 + đi CONFIRMING."""
        s = create_session()
        s.current_slot = "4.0"
        extracted = {"brandkit_consent": "no"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.ADVANCE
        assert next_slot is None  # → CONFIRMING
        assert "4.1" in s.skipped_slots
        assert "4.2" in s.skipped_slots

    def test_consent_yes_normal_advance(self):
        """Slot 4.0 + consent=yes → ADVANCE bình thường tới 4.1."""
        s = create_session()
        s.current_slot = "4.0"
        extracted = {"brandkit_consent": "yes"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.ADVANCE
        assert next_slot == "4.1"
        assert "4.1" not in s.skipped_slots


# ============================================================
# Phase 6 R1 — Slot 4.1 THÔNG BÁO + Slot 4.2 OPTIONAL flow
# ============================================================


class TestSlot41ThongBao:
    def test_4_1_advances_on_affirmative(self):
        """Slot 4.1 THÔNG BÁO + AFFIRMATIVE → ADVANCE 4.2."""
        s = create_session()
        s.current_slot = "4.1"
        next_slot, action = decide_action(s, Intent.AFFIRMATIVE, None)
        assert action == Action.ADVANCE
        assert next_slot == "4.2"

    def test_4_1_advances_on_normal(self):
        """Slot 4.1 + NORMAL (dealer ack tự do) → ADVANCE 4.2."""
        s = create_session()
        s.current_slot = "4.1"
        next_slot, action = decide_action(s, Intent.NORMAL, None)
        assert action == Action.ADVANCE
        assert next_slot == "4.2"

    def test_4_1_no_extractor_no_partial_loop(self):
        """ADVERSARIAL: slot 4.1 no field — extracted={} → vẫn advance, không loop PARTIAL."""
        s = create_session()
        s.current_slot = "4.1"
        next_slot, action = decide_action(s, Intent.NORMAL, {})
        assert action == Action.ADVANCE
        assert next_slot == "4.2"


class TestSlot42Optional:
    def test_4_2_color_filled_advances_to_confirming(self):
        """Slot 4.2 fill color_accent → ADVANCE → next_slot=None (CONFIRMING)."""
        s = create_session()
        s.current_slot = "4.2"
        extracted = {"color_accent": "xanh dương"}
        next_slot, action = decide_action(s, Intent.NORMAL, extracted)
        assert action == Action.ADVANCE
        assert next_slot is None  # Cuối cùng → CONFIRMING

    def test_4_2_skip_on_dealer_declined(self):
        """Slot 4.2 OPTIONAL + dealer không quan tâm → SKIP advance."""
        s = create_session()
        s.current_slot = "4.2"
        # Optional slot fills with empty extracted → SKIP after first try
        next_slot, action = decide_action(s, Intent.NORMAL, None)
        # OPTIONAL fallback → SKIP/ADVANCE (cuối → CONFIRMING)
        assert action in (Action.SKIP, Action.ADVANCE)


# ============================================================
# Config constants
# ============================================================


class TestConfigConstants:
    def test_max_retry_total_is_3(self):
        """D11 STRATEGY: MAX_RETRY_TOTAL = 3."""
        assert MAX_RETRY_TOTAL == 3

    def test_max_retry_consecutive_is_2(self):
        """D11 STRATEGY: MAX_RETRY_CONSECUTIVE = 2."""
        assert MAX_RETRY_CONSECUTIVE == 2

    def test_max_defer_per_slot_is_1(self):
        """1 slot defer max 1 lần."""
        assert MAX_DEFER_PER_SLOT == 1
