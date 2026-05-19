"""Test edge case handlers — Phase 3 R4. Refer File 1C § 2/4/5/12/13.

Test PHẢI cover adversarial path (memory feedback_test_adversarial):
- Happy: 1 lần defensive → trả L1
- Adversarial: 3 lần defensive → escalation L3 + close. 4 lần → vẫn L3 (idempotent).
"""
from __future__ import annotations

import pytest

from app.core.edge_cases import (
    DEFENSIVE_L1_TEMPLATE,
    DEFENSIVE_L2_TEMPLATE,
    DEFENSIVE_L3_TEMPLATE,
    OPTIONAL_REFUSAL_THRESHOLD,
    PHONE_RETRY_THRESHOLD,
    check_phone_retry_exhausted,
    handle_defensive_escalation,
    is_session_escalated,
    raise_escalation,
    record_optional_refusal,
    reset_optional_refusal,
    should_skip_in_rush_mode,
    enter_rush_mode,
)
from app.admin.queue import increment_flag_count
from app.core.session import create_session
from app.models.enums import Flag
from app.models.schema import SlotAttempts


# ============================================================
# 1. Defensive escalation 3 cấp
# ============================================================


class TestDefensiveEscalation:
    def test_l1_first_defensive(self):
        """Lần 1 defensive → L1 template, không close."""
        s = create_session()
        increment_flag_count(s, Flag.DEALER_TOO_DEFENSIVE)  # count=1
        reply, should_close = handle_defensive_escalation(s)
        assert reply == DEFENSIVE_L1_TEMPLATE
        assert should_close is False
        # Chưa escalation
        assert Flag.ESCALATION not in s.flags

    def test_l2_second_defensive(self):
        s = create_session()
        increment_flag_count(s, Flag.DEALER_TOO_DEFENSIVE)
        increment_flag_count(s, Flag.DEALER_TOO_DEFENSIVE)  # count=2
        reply, should_close = handle_defensive_escalation(s)
        assert reply == DEFENSIVE_L2_TEMPLATE
        assert should_close is False
        assert Flag.ESCALATION not in s.flags

    def test_l3_third_defensive_triggers_escalation(self):
        s = create_session()
        for _ in range(3):
            increment_flag_count(s, Flag.DEALER_TOO_DEFENSIVE)  # count=3
        reply, should_close = handle_defensive_escalation(s)
        assert reply == DEFENSIVE_L3_TEMPLATE
        assert should_close is True
        assert Flag.ESCALATION in s.flags
        # ESCALATION counter = 1
        assert s.flag_counts.get(Flag.ESCALATION.value) == 1

    def test_l3_idempotent_after_4th_call(self):
        """ADVERSARIAL: dealer tiếp tục defensive sau L3 → vẫn L3 template."""
        s = create_session()
        for _ in range(4):
            increment_flag_count(s, Flag.DEALER_TOO_DEFENSIVE)  # count=4
        reply, should_close = handle_defensive_escalation(s)
        assert reply == DEFENSIVE_L3_TEMPLATE
        assert should_close is True
        # ESCALATION đã raise 1 lần ở turn count=3 (test khác); ở đây
        # count=4 cũng raise lại — caller chịu trách nhiệm idempotent
        assert Flag.ESCALATION in s.flags

    def test_zero_count_returns_l1(self):
        """EDGE: count=0 (chưa increment) → vẫn trả L1 (safe default)."""
        s = create_session()
        reply, should_close = handle_defensive_escalation(s)
        assert reply == DEFENSIVE_L1_TEMPLATE
        assert should_close is False


class TestRaiseEscalation:
    def test_raise_adds_flag_and_increments(self):
        s = create_session()
        raise_escalation(s, reason="test")
        assert Flag.ESCALATION in s.flags
        assert s.flag_counts[Flag.ESCALATION.value] == 1

    def test_raise_multiple_times_increments_count(self):
        """ADVERSARIAL: raise nhiều lần → count tăng (caller check idempotent)."""
        s = create_session()
        raise_escalation(s, reason="r1")
        raise_escalation(s, reason="r2")
        # flag không duplicate
        assert s.flags.count(Flag.ESCALATION) == 1
        # count tăng
        assert s.flag_counts[Flag.ESCALATION.value] == 2

    def test_is_session_escalated(self):
        s = create_session()
        assert is_session_escalated(s) is False
        raise_escalation(s, reason="test")
        assert is_session_escalated(s) is True


# ============================================================
# 2. Optional refusal streak
# ============================================================


