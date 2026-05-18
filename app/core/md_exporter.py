"""Export profile + session ra Markdown — admin xem/share offline.

Refer:
- CORE § H.2 — card 5 phần (export theo cấu trúc tương tự)
- F2A.7 sanity check (note status nếu fail)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.models.schema import DealerProfileRaw, SessionState


def safe_filename(name: str, max_len: int = 80) -> str:
    """Sanitize string thành filename hợp lệ (Windows + Unix)."""
    if not name:
        return "untitled"
    # Strip + replace forbidden chars
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned[:max_len] or "untitled"


def render_profile_md(
    session: SessionState,
    profile: DealerProfileRaw,
) -> str:
    """Render 1 profile thành Markdown đầy đủ.

    Format:
    - Header với session_id + status
    - 5 section theo CORE § H.2 (Danh thiếp / Công việc & Kênh / Khách cũ /
      Bộ thương hiệu / Trong 3 ngày tới)
    - Metadata cuối: turns, flags, timestamps

    Returns Markdown text Việt thuần (no vocab cấm Tier/C-score).
    """
    lines: list[str] = []
    title = profile.dealer_name or profile.owner_name or f"Session {session.session_id[:8]}"
    lines.append(f"# Hồ sơ đại lý — {title}")
    lines.append("")
    lines.append(f"> **Status:** `{session.confirmation_status.value}` | "
                 f"**Stage:** `{session.stage.value}` | "
                 f"**Turn:** {session.turn_count}")
    lines.append("")

    if session.flags:
        flag_list = ", ".join(f"`{f.value}`" for f in session.flags)
        lines.append(f"> ⚠️ **Flags:** {flag_list}")
        lines.append("")

    # Section 1: Danh thiếp
    lines.append("## 🏪 Danh thiếp cửa hàng")
    lines.append("")
    lines.append(f"- **Chủ cửa hàng:** {profile.owner_name or '_(chưa có)_'}")
    lines.append(f"- **Tên cửa hàng:** {profile.dealer_name or '_(chưa có)_'}")
    lines.append(f"- **Địa chỉ:** {profile.address or '_(chưa có)_'}")
    lines.append(f"- **SĐT / Zalo:** {profile.phone_or_zalo or '_(chưa có)_'}")
    if profile.facebook:
        lines.append(f"- **Facebook:** {profile.facebook}")
    if profile.zalo and profile.zalo != profile.phone_or_zalo:
        lines.append(f"- **Zalo riêng:** {profile.zalo}")
    if profile.province:
        location = profile.province
        if profile.district:
            location = f"{profile.district}, {location}"
        lines.append(f"- **Tỉnh / Huyện:** {location}")
    if profile.province_specialty:
        lines.append(f"- **Đặc sản tỉnh:** {profile.province_specialty}")
    lines.append("")

    # Section 2: Công việc & Kênh
    lines.append("## 🛠 Công việc & Kênh khách")
    lines.append("")
    if profile.main_product:
        lines.append(f"- **Sản phẩm mạnh nhất:** {profile.main_product}")
    if profile.main_category:
        lines.append(f"- **Danh mục chuẩn hóa:** `{profile.main_category}`")
    if profile.category_stack:
        cats = ", ".join(profile.category_stack)
        lines.append(f"- **Danh mục đang làm:** {cats}")
    if profile.business_model_signal:
        lines.append(f"- **Mô hình kinh doanh:** {profile.business_model_signal}")
    if profile.dealer_type:
        lines.append(f"- **Loại đại lý:** `{profile.dealer_type}`")
    if profile.est_team_size is not None:
        team_str = f"{profile.est_team_size} người"
        if profile.team_stability_signal:
            team_str += f" — {profile.team_stability_signal}"
        lines.append(f"- **Đội thợ:** {team_str}")
    if profile.supplier_brands:
        brands = ", ".join(profile.supplier_brands)
        lines.append(f"- **Hãng nhập:** {brands}")
    if profile.customer_segment_signal:
        lines.append(f"- **Phân khúc khách:** {profile.customer_segment_signal}")
    if profile.primary_contact_channel:
        lines.append(f"- **Kênh liên hệ chính:** {profile.primary_contact_channel}")
    if profile.fb_marketing_status:
        lines.append(f"- **Facebook marketing:** {profile.fb_marketing_status}")
    if len(lines) > 0 and lines[-1].startswith("## 🛠"):
        # Empty section
        lines.append("_(chưa thu thập phần này)_")
    lines.append("")

    # Section 3: Khách cũ & Vướng mắc
    lines.append("## 💛 Khách cũ & Vướng mắc")
    lines.append("")
    has_section_3 = False
    if profile.customer_old_percentage:
        lines.append(f"- **Tỉ lệ khách cũ giới thiệu:** {profile.customer_old_percentage}")
        has_section_3 = True
    if profile.customer_storage_method:
        lines.append(f"- **Cách lưu khách:** {profile.customer_storage_method}")
        has_section_3 = True
    if profile.customer_pain:
        lines.append(f"- **Vướng mắc:** {profile.customer_pain}")
        has_section_3 = True
    if profile.payment_terms_signal:
        lines.append(f"- **Cọc & công nợ:** {profile.payment_terms_signal}")
        has_section_3 = True
    if profile.warranty_responsibility_signal:
        lines.append(f"- **Trách nhiệm bảo hành:** {profile.warranty_responsibility_signal}")
        has_section_3 = True
    # RAW signals
    raw_signals = []
    if profile.local_dominance_signal:
        raw_signals.append(f"  - Địa bàn: {profile.local_dominance_signal}")
    if profile.supplier_negotiation_signal:
        raw_signals.append(f"  - Đàm phán supplier: {profile.supplier_negotiation_signal}")
    if profile.community_network_signal:
        raw_signals.append(f"  - Mạng lưới thợ: {profile.community_network_signal}")
    if profile.motivation_signal:
        raw_signals.append(f"  - Động lực: {profile.motivation_signal}")
    if profile.usp_signal:
        raw_signals.append(f"  - USP: {profile.usp_signal}")
    if raw_signals:
        lines.append("- **Tín hiệu thô (RAW, cho team review):**")
        lines.extend(raw_signals)
        has_section_3 = True
    if not has_section_3:
        lines.append("_(chưa thu thập phần này)_")
    lines.append("")

    # Section 4: Bộ thương hiệu
    lines.append("## 🎁 Bộ thương hiệu")
    lines.append("")
    if profile.brandkit_consent == "yes":
        lines.append("- **Đồng ý nhận:** ✓ Có")
        if profile.color_accent:
            color_info = profile.color_accent
            if profile.feng_shui_signal:
                color_info += f" ({profile.feng_shui_signal})"
            lines.append(f"- **Màu chủ đạo:** {color_info}")
        if profile.brand_name_short:
            lines.append(f"- **Tên rút gọn:** {profile.brand_name_short}")
        if profile.initials_full:
            lines.append(f"- **Viết tắt đầy đủ:** {profile.initials_full}")
        if profile.initial_single:
            lines.append(f"- **Chữ cái biểu trưng:** {profile.initial_single}")
        if profile.slogan_options:
            lines.append("- **Slogan options:**")
            for i, s in enumerate(profile.slogan_options, 1):
                lines.append(f"  {i}. {s}")
    elif profile.brandkit_consent == "no":
        lines.append("- **Đồng ý nhận:** ✗ Không")
    else:
        lines.append("- **Đồng ý nhận:** _(chưa có)_")
    lines.append("")

    # Section 5: Trong 3 ngày tới
    lines.append("## ⏰ Hành động trong 3 ngày tới")
    lines.append("")
    if profile.brandkit_consent == "yes":
        lines.append("- Gửi kế hoạch chiến lược nền tảng số đầy đủ qua Zalo")
        lines.append("- Gửi bộ thương hiệu (logo + danh thiếp + video) trong ứng dụng nhỏ Zalo")
        lines.append("- Giới thiệu nhóm Cộng Đồng Thợ 4.0 phù hợp khu vực + ngành")
    else:
        lines.append("- Gửi kế hoạch chiến lược nền tảng số qua Zalo")
        lines.append("- Giới thiệu nhóm Cộng Đồng Thợ 4.0 phù hợp")
    lines.append("")

    # Metadata
    lines.append("---")
    lines.append("")
    lines.append("## 📝 Metadata")
    lines.append("")
    lines.append(f"- **Session ID:** `{session.session_id}`")
    lines.append(f"- **Channel:** {session.channel.value}")
    if session.ip_address:
        lines.append(f"- **IP:** `{session.ip_address}`")
    if session.detected_dealer_type:
        lines.append(f"- **Dealer type:** `{session.detected_dealer_type.value}`")
    lines.append(f"- **Tạo:** {_fmt_dt(session.created_at)}")
    lines.append(f"- **Cập nhật cuối:** {_fmt_dt(session.updated_at)}")
    if session.closed_at:
        lines.append(f"- **Đóng:** {_fmt_dt(session.closed_at)}")
    if session.skipped_slots:
        lines.append(f"- **Slot skipped:** `{', '.join(session.skipped_slots)}`")
    lines.append("")

    return "\n".join(lines)


def render_session_history_md(session: SessionState) -> str:
    """Render history conversation ra Markdown."""
    if not session.history:
        return "_(chưa có history)_"
    lines = ["## 💬 Lịch sử trò chuyện", ""]
    for msg in session.history:
        role_label = "**👤 Dealer**" if msg.role == "dealer" else "**🤖 Bot**"
        ts = _fmt_dt(msg.ts)
        lines.append(f"### {role_label} _{ts}_")
        lines.append("")
        # Indent multi-line content as blockquote
        for line in msg.content.split("\n"):
            lines.append(f"> {line}" if line.strip() else ">")
        lines.append("")
    return "\n".join(lines)


def render_full_md(
    session: SessionState,
    profile: DealerProfileRaw,
    include_history: bool = True,
) -> str:
    """Render profile + history thành 1 file Markdown."""
    parts = [render_profile_md(session, profile)]
    if include_history and session.history:
        parts.append("\n---\n")
        parts.append(render_session_history_md(session))
    return "\n".join(parts)


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(dt)
