"""Test brand_correction module — refer F2B.5 + 1C § 8. Phase 4 R2."""
from __future__ import annotations

import pytest

from app.llm.brand_correction import (
    clear_cache,
    correct_brand,
    correct_stt,
    get_corrections_count,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


class TestCorrectStt:
    @pytest.mark.parametrize("typo,correct", [
        ("xinhpha", "Xingfa"),
        ("Xinh Pha", "Xingfa"),
        ("XINHPHA", "Xingfa"),
        ("shu cô", "Schüco"),
        ("rê na", "Reynaers"),
        ("hết tích", "Hettich"),
        ("blum", "Blum"),
        ("ốt đo", "Austdoor"),
        ("ha phê lê", "Hafele"),
    ])
    def test_brand_substitution(self, typo, correct):
        text = f"Anh nhập hãng {typo} lâu rồi"
        result = correct_stt(text)
        assert correct in result, f"Should contain {correct!r}: {result!r}"

    def test_multiple_brands_in_one_text(self):
        text = "Anh dùng xinhpha và blum chính"
        result = correct_stt(text)
        assert "Xingfa" in result
        assert "Blum" in result

    def test_longest_first_match(self):
        """'viet phap' phải replace cả cụm, không chỉ 'viet'."""
        text = "anh dùng viet phap chính"
        result = correct_stt(text)
        assert "Việt Pháp" in result

    def test_clean_text_unchanged(self):
        text = "Anh tên Tùng, cửa hàng Nhôm Kính Thanh Tùng"
        assert correct_stt(text) == text

    def test_word_boundary_no_partial_replace(self):
        """ADVERSARIAL: 'xinhphabar' KHÔNG match 'xinhpha' (cần \\b)."""
        text = "xinhphabar không phải brand"
        result = correct_stt(text)
        assert "Xingfa" not in result
        # Original giữ
        assert "xinhphabar" in result

    def test_none_input(self):
        assert correct_stt(None) == ""
        assert correct_stt("") == ""

    def test_vn_word_correction(self):
        text = "anh bán cửa cuồn"
        result = correct_stt(text)
        assert "cửa cuốn" in result


class TestCorrectBrand:
    def test_exact_match(self):
        assert correct_brand("xinhpha") == "Xingfa"
        assert correct_brand("Xinh Pha") == "Xingfa"

    def test_unknown_brand_kept(self):
        """ADVERSARIAL: brand không trong mapping → giữ nguyên (trim)."""
        assert correct_brand("XYZ Random") == "XYZ Random"
        assert correct_brand("  Xingfa  ") == "Xingfa"  # already correct

    def test_none_input(self):
        assert correct_brand(None) == ""
        assert correct_brand("") == ""


class TestCorrectionsCount:
    def test_at_least_some_corrections_loaded(self):
        count = get_corrections_count()
        assert count >= 20  # Min brand + common VN corrections
