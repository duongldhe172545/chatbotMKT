"""Brandkit pack exporter — CORE § H.4 bản #2 cho designer team.

Refer:
- CORE § H.4 "Xuất hai bản" — bản chấm điểm + bản brandkit
- CORE § A.3 promise bộ thương hiệu (logo + danh thiếp + video)
- CORE § B.2 auto-derive Scope 2 (brand_short / initials / slogan)
- LUAT 2B F2B.7 (auto-derive)

Bản #1 (chấm điểm) đã có ở `app/core/md_exporter.py` (cho Backend Scoring).
Bản #2 (brandkit) là JSON struct designer team đọc → gen logo/danh thiếp/
video config.

Bot KHÔNG render trong chat — chỉ EXPORT struct. Designer team / hệ
thống ngoài đọc + gen async, push qua Zalo (refer CORE § L.1 Mini App).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from app.models.schema import DealerProfileRaw


def export_brandkit_pack(
    profile: DealerProfileRaw,
    session_id: Optional[str] = None,
) -> dict:
    """Build brandkit pack JSON cho designer team.

    Pack gồm 4 phần (refer CORE § H.4):
    1. logo_elements — tên thương hiệu + viết tắt + sản phẩm chính
    2. color_scheme — màu chủ đạo + phong thủy
    3. namecard — SĐT, Zalo, FB, địa chỉ (cho danh thiếp)
    4. video_config — logo + tone + slogan (cho video giới thiệu)

    Bot CHỈ export struct. Designer team đọc + gen async.

    Args:
        profile: DealerProfileRaw (đã CONFIRMED, có Scope 1 + Scope 2)
        session_id: optional — để track origin session

    Returns:
        Dict JSON-serializable. None values cho field chưa có.

    Pre-condition:
    - profile.brandkit_consent == "yes" (caller check trước)
    - profile.confirmation_status == "CONFIRMED" (caller check trước)

    Note: KHÔNG chứa Scope 4 (c_score, tier, dealer_id) — designer
    không cần biết scoring. Cũng KHÔNG chứa raw signal C1-C9 (cho
    backend scoring riêng).
    """
    pack: dict = {
        "version": "v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "logo_elements": _build_logo_elements(profile),
        "color_scheme": _build_color_scheme(profile),
        "namecard": _build_namecard(profile),
        "video_config": _build_video_config(profile),
    }
    return pack


def export_brandkit_pack_json(
    profile: DealerProfileRaw,
    session_id: Optional[str] = None,
    indent: int = 2,
) -> str:
    """Wrapper trả JSON string (cho file write / API response).

    Args:
        indent: pretty-print indent, 0 = compact.
    """
    pack = export_brandkit_pack(profile, session_id=session_id)
    return json.dumps(pack, ensure_ascii=False, indent=indent or None)


# ============================================================
# Section builders
# ============================================================


def _build_logo_elements(profile: DealerProfileRaw) -> dict:
    """Logo cần: tên đầy đủ, viết tắt, viết tắt 1 chữ, ngành chính."""
    return {
        "dealer_name": profile.dealer_name,
        "brand_name_short": profile.brand_name_short,
        "initials_full": profile.initials_full,
        "initial_single": profile.initial_single,
        "main_product": profile.main_product,
        "main_category": profile.main_category,
    }


def _build_color_scheme(profile: DealerProfileRaw) -> dict:
    """Màu + phong thủy (slot 4.2). null nếu dealer chưa cho."""
    return {
        "color_accent": profile.color_accent,
        "feng_shui_signal": profile.feng_shui_signal,
        # Hint cho designer: nếu null → chọn theo main_category default
        "designer_hint": (
            "Dealer chưa cho màu cụ thể, chọn palette theo main_category."
            if not profile.color_accent
            else None
        ),
    }


def _build_namecard(profile: DealerProfileRaw) -> dict:
    """Danh thiếp: SĐT, Zalo, Facebook, địa chỉ + tên owner."""
    return {
        "owner_name": profile.owner_name,
        "contact_name": profile.contact_name,
        "contact_role": profile.contact_role,
        "hotline": profile.hotline,
        "phone_or_zalo": profile.phone_or_zalo,
        "zalo": profile.zalo,
        "facebook": profile.facebook,
        "address": profile.address,
        "province": profile.province,
        "district": profile.district,
    }


def _build_video_config(profile: DealerProfileRaw) -> dict:
    """Video config: tên brand + slogan options + tone + duration default.

    Defaults theo CORE § H.1 Nhóm 4 (designer team):
    - TVC_DURATION = 8s
    - TVC_RATIO = 16:9
    """
    return {
        "brand_name": profile.brand_name_short or profile.dealer_name,
        "main_product": profile.main_product,
        "slogan_options": _parse_slogan_options(profile.slogan_options),
        "duration_seconds": 8,
        "aspect_ratio": "16:9",
        # Tone gợi ý dựa dealer_type (nếu có signal Khoe → tone tự tin)
        "tone_hint": _suggest_tone(profile.business_model_signal),
    }


def _parse_slogan_options(raw) -> list:
    """Profile.slogan_options là list[str] (Pydantic schema).

    Hỗ trợ cả case raw là JSON str (từ SQLite store cũ) cho backward compat.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _suggest_tone(business_signal: Optional[str]) -> str:
    """Suggest tone video cho designer dựa business_model_signal.

    Note: chỉ là HINT, designer team quyết. KHÔNG khoá case cụ thể —
    designer dùng kinh nghiệm + judgment.
    """
    if not business_signal:
        return "neutral"
    signal_lower = business_signal.lower()
    if any(kw in signal_lower for kw in ["xưởng", "sản xuất", "gia công"]):
        return "professional"
    if any(kw in signal_lower for kw in ["lắp đặt", "thi công", "thợ"]):
        return "trustworthy"
    return "neutral"
