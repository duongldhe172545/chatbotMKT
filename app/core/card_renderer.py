"""Card render — confirmation card 5 phần ASCII.

Refer:
- F2A.7 sanity check (chạy TRƯỚC render card)
- CORE § H.2 v3.0.5 — 5 phần principle (gộp Kênh online + thêm "Trong 3 ngày tới")
- File 1A § 6.3 + § 6.4 — template ASCII đầy đủ + render rule cho null
"""
from __future__ import annotations

from typing import Optional

from app.models.schema import DealerProfileRaw


# Placeholder strings (Việt hóa)
_PLACEHOLDER_REQUIRED_MISSING = "(chưa có — team em sẽ hỏi lại sau)"
_PLACEHOLDER_OPTIONAL_DECLINED = "(em sẽ đề xuất, duyệt sau)"
_PLACEHOLDER_CATEGORY_EMPTY = "(chưa thu thập phần này)"


# Nhu cầu với logo hiện có — enum → display Việt (feedback 2026-06-10)
_LOGO_EXISTING_INTENT_DISPLAY: dict[str, str] = {
    "upgrade": "nâng cấp logo hiện có",
    "redesign": "thiết kế lại bố cục/màu từ logo hiện có",
    "new": "làm mới hoàn toàn",
    "unclarified": "(em sẽ hỏi thêm nhu cầu với logo hiện có)",
}


# Fix Lỗi 18: mapping category code → display name tiếng Việt
_CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "tu_bep": "tủ bếp",
    "nhom_kinh": "nhôm kính",
    "cua_cuon": "cửa cuốn",
    "cua_nhom": "cửa nhôm",
    "cua_go": "cửa gỗ",
    "cua_thep": "cửa thép",
    "cua_sat": "cửa sắt",
    "cua_chong_chay": "cửa chống cháy",
    "vlxd": "VLXD",
    "noi_that": "nội thất",
    "dien_mat_troi": "điện mặt trời",
    "kinh_cuong_luc": "kính cường lực",
}


def render_card(profile: DealerProfileRaw, address_form: str = "anh") -> str:
    """Render confirmation card 4 phần — CHỈ thông tin cơ bản để làm bộ thương hiệu.

    Feedback 2026-06-10: card cũ dump cả dữ liệu phỏng vấn (khách cũ, thanh toán,
    bảo hành...) nhìn như bảng khảo sát. Dữ liệu đó VẪN lưu DB + xuất đầy đủ qua
    md_exporter cho admin — chỉ card hiển thị cho dealer là rút gọn.
    """
    af = address_form
    lines: list[str] = []
    lines.append(f"📋 HỒ SƠ CỬA HÀNG — {af} duyệt giúp em ạ")
    lines.append("")

    # ----- Phần 1: 🏪 Danh thiếp cửa hàng -----
    lines.append(_render_section_1_danh_thiep(profile))
    lines.append("")

    # ----- Phần 2: 🛠 Công việc chính (rút gọn — chỉ ngành + mô hình) -----
    lines.append(_render_section_2_cong_viec(profile))
    lines.append("")

    # ----- Phần 3: 🎁 Bộ thương hiệu sẽ tặng -----
    lines.append(_render_section_4_brandkit(profile, af))
    lines.append("")

    # ----- Phần 4: ⏰ Trong 3 ngày tới -----
    lines.append(_render_section_5_trong_3_ngay(profile, af))
    lines.append("")

    lines.append("═" * 40)
    lines.append(f"{af.capitalize()} duyệt OK hay cần chỉnh chỗ nào ạ?")

    return "\n".join(lines)


# ============================================================
# Per-section renderers
# ============================================================


def _render_section_1_danh_thiep(profile: DealerProfileRaw) -> str:
    """Phần 1: Danh thiếp cửa hàng (slot 1.1, 1.2, 1.3 + facebook)."""
    lines = ["🏪 DANH THIẾP CỬA HÀNG"]
    lines.append(f"   • Chủ: {_fmt(profile.owner_name, required=True)}")
    lines.append(f"   • Tên cửa hàng: {_fmt(profile.dealer_name, required=True)}")
    lines.append(f"   • Địa chỉ: {_fmt(profile.address, required=True)}")
    lines.append(f"   • SĐT (Zalo): {_fmt(profile.phone_or_zalo, required=True)}")  # FIX M3
    if profile.facebook:
        lines.append(f"   • Facebook: {profile.facebook}")
    return "\n".join(lines)


def _render_section_2_cong_viec(profile: DealerProfileRaw) -> str:
    """Phần 2: Công việc chính — rút gọn còn ngành hàng + mô hình.

    Feedback 2026-06-10: bỏ đội thợ / hãng nhập / kênh liên hệ khỏi card
    (vẫn lưu DB + md_exporter). Card chỉ giữ info phục vụ làm bộ thương hiệu.
    """
    lines = ["🛠 CÔNG VIỆC CHÍNH"]
    if profile.main_product:
        lines.append(f"   • Sản phẩm mạnh nhất: {profile.main_product}")
    if profile.business_model_signal:
        lines.append(f"   • Mô hình: {profile.business_model_signal}")
    # Section empty (Phase 1: nhiều slot null) → placeholder
    if len(lines) == 1:
        lines.append(f"   {_PLACEHOLDER_CATEGORY_EMPTY}")
    return "\n".join(lines)


