"""P4 — chất lượng thu thập & khớp 9 tiêu chí (2026-06-10).

- P4.1: sửa lệch C2 (ký gửi/mua đứt) + C5 (động lực/nút thắt) trong prompt_hint.
- P4.2: gặng C6/C9/C8 qua hint enrichment.
- P4.3: bug serializers field "slogan" → slogan_preference.
- P4.4: brandkit hỏi logo_style + slogan_preference (OPTIONAL, sau màu).
"""
from __future__ import annotations

from app.parlant.context_builder import _build_collection_status
from app.parlant.workflow_engine import OPTIONAL_FIELDS_PRIORITY, WorkflowEngine
from app.services.serializers import DESIGN_PROFILE_FIELDS, LOGO_VISIBLE_FIELDS


def _hint(field: str) -> str:
    for f, _label, hint in OPTIONAL_FIELDS_PRIORITY:
        if f == field:
            return hint
    raise AssertionError(f"{field} không có trong OPTIONAL_FIELDS_PRIORITY")


# ============================================================
# P4.1 — C2/C5 hết lệch trọng tâm
# ============================================================


class TestCriteriaRealignment:
    def test_c2_payment_probes_financial_autonomy(self):
        """C2 phải gặng mua đứt vs ký gửi (không chỉ % cọc)."""
        h = _hint("payment_terms_signal").lower()
        assert "ký gửi" in h and "mua đứt" in h

    def test_c5_pain_probes_improvement(self):
        """C5 hỏi điều mong cải thiện (1 câu, bỏ liệt kê nút thắt — Fix 1)."""
        h = _hint("customer_pain").lower()
        assert "cải thiện" in h

    def test_c8_supplier_asks_source_one_question(self):
        """Fix 1: C8 hỏi 1 câu về hãng nhập; đàm phán/đổi nguồn → mine thụ động."""
        h = _hint("supplier_brands").lower()
        assert "hãng nào" in h
        assert "đàm phán" not in h and "đổi hãng" not in h

    def test_c9_asks_facebook_one_question(self):
        """Fix 1: C9 hỏi 1 câu về Facebook; mạng lưới → mine thụ động."""
        h = _hint("facebook").lower()
        assert "facebook" in h or "fanpage" in h
        assert "giới thiệu" not in h

    def test_c6_is_standalone_probe(self):
        # C6 giờ là câu hỏi RIÊNG (local_dominance_signal), tách khỏi C1
        h = _hint("local_dominance_signal").lower()
        assert "quảng cáo" in h or "tự tìm" in h
        assert "quảng cáo" not in _hint("customer_old_percentage").lower()


# ============================================================
# P4.3 — serializers field name
# ============================================================


class TestSerializerFields:
    def test_no_phantom_slogan_field(self):
        assert "slogan" not in DESIGN_PROFILE_FIELDS
        assert "slogan" not in LOGO_VISIBLE_FIELDS

    def test_real_slogan_fields_present(self):
        assert "slogan_preference" in DESIGN_PROFILE_FIELDS
        assert "slogan_preference" in LOGO_VISIBLE_FIELDS

    def test_logo_existing_intent_still_present(self):
        # không phá wiring cũ
        assert "logo_existing_intent" in DESIGN_PROFILE_FIELDS


# ============================================================
# P4.4 — brandkit hỏi phong cách + slogan (OPTIONAL, sau màu)
# ============================================================


def _brandkit_snapshot(**extra) -> dict:
    all_fields = {
        "owner_name": "Hùng", "dealer_name": "Hùng Phát", "address": "Hà Đông HN",
        "phone_or_zalo": "0912345678", "main_product": "nhôm kính",
        "business_model_signal": "xưởng", "brandkit_consent": "yes",
    }
    all_fields.update(extra)
    return {
        "all_fields": all_fields,
        "missing_required_fields": [],
        "skipped_fields": extra.pop("_skipped", []) if False else [],
        "blocking_flags": [],
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
    }


class TestBrandkitFlow:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def _snapshot(self, *, skipped=None, **fields):
        snap = _brandkit_snapshot(**fields)
        snap["skipped_fields"] = skipped or []
        # đã thu hết optional 2.3-3.5 để flow chạm tới brandkit
        for f, _l, _h in OPTIONAL_FIELDS_PRIORITY:
            snap["all_fields"].setdefault(f, "x")
        return snap

    def test_asks_logo_style_after_color(self):
        snap = self._snapshot(color_accent="xanh")
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["target_field"] == "logo_style"

    def test_asks_slogan_after_style(self):
        snap = self._snapshot(color_accent="xanh", logo_style="hiện đại")
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["target_field"] == "slogan_preference"

    def test_review_after_brandkit_complete(self):
        snap = self._snapshot(color_accent="auto", logo_style="auto", slogan_preference="auto")
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["type"] == "show_profile_review"

    def test_skipping_brandkit_extra_still_reviews(self):
        """Khách 'tùy em' bỏ qua phong cách/slogan → vẫn chốt được (OPTIONAL)."""
        snap = self._snapshot(color_accent="auto", skipped=["logo_style", "slogan_preference"])
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=20)
        assert obj["type"] == "show_profile_review"

    def test_workflow_state_waits_on_missing_brandkit_extra(self):
        snap = self._snapshot(color_accent="xanh")  # style/slogan chưa có
        assert self.engine.compute_workflow_state(snap) == "WAITING_REQUIRED_FIELD"

    def test_workflow_state_ready_when_brandkit_done(self):
        snap = self._snapshot(color_accent="auto", logo_style="auto", slogan_preference="auto")
        assert self.engine.compute_workflow_state(snap) == "READY_FOR_REVIEW"


# ============================================================
# collection_status — phong cách/slogan vào danh sách CÒN PHẢI HỎI
# ============================================================


class TestCollectionStatusBrandkit:
    def test_lists_style_and_slogan_when_pending(self):
        snap = _brandkit_snapshot(color_accent="xanh")
        status = _build_collection_status(snap)
        assert "phong cách logo" in status
        assert "slogan" in status

    def test_no_brandkit_extra_when_skipped(self):
        snap = _brandkit_snapshot(color_accent="xanh")
        snap["skipped_fields"] = ["logo_style", "slogan_preference"]
        status = _build_collection_status(snap)
        # không liệt kê lại field đã skip
        assert "phong cách logo" not in status
