"""9.4a — REORDER brandkit-first (2026-06-17).

Khoá thứ tự MỚI: required → BRANDKIT (consent → màu/phong cách/slogan) → TƯ VẤN C1-C9.
Trước đây C1-C9 đứng trước brandkit (16 câu mới tới brandkit) — đảo lại để brandkit lên sớm.
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
_CRITERIA = {f for f, _l, _h in OPTIONAL_FIELDS_PRIORITY}  # 9 C + 1 phụ


def _required_done():
    return {
        "owner_name": "A", "dealer_name": "B", "address": "HN",
        "phone_or_zalo": "0912345678", "main_product": "nhôm",
        "business_model_signal": "xưởng",
    }


def _snap(**all_fields):
    return {
        "all_fields": dict(all_fields),
        "missing_required_fields": [],
        "skipped_fields": [],
        "blocking_flags": [],
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
    }


def _fields(snap):
    return [s.target_field for s in iter_pending_steps(snap)]


class TestBrandkitBeforeCriteria:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_required_done_asks_brandkit_consent_first(self):
        """Xong required → hỏi brandkit_consent NGAY, KHÔNG hỏi C1-C9 trước."""
        snap = _snap(**_required_done())
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=1)
        assert obj["target_field"] == "brandkit_consent"
        order = _fields(snap)
        # consent đứng trước MỌI tiêu chí C1-C9
        first_criteria = next(i for i, f in enumerate(order) if f in _CRITERIA)
        assert order.index("brandkit_consent") < first_criteria

    def test_consent_yes_brandkit_subfields_before_criteria(self):
        """consent=yes → màu/phong cách/slogan hỏi TRƯỚC C1-C9."""
        snap = _snap(**_required_done(), brandkit_consent="yes")
        order = _fields(snap)
        last_brandkit = max(order.index(f) for f in _BRANDKIT_SUB)
        first_criteria = next(i for i, f in enumerate(order) if f in _CRITERIA)
        assert last_brandkit < first_criteria, f"brandkit phải trước C1-C9: {order}"

    def test_consent_no_drops_to_criteria(self):
        """consent=no → KHÔNG sinh bước brandkit phụ → rơi thẳng xuống tư vấn C1-C9."""
        snap = _snap(**_required_done(), brandkit_consent="no")
        order = _fields(snap)
        assert not (_BRANDKIT_SUB & set(order)), "consent=no không được hỏi màu/phong cách/slogan"
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=1)
        assert obj["target_field"] in _CRITERIA

    def test_consent_no_to_yes_reopens_brandkit(self):
        """Khách đổi ý no→yes → khối brandkit hiện lại (tính mỗi lượt từ snapshot)."""
        snap = _snap(**_required_done(), brandkit_consent="yes")
        order = _fields(snap)
        assert _BRANDKIT_SUB & set(order), "no→yes phải mở lại brandkit"


class TestCollectionStatusOrder:
    def test_status_lists_brandkit_before_criteria(self):
        """Prompt 'Còn phải hỏi' cũng theo thứ tự mới (dùng chung iter_pending_steps)."""
        snap = _snap(**_required_done(), brandkit_consent="yes")
        status = _build_collection_status(snap)
        pos_style = status.find("phong cách logo")
        pos_team = status.find("quy mô đội thợ")  # C3
        assert pos_style != -1 and pos_team != -1
        assert pos_style < pos_team, "brandkit phải liệt kê trước C1-C9"


def _brandkit_done():
    """Required + brandkit + ĐÃ show preview → đang ở giai đoạn tư vấn C1-C9."""
    af = _required_done()
    af.update({"brandkit_consent": "yes", "color_accent": "đỏ",
               "logo_style": "hiện đại", "slogan_preference": "x",
               "brandkit_preview_shown": "yes"})
    return af


class TestWrapupSignal:
    def test_detect_wrapup_positive(self):
        for t in ["đủ rồi em ơi", "thế thôi nhé", "chốt luôn đi", "xong rồi",
                  "không cần hỏi thêm", "tạm đủ rồi", "dừng ở đây nhé"]:
            assert detect_wrapup(t), t

    def test_detect_wrapup_negative(self):
        # câu trả lời tư vấn bình thường KHÔNG bị bắt
        for t in ["khoảng 5 người", "em nhập của Xingfa", "khách cũ tầm 30%",
                  "anh muốn màu đỏ", "shop ở Hà Nội"]:
            assert not detect_wrapup(t), t


class TestConsultationPhase:
    def test_phase_true_only_after_brandkit(self):
        # đang còn brandkit → CHƯA phải giai đoạn tư vấn
        assert not is_consultation_phase(_snap(**_required_done(), brandkit_consent="yes"))
        # còn thiếu required → không
        snap_req = _snap(); snap_req["missing_required_fields"] = ["owner_name"]
        assert not is_consultation_phase(snap_req)
        # xong brandkit, còn C1-C9 → ĐÚNG là giai đoạn tư vấn
        assert is_consultation_phase(_snap(**_brandkit_done()))

    def test_pending_consultation_fields_are_criteria(self):
        snap = _snap(**_brandkit_done())
        fields = pending_consultation_fields(snap)
        assert fields and all(f in _CRITERIA for f in fields)
        assert "color_accent" not in fields  # brandkit không tính

    def test_skip_all_consultation_reaches_review(self):
        """Mô phỏng 'đủ rồi': skip nốt field tư vấn → READY_FOR_REVIEW."""
        engine = WorkflowEngine()
        snap = _snap(**_brandkit_done())
        assert engine.compute_workflow_state(snap) == "WAITING_REQUIRED_FIELD"
        snap["skipped_fields"] = pending_consultation_fields(snap)
        assert engine.compute_workflow_state(snap) == "READY_FOR_REVIEW"
        obj = engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=5)
        assert obj["type"] == "show_profile_review"


class TestBrandkitPreviewStep:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def _brandkit_filled_no_preview(self):
        af = _required_done()
        af.update({"brandkit_consent": "yes", "color_accent": "đỏ",
                   "logo_style": "hiện đại", "slogan_preference": "x"})
        return af  # KHÔNG có brandkit_preview_shown

    def test_preview_after_brandkit_before_criteria(self):
        """Xong màu/phong cách/slogan → bước kế là SHOW MẪU (trước C1-C9)."""
        snap = _snap(**self._brandkit_filled_no_preview())
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=5)
        assert obj["type"] == "show_brandkit_preview"
        # và đứng trước mọi tiêu chí C1-C9
        order = _fields(snap)
        assert order[0] == "brandkit_preview"

    def test_preview_pending_is_not_consultation_phase(self):
        """Đang chờ preview → CHƯA phải giai đoạn tư vấn → 'đủ rồi' không kích."""
        snap = _snap(**self._brandkit_filled_no_preview())
        assert not is_consultation_phase(snap)

    def test_preview_shown_moves_to_criteria(self):
        """Đã show mẫu → bước kế là tư vấn C1-C9, không lặp lại preview."""
        af = self._brandkit_filled_no_preview()
        af["brandkit_preview_shown"] = "yes"
        snap = _snap(**af)
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=5)
        assert obj["type"] == "collect_optional_field"
        assert obj["target_field"] in _CRITERIA
        assert "brandkit_preview" not in _fields(snap)

    def test_consent_no_skips_preview(self):
        """consent=no → không màu/phong cách → KHÔNG có bước preview."""
        snap = _snap(**_required_done(), brandkit_consent="no")
        assert "brandkit_preview" not in _fields(snap)


class TestPickSamples:
    def test_match_by_style(self):
        from app.services.brandkit_samples import pick_samples
        ids = [s["id"] for s in pick_samples(style="sang trọng")]
        assert ids and all("luxury" in i or "navy" in i for i in ids)

    def test_match_by_color(self):
        from app.services.brandkit_samples import pick_samples
        assert pick_samples(color="đỏ")[0]["id"] == "bold-red"

    def test_unknown_returns_random_nonempty(self):
        import random
        from app.services.brandkit_samples import pick_samples
        out = pick_samples(rng=random.Random(7))
        assert 1 <= len(out) <= 3
        assert {"logo_url", "namecard_url", "caption"} <= set(out[0])
