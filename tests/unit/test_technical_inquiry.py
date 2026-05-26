"""Unit test cho detect_technical_inquiry (CORE E.3).

7 nhóm pattern: báo giá / bảo hành / kỹ thuật / hợp tác / pháp lý /
y tế / tài chính → escalate template.
"""
from __future__ import annotations

import pytest

from app.core.intent import (
    TECHNICAL_INQUIRY_ESCALATE_TEMPLATE,
    detect_technical_inquiry,
)


# ============================================================
# Phase 6 R+ fix 2026-05-22: slot context — skip warranty pattern
# tại slot 3.5 (dealer reply "anh chịu bảo hành" = valid data).
# ============================================================


class TestSlotContextSkip:
    """Test detect_technical_inquiry skip warranty pattern khi slot 3.5."""

    def test_slot_3_5_dealer_reply_warranty_not_escalate(self):
        """Slot 3.5 expects warranty answer — dealer reply 'anh chịu bảo hành'
        KHÔNG được trigger technical inquiry."""
        msgs = [
            "anh chịu bảo hành trực tiếp",
            "anh đứng ra bảo hành cho khách",
            "nhà cung cấp bảo hành",
            "team em bảo hành cho khách 12 tháng",
            "bảo hành 2 năm anh chịu hết",
        ]
        for m in msgs:
            # Tại slot 3.5 — KHÔNG escalate
            assert not detect_technical_inquiry(m, current_slot="3.5"), \
                f"Should NOT escalate at slot 3.5: {m!r}"
            # Tại slot khác (vd 1.1) — VẪN escalate (vì user hỏi bảo hành)
            assert detect_technical_inquiry(m, current_slot="1.1"), \
                f"Should escalate at slot 1.1: {m!r}"

    def test_slot_3_5_real_technical_question_still_escalate(self):
        """Slot 3.5 nhưng dealer hỏi câu KHÁC (báo giá/y tế/pháp lý)
        → VẪN escalate (chỉ skip warranty pattern, không skip cả)."""
        msgs = [
            "1m² vách kính bao nhiêu tiền?",
            "anh đau lưng nên đi viện không?",
            "thuế VAT bao nhiêu?",
            "anh muốn làm đại lý phân phối",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m, current_slot="3.5"), \
                f"Should escalate (non-warranty pattern): {m!r}"

    def test_no_current_slot_default_check_all(self):
        """KHÔNG truyền current_slot → check all pattern (backward compat)."""
        assert detect_technical_inquiry("anh chịu bảo hành") is True
        assert detect_technical_inquiry("anh chịu bảo hành", current_slot=None) is True


# ============================================================
# 7 nhóm pattern positive cases
# ============================================================


class TestDetectTechnicalInquiryPositive:
    def test_bao_gia(self):
        msgs = [
            "1m² vách kính bao nhiêu tiền em?",
            "Em báo giá Xingfa cho anh xem",
            "Chiết khấu được bao nhiêu %?",
            "Cho anh xin bảng giá",
            "Giá sỉ bao nhiêu thế em?",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"

    def test_bao_hanh_khieu_nai(self):
        msgs = [
            "Cửa hỏng rồi, ai bảo hành?",
            "Anh muốn khiếu nại sản phẩm",
            "Hàng lỗi đổi trả thế nào?",
            "Bên em có sửa chữa miễn phí không?",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"

    def test_tu_van_ky_thuat(self):
        msgs = [
            "Loại nhôm nào tốt cho biển?",
            "Loại kính nào hợp nắng?",
            "Nên dùng hãng nào cho chống cháy?",
            "Chịu lực bao nhiêu thì gãy?",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"

    def test_hop_tac_phan_phoi(self):
        msgs = [
            "Anh muốn làm đại lý bên em",
            "Đăng ký đại lý sao em?",
            "Có nhượng quyền không?",
            "Anh muốn hợp tác phân phối",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"

    def test_phap_ly_thue(self):
        msgs = [
            "Anh có cần đăng ký kinh doanh không?",
            "Thuế VAT bao nhiêu?",
            "Hợp đồng mẫu thế nào?",
            "Có tranh chấp gì không?",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"

    def test_y_te_advice(self):
        msgs = [
            "Anh đau lưng nên đi viện không?",
            "Uống thuốc gì cho khỏi đau?",
            "Có nên phẫu thuật không em?",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"

    def test_tai_chinh_ca_nhan(self):
        msgs = [
            "Anh nên vay ngân hàng không?",
            "Đầu tư chứng khoán có rủi ro không?",
            "Lãi suất bao nhiêu thì hợp lý?",
        ]
        for m in msgs:
            assert detect_technical_inquiry(m), f"FAIL: {m!r}"


# ============================================================
# Negative cases — không match
# ============================================================


class TestDetectTechnicalInquiryNegative:
    def test_slot_answer_not_match(self):
        msgs = [
            "anh Tuấn, cửa hàng Tuấn Nhôm Kính",
            "ở Quận 1 TP HCM",
            "0912345678",
            "nội thất",
            "anh có xưởng riêng",
            "8 thợ chính",
            "xingfa với việt pháp",
        ]
        for m in msgs:
            assert not detect_technical_inquiry(m), f"False positive: {m!r}"

    def test_normal_chat_not_match(self):
        msgs = [
            "OK em",
            "ừ tiếp đi",
            "dạ vâng",
            "trời mưa quá nhỉ",
            "anh không nhớ",
        ]
        for m in msgs:
            assert not detect_technical_inquiry(m), f"False positive: {m!r}"

    def test_empty(self):
        assert not detect_technical_inquiry("")
        assert not detect_technical_inquiry(None)  # type: ignore
        assert not detect_technical_inquiry("   ")


# ============================================================
# Escalate template content
# ============================================================


class TestEscalateTemplate:
    def test_template_has_escalate_keyword(self):
        # Template phải mention "team chuyên môn" để dealer hiểu chuyển
        assert "team chuyên môn" in TECHNICAL_INQUIRY_ESCALATE_TEMPLATE

    def test_template_polite(self):
        # Polite: "Dạ", "anh"
        assert "Dạ" in TECHNICAL_INQUIRY_ESCALATE_TEMPLATE
        assert "anh" in TECHNICAL_INQUIRY_ESCALATE_TEMPLATE.lower()

    def test_template_does_not_promise(self):
        # KHÔNG hứa thời gian / kết quả cụ thể (CORE A.3)
        forbidden = ["sẽ liên hệ trong", "trong vòng", "ngay lập tức", "chắc chắn"]
        for f in forbidden:
            assert f not in TECHNICAL_INQUIRY_ESCALATE_TEMPLATE.lower(), \
                f"Template không nên hứa: {f!r}"