def get_default_color_for_profile(profile: DealerProfileRaw) -> str:
    category = (profile.main_category or "").lower()
    product = (profile.main_product or "").lower()

    if "bep" in product or "bep" in category:
        return "vàng hoàng kim phối đen"
    elif "dien" in product or "solar" in product or "dien_mat_troi" in category:
        return "xanh lục ngọc phối xám trắng"
    elif "cuon" in product or "cua_cuon" in category:
        return "ghi sáng phối xám đậm"
    # Default for nhôm kính or general
    return "xanh dương phối ghi bạc"


def _render_section_4_brandkit(profile: DealerProfileRaw, af: str = "anh") -> str:
    """Phần 4: Bộ thương hiệu sẽ tặng (slot 4.0, 4.1, 4.2)."""
    lines = ["🎁 BỘ THƯƠNG HIỆU SẼ TẶNG"]
    consent_display = "Có ✓" if profile.brandkit_consent == "yes" else (
        "Không ✗" if profile.brandkit_consent == "no" else _PLACEHOLDER_REQUIRED_MISSING
    )
    lines.append(f"   • Đồng ý nhận: {consent_display}")

    if profile.brandkit_consent == "yes":
        # Nhu cầu với logo hiện có (nếu dealer đã có logo)
        if profile.logo_existing_intent:
            intent_display = _LOGO_EXISTING_INTENT_DISPLAY.get(
                profile.logo_existing_intent, profile.logo_existing_intent
            )
            lines.append(f"   • Nhu cầu logo: {intent_display}")

        # Phong cách logo (4.1) — 1 DÒNG duy nhất (7.2: trước đây tách "Phong cách
        # logo" mặc định + "Gu logo" giá trị thật → 2 dòng trùng, lệch nhau).
        # Chỉ render khi KHÔNG giữ logo cũ (upgrade/redesign giữ phong cách cũ).
        if profile.logo_existing_intent not in ("upgrade", "redesign"):
            if profile.logo_style and profile.logo_style.casefold() != "auto":
                style_display = profile.logo_style
            elif profile.logo_style and profile.logo_style.casefold() == "auto":
                style_display = "Tối giản hiện đại (Em đề xuất)"
            else:
                raw_category = profile.main_category or "ngành mình"
                category_name = _CATEGORY_DISPLAY_NAMES.get(raw_category, raw_category)
                style_display = f"em chọn theo {category_name}"
            lines.append(f"   • Phong cách logo: {style_display}")

        # Màu + phong thủy (4.2)
        is_color_suggested = False
        color_info = profile.color_accent or ""
        if not color_info or color_info.casefold() == "auto":
            color_info = get_default_color_for_profile(profile)
            is_color_suggested = True

        if is_color_suggested:
            color_info += " (Em đề xuất)"
        # Fix 2026-06-10: feng_shui_signal="auto" từng bị append nguyên văn
        # thành "... (Em đề xuất) (auto)" trên card thật
        if profile.feng_shui_signal and profile.feng_shui_signal.casefold() != "auto":
            color_info += f" ({profile.feng_shui_signal})"
        lines.append(f"   • Màu chủ đạo: {color_info}")

        if profile.slogan_preference:
            if profile.slogan_preference == "auto":
                slogan = "Vững chất lượng, bền niềm tin (Em đề xuất)"
            else:
                slogan = profile.slogan_preference
            lines.append(f"   • Slogan: {slogan}")
        # (7.2) "Gu logo" gỡ bỏ — phong cách logo đã gộp vào 1 dòng ở trên.
        # (2026-06-24) bỏ "Viết tắt logo" — tàn dư luồng tự-gen-logo cũ.
    return "\n".join(lines)


def _render_section_5_trong_3_ngay(profile: DealerProfileRaw, af: str = "anh") -> str:
    """Phần cuối: Trong 3 ngày tới.

    Feedback 2026-06-10: chỉ hứa bộ nhận diện (+ hồ sơ số, mẫu báo giá nếu cần).
    KHÔNG hứa "kế hoạch chiến lược nền tảng số".
    """
    lines = ["⏰ TRONG 3 NGÀY TỚI"]
    if profile.brandkit_consent == "yes":
        lines.append(f"   • Bộ thương hiệu (logo + danh thiếp + video) gửi {af} trong ứng dụng nhỏ Zalo")
        lines.append(f"   • Kèm hồ sơ số + mẫu báo giá nếu {af} cần")
        lines.append(f"   • Nhóm Cộng Đồng Thợ 4.0 phù hợp khu vực + ngành mình")
    else:
        lines.append(f"   • Em gửi {af} hồ sơ số + mẫu báo giá qua Zalo nếu {af} cần")
        lines.append(f"   • Nhóm Cộng Đồng Thợ 4.0 phù hợp")
    return "\n".join(lines)


# ============================================================
# Helpers
# ============================================================


def _fmt(value: Optional[str], required: bool = False) -> str:
    """Format value cho card. Null + required → placeholder, null + optional → '-'."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return _PLACEHOLDER_REQUIRED_MISSING if required else "—"
    return str(value)
