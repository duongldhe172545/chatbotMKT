"""Test data loaders. Refer F2C.7.

Sau refactor "không khoá case" (2026-05-18):
- BỎ get_province_specialty_map + get_specialty (lookup table CASE).
- BỎ find_category_by_keyword (substring match CASE).
- GIỮ get_province_list (LUẬT enum 63 tỉnh).
- GIỮ get_main_category_list nhưng schema chỉ còn code + name (không keywords).
"""
from __future__ import annotations

import pytest

from app.cache.data_loaders import (
    clear_cache,
    get_category_codes,
    get_category_name,
    get_main_category_list,
    get_province_list,
    is_valid_province,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# ============================================================
# Province list — 63 tỉnh (LUẬT enum)
# ============================================================


class TestProvinceList:
    def test_has_63_provinces(self):
        """Phase 1 giữ 63 tỉnh VN (refer C3 batch 4)."""
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
# Main category enum — 7 loại (LUẬT enum)
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

    def test_each_category_has_code_and_name(self):
        for cat in get_main_category_list():
            assert "code" in cat
            assert "name" in cat
            assert isinstance(cat["code"], str)
            assert isinstance(cat["name"], str)

    def test_no_keywords_field(self):
        """Sau refactor 2026-05-18: bỏ keywords (khoá case)."""
        for cat in get_main_category_list():
            assert "keywords" not in cat, (
                f"Category {cat.get('code')} vẫn còn keywords[] — "
                f"vi phạm nguyên tắc 'không khoá case'"
            )

    def test_get_category_name(self):
        assert get_category_name("cua_cuon") == "Cửa cuốn"
        assert get_category_name("cua_nhom_kinh") == "Cửa nhôm kính"
        assert get_category_name("nonexistent") is None
