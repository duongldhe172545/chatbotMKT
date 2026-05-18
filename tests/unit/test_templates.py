"""Test slot Q&A templates. Refer 1A § 4 + D9 STRATEGY (Phase 1 cut 3 REQUIRED)."""
from __future__ import annotations

import pytest

from app.slots.definitions import REQUIRED_SLOTS, SLOT_PRIORITY_ORDER
from app.slots.templates import (
    SlotTemplate,
    get_question,
    get_retry_question,
    get_template,
    is_phase_1_ready,
)


# ============================================================
# Phase 1 — 3 slot REQUIRED đầy đủ
# ============================================================


class TestPhase1Templates:
    @pytest.mark.parametrize("slot_id", ["1.1", "1.2", "4.0"])
    def test_phase_1_slot_has_3_questions(self, slot_id):
        """Phase 1 slot phải có 3 biến thể câu hỏi gốc."""
        tpl = get_template(slot_id)
        assert tpl is not None, f"Slot {slot_id} missing template"
        assert len(tpl.questions) == 3, \
            f"Slot {slot_id} phải có 3 biến thể, hiện {len(tpl.questions)}"

    @pytest.mark.parametrize("slot_id", ["1.1", "1.2", "4.0"])
    def test_phase_1_slot_has_2_retry_questions(self, slot_id):
        """Phase 1 REQUIRED slot phải có 2 retry question (lượt 2 + lượt 3)."""
        tpl = get_template(slot_id)
        assert len(tpl.retry_questions) == 2, \
            f"Slot {slot_id} phải có 2 retry, hiện {len(tpl.retry_questions)}"

    @pytest.mark.parametrize("slot_id", ["1.1", "1.2", "4.0"])
    def test_phase_1_marked_ready(self, slot_id):
        assert is_phase_1_ready(slot_id) is True

    @pytest.mark.parametrize("slot_id", ["1.3", "2.1", "2.2", "2.3", "3.5", "4.1", "4.2"])
    def test_other_slots_not_phase_1(self, slot_id):
        """Slot non-Phase-1 chưa marked ready."""
        assert is_phase_1_ready(slot_id) is False


# ============================================================
# All 17 slot có template
# ============================================================


class TestAllSlotsHaveTemplate:
    @pytest.mark.parametrize("slot_id", SLOT_PRIORITY_ORDER)
    def test_each_slot_has_template(self, slot_id):
        """Mọi slot trong SLOT_PRIORITY_ORDER phải có template (đầy đủ hoặc stub)."""
        tpl = get_template(slot_id)
        assert tpl is not None, f"Slot {slot_id} missing template"
        assert tpl.slot_id == slot_id

    @pytest.mark.parametrize("slot_id", SLOT_PRIORITY_ORDER)
    def test_each_slot_has_at_least_1_question(self, slot_id):
        tpl = get_template(slot_id)
        assert len(tpl.questions) >= 1


# ============================================================
# get_question helper
# ============================================================


class TestGetQuestion:
    def test_get_default_variant(self):
        q = get_question("1.1", variant=0)
        assert q is not None
        assert len(q) > 10
        assert "tên" in q.lower()

    def test_variant_rotation(self):
        """3 biến thể khác nhau."""
        q0 = get_question("1.1", variant=0)
        q1 = get_question("1.1", variant=1)
        q2 = get_question("1.1", variant=2)
        assert q0 != q1
        assert q1 != q2
        assert q0 != q2

    def test_variant_overflow_mods(self):
        """variant > 2 → mod 3."""
        q0 = get_question("1.1", variant=0)
        q3 = get_question("1.1", variant=3)  # = variant 0
        assert q0 == q3

    def test_invalid_slot_returns_none(self):
        assert get_question("99.99", variant=0) is None


# ============================================================
# get_retry_question helper
# ============================================================


class TestGetRetryQuestion:
    def test_attempt_1_returns_original(self):
        """attempt=1 trả về câu hỏi gốc (biến thể 0)."""
        q1 = get_retry_question("1.1", attempt=1)
        q_original = get_question("1.1", variant=0)
        assert q1 == q_original

    def test_attempt_2_returns_first_retry(self):
        """attempt=2 — tone nhẹ + giải thích."""
        q2 = get_retry_question("1.1", attempt=2)
        assert q2 is not None
        # Lượt 2 thường có cụm 'em chỉ lưu' hoặc 'xin tên để'
        assert q2 != get_question("1.1", variant=0)

    def test_attempt_3_returns_second_retry(self):
        """attempt=3 — tha thiết + offer fallback (sau DEFER re-check)."""
        q3 = get_retry_question("1.1", attempt=3)
        assert q3 is not None
        assert q3 != get_retry_question("1.1", attempt=2)

    def test_attempt_4_returns_none(self):
        """Sau 3 lượt → SKIP, không có retry."""
        q4 = get_retry_question("1.1", attempt=4)
        assert q4 is None

    def test_optional_slot_only_attempt_1(self):
        """Slot non-Phase-1 chỉ có question gốc, không retry detail."""
        q1 = get_retry_question("1.3", attempt=1)
        assert q1 is not None
        q2 = get_retry_question("1.3", attempt=2)
        assert q2 is None  # chưa có retry_questions cho stub


# ============================================================
# Vocab check — Việt hóa, không lộ Tier/C-score
# ============================================================


class TestVocabCompliance:
    @pytest.mark.parametrize("slot_id", ["1.1", "1.2", "4.0"])
    def test_no_forbidden_vocab_in_questions(self, slot_id):
        """Refer GLOSSARY § 6 + F2B.8 G3: cấm Tier/C-score/BRANDKIT/etc."""
        forbidden = ["Tier", "C-score", "Scoring", "chấm điểm",
                     "BRANDKIT", "Profile", "Namecard", "Slogan",
                     "Mini App", "Marketing", "evaluation", "ranking"]
        tpl = get_template(slot_id)
        for q in tpl.questions:
            for word in forbidden:
                assert word not in q, \
                    f"Slot {slot_id} câu '{q[:50]}...' chứa vocab cấm '{word}'"
        for q in tpl.retry_questions:
            for word in forbidden:
                assert word not in q, \
                    f"Slot {slot_id} retry chứa vocab cấm '{word}'"

    @pytest.mark.parametrize("slot_id", ["1.1", "1.2", "4.0"])
    def test_slot_4_0_mentions_zalo(self, slot_id):
        """Slot 4.0: bot phải nói 'qua Zalo' (CORE § A.3 + 1A § 3.2)."""
        if slot_id != "4.0":
            return
        tpl = get_template(slot_id)
        for q in tpl.questions:
            # Phải có "qua Zalo" hoặc "Zalo" — bot không render trực tiếp
            assert "Zalo" in q, f"Slot 4.0 câu phải mention Zalo: {q[:80]}"
