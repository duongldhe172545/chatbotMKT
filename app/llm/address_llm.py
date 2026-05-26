"""Address parser Layer 2 — LLM fuzzy fallback khi regex Layer 1 fail.

Refer:
- F2B.6 (LUAT_2B_llm) — algorithm 3 layer (regex → LLM → district extract)
- D8 STRATEGY — LLM_FAST tier (cheap, deterministic 0.0 temp)
- F2A.3 Scope 2 — province/district auto-derive

Khi dealer gõ sai chính tả ("Hà Nôi" thiếu dấu) hoặc viết lạ ("vùng cao
xa lắm"), regex match whitelist 63 tỉnh KHÔNG cover. Layer 2 LLM fuzzy
match với whitelist + trả province chuẩn hoặc null.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.cache.data_loaders import get_province_list
from app.llm.client import LLMClient
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


_ADDRESS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "province": {
            "type": "string",
            "description": (
                "Tên tỉnh/thành phố chuẩn theo whitelist 63 tỉnh VN, "
                "hoặc null nếu không xác định được."
            ),
        },
        "district": {
            "type": "string",
            "description": "Quận/huyện/thị xã/TP trực thuộc tỉnh, null nếu không có.",
        },
        "ward": {
            "type": "string",
            "description": "Phường/xã (optional), null nếu không có.",
        },
    },
    "required": ["province"],
}


def _build_task(address_raw: str, province_list: list[str]) -> str:
    """Task instruction cho LLM_FAST address parser."""
    provinces_str = ", ".join(province_list)
    return (
        f'Phân tích địa chỉ Việt Nam sau:\n"{address_raw}"\n\n'
        f"Whitelist 63 tỉnh chuẩn (BẮT BUỘC match đúng):\n{provinces_str}\n\n"
        f"Yêu cầu:\n"
        f"- province PHẢI là 1 trong whitelist 63 tỉnh (đúng chính tả + dấu).\n"
        f"- Nếu địa chỉ không chứa tỉnh xác định được → province=null.\n"
        f'- Hiểu các viết tắt: "TPHCM"/"HCM"/"Sài Gòn" → "TP.HCM"; "HN" → "Hà Nội".\n'
        f'- Hiểu sai chính tả nhẹ: "Hà Nôi" → "Hà Nội", "Hồ Chí Minh" → "TP.HCM".\n'
        f"- KHÔNG bịa tỉnh ngoài whitelist (vd Thái Lan, Lào, Campuchia → null).\n"
        f"- district = quận/huyện/thị xã/TP cấp dưới (vd Hoàn Kiếm, Quận 1).\n"
        f"- ward = phường/xã (optional)."
    )


def llm_parse_address(
    address_raw: str,
    client: LLMClient,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """LLM Layer 2 fuzzy parse address → (province, district, ward).

    Args:
        address_raw: Địa chỉ thô từ dealer
        client: LLMClient

    Returns:
        (province_or_None, district_or_None, ward_or_None).
        Province luôn match whitelist 63 tỉnh hoặc None (reject bịa).
    """
    if not address_raw or not isinstance(address_raw, str):
        return (None, None, None)

    province_list = get_province_list()
    task = _build_task(address_raw, province_list)
    system = build_system_prompt(
        dealer_type=DealerType.UNKNOWN,
        address_form=AddressForm.ANH,
        task=task,
    )

    try:
        result = client.extract_fast(
            system_prompt=system,
            conversation_text=f"Địa chỉ dealer: {address_raw}",
            tool_name="parse_vn_address",
            tool_description="Parse địa chỉ VN → province + district + ward.",
            input_schema=_ADDRESS_SCHEMA,
        )
    except Exception as e:
        logger.exception("LLM address parse fail: %s", e)
        return (None, None, None)

    if not isinstance(result, dict):
        return (None, None, None)

    province = result.get("province")
    district = result.get("district")
    ward = result.get("ward")

    # Validate province PHẢI match whitelist (chống bịa)
    if province:
        province_normalized = _match_whitelist(province, province_list)
        if not province_normalized:
            logger.warning(
                "LLM bịa province ngoài whitelist: %r — reject", province,
            )
            province = None
        else:
            province = province_normalized

    district = district if district and isinstance(district, str) else None
    ward = ward if ward and isinstance(ward, str) else None

    return (province, district, ward)


def _norm_for_match(text: str) -> str:
    """Normalize spaces + dots cho fuzzy match."""
    return (
        text.strip().lower()
        .replace(".", "")
        .replace(",", "")
        .replace("  ", " ")
    )


# Alias map cho LLM output thường gặp → canonical trong whitelist
_LLM_PROVINCE_ALIAS: dict[str, str] = {
    "ho chi minh": "TP.HCM",
    "hồ chí minh": "TP.HCM",
    "thanh pho ho chi minh": "TP.HCM",
    "thành phố hồ chí minh": "TP.HCM",
    "tp ho chi minh": "TP.HCM",
    "tp hồ chí minh": "TP.HCM",
    "tphcm": "TP.HCM",
    "tp hcm": "TP.HCM",
    "hcm": "TP.HCM",
    "sài gòn": "TP.HCM",
    "sai gon": "TP.HCM",
}


def _match_whitelist(
    province: str,
    province_list: list[str],
) -> Optional[str]:
    """Match province text với whitelist, return canonical name hoặc None."""
    if not province or not isinstance(province, str):
        return None
    target_norm = _norm_for_match(province)
    # 1. Alias map check trước (HCM/Sài Gòn → TP.HCM)
    if target_norm in _LLM_PROVINCE_ALIAS:
        return _LLM_PROVINCE_ALIAS[target_norm]
    # 2. Exact match (after norm)
    for canonical in province_list:
        if _norm_for_match(canonical) == target_norm:
            return canonical
    # 3. Fuzzy substring match
    for canonical in province_list:
        canonical_norm = _norm_for_match(canonical)
        if canonical_norm in target_norm or target_norm in canonical_norm:
            return canonical
    return None
