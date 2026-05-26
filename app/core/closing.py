"""Closing render — Phase 1 + Phase 5 R2 Gap 10 local hook.

Refer:
- F2A.8 (LUAT_2A_core v0.2.5) — Closing engine (KHÔNG khoá case đặc sản)
- File 1A § 7 — Closing templates + consent=no path
- CORE § H.3 + § A.3 — bot KHÔNG render trực tiếp, chỉ dẫn Zalo
- D10 STRATEGY — consent=no skip path

Nguyên tắc "không khoá case":
- Bỏ lookup table "province → đặc sản" (vd HN → phở) — ép câu robot.
- Phase 5 R2 Gap 10: local hook gen qua LLM_FAST (refer F2A.8 + local_hook.py),
  có thể rỗng. Cache 7 ngày key local_hook:{province}:{dealer_type}.
- Nếu KHÔNG có client / KHÔNG có province → template tổng quát (Phase 1 fallback).
"""
from __future__ import annotations

from typing import Optional

from app.models.enums import AddressForm, DealerType


# ============================================================
# Closing templates — consent=yes path
# ============================================================


# Phase 6 R4: 3 biến thể consent=yes (refer 1A § 7.3) — rotate hash session_id
# Placeholder {dealer_name} điền từ profile, {local_hook} từ LLM gen.
_CLOSING_CONSENT_YES_VARIANTS: list[str] = [
    (
        "Em cảm ơn {af} đã dành thời gian trò chuyện cùng em hôm nay ạ 🌷.\n\n"
        "Bộ thương hiệu (logo + danh thiếp + video giới thiệu) cho cửa hàng "
        "{dealer_name} em đang gen — em sẽ gửi {af} trong ứng dụng nhỏ Zalo "
        "của em, {af} nhận sau ít phút nha.\n\n"
        "Trong 3 ngày tới em cũng gửi {af} kế hoạch chiến lược phát triển nền "
        "tảng số đầy đủ qua Zalo — đó là phần em đã hứa từ đầu ạ.\n\n"
        "Chúc {af} một ngày làm việc nhiều đơn hàng ạ! Hẹn gặp lại {af}."
    ),
    (
        "Em cảm ơn {af} nhiều ạ 🌷!\n\n"
        "Bộ thương hiệu của cửa hàng {dealer_name} em đang làm — em gửi {af} "
        "trong ứng dụng nhỏ Zalo trong ít phút.\n\n"
        "Kế hoạch chiến lược nền tảng số đầy đủ em gửi {af} trong 3 ngày tới "
        "qua Zalo nhé.\n\n"
        "Chúc cửa hàng mình ngày càng phát đạt!"
    ),
    (
        "Em cảm ơn {af} nhiều lắm 🌷. Cuộc trò chuyện này em học được nhiều "
        "điều thật đó ạ.\n\n"
        "Bộ thương hiệu (logo + danh thiếp + video) của {dealer_name} em "
        "gen ngay — em gửi {af} qua ứng dụng nhỏ Zalo trong ít phút.\n\n"
        "Kế hoạch chiến lược nền tảng số đầy đủ — em gửi {af} trong 3 ngày.\n\n"
        "Hẹn gặp lại {af} nha!"
    ),
]


# ============================================================
# Closing templates — consent=no path (refer D10 STRATEGY)
# ============================================================


_CLOSING_CONSENT_NO_TEMPLATE = (
    "Dạ em hiểu {af} chưa cần bộ thương hiệu, em không ép đâu ạ.\n\n"
    "Em vẫn ghi nhận thông tin của cửa hàng mình. Nếu sau này {af} đổi ý "
    "muốn nhận bộ thương hiệu, {af} nhắn lại em nhé — bên em luôn sẵn sàng.\n\n"
    "Nhóm Cộng Đồng Thợ 4.0 phù hợp với khu vực + ngành mình em cũng sẽ "
    "giới thiệu qua Zalo trong 3 ngày tới ạ.\n\n"
    "Em cảm ơn {af} rất nhiều đã dành thời gian!"
)


# ============================================================
# Soft-end templates — escalation L3 / timeout
# ============================================================


_CLOSING_SOFT_END_TEMPLATE = (
    "Dạ vâng, em ngừng tại đây ạ. Em ghi nhận thông tin {af} đã chia sẻ. "
    "Team người thật bên em có thể sẽ liên hệ {af} sau nếu cần hỗ trợ thêm. "
    "Em cảm ơn {af} nhiều ạ 🌷"
)


# ============================================================
# Render functions
# ============================================================


def render_closing(
    province: Optional[str] = None,
    consent: Optional[str] = None,
    client=None,
    dealer_type: Optional[DealerType] = None,
    address_form: AddressForm = AddressForm.ANH,
    session_id: Optional[str] = None,
    dealer_name: Optional[str] = None,
) -> str:
    """Render closing dựa trên consent + local hook LLM gen + 3 biến thể.

    Args:
        province: Tỉnh (canonical từ whitelist) cho LLM gen local hook.
        consent: brandkit_consent value ("yes"/"no"/None).
        client: Optional LLMClient — nếu provided + có province → LLM gen
            local hook 1 câu prepend vào closing. None → template tổng quát.
        dealer_type: Detected dealer type cho LLM context.
        address_form: anh / chị.
        session_id: UUID session cho hash rotate variant (1A § 7.3).
        dealer_name: Tên cửa hàng fill {dealer_name} placeholder.

    Returns:
        Closing text Việt thuần (template + optional local hook + filled name).
    """
    if consent == "no":
        base = _CLOSING_CONSENT_NO_TEMPLATE
    else:
        base = _pick_consent_yes_variant(session_id)
        name = dealer_name or "cửa hàng mình"
        base = base.replace("{dealer_name}", name)

    # Fix Lỗi 14: replace {af} placeholder với address_form thực tế
    af_value = address_form.value if hasattr(address_form, 'value') else str(address_form)
    base = base.replace("{af}", af_value)

    # Phase 5 R2 Gap 10: gen local hook qua LLM_FAST (refer F2A.8 + local_hook)
    if client is not None and province:
        try:
            from app.llm.local_hook import gen_local_hook
            hook = gen_local_hook(
                province=province,
                dealer_type=dealer_type,
                client=client,
                address_form=address_form,
            )
        except Exception:
            hook = ""
        if hook:
            # Prepend hook + blank line vào closing
            return f"{hook}\n\n{base}"
    return base


def _pick_consent_yes_variant(session_id: Optional[str]) -> str:
    """Hash session_id mod 3 → biến thể closing cố định trong session."""
    if not session_id:
        return _CLOSING_CONSENT_YES_VARIANTS[0]
    import hashlib
    h = hashlib.md5(f"{session_id}|closing".encode("utf-8")).hexdigest()
    idx = int(h, 16) % len(_CLOSING_CONSENT_YES_VARIANTS)
    return _CLOSING_CONSENT_YES_VARIANTS[idx]


def get_num_closing_variants() -> int:
    """Số biến thể closing consent=yes."""
    return len(_CLOSING_CONSENT_YES_VARIANTS)


def render_soft_end_closing(address_form=None) -> str:
    """Render closing rút gọn cho escalation L3 / timeout.

    Refer 1C § 13 escalation script. Fix Lỗi 14: dynamic address_form.
    """
    template = _CLOSING_SOFT_END_TEMPLATE
    if address_form:
        af_value = address_form.value if hasattr(address_form, 'value') else str(address_form)
    else:
        af_value = "anh"
    return template.replace("{af}", af_value)
