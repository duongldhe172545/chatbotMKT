"""Test intent detection Layer 1 (regex). Refer F2A.2 + GLOSSARY § Intent."""
from __future__ import annotations

import pytest

from app.core.intent import detect_intent, detect_intent_layer1
from app.models.enums import Intent


# ============================================================
# AFFIRMATIVE detection
# ============================================================


class TestAffirmative:
    @pytest.mark.parametrize("msg", [
        "ok", "OK", "oke", "okê",
        "vâng", "dạ vâng", "ừ", "ờ",
        "được", "được rồi", "chuẩn", "đúng", "đồng ý",
        "ok anh",
        "ok ok ok",
        "yes", "yeah",
    ])
    def test_affirmative_match(self, msg):
        assert detect_intent_layer1(msg) == Intent.AFFIRMATIVE


# ============================================================
# REFUSAL detection
# ============================================================


class TestRefusal:
    @pytest.mark.parametrize("msg", [
        "không cho",
        "đéo cho",
        "miễn cho tôi",
        "không nói",
        "không muốn nói",
        "kệ đi",
        "không cần",
        "đéo cần",
        "tao đéo nói đâu",
    ])
    def test_refusal_match(self, msg):
        assert detect_intent_layer1(msg) == Intent.REFUSAL


# ============================================================
# KHONG_BIET detection
# ============================================================


class TestKhongBiet:
    @pytest.mark.parametrize("msg", [
        "không biết",
        "không nhớ",
        "chưa biết",
        "tùy em",
        "tùy anh",
        "chưa có",
        "quên mất",
        "quên rồi",
    ])
    def test_khong_biet_match(self, msg):
        assert detect_intent_layer1(msg) == Intent.KHONG_BIET


# ============================================================
# DEFENSIVE detection
# ============================================================


class TestDefensive:
    @pytest.mark.parametrize("msg", [
        "lừa đảo à",
        "phí gì không",
        "scam à",
        "em là ai",
        "ai làm cái này",
        "ai đứng sau",
        "công ty nào",
        "bán data à",
        "có lộ không",
        "tin được không",
        "sao tin được",
    ])
    def test_defensive_match(self, msg):
        assert detect_intent_layer1(msg) == Intent.DEFENSIVE


# ============================================================
# TAM_SU detection
# ============================================================


class TestTamSu:
    @pytest.mark.parametrize("msg", [
        "vợ tao mới sinh",
        "con anh ốm",
        "gia đình mệt quá",
        "trời mưa hôm nay",
        "stress quá",
        "đau lưng ghê",
        "đi cà phê không em",
        "dịch bệnh hết tiền",
        "khó khăn quá",
    ])
    def test_tam_su_match(self, msg):
        assert detect_intent_layer1(msg) == Intent.TAM_SU


# ============================================================
# EDIT detection
# ============================================================


class TestEdit:
    @pytest.mark.parametrize("msg", [
        "sửa địa chỉ",
        "đổi tên thành Tùng",
        "sai rồi",
        "nhầm rồi",
        "không phải vậy",
    ])
    def test_edit_match(self, msg):
        assert detect_intent_layer1(msg) == Intent.EDIT


# ============================================================
# NORMAL fallback
# ============================================================


class TestNormal:
    @pytest.mark.parametrize("msg", [
        "tên anh là Tùng",
        "Nhôm Kính Thanh Tùng",
        "123 Lê Lợi quận 1",
        "0912345678",
        "cửa nhôm kính cường lực",
    ])
    def test_normal_data_messages(self, msg):
        """Normal data → không match marker → fallback NORMAL."""
        assert detect_intent(msg) == Intent.NORMAL


class TestEdgeCases:
    def test_empty_string(self):
        assert detect_intent_layer1("") is None
        assert detect_intent("") == Intent.NORMAL

    def test_whitespace_only(self):
        assert detect_intent_layer1("   ") is None
        assert detect_intent("\n\t  ") == Intent.NORMAL

    def test_case_insensitive(self):
        """Match regardless of case."""
        assert detect_intent_layer1("OK") == Intent.AFFIRMATIVE
        assert detect_intent_layer1("Lừa Đảo Gì") == Intent.DEFENSIVE
        assert detect_intent_layer1("KHÔNG BIẾT") == Intent.KHONG_BIET


# ============================================================
# Priority order — multiple match → priority quyết định
# Priority: defensive > tam_su > refusal > khong_biet > edit > affirmative
# ============================================================


class TestPriority:
    def test_defensive_beats_affirmative(self):
        """'ok, nhưng lừa đảo à' → DEFENSIVE (priority > AFFIRMATIVE)."""
        result = detect_intent_layer1("ok nhưng lừa đảo à")
        assert result == Intent.DEFENSIVE

    def test_defensive_beats_tam_su(self):
        """Message vừa tâm sự vừa defensive → DEFENSIVE (priority cao hơn)."""
        result = detect_intent_layer1("vợ tôi bảo tôi không nên tin, lừa đảo à?")
        assert result == Intent.DEFENSIVE

    def test_refusal_beats_khong_biet(self):
        result = detect_intent_layer1("không biết, không cần")
        assert result == Intent.REFUSAL

    def test_khong_biet_beats_affirmative(self):
        """'ok không biết' → KHONG_BIET."""
        result = detect_intent_layer1("ok không biết đâu")
        assert result == Intent.KHONG_BIET
