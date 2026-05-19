"""Test brand whitelist check — refer 1C § 11."""
from __future__ import annotations

import pytest

from app.core.brand_check import (
    clear_cache,
    get_all_brands,
    get_unknown_brands,
    is_brand_known,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


class TestIsBrandKnown:
    @pytest.mark.parametrize("brand", [
        "Xingfa", "xingfa", "XINGFA",
        "Việt Pháp", "việt pháp",
        "PMA", "pma",
        "Austdoor",
        "Blum",
    ])
    def test_known_brand(self, brand):
        assert is_brand_known(brand) is True

    @pytest.mark.parametrize("brand", [
        "XYZ Premium 999",
        "Hãng Lạ Random",
        "ABC Door",
        "",
        "   ",
    ])
    def test_unknown_brand(self, brand):
        assert is_brand_known(brand) is False

    def test_none_brand(self):
        assert is_brand_known(None) is False

    def test_case_insensitive_match(self):
        assert is_brand_known("XingFa") is True
        assert is_brand_known("xINGFA") is True


class TestGetUnknownBrands:
    def test_all_known(self):
        result = get_unknown_brands(["Xingfa", "PMA", "Blum"])
        assert result == []

    def test_mixed(self):
        """ADVERSARIAL: dealer kê 1 known + 1 unknown → trả 1 unknown."""
        result = get_unknown_brands(["Xingfa", "XYZ Random Brand"])
        assert result == ["XYZ Random Brand"]

    def test_all_unknown(self):
        result = get_unknown_brands(["ABC", "XYZ", "Foo"])
        assert set(result) == {"ABC", "XYZ", "Foo"}

    def test_empty_list(self):
        assert get_unknown_brands([]) == []

    def test_none_input(self):
        assert get_unknown_brands(None) == []


class TestGetAllBrands:
    def test_returns_list(self):
        brands = get_all_brands()
        assert isinstance(brands, list)
        # Lowercase trong whitelist set
        assert "xingfa" in brands
        assert "pma" in brands

    def test_sorted(self):
        brands = get_all_brands()
        assert brands == sorted(brands)
