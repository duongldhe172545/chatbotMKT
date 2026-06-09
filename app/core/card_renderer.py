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
    """Render confirmation card 5 phần.

    Fix Lỗi 5: nhận address_form param.
    Fix Lỗi 10: bỏ box drawing border, dùng emoji separator.
    Fix Lỗi 18: category code → display name.
    """
    af = address_form
    lines: list[str] = []
    lines.append(f"📋 HỒ SƠ CỬA HÀNG — {af} duyệt giúp em ạ")
    lines.append("")

    # ----- Phần 1: 🏪 Danh thiếp cửa hàng -----
    lines.append(_render_section_1_danh_thiep(profile))
    lines.append("")

    # ----- Phần 2: 🛠 Công việc & Kênh -----
    lines.append(_render_section_2_cong_viec(profile))
    lines.append("")

    # ----- Phần 3: 💛 Khách cũ & Vướng mắc -----
    lines.append(_render_section_3_khach_cu(profile))
    lines.append("")

    # ----- Phần 4: 🎁 Bộ thương hiệu sẽ tặng -----
    lines.append(_render_section_4_brandkit(profile, af))
    lines.append("")

    # ----- Phần 5: ⏰ Trong 3 ngày tới -----
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
    # FIX M2: hiển thị SĐT phụ nếu dealer cho 2 số
    if profile.phone_secondary:
        lines.append(f"   • SĐT phụ: {profile.phone_secondary}")
    if profile.facebook:
        lines.append(f"   • Facebook: {profile.facebook}")
    return "\n".join(lines)


def _render_section_2_cong_viec(profile: DealerProfileRaw) -> str:
    """Phần 2: Công việc & Kênh (slot 2.1-2.6)."""
    lines = ["🛠 CÔNG VIỆC & KÊNH"]
    if profile.main_product:
        lines.append(f"   • Sản phẩm mạnh nhất: {profile.main_product}")
    if profile.category_stack:
        lines.append(f"   • Danh mục: {', '.join(profile.category_stack)}")
    if profile.business_model_signal:
        lines.append(f"   • Mô hình: {profile.business_model_signal}")
    if profile.est_team_size is not None:
        team_info = f"{profile.est_team_size} người"
        if profile.team_stability_signal:
            team_info += f" ({profile.team_stability_signal})"
        lines.append(f"   • Đội thợ: {team_info}")
    if profile.supplier_brands:
        lines.append(f"   • Hãng nhập: {', '.join(profile.supplier_brands)}")
    if profile.primary_contact_channel:
        lines.append(f"   • Kênh khách liên hệ: {profile.primary_contact_channel}")
    # Section empty (Phase 1: nhiều slot null) → placeholder
    if len(lines) == 1:
        lines.append(f"   {_PLACEHOLDER_CATEGORY_EMPTY}")
    return "\n".join(lines)


def _render_section_3_khach_cu(profile: DealerProfileRaw) -> str:
    """Phần 3: Khách cũ & Vướng mắc (slot 3.1-3.5)."""
    lines = ["💛 KHÁCH CŨ & VƯỚNG MẮC"]
    if profile.customer_old_percentage:
        lines.append(f"   • Tỉ lệ khách cũ giới thiệu: {profile.customer_old_percentage}")
    if profile.customer_storage_method:
        lines.append(f"   • Cách lưu danh sách: {profile.customer_storage_method}")
    if profile.customer_pain:
        lines.append(f"   • Vướng mắc: {profile.customer_pain}")
    if profile.payment_terms_signal:
        lines.append(f"   • Thanh toán cọc / công nợ: {profile.payment_terms_signal}")
    if profile.warranty_responsibility_signal:
        lines.append(
            f"   • Trách nhiệm bảo hành: "
            f"{_display_warranty(profile.warranty_responsibility_signal)}"
        )
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
        # Phong cách logo (4.1) — bot chọn theo ngành
        raw_category = profile.main_category or "ngành mình"
        category_name = _CATEGORY_DISPLAY_NAMES.get(raw_category, raw_category)
        lines.append(f"   • Phong cách logo: em chọn theo {category_name}")

        # Màu + phong thủy (4.2)
        is_color_suggested = False
        color_info = profile.color_accent or ""
        if not color_info or color_info.casefold() == "auto":
            color_info = get_default_color_for_profile(profile)
            is_color_suggested = True

        if is_color_suggested:
            color_info += " (Em đề xuất)"
        if profile.feng_shui_signal:
            color_info += f" ({profile.feng_shui_signal})"
        lines.append(f"   • Màu chủ đạo: {color_info}")

        if profile.logo_initials:
            if profile.logo_initials == "auto":
                from app.llm.auto_derive import gen_initials_full
                brand_name = profile.dealer_name or "Cửa hàng"
                resolved_initials = (profile.initials_full or gen_initials_full(brand_name) or "CH").upper()
                initials = f"{resolved_initials} (Em rút gọn)"
            else:
                initials = profile.logo_initials
            lines.append(f"   • Viết tắt logo: {initials}")

        if profile.slogan_preference:
            if profile.slogan_preference == "auto":
                resolved_slogan = "Vững chất lượng, bền niềm tin"
                if profile.slogan_options:
                    resolved_slogan = str(profile.slogan_options[0])
                slogan = f"{resolved_slogan} (Em đề xuất)"
            else:
                slogan = profile.slogan_preference
            lines.append(f"   • Slogan: {slogan}")

        if profile.logo_style:
            if profile.logo_style == "auto":
                style = "Tối giản hiện đại (Em đề xuất)"
            else:
                style = profile.logo_style
            lines.append(f"   • Gu logo: {style}")
    return "\n".join(lines)


def _render_section_5_trong_3_ngay(profile: DealerProfileRaw, af: str = "anh") -> str:
    """Phần 5: Trong 3 ngày tới (next action). Fix Lỗi 5: dùng af."""
    lines = ["⏰ TRONG 3 NGÀY TỚI"]
    if profile.brandkit_consent == "yes":
        lines.append(f"   • Em gửi {af} kế hoạch chiến lược nền tảng số đầy đủ qua Zalo")
        lines.append(f"   • Bộ thương hiệu (logo + danh thiếp + video) gửi trong ứng dụng nhỏ Zalo")
        lines.append(f"   • Nhóm Cộng Đồng Thợ 4.0 phù hợp khu vực + ngành mình")
    else:
        lines.append(f"   • Em gửi {af} kế hoạch chiến lược nền tảng số qua Zalo")
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


def _display_warranty(value: str) -> str:
    """Keep raw profile data intact while showing a clean confirmation card."""
    folded = value.casefold()
    if "anh lo" in folded or "anh xử lý" in folded or "anh xu ly" in folded:
        return "chủ cửa hàng trực tiếp xử lý"
    return value
