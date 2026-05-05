"""Render Confirmation Card — mục 12 trong tài liệu MVP."""
from __future__ import annotations

from app.labels import CATEGORY_LABEL, PRIORITY_LABEL
from app.models.schema import DealerProfileRaw


def render_card(profile: DealerProfileRaw) -> str:
    def _val(v, default="(chưa có)"):
        return v if v else default

    category = CATEGORY_LABEL.get(profile.main_category or "", profile.main_category or "(chưa có)")
    priority = (
        ", ".join(PRIORITY_LABEL.get(p, p) for p in profile.dl0_priority)
        if profile.dl0_priority
        else "(chưa có)"
    )
    region = (
        f"{profile.district}, {profile.province}"
        if profile.district and profile.province
        else _val(profile.province)
    )

    pain_text = (
        "; ".join(profile.pain_points)
        if profile.pain_points
        else "(chưa có)"
    )

    return (
        "Em xin tóm tắt lại để mình xem có đúng chưa nhé ạ:\n\n"
        f"• Tên đại lý: {_val(profile.dealer_name)}\n"
        f"• Người phụ trách: {_val(profile.owner_name)}\n"
        f"• Zalo/SĐT: {_val(profile.phone_or_zalo)}\n"
        f"• Khu vực mạnh: {region}\n"
        f"• Ngành chính: {category}\n"
        f"• Khách cũ ước lượng: {_val(profile.customer_base_estimate)}\n"
        f"• Đau nhất: {pain_text}\n"
        f"• Ưu tiên: {priority}\n\n"
        "Anh xem giúp em đúng chưa ạ?\n"
        "Anh trả lời \"đúng\" để chốt giúp em, hoặc nói cần sửa gì để em chỉnh lại "
        "(ví dụ: \"sửa SĐT thành 0901234567\") nhé ạ."
    )
