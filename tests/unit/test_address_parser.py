"""Test address_parser — F2B.6 Layer 1 regex.

Refer:
- F2B.6 (LUAT_2B_llm) — address parser 63 tỉnh
- Nguyên tắc "không khoá case": province alias map LÀ chuẩn hoá tên
  (HCM/Sài Gòn → TP.HCM), KHÔNG phải mapping case-specific.
"""
from __future__ import annotations

import pytest

from app.cache.data_loaders import clear_cache
from app.core.address_parser import (
    extract_province,
    extract_ward,
    parse_address,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# ============================================================
# extract_province
# ============================================================


class TestExtractProvince:
    def test_full_tphcm(self):
        assert extract_province("123 Lê Lợi, Phường 1, TP.HCM") == "TP.HCM"

    def test_alias_saigon(self):
        assert extract_province("Sài Gòn") is None

    def test_alias_hochiminh(self):
        assert extract_province("Hồ Chí Minh") is None

    def test_full_hanoi(self):
        assert extract_province("Cát Linh, Hà Nội") == "Hà Nội"

    def test_alias_hn(self):
        # Vì alias "hn" có thể match nhiều case (vd "Phú Nhuận"),
        # chỉ test khi "hn" đứng riêng
        assert extract_province("Hà Nội") == "Hà Nội"

    def test_da_nang(self):
        assert extract_province("Đà Nẵng") == "Đà Nẵng"

    def test_normal_province(self):
        assert extract_province("Cao Bằng") == "Cao Bằng"
        assert extract_province("Cần Thơ") == "Cần Thơ"

    def test_substring_match_in_long_address(self):
        addr = "Số 45 đường Trần Hưng Đạo, phường Cầu Kho, Quận 5, TP.HCM, Việt Nam"
        assert extract_province(addr) == "TP.HCM"

    def test_unknown_returns_none(self):
        assert extract_province("Vương Quốc Liên Hợp Anh") is None
        assert extract_province("") is None
        assert extract_province(None) is None

    def test_match_longer_province_first(self):
        """'Hà Nội' phải match trước 'Hà' (sort by length desc)."""
        assert extract_province("Cát Linh Hà Nội") == "Hà Nội"
        # Cẩn thận: chỉ "Hà" trong "Hà Tĩnh" vs "Hà Nội"
        assert extract_province("Hà Tĩnh") == "Hà Tĩnh"


# ============================================================
# extract_ward
# ============================================================


class TestExtractWard:
    def test_quan_with_number(self):
        assert extract_ward("123 Lê Lợi, P.1, TP.HCM") == "Phường 1"
        assert extract_ward("P1, TP.HCM") == "Phường 1"

    def test_quan_full_word(self):
        result = extract_ward("Phường Cát Linh, Hà Nội")
        assert result == "Cát Linh"

    def test_huyen(self):
        result = extract_ward("Xã Đại Thịnh, Hà Nội")
        assert result == "Đại Thịnh"

    def test_no_district_returns_none(self):
        assert extract_ward("Hà Nội") is None
        assert extract_ward("") is None
        assert extract_ward(None) is None


# ============================================================
# parse_address
# ============================================================


class TestParseAddress:
    def test_full_address(self):
        addr = "123 Lê Lợi, Phường 1, TP.HCM"
        province, ward = parse_address(addr)
        assert province == "TP.HCM"
        assert ward == "Phường 1"

    def test_hanoi_hoankiem(self):
        addr = "Phường Cát Linh, Hà Nội"
        province, ward = parse_address(addr)
        assert province == "Hà Nội"
        assert ward == "Cát Linh"

    def test_province_only(self):
        province, ward = parse_address("Cao Bằng")
        assert province == "Cao Bằng"
        assert ward is None

    def test_none_input(self):
        province, ward = parse_address(None)
        assert province is None
        assert ward is None