class TestOptionalRefusalStreak:
    def test_threshold_constant(self):
        assert OPTIONAL_REFUSAL_THRESHOLD == 3

    def test_below_threshold_no_flag(self):
        s = create_session()
        assert record_optional_refusal(s) is False
        assert record_optional_refusal(s) is False
        assert s.consecutive_optional_refusal == 2
        assert Flag.MULTIPLE_REFUSAL_IN_ROW not in s.flags

    def test_exactly_threshold_triggers_flag(self):
        s = create_session()
        record_optional_refusal(s)
        record_optional_refusal(s)
        triggered = record_optional_refusal(s)  # 3rd
        assert triggered is True
        assert Flag.MULTIPLE_REFUSAL_IN_ROW in s.flags
        assert s.consecutive_optional_refusal == 3

    def test_4th_refusal_not_re_trigger(self):
        """ADVERSARIAL: sau khi đã trigger (3), refuse tiếp → không re-trigger."""
        s = create_session()
        for _ in range(3):
            record_optional_refusal(s)
        # 4th refuse
        result = record_optional_refusal(s)
        # Flag đã có rồi → không re-raise (return False)
        assert result is False
        assert s.consecutive_optional_refusal == 4

    def test_reset_clears_counter_not_flag(self):
        """ADVERSARIAL: dealer answer → reset counter, NHƯNG flag đã raise vẫn giữ."""
        s = create_session()
        for _ in range(3):
            record_optional_refusal(s)
        assert Flag.MULTIPLE_REFUSAL_IN_ROW in s.flags
        reset_optional_refusal(s)
        assert s.consecutive_optional_refusal == 0
        # Flag KHÔNG bị xóa (admin queue đã trigger)
        assert Flag.MULTIPLE_REFUSAL_IN_ROW in s.flags

    def test_alternating_refuse_advance_doesnt_reach_threshold(self):
        """ADVERSARIAL: dealer refuse → answer → refuse → answer → ... không trigger
        (counter reset mỗi lần advance)."""
        s = create_session()
        record_optional_refusal(s)  # 1
        reset_optional_refusal(s)
        record_optional_refusal(s)  # 1 (vì đã reset)
        reset_optional_refusal(s)
        triggered = record_optional_refusal(s)  # 1 again
        assert triggered is False
        assert Flag.MULTIPLE_REFUSAL_IN_ROW not in s.flags


class TestRushMode:
    def test_should_skip_when_rush_mode_off(self):
        s = create_session()
        assert should_skip_in_rush_mode(s, "2.3") is False
        assert should_skip_in_rush_mode(s, "1.1") is False

    def test_rush_mode_skips_optional_only(self):
        s = create_session()
        enter_rush_mode(s)
        # OPTIONAL (2.3, 3.1) → skip
        assert should_skip_in_rush_mode(s, "2.3") is True
        assert should_skip_in_rush_mode(s, "3.1") is True
        # REQUIRED (1.1, 4.0) → KHÔNG skip
        assert should_skip_in_rush_mode(s, "1.1") is False
        assert should_skip_in_rush_mode(s, "4.0") is False


# ============================================================
# 4. Phone retry exhausted
# ============================================================


class TestPhoneRetryExhausted:
    def test_threshold_constant(self):
        assert PHONE_RETRY_THRESHOLD == 3

    def test_below_threshold_no_flag(self):
        s = create_session()
        s.slot_attempts["1.3"] = SlotAttempts(total=2, consecutive=2)
        triggered = check_phone_retry_exhausted(s)
        assert triggered is False
        assert Flag.PHONE_INVALID_AFTER_RETRY not in s.flags

    def test_exactly_threshold_triggers_flag(self):
        s = create_session()
        s.slot_attempts["1.3"] = SlotAttempts(total=3, consecutive=3)
        triggered = check_phone_retry_exhausted(s)
        assert triggered is True
        assert Flag.PHONE_INVALID_AFTER_RETRY in s.flags

    def test_no_slot_attempts_returns_false(self):
        """EDGE: chưa retry slot 1.3 (vd dealer chưa tới slot này)."""
        s = create_session()
        triggered = check_phone_retry_exhausted(s)
        assert triggered is False

    def test_4th_retry_not_re_trigger(self):
        """ADVERSARIAL: state machine retry quá 3 lần (lỗi logic) → không re-flag."""
        s = create_session()
        s.slot_attempts["1.3"] = SlotAttempts(total=4, consecutive=4)
        check_phone_retry_exhausted(s)
        # Re-check
        result = check_phone_retry_exhausted(s)
        assert result is False
        # Flag chỉ raise 1 lần
        assert s.flags.count(Flag.PHONE_INVALID_AFTER_RETRY) == 1
        assert s.flag_counts[Flag.PHONE_INVALID_AFTER_RETRY.value] == 1
