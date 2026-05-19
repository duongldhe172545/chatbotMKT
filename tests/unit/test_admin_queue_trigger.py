"""Test admin queue trigger logic — F2C.8."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.admin.queue import (
    QUEUE_TRIGGER_RULES,
    get_priority_for_flag,
    increment_flag_count,
    trigger_queue_if_needed,
)
from app.core.session import create_session
from app.models.enums import Flag, Priority
from app.models.schema import DealerProfileRaw


def _make_store_mock():
    """Mock SQLiteStore.push_admin_queue."""
    store = MagicMock()
    store.push_admin_queue = MagicMock()
    return store


# ============================================================
# increment_flag_count
# ============================================================


class TestIncrementFlagCount:
    def test_first_increment_returns_1(self):
        s = create_session()
        count = increment_flag_count(s, Flag.PROMPT_INJECTION)
        assert count == 1
        assert s.flag_counts["prompt_injection"] == 1
        assert Flag.PROMPT_INJECTION in s.flags

    def test_multiple_increments(self):
        s = create_session()
        increment_flag_count(s, Flag.HALLUCINATE)
        increment_flag_count(s, Flag.HALLUCINATE)
        count = increment_flag_count(s, Flag.HALLUCINATE)
        assert count == 3
        assert s.flag_counts["hallucinate"] == 3
        # flags list không duplicate
        assert s.flags.count(Flag.HALLUCINATE) == 1

    def test_different_flags_separate_counts(self):
        s = create_session()
        increment_flag_count(s, Flag.PROMPT_INJECTION)
        increment_flag_count(s, Flag.PROMPT_INJECTION)
        increment_flag_count(s, Flag.HALLUCINATE)
        assert s.flag_counts["prompt_injection"] == 2
        assert s.flag_counts["hallucinate"] == 1


# ============================================================
# trigger_queue_if_needed
# ============================================================


class TestTriggerQueue:
    def test_no_flag_no_trigger(self):
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()
        fired = trigger_queue_if_needed(s, p, store)
        assert fired == []
        store.push_admin_queue.assert_not_called()

    def test_required_missing_single_shot_high_priority(self):
        """REQUIRED_MISSING single-shot → MEDIUM (refer F2C.8)."""
        s = create_session()
        p = DealerProfileRaw()
        increment_flag_count(s, Flag.REQUIRED_MISSING)
        store = _make_store_mock()
        fired = trigger_queue_if_needed(s, p, store)
        assert "required_missing" in fired
        store.push_admin_queue.assert_called_once()
        entry = store.push_admin_queue.call_args[0][0]
        assert entry.priority == Priority.MEDIUM
        assert entry.trigger == Flag.REQUIRED_MISSING

    def test_prompt_injection_needs_3_count(self):
        """prompt_injection threshold = 3 (refer F2C.8)."""
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()

        # 1 inject — chưa trigger
        increment_flag_count(s, Flag.PROMPT_INJECTION)
        assert trigger_queue_if_needed(s, p, store) == []

        # 2 inject — vẫn chưa
        increment_flag_count(s, Flag.PROMPT_INJECTION)
        assert trigger_queue_if_needed(s, p, store) == []

        # 3 inject — trigger
        increment_flag_count(s, Flag.PROMPT_INJECTION)
        fired = trigger_queue_if_needed(s, p, store)
        assert "prompt_injection" in fired
        entry = store.push_admin_queue.call_args[0][0]
        assert entry.priority == Priority.HIGH

    def test_hallucinate_threshold_2(self):
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()
        increment_flag_count(s, Flag.HALLUCINATE)
        # 1 hallucinate → chưa
        assert trigger_queue_if_needed(s, p, store) == []
        increment_flag_count(s, Flag.HALLUCINATE)
        # 2 hallucinate → trigger
        fired = trigger_queue_if_needed(s, p, store)
        assert "hallucinate" in fired

    def test_no_duplicate_trigger(self):
        """Trigger 1 lần, sau dù count tăng cũng không push lại."""
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()
        increment_flag_count(s, Flag.REQUIRED_MISSING)

        fired1 = trigger_queue_if_needed(s, p, store)
        assert fired1 == ["required_missing"]
        assert store.push_admin_queue.call_count == 1

        # Lần 2 — không trigger nữa
        increment_flag_count(s, Flag.REQUIRED_MISSING)
        fired2 = trigger_queue_if_needed(s, p, store)
        assert fired2 == []
        assert store.push_admin_queue.call_count == 1

    def test_multiple_triggers_in_one_call(self):
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()
        increment_flag_count(s, Flag.SANITY_CHECK_FAILED)
        increment_flag_count(s, Flag.REQUIRED_MISSING)
        increment_flag_count(s, Flag.PII_LEAK)
        fired = trigger_queue_if_needed(s, p, store)
        assert set(fired) == {"sanity_check_failed", "required_missing", "pii_leak"}
        assert store.push_admin_queue.call_count == 3

    def test_garbage_input_does_not_trigger(self):
        """garbage_input KHÔNG trigger queue (refer F2C.8 note)."""
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()
        increment_flag_count(s, Flag.GARBAGE_INPUT)
        fired = trigger_queue_if_needed(s, p, store)
        assert fired == []
        store.push_admin_queue.assert_not_called()

    def test_dealer_too_defensive_does_not_trigger(self):
        s = create_session()
        p = DealerProfileRaw()
        store = _make_store_mock()
        increment_flag_count(s, Flag.DEALER_TOO_DEFENSIVE)
        fired = trigger_queue_if_needed(s, p, store)
        assert fired == []

    def test_store_exception_doesnt_raise(self):
        """Push fail → log + tiếp tục, không crash conversation."""
        s = create_session()
        p = DealerProfileRaw()
        store = MagicMock()
        store.push_admin_queue = MagicMock(side_effect=RuntimeError("DB down"))
        increment_flag_count(s, Flag.REQUIRED_MISSING)
        # KHÔNG raise
        fired = trigger_queue_if_needed(s, p, store)
        # Vẫn mark là fired (tránh retry infinite)
        assert "required_missing" in fired

    def test_profile_snapshot_captured(self):
        s = create_session()
        p = DealerProfileRaw(owner_name="Tùng", dealer_name="Nhôm Kính")
        store = _make_store_mock()
        increment_flag_count(s, Flag.SANITY_CHECK_FAILED)
        trigger_queue_if_needed(s, p, store)
        entry = store.push_admin_queue.call_args[0][0]
        assert entry.profile_snapshot is not None
        assert entry.profile_snapshot.owner_name == "Tùng"
        # Snapshot là copy — sửa profile sau không ảnh hưởng snapshot
        p.owner_name = "CHANGED"
        assert entry.profile_snapshot.owner_name == "Tùng"


# ============================================================
# QUEUE_TRIGGER_RULES integrity
# ============================================================


class TestRules:
    def test_rules_count(self):
        """13 rule theo F2C.8."""
        # 7 HIGH + 4 MEDIUM + 2 LOW = 13
        assert len(QUEUE_TRIGGER_RULES) == 13

    def test_priority_distribution(self):
        by_priority = {p: 0 for p in Priority}
        for rule in QUEUE_TRIGGER_RULES:
            by_priority[rule.priority] += 1
        assert by_priority[Priority.HIGH] == 7
        assert by_priority[Priority.MEDIUM] == 4
        assert by_priority[Priority.LOW] == 2

    def test_get_priority_for_flag(self):
        assert get_priority_for_flag(Flag.REQUIRED_MISSING) == Priority.MEDIUM
        assert get_priority_for_flag(Flag.HALLUCINATE) == Priority.HIGH
        assert get_priority_for_flag(Flag.VOICE_QUALITY_POOR) == Priority.LOW
        assert get_priority_for_flag(Flag.GARBAGE_INPUT) is None
