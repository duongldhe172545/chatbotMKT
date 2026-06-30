"""Test 17 slot definitions + mappings. Refer F2A.5 + CORE § G.3 + D9 STRATEGY."""
from __future__ import annotations

import pytest

from app.slots.definitions import (
    MULTI_FIELD_SLOTS,
    OPTIONAL_SLOTS,
    PHASE_1_REQUIRED_SLOTS,
    REQUIRED_SLOTS,
    SLOT_PRIORITY_ORDER,
    SLOT_TO_ALL_FIELDS,
    SLOT_TO_REQUIRED_FIELDS,
    SLOTS,
    THONG_BAO_SLOTS,
    get_slot,
    is_multi_field,
    is_optional,
    is_required,
    is_thong_bao,
    next_slot,
)


class TestSlotConstants:
    def test_priority_order_has_17_slots(self):
        assert len(SLOT_PRIORITY_ORDER) == 17

    def test_priority_order_no_duplicate(self):
        assert len(set(SLOT_PRIORITY_ORDER)) == 17

    def test_required_has_6(self):
        """6 REQUIRED — refer F2A.5 + CORE § G.3 line 485."""
        assert len(REQUIRED_SLOTS) == 6
        assert set(REQUIRED_SLOTS) == {"1.1", "1.2", "1.3", "2.1", "2.2", "4.0"}

    def test_optional_has_10(self):
        """10 OPTIONAL — refer CORE § G.3 line 486."""
        assert len(OPTIONAL_SLOTS) == 10

    def test_thong_bao_has_1(self):
        """1 THÔNG BÁO — slot 4.1 (logo) — refer GLOSSARY § 1."""
        assert THONG_BAO_SLOTS == ["4.1"]

    def test_total_partition_equals_17(self):
        """6 + 10 + 1 = 17 — không overlap, không miss."""
        all_classified = (
            set(REQUIRED_SLOTS) | set(OPTIONAL_SLOTS) | set(THONG_BAO_SLOTS)
        )
        assert all_classified == set(SLOT_PRIORITY_ORDER)

    def test_no_overlap_between_categories(self):
        assert set(REQUIRED_SLOTS).isdisjoint(set(OPTIONAL_SLOTS))
        assert set(REQUIRED_SLOTS).isdisjoint(set(THONG_BAO_SLOTS))
        assert set(OPTIONAL_SLOTS).isdisjoint(set(THONG_BAO_SLOTS))

    def test_multi_field_has_7(self):
        """7 slot multi-field — refer 1A § 1.5 + F2A.4 step 2.6."""
        assert len(MULTI_FIELD_SLOTS) == 7
        assert set(MULTI_FIELD_SLOTS) == {
            "1.1", "1.2", "2.1", "2.4", "2.5", "2.6", "3.3"
        }

    def test_phase_1_required_has_3(self):
        """D9 STRATEGY: Phase 1 cut scope 3 REQUIRED (1.1, 1.2, 4.0)."""
        assert len(PHASE_1_REQUIRED_SLOTS) == 3
        assert set(PHASE_1_REQUIRED_SLOTS) == {"1.1", "1.2", "4.0"}

    def test_phase_1_subset_of_required(self):
        assert set(PHASE_1_REQUIRED_SLOTS).issubset(set(REQUIRED_SLOTS))


class TestSlotMappings:
    def test_required_fields_mapping_keys_match_required_slots(self):
        """SLOT_TO_REQUIRED_FIELDS có đúng 6 key = REQUIRED_SLOTS."""
        assert set(SLOT_TO_REQUIRED_FIELDS.keys()) == set(REQUIRED_SLOTS)

    def test_slot_1_1_requires_2_fields(self):
        """Slot 1.1 multi-field — 2 field bắt buộc owner + dealer."""
        assert SLOT_TO_REQUIRED_FIELDS["1.1"] == ["owner_name", "dealer_name"]

    def test_slot_2_1_only_main_product(self):
        """Slot 2.1: chỉ main_product (category_stack đã xoá — field rác 2026-06-22)."""
        assert SLOT_TO_REQUIRED_FIELDS["2.1"] == ["main_product"]
        assert SLOT_TO_ALL_FIELDS["2.1"] == ["main_product"]
        assert "category_stack" not in SLOT_TO_ALL_FIELDS["2.1"]

    def test_all_17_slots_have_all_fields_mapping(self):
        assert set(SLOT_TO_ALL_FIELDS.keys()) == set(SLOT_PRIORITY_ORDER)

    def test_thong_bao_slot_4_1_has_no_fields(self):
        """Slot 4.1 THÔNG BÁO — không fill field nào."""
        assert SLOT_TO_ALL_FIELDS["4.1"] == []

    def test_required_fields_subset_of_all_fields(self):
        """required_fields phải là subset của all_fields cho mỗi slot."""
        for slot_id, required in SLOT_TO_REQUIRED_FIELDS.items():
            all_f = SLOT_TO_ALL_FIELDS[slot_id]
            assert set(required).issubset(set(all_f)), \
                f"Slot {slot_id}: required {required} không trong all_fields {all_f}"


