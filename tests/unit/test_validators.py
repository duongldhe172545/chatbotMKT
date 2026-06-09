"""Test field validators. Refer F2A.7 sanity check + F2B.2."""
from __future__ import annotations

import pytest

from app.llm.extractors.validators import (
    validate_address,
    validate_brandkit_consent,
    validate_field,
    validate_free_text,
    validate_name,
    validate_phone,
)


# ============================================================
# Phone
# ============================================================


class TestValidatePhone:
    @pytest.mark.parametrize("raw,expected", [
        ("0912345678", "0912345678"),
        ("0912 345 678", "0912345678"),  # strip spaces
        ("0912-345-678", "0912345678"),  # strip dashes
        ("0912.345.678", "0912345678"),  # strip dots
        ("(091) 2345-678", "0912345678"),  # strip parens
        ("02412345678", "02412345678"),  # landline
        ("84912345678", "0912345678"),  # international - normalized 84 to 0
        ("0123456789", "0123456789"),  # previously retired, now valid
        ("0134289121", "0134289121"),  # previously retired, now valid
    ])
    def test_valid_phone_formats(self, raw, expected):
        ok, cleaned = validate_phone(raw)
        assert ok is True
        assert cleaned == expected

    @pytest.mark.parametrize("raw", [
        None,
        "",
        "   ",
        "abc",
        "0912",  # quá ngắn
        "0912345678901234",  # quá dài
        "1234567890",  # không start với 0/84
        "+84912345678",  # có dấu +
        "+",
    ])
    def test_invalid_phone(self, raw):
        ok, cleaned = validate_phone(raw)
        assert ok is False
        assert cleaned is None


# ============================================================
# Address
# ============================================================


class TestValidateAddress:
    @pytest.mark.parametrize("raw", [
        "123 Lê Lợi, P. Bến Nghé, Quận 1, TP.HCM",
        "Quận 1, TP.HCM",
        "123 Trần Hưng Đạo",
        "HN",  # 2 char không pass
    ])
    def test_valid_address_basic(self, raw):
        ok, cleaned = validate_address(raw)
        if len(raw.strip()) >= 3:
            assert ok is True
            assert cleaned == raw.strip()
        else:
            assert ok is False

    def test_strip_whitespace(self):
        ok, cleaned = validate_address("  123 Lê Lợi  ")
        assert ok is True
        assert cleaned == "123 Lê Lợi"

    @pytest.mark.parametrize("raw", [
        None,
        "",
        "  ",
        "ab",  # < 3 char
    ])
    def test_invalid_address(self, raw):
        ok, _ = validate_address(raw)
        assert ok is False

    def test_too_long(self):
        ok, _ = validate_address("a" * 501)
        assert ok is False

    @pytest.mark.parametrize("blacklist_msg", [
        "Lăng Bác Hà Nội",
        "Đường tô lâm Quận 1",
        "Gần Lăng Bác",
        "Khu vực đức phật",
        "Bắc kỳ chiến lược",
    ])
    def test_blacklist_rejected(self, blacklist_msg):
        """Address chính trị/tôn giáo/vùng miền slur → REJECT (refer 1C § 10)."""
        ok, _ = validate_address(blacklist_msg)
        assert ok is False


# ============================================================
# Brandkit consent
# ============================================================


class TestValidateBrandkitConsent:
    def test_yes(self):
        ok, cleaned = validate_brandkit_consent("yes")
        assert ok is True
        assert cleaned == "yes"

    def test_no(self):
        ok, cleaned = validate_brandkit_consent("no")
        assert ok is True
        assert cleaned == "no"

    @pytest.mark.parametrize("invalid", [
        None,
        "",
        "YES",  # case sensitive
        "có",
        "không",
        "true",
        "maybe",
    ])
    def test_invalid(self, invalid):
        ok, _ = validate_brandkit_consent(invalid)
        assert ok is False


# ============================================================
# Name
# ============================================================


