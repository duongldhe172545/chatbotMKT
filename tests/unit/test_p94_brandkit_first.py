"""Luồng brandkit-first + CHỐT SỚM (FIX_GAP 2026-06-30).

Thứ tự: required → brandkit (consent→màu→phong cách→slogan) → THẺ CHỐT (review)
→ (CONFIRMED) → 9 tiêu chí C1-C9 tư vấn → handoff.
KHÔNG còn bước show_brandkit_preview (đội thiết kế gửi ảnh qua Zalo).
9 tiêu chí CHỈ chạy SAU khi review_status=CONFIRMED.
"""
from __future__ import annotations

from app.parlant.context_builder import _build_collection_status
from app.parlant.observation_detector import detect_wrapup
from app.parlant.workflow_engine import (
    OPTIONAL_FIELDS_PRIORITY,
    WorkflowEngine,
    is_consultation_phase,
    iter_pending_steps,
    pending_consultation_fields,
)

_BRANDKIT_SUB = {"color_accent", "logo_style", "slogan_preference"}
_CRITERIA = {f for f, _l, _h in OPTIONAL_FIELDS_PRIORITY}


def _required_done():
    return {
        "owner_name": "A", "dealer_name": "B", "address": "HN",
        "phone_or_zalo": "0912345678", "main_product": "nhôm",
        "business_model_signal": "xưởng",
    }


def _snap(review_status="DRAFT", **all_fields):
    return {
        "all_fields": dict(all_fields),
        "missing_required_fields": [],
        "skipped_fields": [],
        "blocking_flags": [],
        "review_status": review_status,
        "logo_issued_status": "NONE",
    }


def _fields(snap):
    return [s.target_field for s in iter_pending_steps(snap)]


def _brandkit_done(**extra):
    af = _required_done()
    af.update({"brandkit_consent": "yes", "color_accent": "đỏ",
               "logo_style": "hiện đại", "slogan_preference": "x"})
    af.update(extra)
    return af


class TestBrandkitFirst:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_required_done_asks_brandkit_consent_first(self):
        snap = _snap(**_required_done())
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=1)
        assert obj["target_field"] == "brandkit_consent"
        # DRAFT: KHÔNG có C1-C9 trong pending (chúng sau chốt)
        assert not (_CRITERIA & set(_fields(snap)))

    def test_consent_yes_asks_color(self):
        snap = _snap(**_required_done(), brandkit_consent="yes")
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=1)
        assert obj["target_field"] == "color_accent"

    def test_no_preview_step(self):
        """Sau brandkit KHÔNG còn bước show_brandkit_preview."""
        snap = _snap(**_brandkit_done())  # DRAFT, brandkit xong
        assert "brandkit_preview" not in _fields(snap)
        assert not any(s.objective_type == "show_brandkit_preview" for s in iter_pending_steps(snap))


class TestReviewAfterBrandkit:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_brandkit_done_draft_goes_review(self):
        """Brandkit xong (DRAFT) → hết pending → READY_FOR_REVIEW + show_profile_review (KHÔNG C1-C9)."""
        snap = _snap(**_brandkit_done())
        assert not _fields(snap)  # không còn bước nào trước chốt
        assert self.engine.compute_workflow_state(snap) == "READY_FOR_REVIEW"
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=5)
        assert obj["type"] == "show_profile_review"

    def test_consent_no_also_goes_review_not_criteria(self):
        """consent=no → KHÔNG hỏi C1-C9 trước chốt → đi review."""
        snap = _snap(**_required_done(), brandkit_consent="no")
        assert not (_CRITERIA & set(_fields(snap)))
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=5)
        assert obj["type"] == "show_profile_review"


class TestConsultationAfterConfirm:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_confirmed_then_asks_criteria(self):
        """CONFIRMED + C1-C9 chưa thu → tư vấn (est_team_size). State vẫn CONFIRMED."""
        snap = _snap("CONFIRMED", **_brandkit_done())
        assert self.engine.compute_workflow_state(snap) == "CONFIRMED"
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["type"] == "collect_optional_field"
        assert obj["target_field"] in _CRITERIA

    def test_confirmed_all_criteria_done_handoff(self):
        af = _brandkit_done()
        for f in _CRITERIA:
            af.setdefault(f, "x")
        snap = _snap("CONFIRMED", **af)
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=30)
        assert obj["type"] == "zalo_handoff"

    def test_consultation_phase_only_after_confirm(self):
        # DRAFT brandkit done → KHÔNG phải consultation phase (chưa chốt)
        assert not is_consultation_phase(_snap(**_brandkit_done()))
        # CONFIRMED + C1-C9 pending → ĐÚNG là consultation phase
        assert is_consultation_phase(_snap("CONFIRMED", **_brandkit_done()))

    def test_wrapup_skips_remaining_criteria_after_confirm(self):
        """'đủ rồi' lúc tư vấn (CONFIRMED) → skip nốt C1-C9 → handoff."""
        snap = _snap("CONFIRMED", **_brandkit_done())
        snap["skipped_fields"] = pending_consultation_fields(snap)
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=25)
        assert obj["type"] == "zalo_handoff"


class TestWrapupSignal:
    def test_detect_wrapup_positive(self):
        for t in ["đủ rồi em ơi", "thế thôi nhé", "chốt luôn đi", "xong rồi",
                  "không cần hỏi thêm", "tạm đủ rồi", "dừng ở đây nhé"]:
            assert detect_wrapup(t), t

    def test_detect_wrapup_negative(self):
        for t in ["khoảng 5 người", "em nhập của Xingfa", "khách cũ tầm 30%",
                  "anh muốn màu đỏ", "shop ở Hà Nội"]:
            assert not detect_wrapup(t), t


class TestCollectionStatusOrder:
    def test_draft_lists_brandkit_not_criteria(self):
        """DRAFT: 'Còn phải hỏi' có brandkit, CHƯA có C1-C9."""
        snap = _snap(**_required_done(), brandkit_consent="yes")
        status = _build_collection_status(snap)
        assert "phong cách logo" in status
        assert "quy mô đội thợ" not in status  # C3 chỉ sau chốt

    def test_confirmed_lists_criteria(self):
        snap = _snap("CONFIRMED", **_brandkit_done())
        status = _build_collection_status(snap)
        assert "quy mô đội thợ" in status  # C3 hiện sau chốt


class TestPickSamples:
    def test_match_by_style(self):
        from app.services.brandkit_samples import pick_samples
        ids = [s["id"] for s in pick_samples(style="sang trọng")]
        assert ids and all("luxury" in i or "navy" in i for i in ids)

    def test_unknown_returns_random_nonempty(self):
        import random
        from app.services.brandkit_samples import pick_samples
        out = pick_samples(rng=random.Random(7))
        assert 1 <= len(out) <= 3
