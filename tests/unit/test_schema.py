"""Test Pydantic schemas + enums. Refer F2A.3 + STRATEGY D12."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import (
    Action,
    AddressForm,
    Channel,
    ConfirmationStatus,
    DealerType,
    Flag,
    Intent,
    Priority,
    QueueStatus,
    ReviewStatus,
    Stage,
)
from app.models.schema import (
    AdminQueueEntry,
    DealerProfileRaw,
    DeferredSlot,
    HistoryMessage,
    SessionState,
    SlotAttempts,
)


# ============================================================
# Enum count + value verification
# ============================================================


class TestEnumCounts:
    """Verify enum sizes khớp spec — chống regression."""

    def test_stage_has_4_values(self):
        """4 stage forward-only — refer F2A.1 + D2 STRATEGY."""
        assert len(list(Stage)) == 4
        assert {s.value for s in Stage} == {"GREETING", "ASKING", "CONFIRMING", "DONE"}

    def test_action_has_6_values(self):
        """6 action — refer F2A.4 + D11 STRATEGY (thêm PARTIAL_RETRY + DEFER batch 4)."""
        assert len(list(Action)) == 6
        assert {a.value for a in Action} == {
            "ADVANCE", "RETRY", "PARTIAL_RETRY", "DEFER", "SKIP", "PAUSE"
        }

    def test_intent_has_8_values(self):
        """8 intent — refer F2A.2 + GLOSSARY § 3 + CORE D.1 (CONFUSION added 2026-05-22)."""
        assert len(list(Intent)) == 8
        assert {i.value for i in Intent} == {
            "affirmative", "refusal", "khong_biet", "confusion",
            "defensive", "tam_su", "edit", "normal",
        }

    def test_dealer_type_has_5_values(self):
        """4 nhóm tone + unknown default — refer F2A.6 + 1B § 2."""
        assert len(list(DealerType)) == 5
        assert {d.value for d in DealerType} == {
            "lua_lo", "khoe", "lo", "ban", "unknown"
        }

    def test_flag_has_18_values_in_6_groups(self):
        """18 flag — Phase 3 R4 add ESCALATION, Phase 5 R5 add NUDGE_PENDING,
        Phase 10 add PHONE_UNVERIFIED (van an toàn SĐT).
        Refer STRATEGY D12 + F2A.3 + GLOSSARY § 4 + 1C § 9."""
        assert len(list(Flag)) == 18
        behavior = {
            Flag.DEALER_DECLINED, Flag.REQUIRED_MISSING,
            Flag.CONSENT_UNCLEAR, Flag.MULTIPLE_REFUSAL_IN_ROW,
        }
        abuse = {
            Flag.PROMPT_INJECTION, Flag.ABUSIVE_LANGUAGE, Flag.GARBAGE_INPUT,
            Flag.DEALER_TOO_DEFENSIVE, Flag.ADDRESS_BLACKLIST,
        }
        escalation = {Flag.ESCALATION}
        data_quality = {
            Flag.SANITY_CHECK_FAILED, Flag.PHONE_INVALID_AFTER_RETRY,
            Flag.VOICE_QUALITY_POOR, Flag.BRAND_NOT_IN_WHITELIST,
        }
        llm_guard = {Flag.HALLUCINATE, Flag.PII_LEAK}
        lifecycle = {Flag.NUDGE_PENDING}
        assert len(behavior) == 4
        assert len(abuse) == 5
        assert len(escalation) == 1
        assert len(data_quality) == 4
        assert len(llm_guard) == 2
        assert len(lifecycle) == 1
        # Union = 17, không overlap
        assert len(behavior | abuse | escalation | data_quality | llm_guard | lifecycle) == 17

    def test_address_form_has_2(self):
        assert {a.value for a in AddressForm} == {"anh", "chị"}

    def test_priority_has_3(self):
        assert {p.value for p in Priority} == {"HIGH", "MEDIUM", "LOW"}


# ============================================================
# DealerProfileRaw — schema profile
# ============================================================


class TestDealerProfileRaw:
    def test_empty_profile_valid(self):
        """Tất cả field Optional → empty profile vẫn valid."""
        p = DealerProfileRaw()
        assert p.dealer_name is None
        assert p.owner_name is None
        assert p.address is None
        assert p.brandkit_consent is None
        # Default factory
        assert p.category_stack == []
        assert p.supplier_brands == []
        assert p.slogan_options == []
        # Default fixed
        assert p.contact_role == "Chủ cửa hàng"

    def test_full_profile_valid(self):
        p = DealerProfileRaw(
            dealer_name="Nhôm Kính Thanh Tùng",
            owner_name="Tùng",
            address="123 Lê Lợi, P.1, Q.1, TP.HCM",
            phone_or_zalo="0912345678",
            main_product="cửa nhôm kính",
            brandkit_consent="yes",
            category_stack=["cua_nhom_kinh", "tu_bep"],
            est_team_size=5,
            province="TP.HCM",
            brand_name_short="Thanh Tùng",
            slogan_options=["A", "B", "C", "D", "E"],
        )
        assert p.dealer_name == "Nhôm Kính Thanh Tùng"
        assert len(p.slogan_options) == 5

    def test_no_scope_4_fields_in_schema(self):
        """Drift guard: Scope 4 field KHÔNG được trong DealerProfileRaw.

        Refer STRATEGY D7: Backend Scoring service riêng, chatbot KHÔNG ghi.
        """
        scope_4_forbidden = [
            "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9",
            "c_score", "tier", "batch", "dealer_id",
            "dealer_status", "admin_area_code", "editor_name",
        ]
        profile_fields = set(DealerProfileRaw.model_fields.keys())
        for field in scope_4_forbidden:
            assert field not in profile_fields, \
                f"Scope 4 field {field} KHÔNG được trong DealerProfileRaw"

    def test_all_28_scope_1_fields_present(self):
        """6 REQUIRED + 16 OPTIONAL + 6 RAW SIGNAL = 28 Scope 1 fields."""
        fields = set(DealerProfileRaw.model_fields.keys())
        required = {
            "dealer_name", "owner_name", "address",
            "phone_or_zalo", "main_product", "brandkit_consent",
        }
        optional = {
            "category_stack", "business_model_signal", "est_team_size",
            "team_stability_signal", "supplier_brands", "customer_segment_signal",
            "zalo", "facebook", "primary_contact_channel", "fb_marketing_status",
            "customer_old_percentage", "customer_storage_method", "customer_pain",
            "payment_terms_signal", "color_accent", "feng_shui_signal",
        }
        raw_signal = {
            "local_dominance_signal", "supplier_negotiation_signal",
            "community_network_signal", "motivation_signal",
            "warranty_responsibility_signal", "usp_signal",
        }
        assert required.issubset(fields), f"Missing REQUIRED: {required - fields}"
        assert optional.issubset(fields), f"Missing OPTIONAL: {optional - fields}"
        assert raw_signal.issubset(fields), f"Missing RAW SIGNAL: {raw_signal - fields}"
        assert len(required) + len(optional) + len(raw_signal) == 28

    def test_all_12_scope_2_derive_fields_present(self):
        """12 auto-derive fields (including ward). Refactor 2026-05-18: bỏ province_specialty."""
        fields = set(DealerProfileRaw.model_fields.keys())
        derive = {
            "province", "ward", "district", "main_category", "dealer_type",
            "brand_name_short", "initials_full", "initial_single",
            "contact_name", "contact_role", "hotline", "slogan_options",
        }
        assert derive.issubset(fields), f"Missing derive: {derive - fields}"
        assert len(derive) == 12
        # province_specialty bị bỏ → KHÔNG được có lại
        assert "province_specialty" not in fields


# ============================================================
# SessionState — state machine
# ============================================================


class TestSessionState:
    def test_default_session(self):
        s = SessionState(session_id="test-uuid-1")
        assert s.stage == Stage.GREETING
        assert s.current_slot is None
        assert s.slot_attempts == {}
        assert s.deferred_slots == {}
        assert s.skipped_slots == []
        assert s.flags == []
        assert s.turn_count == 0
        assert s.confirmation_status == ConfirmationStatus.PENDING
        assert s.review_status == ReviewStatus.RAW
        assert s.address_form == AddressForm.ANH
        assert s.channel == Channel.WEB
        assert s.closed_at is None
        assert s.paused_for is None

    def test_session_with_flags(self):
        s = SessionState(
            session_id="test-uuid-2",
            flags=[Flag.REQUIRED_MISSING, Flag.HALLUCINATE],
        )
        assert len(s.flags) == 2
        assert Flag.REQUIRED_MISSING in s.flags
        assert Flag.HALLUCINATE in s.flags

    def test_invalid_flag_value_rejected(self):
        """Flag enum strict — value lạ raise ValidationError."""
        with pytest.raises(ValidationError):
            SessionState(session_id="x", flags=["unknown_flag_lol"])

    def test_invalid_stage_value_rejected(self):
        with pytest.raises(ValidationError):
            SessionState(session_id="x", stage="WRONG_STAGE")

    def test_invalid_dealer_type_rejected(self):
        with pytest.raises(ValidationError):
            SessionState(session_id="x", detected_dealer_type="wrong_type")

    def test_slot_attempts_tracking(self):
        s = SessionState(session_id="test-uuid-3")
        s.slot_attempts["1.1"] = SlotAttempts(consecutive=1, total=1)
        assert s.slot_attempts["1.1"].consecutive == 1
        assert s.slot_attempts["1.1"].total == 1


# ============================================================
# Sub-models
# ============================================================


class TestSlotAttempts:
    def test_default_zero(self):
        a = SlotAttempts()
        assert a.consecutive == 0
        assert a.total == 0

    def test_track_defer_pattern(self):
        """Simulate retry pattern: 1 → 2 (consecutive) → DEFER → reset → 3."""
        a = SlotAttempts()
        # Lượt 1
        a.consecutive = 1
        a.total = 1
        # Lượt 2 liên tiếp
        a.consecutive = 2
        a.total = 2
        # DEFER: reset consecutive, giữ total
        a.consecutive = 0
        assert a.total == 2
        # Lần re-check sau pause: consecutive = 1 lại, total = 3
        a.consecutive = 1
        a.total = 3
        assert a.consecutive == 1
        assert a.total == 3


class TestDeferredSlot:
    def test_default(self):
        d = DeferredSlot(defer_at_turn=5)
        assert d.defer_at_turn == 5
        assert d.recheck_after_n_slots == 2  # default


class TestHistoryMessage:
    def test_basic(self):
        from datetime import datetime, timezone
        msg = HistoryMessage(
            role="dealer",
            content="anh tên Tùng",
            ts=datetime.now(timezone.utc),
        )
        assert msg.role == "dealer"


# ============================================================
# AdminQueueEntry
# ============================================================


class TestAdminQueueEntry:
    def test_basic_entry(self):
        q = AdminQueueEntry(
            queue_id="q-1",
            session_id="s-1",
            trigger=Flag.HALLUCINATE,
            priority=Priority.HIGH,
        )
        assert q.status == QueueStatus.PENDING
        assert q.trigger == Flag.HALLUCINATE
        assert q.priority == Priority.HIGH
        assert q.resolved_at is None

    def test_with_profile_snapshot(self):
        profile = DealerProfileRaw(owner_name="Tùng")
        q = AdminQueueEntry(
            queue_id="q-2",
            session_id="s-2",
            trigger=Flag.SANITY_CHECK_FAILED,
            priority=Priority.HIGH,
            profile_snapshot=profile,
        )
        assert q.profile_snapshot.owner_name == "Tùng"
