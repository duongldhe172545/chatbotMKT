"""Export profile + session ra Markdown — admin xem/share offline.

Refer:
- CORE § H.2 — card 5 phần (export theo cấu trúc tương tự)
- F2A.7 sanity check (note status nếu fail)
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional

from app.models.schema import DealerProfileRaw, SessionState


def safe_filename(name: str, max_len: int = 80) -> str:
    """Sanitize string thành filename hợp lệ (Windows + Unix) + HTTP-safe.

    Phase 5 R4 Gap 13: strip diacritics (Việt → ASCII) cho HTTP
    Content-Disposition header (chỉ accept Latin-1). Filename không
    cần đẹp — chỉ cần unique + sortable.
    """
    if not name:
        return "untitled"
    # Strip Vietnamese diacritics: "Nhôm Kính" → "Nhom Kinh"
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Đặc biệt: đ/Đ không có combining char → manual replace
    ascii_only = ascii_only.replace("đ", "d").replace("Đ", "D")
    # Strip + replace forbidden chars
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", ascii_only.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._")
    # Đảm bảo ASCII printable only
    cleaned = "".join(c if 32 <= ord(c) < 127 else "_" for c in cleaned)
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

    # 1. Thông tin cơ bản
    lines.append("## 🏪 1. Thông tin cơ bản")
    lines.append("")
    lines.append(f"- **Chủ cửa hàng:** {profile.owner_name or '_(chưa có)_'}")
    lines.append(f"- **Tên cửa hàng:** {profile.dealer_name or '_(chưa có)_'}")
    lines.append(f"- **SĐT / Zalo:** {profile.phone_or_zalo or '_(chưa có)_'}")
    lines.append(f"- **Địa chỉ:** {profile.address or '_(chưa có)_'}")
    location = ""
    if profile.province:
        location = profile.province
        if profile.ward:
            location = f"{profile.ward}, {location}"
    if location:
        lines.append(f"- **Tỉnh / Xã chuẩn hóa:** {location}")
    # (bỏ "Quận / Huyện": district vestigial sau refactor địa chỉ → ward/province, không bao giờ được ghi)
    if profile.business_model_signal or profile.dealer_type:
        model_str = profile.business_model_signal or profile.dealer_type
        lines.append(f"- **Mô hình kinh doanh:** {model_str}")
    if profile.main_product:
        lines.append(f"- **Sản phẩm chính:** {profile.main_product}")
    if profile.main_category:
        lines.append(f"- **Danh mục (ngành) suy ra:** {profile.main_category}")
    if profile.primary_contact_channel:
        lines.append(f"- **Kênh liên hệ chính:** {profile.primary_contact_channel}")
    lines.append("")

    # 2. 9 Tiêu chí đánh giá
    lines.append("## 🛠 2. 9 Tiêu chí đánh giá")
    lines.append("")
    
    # C1
    c1_str = profile.customer_old_percentage or '_(chưa có)_'
    lines.append(f"- **C1. Tỉ lệ khách cũ:** {c1_str}")
    
    # C2
    c2_str = profile.payment_terms_signal or '_(chưa có)_'
    lines.append(f"- **C2. Quy trình cọc/thanh toán:** {c2_str}")
    
    # C3
    c3_str = '_(chưa có)_'
    if profile.est_team_size is not None:
        c3_str = f"{profile.est_team_size} người"
        if profile.team_stability_signal:
            c3_str += f" — {profile.team_stability_signal}"
    elif profile.team_stability_signal:
        c3_str = profile.team_stability_signal
    lines.append(f"- **C3. Quy mô & độ ổn định đội thợ:** {c3_str}")
    
    # C4
    c4_str = profile.warranty_responsibility_signal or '_(chưa có)_'
    lines.append(f"- **C4. Trách nhiệm xử lý bảo hành:** {c4_str}")
    
    # C5
    c5_parts = []
    if profile.customer_pain:
        c5_parts.append(profile.customer_pain)
    if profile.motivation_signal:
        c5_parts.append(f"(Động lực: {profile.motivation_signal})")
    c5_str = " ".join(c5_parts) if c5_parts else '_(chưa có)_'
    lines.append(f"- **C5. Khó khăn & động lực:** {c5_str}")
    
    # C6
    c6_str = profile.local_dominance_signal or '_(chưa có)_'
    lines.append(f"- **C6. Bán kính & nhận diện địa bàn:** {c6_str}")
    
    # C7
    c7_str = profile.customer_storage_method or '_(chưa có)_'
    lines.append(f"- **C7. Cách lưu thông tin khách:** {c7_str}")
    
    # C8
    c8_parts = []
    if profile.supplier_brands:
        c8_parts.append(", ".join(profile.supplier_brands))
    if profile.supplier_negotiation_signal:
        c8_parts.append(f"(Đàm phán: {profile.supplier_negotiation_signal})")
    c8_str = " — ".join(c8_parts) if c8_parts else '_(chưa có)_'
    lines.append(f"- **C8. Hãng nhập & đàm phán cung ứng:** {c8_str}")
    
    # C9
    c9_parts = []
    if profile.facebook:
        c9_parts.append(f"Facebook: {profile.facebook}")
        if profile.fb_marketing_status:
            c9_parts.append(f"({profile.fb_marketing_status})")
    if profile.community_network_signal:
        c9_parts.append(f"Mạng lưới: {profile.community_network_signal}")
    c9_str = " — ".join(c9_parts) if c9_parts else '_(chưa có)_'
    lines.append(f"- **C9. Mạng lưới & sức ảnh hưởng:** {c9_str}")
    lines.append("")

    # 3. Thông tin bổ sung làm Logo & Thương hiệu
    lines.append("## 🎁 3. Thông tin bổ sung làm Logo & Thương hiệu")
    lines.append("")
    consent_display = "Có ✓" if profile.brandkit_consent == "yes" else (
        "Không ✗" if profile.brandkit_consent == "no" else '_(chưa có)_'
    )
    lines.append(f"- **Đồng ý nhận bộ thương hiệu:** {consent_display}")
    
    if profile.brandkit_consent == "yes":
        if profile.logo_existing_intent:
            lines.append(f"- **Nhu cầu với logo hiện có:** {profile.logo_existing_intent}")
        color_info = profile.color_accent or '_(chưa có)_'
        if profile.feng_shui_signal:
            color_info += f" ({profile.feng_shui_signal})"
        lines.append(f"- **Màu chủ đạo:** {color_info}")
        if profile.slogan_preference:
            lines.append(f"- **Slogan:** {profile.slogan_preference}")
        lines.append(f"- **Gu logo / phong cách:** {profile.logo_style or '_(chưa có)_'}")
    lines.append("")

    # Section 5: Trong 3 ngày tới
    lines.append("## ⏰ Hành động trong 3 ngày tới")
    lines.append("")
    # Feedback 2026-06-10: chỉ cam kết bộ nhận diện (+ hồ sơ số, báo giá nếu cần)
    if profile.brandkit_consent == "yes":
        lines.append("- Gửi bộ thương hiệu (logo + danh thiếp) trong ứng dụng nhỏ Zalo")
        lines.append("- Gửi kèm hồ sơ số, video giới thiệu, mẫu báo giá nếu đại lý cần")
        lines.append("- Giới thiệu nhóm Cộng Đồng Thợ 4.0 phù hợp khu vực + ngành")
    else:
        lines.append("- Gửi hồ sơ số + mẫu báo giá qua Zalo nếu đại lý cần")
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
        lines.append(f"- **Conversation tone:** `{session.detected_dealer_type.value}`")
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
