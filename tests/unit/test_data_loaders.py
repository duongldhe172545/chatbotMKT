"""Test data loaders. Refer F2C.7."""
from __future__ import annotations

import pytest

from app.cache.data_loaders import (
    clear_cache,
    find_category_by_keyword,
    get_category_codes,
    get_main_category_list,
    get_province_list,
    get_province_specialty_map,
    get_specialty,
    is_valid_province,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# ============================================================
# Province list — 63 tỉnh
# ============================================================


class TestProvinceList:
    def test_has_63_provinces(self):
        """Phase 1 giữ 63 tỉnh VN cũ (refer C3 batch 4)."""
        provinces = get_province_list()
        assert len(provinces) == 63

    def test_includes_major_cities(self):
        provinces = get_province_list()
        for city in ["Hà Nội", "TP.HCM", "Đà Nẵng", "Hải Phòng", "Cần Thơ"]:
            assert city in provinces

    def test_is_valid_province(self):
        assert is_valid_province("Hà Nội") is True
        assert is_valid_province("TP.HCM") is True
        assert is_valid_province("Province không có") is False
        assert is_valid_province("") is False


# ============================================================
# Province specialty — 50 tỉnh có specialty
# ============================================================


class TestProvinceSpecialty:
    def test_has_50_specialties(self):
        """50/63 tỉnh có specialty (refer F2A.8)."""
        specialties = get_province_specialty_map()
        assert len(specialties) == 50

    def test_get_specialty_known(self):
        assert "vịt quay 7 vị" in (get_specialty("Cao Bằng") or "")
        assert "phở" in (get_specialty("Hà Nội") or "").lower()

    def test_get_specialty_unknown_returns_none(self):
        """Tỉnh không trong 50 → None (fallback generic)."""
        result = get_specialty("Province không có specialty")
        assert result is None

    def test_specialty_keys_subset_of_provinces(self):
        """Mọi key trong specialty map phải có trong province_list."""
        specialties = get_province_specialty_map()
        provinces = set(get_province_list())
        for key in specialties.keys():
            assert key in provinces, f"Specialty key '{key}' không có trong province_list"


# ============================================================
# Main category enum — 7 loại
# ============================================================


class TestMainCategory:
    def test_has_7_categories(self):
        """7 category cover ≥95% dealer ngành cửa/VLXD VN."""
        cats = get_main_category_list()
        assert len(cats) == 7

    def test_codes_are_unique(self):
        codes = get_category_codes()
        assert len(codes) == len(set(codes))

    def test_required_codes_present(self):
        codes = set(get_category_codes())
        for required in ["cua_cuon", "cua_nhom_kinh", "cua_thep", "tu_bep",
                         "solar", "bao_tri_sua_chua", "vlxd_tong_hop"]:
            assert required in codes

    @pytest.mark.parametrize("text,expected_code", [
        ("Tôi làm cửa cuốn", "cua_cuon"),
        ("nhôm kính cường lực", "cua_nhom_kinh"),
        ("tủ bếp acrylic", "tu_bep"),
        ("Xingfa hệ", "cua_nhom_kinh"),
        ("điện mặt trời", "solar"),
        ("bảo trì sửa chữa", "bao_tri_sua_chua"),
    ])
    def test_find_category_by_keyword(self, text, expected_code):
        assert find_category_by_keyword(text) == expected_code

    def test_find_category_no_match(self):
        assert find_category_by_keyword("xyz unrelated") is None
        assert find_category_by_keyword("") is None
        assert find_category_by_keyword(None) is None
