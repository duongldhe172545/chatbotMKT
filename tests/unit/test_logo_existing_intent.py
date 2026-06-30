"""Test logo_existing_intent — feedback 2026-06-10.

Dealer "đã có logo rồi" → KHÔNG nhét vào logo_initials, hỏi ngược nhu cầu thật
(nâng cấp / thiết kế lại / làm mới) trước khi chốt brandkit.
"""
from __future__ import annotations

from app.llm.extractors.validators import validate_field, validate_logo_existing_intent
from app.llm.intake_fact_extractor import BRANDING_PREFERENCE_FIELDS, INTAKE_ALLOWED_FIELDS
from app.models.schema import DealerProfileRaw
from app.parlant.workflow_engine import WorkflowEngine
from app.services.serializers import DESIGN_PROFILE_FIELDS, empty_profile_snapshot


# ============================================================
# Validator — enum 4 giá trị, khoá luật không khoá case
# ============================================================


class TestValidator:
    def test_valid_values(self):
        for v in ("unclarified", "upgrade", "redesign", "new"):
            ok, cleaned = validate_logo_existing_intent(v)
            assert ok and cleaned == v

    def test_case_insensitive(self):
        ok, cleaned = validate_logo_existing_intent("  Upgrade ")
        assert ok and cleaned == "upgrade"

    def test_invalid_free_text_rejected(self):
        """ADVERSARIAL: câu thoại thô không được lọt vào enum."""
        for bad in ("anh có logo rồi", "đã có", "ok", "", None, 123):
            ok, cleaned = validate_logo_existing_intent(bad)
            assert not ok and cleaned is None

    def test_dispatch_via_validate_field(self):
        ok, cleaned = validate_field("logo_existing_intent", "redesign")
        assert ok and cleaned == "redesign"
        ok, _ = validate_field("logo_existing_intent", "đã có logo")
        assert not ok


# ============================================================
# Field wiring — schema + extractor allowlist + serializers
# ============================================================


class TestFieldWiring:
    def test_in_dealer_profile_schema(self):
        assert "logo_existing_intent" in DealerProfileRaw.model_fields

    def test_in_intake_allowed_fields(self):
        assert "logo_existing_intent" in BRANDING_PREFERENCE_FIELDS
        assert "logo_existing_intent" in INTAKE_ALLOWED_FIELDS

    def test_in_design_profile_fields(self):
        assert "logo_existing_intent" in DESIGN_PROFILE_FIELDS


# ============================================================
# Workflow — unclarified → hỏi nhu cầu TRƯỚC màu, chặn review
# ============================================================


def _snapshot_required_done(**extra_fields):
    snap = empty_profile_snapshot()
    all_fields = {
        "owner_name": "Hải An", "dealer_name": "An Hải", "address": "Hoàng Mai HN",
        "phone_or_zalo": "0987156224", "main_product": "nhôm kính",
        "business_model_signal": "xưởng", "est_team_size": 4,
        "supplier_brands": ["Topal"], "primary_contact_channel": "zalo",
        "facebook": "không có", "customer_old_percentage": "nhiều",
        "local_dominance_signal": "khách quen quanh khu",
        "customer_storage_method": "không lưu", "customer_pain": "không",
        "payment_terms_signal": "cọc 50%", "warranty_responsibility_signal": "5 năm",
        "brandkit_consent": "yes",
    }
    all_fields.update(extra_fields)
    snap["all_fields"] = all_fields
    snap["missing_required_fields"] = []
    snap["skipped_fields"] = []
    return snap


class TestWorkflowProbe:
    def test_unclarified_probes_before_color(self):
        """Có logo rồi + chưa rõ nhu cầu → objective hỏi logo intent (trước màu)."""
        engine = WorkflowEngine()
        snap = _snapshot_required_done(logo_existing_intent="unclarified")
        obj = engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["target_field"] == "logo_existing_intent"
        assert "nâng cấp" in obj["prompt_hint"]
        assert "làm mới" in obj["prompt_hint"]

    def test_clarified_moves_to_color(self):
        engine = WorkflowEngine()
        snap = _snapshot_required_done(logo_existing_intent="upgrade")
        obj = engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["target_field"] == "color_accent"

    def test_no_logo_mentioned_goes_straight_to_color(self):
        engine = WorkflowEngine()
        snap = _snapshot_required_done()
        obj = engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["target_field"] == "color_accent"

    def test_unclarified_blocks_ready_for_review(self):
        """Chưa rõ nhu cầu logo → workflow_state vẫn WAITING, không show card."""
        engine = WorkflowEngine()
        snap = _snapshot_required_done(
            logo_existing_intent="unclarified", color_accent="auto"
        )
        assert engine.compute_workflow_state(snap) == "WAITING_REQUIRED_FIELD"

    def test_clarified_with_color_ready_for_review(self):
        engine = WorkflowEngine()
        # P4.4: brandkit giờ còn hỏi phong cách + slogan → phải xong cả 2 mới review
        snap = _snapshot_required_done(
            logo_existing_intent="new", color_accent="auto",
            logo_style="auto", slogan_preference="auto",
            brandkit_preview_shown="yes",  # 9.4b: đã show mẫu → mới tới review
        )
        assert engine.compute_workflow_state(snap) == "READY_FOR_REVIEW"
