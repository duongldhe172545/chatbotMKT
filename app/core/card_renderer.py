"""Render Confirmation Card v7 — format ASCII gạch ngang, 5 section.

Source: EM_LINH_MKT_v7.md (PHẦN 2 — example Anh Tùng/Cao Bằng).
"""
from __future__ import annotations

from app.models.schema import DealerProfileRaw


def _val(v, default: str = "(chưa có)") -> str:
    if v in (None, "", []):
        return default
    return str(v)


def _val_list(items, default: str = "(chưa có)") -> str:
    if not items:
        return default
    return ", ".join(str(x) for x in items)


def render_card(profile: DealerProfileRaw) -> str:
    """Render Confirmation Card v7 — 5 section, format gạch ngang ASCII.

    Tương thích cả profile v6 (đa số field v7 null) và v7 (đầy đủ).
    """
    # SECTION 1 — CỬA HÀNG & NGƯỜI LIÊN HỆ
    dealer = _val(profile.dealer_name)
    owner = _val(profile.owner_name)
    address = _val(profile.address) if profile.address else _val(
        f"{profile.district}, {profile.province}"
        if profile.district and profile.province
        else profile.province
    )
    phone = _val(profile.phone_or_zalo)
    hotline = _val(profile.phone_or_zalo)  # default hotline = phone

    s1 = (
        "📋 CỬA HÀNG & NGƯỜI LIÊN HỆ\n"
        f"- Tên cửa hàng:    {dealer}\n"
        f"- Chủ cửa hàng:    Anh {owner}\n"
        f"- Chức danh:       Chủ cửa hàng\n"
        f"- Địa chỉ:         {address}\n"
        f"- SĐT/Zalo:        {phone}\n"
        f"- Hotline:         {hotline}"
    )

    # SECTION 2 — CÔNG VIỆC
    cats = _val_list(profile.category_stack)
    if profile.category_stack:
        cats_lines = "\n".join(
            f"  ▪ {c}{'  (mạnh nhất)' if (profile.main_product and profile.main_product.lower() in c.lower()) else ''}"
            for c in profile.category_stack
        )
    else:
        cats_lines = "  ▪ (chưa có)"
    biz_model = _val(profile.business_model_signal)
    team_size = profile.est_team_size if profile.est_team_size is not None else None
    team_line = (
        f"{team_size} thợ cơ hữu, ổn định lâu"
        if team_size and profile.team_stability_signal
        else (str(team_size) + " thợ" if team_size else _val(profile.team_stability_signal))
    )
    suppliers_lines = (
        "\n".join(f"  ▪ {b}" for b in profile.supplier_brands)
        if profile.supplier_brands
        else "  ▪ (chưa có)"
    )
    segment = _val(profile.customer_segment_signal)

    s2 = (
        "🔧 CÔNG VIỆC\n"
        f"- Danh mục chủ lực:\n"
        f"{cats_lines}\n"
        f"- Mô hình:         {biz_model}\n"
        f"- Đội thợ:         {team_line}\n"
        f"- Hãng nhập:\n"
        f"{suppliers_lines}\n"
        f"- Phân khúc:       {segment}"
    )

    # SECTION 3 — KÊNH ONLINE
    zalo = _val(profile.zalo or profile.phone_or_zalo)
    fb = profile.facebook or "chưa có"
    fb_line = fb
    if "chưa có" in fb.lower() or "lười" in (profile.fb_marketing_status or "").lower():
        fb_line = f"{fb}\n                   ↳ (đã ghi nhận để hỗ trợ dựng)"

    s3 = (
        "🌐 KÊNH ONLINE\n"
        f"- Zalo:            {zalo} (kênh chính)\n"
        f"- Facebook:        {fb_line}"
    )

    # SECTION 4 — KHÁCH HÀNG ("Mỏ vàng")
    pct = _val(profile.customer_old_percentage)
    storage = profile.customer_storage_method or "(chưa có)"
    storage_lines = "\n".join(
        f"  ▪ {line.strip()}"
        for line in storage.split(";")
        if line.strip()
    ) if profile.customer_storage_method else "  ▪ (chưa có)"
    payment = _val(profile.payment_terms_signal)
    pain = profile.customer_pain or _val_list(profile.pain_points)

    s4 = (
        "💎 KHÁCH HÀNG (\"Mỏ vàng\")\n"
        f"- Tỷ lệ khách cũ:  ~{pct} (truyền miệng)\n"
        f"- Cách lưu khách:\n"
        f"{storage_lines}\n"
        f"- Quy trình thanh toán:\n"
        f"  ▪ {payment}\n"
        f"- Vướng nhất:      {pain}"
    )

    # SECTION 5 — BRANDKIT
    color = _val(profile.color_accent)
    feng_shui = profile.feng_shui_signal or ""
    color_line = (
        f"{color}\n                   ({feng_shui})" if feng_shui else color
    )
    slogan = _val(profile.slogan, default="Em đề xuất 5 phương án ở Mini App")

    s5 = (
        "🎨 BỘ BRANDKIT\n"
        f"- Logo:            Em chọn phong cách phù hợp\n"
        f"                   (anh duyệt + sửa sau)\n"
        f"- Màu:             {color_line}\n"
        f"- Slogan:          {slogan}"
    )

    # COMBINE + footer
    return (
        f"```\n"
        f"{s1}\n\n"
        f"{s2}\n\n"
        f"{s3}\n\n"
        f"{s4}\n\n"
        f"{s5}\n\n"
        f"═════════════════════════════════════════════════════\n"
        f"Anh xem có gì cần chỉnh sửa không ạ?\n"
        f"- Trả lời \"đúng\" để chốt\n"
        f"- Hoặc nói rõ cần sửa gì để em điều chỉnh ngay\n"
        f"═════════════════════════════════════════════════════\n"
        f"```"
    )


def render_closing(profile: DealerProfileRaw, address_form: str = "anh") -> str:
    """Render Closing v7 — sau khi CONFIRMED, tặng quà + hẹn đặc sản nếu có."""
    specialty = profile.province_specialty
    specialty_line = (
        f"Thời gian có hạn nên em xin phép hẹn {address_form} một ngày đẹp "
        f"trời thưởng thức món {specialty} {address_form} nhé! 🤤"
        if specialty
        else f"Em rất cảm ơn {address_form} đã dành thời gian cho em hôm nay! 🌷"
    )

    return (
        f"Dạ em cảm ơn {address_form} nhiều ạ! Em đã ghi nhận hồ sơ rồi nhé.\n\n"
        f"Em xin phép gửi {address_form} link Mini App bên dưới để xem preview "
        f"logo và chọn phong cách phù hợp nhất 🌷.\n\n"
        f"Phần kế hoạch chiến lược phát triển nền tảng số đầy đủ em sẽ gửi "
        f"{address_form} trong 3 ngày tới qua Zalo nhé.\n\n"
        f"Em rất cảm ơn 5 phút quý báu của {address_form} ngày hôm nay. "
        f"{specialty_line}\n\n"
        f"[Mini App link sẽ gửi qua Zalo trong 5 phút]"
    )
