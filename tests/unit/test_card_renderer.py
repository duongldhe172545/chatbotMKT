"""Test card render — 5 phần ASCII. Refer F2A.7 + CORE § H.2 + 1A § 6."""
from __future__ import annotations

from app.core.card_renderer import render_card
from app.models.schema import DealerProfileRaw


# ============================================================
# Structure — 5 phần đầy đủ
# ============================================================


class TestCardStructure:
    def test_has_4_sections(self):
        """Card rút gọn 4 phần (feedback 2026-06-10) — bỏ phần KHÁCH CŨ (PV data)."""
        profile = _full_profile()
        text = render_card(profile)
        assert "🏪 DANH THIẾP" in text
        assert "🛠 CÔNG VIỆC" in text
        assert "🎁 BỘ THƯƠNG HIỆU" in text
        assert "⏰ TRONG 3 NGÀY TỚI" in text

    def test_no_interview_data_on_card(self):
        """Card KHÔNG hiển thị dữ liệu phỏng vấn — chỉ info làm bộ thương hiệu.

        Dữ liệu PV (khách cũ, thanh toán, bảo hành, đội thợ, hãng nhập) vẫn
        lưu DB + xuất md_exporter cho admin.
        """
        profile = _full_profile()
        profile.customer_old_percentage = "nhiều"
        profile.customer_storage_method = "sổ tay"
        profile.payment_terms_signal = "cọc 50%"
        profile.warranty_responsibility_signal = "bảo hành 5 năm"
        profile.est_team_size = 4
        profile.supplier_brands = ["Xingfa", "Topal"]
        profile.primary_contact_channel = "zalo"
        text = render_card(profile)
        assert "KHÁCH CŨ" not in text
        assert "sổ tay" not in text
        assert "cọc 50%" not in text
        assert "bảo hành 5 năm" not in text
        assert "Đội thợ" not in text
        assert "Xingfa" not in text
        assert "Kênh khách liên hệ" not in text

    def test_starts_with_header(self):
        text = render_card(_full_profile())
        assert "HỒ SƠ CỬA HÀNG" in text

    def test_ends_with_review_prompt(self):
        text = render_card(_full_profile())
        assert "duyệt" in text or "chỉnh" in text


# ============================================================
# Section 1 — Danh thiếp (3 REQUIRED slot)
# ============================================================


class TestSection1:
    def test_shows_owner_name(self):
        profile = _full_profile()
        profile.owner_name = "Tùng"
        text = render_card(profile)
        assert "Tùng" in text

    def test_shows_dealer_name(self):
        profile = _full_profile()
        profile.dealer_name = "Nhôm Kính Thanh Tùng"
        text = render_card(profile)
        assert "Nhôm Kính Thanh Tùng" in text

    def test_required_missing_shows_placeholder(self):
        """REQUIRED null → placeholder '(chưa có — team em sẽ hỏi lại sau)'."""
        profile = _full_profile()
        profile.owner_name = None
        text = render_card(profile)
        assert "(chưa có" in text


# ============================================================
# Section 4 — Brandkit consent=no
# ============================================================


class TestSection4Brandkit:
    def test_consent_yes_shows_check(self):
        profile = _full_profile()
        profile.brandkit_consent = "yes"
        text = render_card(profile)
        assert "Có" in text and "✓" in text

    def test_consent_no_shows_x(self):
        profile = _full_profile()
        profile.brandkit_consent = "no"
        text = render_card(profile)
        # Phần BỘ THƯƠNG HIỆU chỉ show "Không ✗" — KHÔNG show logo/màu lines
        assert "Không" in text and "✗" in text

    def test_consent_no_omits_logo_and_color(self):
        """consent=no → KHÔNG render phong cách logo + màu (D10 STRATEGY)."""
        profile = _full_profile()
        profile.brandkit_consent = "no"
        text = render_card(profile)
        # Section 4 chỉ có 1 dòng "Đồng ý nhận: Không"
        assert "Phong cách logo" not in text

    def test_consent_yes_shows_logo_and_color(self):
        profile = _full_profile()
        profile.brandkit_consent = "yes"
        profile.color_accent = "đỏ"
        text = render_card(profile)
        assert "Phong cách logo" in text
        assert "đỏ" in text


# ============================================================
# Section 5 — Trong 3 ngày tới
# ============================================================


class TestSection5:
    def test_consent_yes_mentions_brandkit_delivery(self):
        profile = _full_profile()
        profile.brandkit_consent = "yes"
        text = render_card(profile)
        assert "Bộ thương hiệu" in text or "bộ thương hiệu" in text
        assert "Zalo" in text

    def test_consent_no_simpler_5_section(self):
        profile = _full_profile()
        profile.brandkit_consent = "no"
        text = render_card(profile)
        # Vẫn có hồ sơ số + Zalo
        assert "Zalo" in text

    def test_no_strategy_plan_promise(self):
        """Feedback 2026-06-10: KHÔNG hứa 'kế hoạch chiến lược nền tảng số'."""
        for consent in ("yes", "no"):
            profile = _full_profile()
            profile.brandkit_consent = consent
            text = render_card(profile)
            assert "kế hoạch chiến lược" not in text
            assert "chiến lược nền tảng" not in text

    def test_promises_quote_and_digital_profile(self):
        """Cam kết mới: bộ nhận diện + hồ sơ số + mẫu báo giá."""
        profile = _full_profile()
        profile.brandkit_consent = "yes"
        text = render_card(profile)
        assert "hồ sơ số" in text
        assert "báo giá" in text


# ============================================================
# Null handling — Phase 1 many null fields
# ============================================================


