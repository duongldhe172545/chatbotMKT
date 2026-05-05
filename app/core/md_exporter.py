"""Export hồ sơ dealer + hội thoại ra Markdown — phục vụ Reviewer ADG / sếp đọc.

Format dễ đọc, có:
- Header với tên dealer + trạng thái + ngày
- Bảng thông tin cơ bản
- Bảng confidence
- Cờ cảnh báo (nếu có)
- Hội thoại đầy đủ với timestamp
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from app.labels import (
    CATEGORY_LABEL,
    DEALER_TYPE_LABEL,
    FIELD_LABEL,
    FLAG_LABEL,
    PRIORITY_LABEL,
)
from app.models.schema import Session

CONFIRMATION_LABEL = {
    "PENDING": "⏳ Đang chờ",
    "CONFIRMED": "✅ Đã xác nhận",
    "EDITED": "✏️ Đã sửa",
}

REVIEW_LABEL = {
    "RAW": "📝 RAW (chờ review)",
    "UNDER_REVIEW": "🔎 Đang review",
    "APPROVED": "✅ Đã duyệt",
    "REJECTED": "❌ Đã từ chối",
}

ROLE_LABEL = {"bot": "🤖 Em Linh", "dealer": "👤 Dealer"}


def _fmt_dt(iso: str | datetime | None) -> str:
    if not iso:
        return "—"
    if isinstance(iso, datetime):
        dt = iso
    else:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return str(iso)
    return dt.strftime("%Y-%m-%d %H:%M")


def _val(v: object, default: str = "—") -> str:
    if v in (None, "", []):
        return default
    return str(v)


def _label_or_raw(mapping: dict, key: str | None) -> str:
    if not key:
        return "—"
    return mapping.get(key, key)


def render_profile_md(session: Session) -> str:
    """Sinh markdown 1 dealer (full info + hội thoại). Input là Session domain object."""
    p = session.profile_raw
    lines: list[str] = []

    # Header
    title = p.dealer_name or p.owner_name or "Dealer chưa có tên"
    lines.append(f"# Hồ sơ dealer — {title}")
    lines.append("")
    lines.append(f"- **Session ID:** `{session.session_id}`")
    lines.append(f"- **Ngày tạo:** {_fmt_dt(session.created_at)}")
    lines.append(f"- **Cập nhật cuối:** {_fmt_dt(session.updated_at)}")
    lines.append(f"- **Stage:** `{session.stage.value if hasattr(session.stage, 'value') else session.stage}`")
    lines.append(
        f"- **Trạng thái xác nhận:** {CONFIRMATION_LABEL.get(p.confirmation_status, p.confirmation_status)}"
    )
    lines.append(
        f"- **Trạng thái review:** {REVIEW_LABEL.get(p.review_status, p.review_status)}"
    )
    lines.append("")

    # Cờ cảnh báo
    if p.flags:
        lines.append("## ⚠️ Cờ cảnh báo")
        lines.append("")
        for flag in p.flags:
            meta = FLAG_LABEL.get(flag, {"text": flag, "cls": ""})
            severity = {"flag-bad": "🔴", "flag-warn": "🟡", "flag-info": "🔵"}.get(
                meta.get("cls", ""), "⚪"
            )
            lines.append(f"- {severity} **{meta.get('text', flag)}** (`{flag}`)")
        lines.append("")

    # Bảng thông tin cơ bản
    region = ", ".join(filter(None, [p.district, p.province])) or "—"
    pain_text = (
        "\n".join(f"  - {x}" for x in p.pain_points) if p.pain_points else None
    )
    priorities = (
        ", ".join(_label_or_raw(PRIORITY_LABEL, x) for x in p.dl0_priority)
        if p.dl0_priority
        else "—"
    )

    lines.append("## 📋 Thông tin cơ bản")
    lines.append("")
    lines.append("| Trường | Giá trị |")
    lines.append("|--------|---------|")
    lines.append(f"| Tên đại lý | {_val(p.dealer_name)} |")
    lines.append(f"| Người phụ trách | {_val(p.owner_name)} |")
    lines.append(f"| Zalo/SĐT | {_val(p.phone_or_zalo)} |")
    lines.append(f"| Khu vực | {region} |")
    lines.append(f"| Ngành chính | {_label_or_raw(CATEGORY_LABEL, p.main_category)} |")
    lines.append(f"| Loại dealer | {_label_or_raw(DEALER_TYPE_LABEL, p.dealer_type)} |")
    lines.append(f"| Khách cũ ước lượng | {_val(p.customer_base_estimate)} |")
    lines.append(f"| Ưu tiên hỗ trợ | {priorities} |")
    if p.recommended_group:
        lines.append(f"| Nhóm CĐ đề xuất | {p.recommended_group} |")
    lines.append("")

    # Đau nhất (list, render riêng vì có nhiều dòng)
    lines.append("**Đau nhất / vướng nhất:**")
    if p.pain_points:
        for pain in p.pain_points:
            lines.append(f"- {pain}")
    else:
        lines.append("- (chưa có)")
    lines.append("")

    # Confidence table
    if session.confidence:
        lines.append("## 🎯 Confidence từng field")
        lines.append("")
        lines.append("| Trường | Mức tin cậy |")
        lines.append("|--------|------------|")
        for field, conf in sorted(session.confidence.items()):
            label = FIELD_LABEL.get(field, field)
            badge = {"HIGH": "🟢 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🔴 LOW"}.get(
                conf, conf
            )
            lines.append(f"| {label} (`{field}`) | {badge} |")
        lines.append("")

    # Field bị skip
    if session.skipped_fields:
        lines.append("## ⏭️ Field đã skip (dealer không trả lời rõ)")
        lines.append("")
        for field in session.skipped_fields:
            lines.append(f"- {FIELD_LABEL.get(field, field)} (`{field}`)")
        lines.append("")

    # Hội thoại
    lines.append("## 💬 Hội thoại đầy đủ")
    lines.append("")
    if not session.messages:
        lines.append("_(Không có tin nhắn)_")
    else:
        for m in session.messages:
            role = ROLE_LABEL.get(m.role.value if hasattr(m.role, "value") else m.role, m.role)
            ts = _fmt_dt(m.ts)
            content = (m.content or "").replace("\n", "  \n")  # giữ line break trong MD
            lines.append(f"**{role}** _{ts}_")
            lines.append("")
            lines.append(f"> {content}")
            lines.append("")

    lines.append("---")
    lines.append(
        f"_Xuất từ Em Linh MKT Chatbot — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    return "\n".join(lines)


def render_bulk_md(sessions: Iterable[Session]) -> str:
    """Bulk export — header tổng + từng dealer ngăn cách bằng `---`."""
    sessions_list = list(sessions)
    lines = [
        f"# Tổng hợp dealer profile — {len(sessions_list)} hồ sơ",
        "",
        f"_Xuất ngày: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Mục lục",
        "",
    ]
    for i, s in enumerate(sessions_list, 1):
        title = s.profile_raw.dealer_name or s.profile_raw.owner_name or f"Dealer #{i}"
        lines.append(f"{i}. {title} (`{s.session_id[:8]}`)")
    lines.append("")
    lines.append("---")
    lines.append("")

    for s in sessions_list:
        lines.append(render_profile_md(s))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def safe_filename(name: str | None, fallback: str = "dealer") -> str:
    """Sinh filename an toàn từ tên dealer — bỏ dấu, ký tự đặc biệt."""
    import re
    import unicodedata

    base = (name or fallback).strip()
    # Bỏ dấu tiếng Việt
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base)
    base = base.strip("_")
    return base[:50] or fallback
