"""Test address_blacklist module — refer KICH_BAN_1C § 10."""
from __future__ import annotations

import pytest

from app.core.address_blacklist import (
    check_address_blacklist,
    clear_cache,
    get_all_keywords,
    is_blacklisted,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


class TestLoadBlacklist:
    def test_load_returns_3_categories(self):
        keywords = get_all_keywords()
        # Có ít nhất 3 category (chinh_tri / ton_giao / vung_mien_slur)
        # mỗi category có ≥ 3 keyword
        assert len(keywords) >= 9

    def test_all_keywords_lowercase(self):
        for kw in get_all_keywords():
            assert kw == kw.lower(), f"keyword không lowercase: {kw!r}"


class TestCheckAddressBlacklist:
    @pytest.mark.parametrize("text,expected_cat", [
        ("123 bác hồ phường 5", "chinh_tri"),
        ("Lăng Bác Hà Nội", "chinh_tri"),
        ("số 7 Tô Lâm Q1", "chinh_tri"),
        ("đường Đức Phật quận 10", "ton_giao"),
        ("phố Allah Hà Nội", "ton_giao"),
        ("Bắc Kỳ xa quá", "vung_mien_slur"),
        ("Nam Kỳ này khác", "vung_mien_slur"),
    ])
    def test_blacklist_hit(self, text, expected_cat):
        assert check_address_blacklist(text) == expected_cat

    @pytest.mark.parametrize("text", [
        "123 Lê Lợi, Quận 1, TP.HCM",
        "Hoàn Kiếm Hà Nội",
        "Đà Nẵng đường Trần Phú",
        "Cao Bằng",
    ])
    def test_clean_address_no_match(self, text):
        assert check_address_blacklist(text) is None

    def test_none_input(self):
        assert check_address_blacklist(None) is None
        assert check_address_blacklist("") is None
        assert check_address_blacklist("   ") is None

    def test_case_insensitive(self):
        assert check_address_blacklist("123 BÁC HỒ phường") == "chinh_tri"
        assert check_address_blacklist("ALLAH district") == "ton_giao"


class TestIsBlacklisted:
    def test_wrapper_returns_bool(self):
        assert is_blacklisted("bác hồ") is True
        assert is_blacklisted("Hoàn Kiếm Hà Nội") is False
        assert is_blacklisted(None) is False


class TestIntegrationWithValidator:
    """Verify validate_address vẫn dùng blacklist."""

    def test_validator_rejects_blacklist(self):
        from app.llm.extractors.validators import validate_address
        ok, _ = validate_address("Lăng Bác Hà Nội")
        assert ok is False

    def test_validator_accepts_clean(self):
        from app.llm.extractors.validators import validate_address
        ok, cleaned = validate_address("123 Lê Lợi, Quận 1, TP.HCM")
        assert ok is True
        assert cleaned == "123 Lê Lợi, Quận 1, TP.HCM"
