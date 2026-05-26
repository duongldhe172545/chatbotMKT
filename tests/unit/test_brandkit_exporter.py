"""Unit test cho brandkit_exporter (CORE H.4 bản #2 cho designer team)."""
from __future__ import annotations

import json

import pytest

from app.core.brandkit_exporter import (
    export_brandkit_pack,
    export_brandkit_pack_json,
)
from app.models.schema import DealerProfileRaw


@pytest.fixture
def full_profile() -> DealerProfileRaw:
    """Profile đầy đủ Scope 1 + Scope 2 sau CONFIRMING."""
    return DealerProfileRaw(
        owner_name="Dương Lê",
        dealer_name="Nhôm Kính Dương Lê",
        address="Số 12, Quận 1, TP HCM",
        province="TP HCM",
        district="Quận 1",
        phone_or_zalo="0912345678",
        zalo="0912345678",
        facebook="fb.com/duongle",
        main_product="cửa nhôm kính",
        main_category="cua_nhom_kinh",
        business_model_signal="có xưởng + đội lắp đặt",
        supplier_brands=["Xingfa", "Việt Pháp"],
        color_accent="xanh dương",
        feng_shui_signal="mệnh Mộc",
        brandkit_consent="yes",
        # Auto-derive Scope 2
        brand_name_short="Dương Lê",
        initials_full="NKDL",
        initial_single="D",
        contact_name="Dương Lê",
        contact_role="Chủ cửa hàng",
        hotline="0912345678",
        slogan_options=[
            "Dương Lê - Cửa nhôm bền đẹp",
            "Dương Lê - Uy tín 10 năm",
            "Dương Lê - Lắp đặt chuyên nghiệp",
        ],
    )


@pytest.fixture
def minimal_profile() -> DealerProfileRaw:
    """Profile chỉ có 6 REQUIRED, không có optional/derive."""
    return DealerProfileRaw(
        owner_name="Tuấn",
        dealer_name="Tuấn Store",
        address="Hà Nội",
        phone_or_zalo="0987654321",
        main_product="tủ bếp",
        brandkit_consent="yes",
    )


class TestExportBrandkitPackStructure:
    def test_has_4_sections(self, full_profile):
        pack = export_brandkit_pack(full_profile, session_id="abc123")
        assert "logo_elements" in pack
        assert "color_scheme" in pack
        assert "namecard" in pack
        assert "video_config" in pack

    def test_has_metadata(self, full_profile):
        pack = export_brandkit_pack(full_profile, session_id="abc123")
        assert pack["version"] == "v1"
        assert pack["session_id"] == "abc123"
        assert "exported_at" in pack
        # ISO 8601 format
        assert "T" in pack["exported_at"]

    def test_session_id_optional(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        assert pack["session_id"] is None


class TestLogoElements:
    def test_full_logo(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        logo = pack["logo_elements"]
        assert logo["dealer_name"] == "Nhôm Kính Dương Lê"
        assert logo["brand_name_short"] == "Dương Lê"
        assert logo["initials_full"] == "NKDL"
        assert logo["initial_single"] == "D"
        assert logo["main_product"] == "cửa nhôm kính"
        assert logo["main_category"] == "cua_nhom_kinh"

    def test_minimal_logo(self, minimal_profile):
        pack = export_brandkit_pack(minimal_profile)
        logo = pack["logo_elements"]
        assert logo["dealer_name"] == "Tuấn Store"
        # Chưa có auto-derive
        assert logo["brand_name_short"] is None
        assert logo["initials_full"] is None


class TestColorScheme:
    def test_full_color(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        color = pack["color_scheme"]
        assert color["color_accent"] == "xanh dương"
        assert color["feng_shui_signal"] == "mệnh Mộc"
        assert color["designer_hint"] is None  # Đã có color → no hint

    def test_designer_hint_when_no_color(self, minimal_profile):
        pack = export_brandkit_pack(minimal_profile)
        color = pack["color_scheme"]
        assert color["color_accent"] is None
        assert color["designer_hint"] is not None
        assert "main_category" in color["designer_hint"]


class TestNamecard:
    def test_full_namecard(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        nc = pack["namecard"]
        assert nc["owner_name"] == "Dương Lê"
        assert nc["hotline"] == "0912345678"
        assert nc["phone_or_zalo"] == "0912345678"
        assert nc["facebook"] == "fb.com/duongle"
        assert nc["address"] == "Số 12, Quận 1, TP HCM"
        assert nc["province"] == "TP HCM"
        assert nc["district"] == "Quận 1"


class TestVideoConfig:
    def test_defaults(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        vid = pack["video_config"]
        assert vid["duration_seconds"] == 8
        assert vid["aspect_ratio"] == "16:9"

    def test_brand_name_prefer_short(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        vid = pack["video_config"]
        # Có brand_name_short → dùng
        assert vid["brand_name"] == "Dương Lê"

    def test_brand_name_fallback_dealer_name(self, minimal_profile):
        pack = export_brandkit_pack(minimal_profile)
        vid = pack["video_config"]
        # Không có brand_name_short → fallback dealer_name
        assert vid["brand_name"] == "Tuấn Store"

    def test_slogan_options_parsed(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        slogans = pack["video_config"]["slogan_options"]
        assert isinstance(slogans, list)
        assert len(slogans) == 3
        assert "Dương Lê" in slogans[0]

    def test_slogan_empty_when_no_options(self, minimal_profile):
        pack = export_brandkit_pack(minimal_profile)
        slogans = pack["video_config"]["slogan_options"]
        assert slogans == []

    def test_tone_hint_xuong(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        # business_model = "có xưởng + đội lắp đặt" → professional
        assert pack["video_config"]["tone_hint"] == "professional"

    def test_tone_hint_neutral_default(self, minimal_profile):
        pack = export_brandkit_pack(minimal_profile)
        assert pack["video_config"]["tone_hint"] == "neutral"


class TestNoScope4Leak:
    """CRITICAL: pack KHÔNG được chứa Scope 4 (scoring/tier/dealer_id)."""

    def test_no_tier(self, full_profile):
        pack = export_brandkit_pack(full_profile)
        pack_str = json.dumps(pack, ensure_ascii=False).lower()
        forbidden = ["tier", "c_score", "c1", "c2", "c3", "c4", "c5",
                     "c6", "c7", "c8", "c9", "batch", "dealer_id",
                     "scoring", "review_status"]
        for word in forbidden:
            # "c1" có thể match trong text khác — kiểm tra context strict
            if word.startswith("c") and len(word) == 2:
                # \bc1\b style check
                import re
                assert not re.search(rf"\b{word}\b", pack_str), \
                    f"Scope 4 leak: {word!r}"
            else:
                assert word not in pack_str, f"Scope 4 leak: {word!r}"


class TestExportJsonString:
    def test_returns_valid_json(self, full_profile):
        s = export_brandkit_pack_json(full_profile, session_id="abc")
        parsed = json.loads(s)
        assert parsed["session_id"] == "abc"

    def test_pretty_print_default(self, full_profile):
        s = export_brandkit_pack_json(full_profile, indent=2)
        # Indent=2 → có newlines
        assert "\n" in s

    def test_compact(self, full_profile):
        s = export_brandkit_pack_json(full_profile, indent=0)
        # Indent=0 → compact (no newlines)
        assert "\n" not in s

    def test_utf8_vietnamese(self, full_profile):
        s = export_brandkit_pack_json(full_profile)
        # ensure_ascii=False → giữ tiếng Việt
        assert "Dương" in s