class TestValidateName:
    @pytest.mark.parametrize("raw,expected", [
        ("Tùng", "Tùng"),
        ("Nguyễn Văn A", "Nguyễn Văn A"),
        ("Nhôm Kính Thanh Tùng", "Nhôm Kính Thanh Tùng"),
        ("  Tùng  ", "Tùng"),
    ])
    def test_valid_names(self, raw, expected):
        ok, cleaned = validate_name(raw)
        assert ok is True
        assert cleaned == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_empty(self, raw):
        ok, _ = validate_name(raw)
        assert ok is False

    def test_too_long(self):
        ok, _ = validate_name("a" * 201)
        assert ok is False


# ============================================================
# Free text
# ============================================================


class TestValidateFreeText:
    def test_short_text_ok(self):
        ok, cleaned = validate_free_text("khách đến từ 5km")
        assert ok is True
        assert cleaned == "khách đến từ 5km"

    def test_long_text_with_custom_max(self):
        text = "a" * 1500
        ok, _ = validate_free_text(text, max_len=2000)
        assert ok is True
        ok, _ = validate_free_text(text, max_len=1000)
        assert ok is False

    def test_empty(self):
        ok, _ = validate_free_text("")
        assert ok is False


# ============================================================
# Dispatch validate_field
# ============================================================


class TestValidateField:
    def test_dispatch_phone(self):
        ok, cleaned = validate_field("phone_or_zalo", "0912345678")
        assert ok is True
        assert cleaned == "0912345678"

    def test_dispatch_address(self):
        ok, cleaned = validate_field("address", "Q.1 TP.HCM")
        assert ok is True

    def test_dispatch_consent(self):
        ok, cleaned = validate_field("brandkit_consent", "yes")
        assert ok is True
        assert cleaned == "yes"

    def test_dispatch_unknown_field_passthrough(self):
        """Field không có validator → passthrough (giữ value nếu non-None)."""
        ok, cleaned = validate_field("some_unknown_field", "value")
        assert ok is True
        assert cleaned == "value"

    def test_dispatch_raw_signal_field(self):
        """Free text validator cho raw signal field."""
        ok, cleaned = validate_field(
            "local_dominance_signal",
            "khách đến từ 5km xung quanh"
        )
        assert ok is True

    def test_dispatch_category_stack(self):
        ok, cleaned = validate_field("category_stack", "tủ bếp, nhôm kính")
        assert ok is True
        assert cleaned == ["tu_bep", "cua_nhom_kinh"]

    def test_dispatch_supplier_brands(self):
        ok, cleaned = validate_field("supplier_brands", "Xingfa, PMA")
        assert ok is True
        assert cleaned == ["Xingfa", "PMA"]


# ============================================================
# List Validators
# ============================================================

class TestValidateCategoryStack:
    def test_valid_list(self):
        from app.llm.extractors.validators import validate_category_stack
        ok, cleaned = validate_category_stack(["tu_bep", "cua_nhom_kinh"])
        assert ok is True
        assert cleaned == ["tu_bep", "cua_nhom_kinh"]

    def test_valid_string_comma_separated(self):
        from app.llm.extractors.validators import validate_category_stack
        ok, cleaned = validate_category_stack("tủ bếp, cửa cuốn, nhôm kính")
        assert ok is True
        assert cleaned == ["tu_bep", "cua_cuon", "cua_nhom_kinh"]

    def test_invalid_values(self):
        from app.llm.extractors.validators import validate_category_stack
        ok, cleaned = validate_category_stack(None)
        assert ok is False
        ok, cleaned = validate_category_stack("không liên quan")
        assert ok is False


class TestValidateSupplierBrands:
    def test_valid_list(self):
        from app.llm.extractors.validators import validate_supplier_brands
        ok, cleaned = validate_supplier_brands(["Xingfa", "PMA"])
        assert ok is True
        assert cleaned == ["Xingfa", "PMA"]

    def test_valid_string_comma_separated(self):
        from app.llm.extractors.validators import validate_supplier_brands
        ok, cleaned = validate_supplier_brands("Xingfa, PMA; Schüco")
        assert ok is True
        assert cleaned == ["Xingfa", "PMA", "Schüco"]
