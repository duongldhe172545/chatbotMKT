"""Test abuse detector — refer 1C § 5 + § 10. Adversarial test."""
from __future__ import annotations

import pytest

from app.admin.queue import increment_flag_count
from app.core.abuse_detector import (
    ABUSE_L1_TEMPLATE,
    ABUSE_L2_TEMPLATE,
    ABUSE_L3_TEMPLATE,
    ADDRESS_BL_L1_TEMPLATE,
    ADDRESS_BL_L2_TEMPLATE,
    ADDRESS_BL_L3_TEMPLATE,
    handle_abuse_escalation,
    handle_address_blacklist_escalation,
    is_personal_abuse,
)
from app.core.session import create_session
from app.models.enums import Flag


# ============================================================
# is_personal_abuse — regex detect
# ============================================================


class TestIsPersonalAbuse:
    @pytest.mark.parametrize("msg", [
        "đm con bot này",
        "ĐM BOT NÀY NGU",
        "bot ngu vl",
        "em ngu vcl",
        "đồ máy",
        "câm mồm đi",
        "im đi",
        "biến đi",
        "con bot",
        "đéo bot ạ",
    ])
    def test_abuse_detected(self, msg):
        assert is_personal_abuse(msg) is True, f"Should detect: {msg!r}"

    @pytest.mark.parametrize("msg", [
        # ADVERSARIAL: chửi chung (Lửa Lò) — KHÔNG phải abuse cá nhân
        "đm em hỏi nhiều thế",   # generic profanity, không nhằm bot
        "vl ngày dài",
        "đéo có thời gian",
        # Normal answer
        "anh tên Tùng",
        "ok em làm đi",
        "không cho",
        "0912345678",
        # Defensive (không phải abuse)
        "em là ai? bot à?",
        "lừa đảo à?",
    ])
    def test_normal_or_general_profanity_not_personal_abuse(self, msg):
        assert is_personal_abuse(msg) is False, f"Should NOT detect: {msg!r}"

    def test_none_input(self):
        assert is_personal_abuse(None) is False
        assert is_personal_abuse("") is False


# ============================================================
# Abuse escalation 3 cấp
# ============================================================


class TestAbuseEscalation:
    def test_l1_first_abuse(self):
        s = create_session()
        increment_flag_count(s, Flag.ABUSIVE_LANGUAGE)  # count=1
        reply, should_close = handle_abuse_escalation(s)
        assert reply == ABUSE_L1_TEMPLATE
        assert should_close is False
        assert Flag.ESCALATION not in s.flags

    def test_l2_second_abuse(self):
        s = create_session()
        increment_flag_count(s, Flag.ABUSIVE_LANGUAGE)
        increment_flag_count(s, Flag.ABUSIVE_LANGUAGE)  # count=2
        reply, should_close = handle_abuse_escalation(s)
        assert reply == ABUSE_L2_TEMPLATE
        assert should_close is False
        assert Flag.ESCALATION not in s.flags

    def test_l3_third_abuse_triggers_escalation(self):
        s = create_session()
        for _ in range(3):
            increment_flag_count(s, Flag.ABUSIVE_LANGUAGE)
        reply, should_close = handle_abuse_escalation(s)
        assert reply == ABUSE_L3_TEMPLATE
        assert should_close is True
        assert Flag.ESCALATION in s.flags

    def test_l3_idempotent_4th_call(self):
        """ADVERSARIAL: dealer abuse 4 lần → vẫn L3."""
        s = create_session()
        for _ in range(4):
            increment_flag_count(s, Flag.ABUSIVE_LANGUAGE)
        reply, should_close = handle_abuse_escalation(s)
        assert reply == ABUSE_L3_TEMPLATE
        assert should_close is True

    def test_zero_count_returns_l1_safe(self):
        """EDGE: gọi mà chưa increment → trả L1 (safe default)."""
        s = create_session()
        reply, should_close = handle_abuse_escalation(s)
        assert reply == ABUSE_L1_TEMPLATE
        assert should_close is False


# ============================================================
# Address blacklist escalation 3 cấp
# ============================================================


class TestAddressBlacklistEscalation:
    def test_l1(self):
        s = create_session()
        increment_flag_count(s, Flag.ADDRESS_BLACKLIST)
        reply, should_close = handle_address_blacklist_escalation(s)
        assert reply == ADDRESS_BL_L1_TEMPLATE
        assert should_close is False

    def test_l2(self):
        s = create_session()
        for _ in range(2):
            increment_flag_count(s, Flag.ADDRESS_BLACKLIST)
        reply, should_close = handle_address_blacklist_escalation(s)
        assert reply == ADDRESS_BL_L2_TEMPLATE
        assert should_close is False

    def test_l3_triggers_escalation(self):
        s = create_session()
        for _ in range(3):
            increment_flag_count(s, Flag.ADDRESS_BLACKLIST)
        reply, should_close = handle_address_blacklist_escalation(s)
        assert reply == ADDRESS_BL_L3_TEMPLATE
        assert should_close is True
        assert Flag.ESCALATION in s.flags