class TestSlotsDict:
    def test_has_17_entries(self):
        assert len(SLOTS) == 17

    def test_keys_match_priority_order(self):
        assert set(SLOTS.keys()) == set(SLOT_PRIORITY_ORDER)

    def test_each_slot_has_correct_kind(self):
        for slot_id, defn in SLOTS.items():
            if slot_id in REQUIRED_SLOTS:
                assert defn.kind == "REQUIRED", f"Slot {slot_id}"
            elif slot_id in OPTIONAL_SLOTS:
                assert defn.kind == "OPTIONAL", f"Slot {slot_id}"
            elif slot_id in THONG_BAO_SLOTS:
                assert defn.kind == "THONG_BAO", f"Slot {slot_id}"

    def test_thong_bao_has_no_extractor(self):
        """Slot 4.1 KHÔNG có extractor — refer batch 4 C-B3 + GLOSSARY § 1."""
        assert SLOTS["4.1"].has_extractor is False

    def test_16_slots_have_extractor(self):
        """16/17 slot có extractor (trừ 4.1 THÔNG BÁO) — refer C-B3."""
        with_extractor = [s for s in SLOTS.values() if s.has_extractor]
        assert len(with_extractor) == 16
        # Tất cả slot trừ 4.1
        without_4_1 = set(SLOT_PRIORITY_ORDER) - {"4.1"}
        with_extractor_ids = {s.slot_id for s in with_extractor}
        assert with_extractor_ids == without_4_1

    def test_multi_field_flag(self):
        """is_multi_field flag khớp MULTI_FIELD_SLOTS list."""
        for slot_id in MULTI_FIELD_SLOTS:
            assert SLOTS[slot_id].is_multi_field is True
        # Slot single-field
        for slot_id in ["1.3", "2.2", "2.3", "3.1", "3.2", "3.4", "3.5", "4.0", "4.1", "4.2"]:
            assert SLOTS[slot_id].is_multi_field is False

    def test_topic_correct(self):
        """topic = số đầu của slot_id."""
        for slot_id, defn in SLOTS.items():
            expected = int(slot_id.split(".")[0])
            assert defn.topic == expected


class TestHelpers:
    def test_get_slot_valid(self):
        s = get_slot("1.1")
        assert s.slot_id == "1.1"
        assert s.kind == "REQUIRED"

    def test_get_slot_invalid_raises_key_error(self):
        with pytest.raises(KeyError):
            get_slot("99.99")

    def test_is_required(self):
        for slot_id in REQUIRED_SLOTS:
            assert is_required(slot_id) is True
        for slot_id in OPTIONAL_SLOTS:
            assert is_required(slot_id) is False
        assert is_required("4.1") is False

    def test_is_optional(self):
        for slot_id in OPTIONAL_SLOTS:
            assert is_optional(slot_id) is True
        for slot_id in REQUIRED_SLOTS:
            assert is_optional(slot_id) is False

    def test_is_thong_bao(self):
        assert is_thong_bao("4.1") is True
        assert is_thong_bao("4.0") is False
        assert is_thong_bao("1.1") is False

    def test_is_multi_field(self):
        for slot_id in MULTI_FIELD_SLOTS:
            assert is_multi_field(slot_id) is True
        # Single-field
        assert is_multi_field("1.3") is False
        assert is_multi_field("4.1") is False


class TestNextSlot:
    def test_normal_advance(self):
        """next_slot trả slot kế tiếp trong SLOT_PRIORITY_ORDER."""
        assert next_slot("1.1") == "1.2"
        assert next_slot("1.2") == "1.3"
        assert next_slot("1.3") == "2.1"
        assert next_slot("4.0") == "4.1"
        assert next_slot("4.1") == "4.2"

    def test_skip_skipped_slots(self):
        """next_slot bỏ qua slot trong skipped list."""
        assert next_slot("1.1", skipped=["1.2"]) == "1.3"
        assert next_slot("1.1", skipped=["1.2", "1.3"]) == "2.1"
        assert next_slot("1.1", skipped=["1.2", "1.3", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6"]) == "3.1"

    def test_end_of_list_returns_none(self):
        """Slot cuối (4.2) → None → chuyển CONFIRMING."""
        assert next_slot("4.2") is None

    def test_consent_no_skips_to_end(self):
        """Slot 4.0 consent=no → skipped=['4.1', '4.2'] → next_slot('4.0') = None.

        Refer D10 STRATEGY + F2A.4 step 2.5.
        """
        assert next_slot("4.0", skipped=["4.1", "4.2"]) is None

    def test_invalid_current_starts_from_first(self):
        """current không trong list → bắt đầu từ slot 1.1."""
        assert next_slot("99.99") == "1.1"

    def test_empty_skipped_list(self):
        assert next_slot("1.1", skipped=[]) == "1.2"
        assert next_slot("1.1", skipped=None) == "1.2"