class TestNullHandling:
    def test_phase_1_partial_profile(self):
        """Phase 1: 3 REQUIRED filled, OPTIONAL slots null."""
        profile = DealerProfileRaw(
            owner_name="Tùng",
            dealer_name="Cửa Hàng Tùng",
            address="HCM",
            phone_or_zalo=None,  # Phase 1 chưa thu
            main_product=None,
            brandkit_consent="yes",
        )
        text = render_card(profile)
        # Section 2 (CÔNG VIỆC) empty → placeholder
        assert "chưa thu thập" in text or "—" in text

    def test_phone_null_shows_placeholder(self):
        profile = _full_profile()
        profile.phone_or_zalo = None
        text = render_card(profile)
        assert "(chưa có" in text


# ============================================================
# Vocab compliance — no Tier/C-score in card
# ============================================================


class TestCardVocab:
    def test_no_forbidden_vocab_with_full_profile(self):
        """Refer CORE § H.2 batch 2: TUYỆT ĐỐI KHÔNG hiển thị C1..C9/Tier/C-score."""
        profile = _full_profile()
        text = render_card(profile)
        forbidden = ["Tier", "C-score", "Scoring", "BRANDKIT",
                     "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]
        for word in forbidden:
            assert word not in text, \
                f"Card chứa vocab cấm '{word}'"


# ============================================================
# Helper
# ============================================================


def _full_profile() -> DealerProfileRaw:
    return DealerProfileRaw(
        owner_name="Tùng",
        dealer_name="Nhôm Kính Thanh Tùng",
        address="123 Lê Lợi Q.1 TP.HCM",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm kính",
        brandkit_consent="yes",
        category_stack=["cua_nhom_kinh"],
        province="TP.HCM",
        main_category="cua_nhom_kinh",
    )



# ============================================================
# Phase 5 R5 Gap 16 — Adversarial null handling
# ============================================================


class TestNullHandling:
    def test_completely_empty_profile_no_crash(self):
        """ADVERSARIAL: profile rỗng hoàn toàn → card render OK, không crash."""
        from app.models.schema import DealerProfileRaw
        empty = DealerProfileRaw()
        text = render_card(empty)
        # Có 4 phần header (card rút gọn 2026-06-10)
        assert "DANH THIẾP" in text
        assert "CÔNG VIỆC" in text
        assert "BỘ THƯƠNG HIỆU" in text
        assert "TRONG 3 NGÀY" in text
        # REQUIRED null → placeholder
        assert "(chưa có" in text

    def test_empty_string_treated_as_null(self):
        """ADVERSARIAL: chuỗi rỗng "" cũng → placeholder."""
        from app.models.schema import DealerProfileRaw
        p = DealerProfileRaw(owner_name="", dealer_name="   ")
        text = render_card(p)
        assert "(chưa có" in text

    def test_partial_section_2_empty_placeholder(self):
        """Phần 2 không có field nào → placeholder (chưa thu thập phần này)."""
        profile = _full_profile()
        # Clear all section 2 fields
        profile.main_product = None
        profile.category_stack = []
        profile.business_model_signal = None
        text = render_card(profile)
        assert "chưa thu thập" in text

    def test_facebook_optional_skipped_when_null(self):
        """OPTIONAL null → skip line (không render rác)."""
        profile = _full_profile()
        profile.facebook = None
        text = render_card(profile)
        # KHÔNG có dòng Facebook trống
        assert "Facebook:" not in text

    def test_team_size_not_on_card(self):
        """Đội thợ là dữ liệu PV → KHÔNG hiển thị trên card (vẫn ở md_exporter)."""
        profile = _full_profile()
        profile.est_team_size = 4
        text = render_card(profile)
        assert "Đội thợ" not in text


# ============================================================
# Feedback 2026-06-10 — logo hiện có + màu "(auto)"
# ============================================================


class TestLogoExistingIntent:
    def test_unclarified_shows_followup_note(self):
        profile = _full_profile()
        profile.logo_existing_intent = "unclarified"
        text = render_card(profile)
        assert "Nhu cầu logo" in text

    def test_upgrade_hides_bot_style_line(self):
        """Dealer giữ logo cũ (upgrade/redesign) → bot KHÔNG tự chọn phong cách."""
        profile = _full_profile()
        profile.logo_existing_intent = "upgrade"
        text = render_card(profile)
        assert "nâng cấp logo hiện có" in text
        assert "Phong cách logo" not in text

    def test_redesign_shows_display_name(self):
        profile = _full_profile()
        profile.logo_existing_intent = "redesign"
        text = render_card(profile)
        assert "thiết kế lại bố cục/màu" in text

    def test_new_keeps_bot_style_line(self):
        profile = _full_profile()
        profile.logo_existing_intent = "new"
        text = render_card(profile)
        assert "làm mới hoàn toàn" in text
        assert "Phong cách logo" in text

    def test_no_intent_renders_as_before(self):
        profile = _full_profile()
        profile.logo_existing_intent = None
        text = render_card(profile)
        assert "Nhu cầu logo" not in text
        assert "Phong cách logo" in text


class TestColorAutoSuffix:
    def test_feng_shui_auto_not_displayed(self):
        """Fix bug card thật: '... (Em đề xuất) (auto)' — ẩn feng_shui='auto'."""
        profile = _full_profile()
        profile.color_accent = "auto"
        profile.feng_shui_signal = "auto"
        text = render_card(profile)
        assert "(auto)" not in text
        assert "(Em đề xuất)" in text

    def test_real_feng_shui_still_displayed(self):
        profile = _full_profile()
        profile.color_accent = "xanh dương"
        profile.feng_shui_signal = "hợp mệnh Thủy"
        text = render_card(profile)
        assert "hợp mệnh Thủy" in text
