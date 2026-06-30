"""Address parser Layer 2 — LLM fuzzy fallback khi regex Layer 1 fail.

Refer:
- F2B.6 (LUAT_2B_llm) — algorithm 2 layer (regex → LLM fuzzy)
- D8 STRATEGY — LLM_FAST tier (cheap, deterministic 0.0 temp)
- F2A.3 Scope 2 — province/ward auto-derive

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
        "ward": {
            "type": "string",
            "description": "Phường/xã/thị trấn cấp dưới, null nếu không có.",
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
        f"- ward = phường/xã/thị trấn (vd Cát Linh, Đại Thịnh, Phường 1)."
    )


def llm_parse_address(
    address_raw: str,
    client: LLMClient,
) -> tuple[Optional[str], Optional[str]]:
    """LLM Layer 2 fuzzy parse address → (province, ward).

    Args:
        address_raw: Địa chỉ thô từ dealer
        client: LLMClient

    Returns:
        (province_or_None, ward_or_None).
        Province luôn match whitelist 63 tỉnh hoặc None (reject bịa).
    """
    if not address_raw or not isinstance(address_raw, str):
        return (None, None)

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
            tool_description="Parse địa chỉ VN → province + ward.",
            input_schema=_ADDRESS_SCHEMA,
        )
    except Exception as e:
        logger.exception("LLM address parse fail: %s", e)
        return (None, None)

    if not isinstance(result, dict):
        return (None, None)

    province = result.get("province")
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

    ward = ward if ward and isinstance(ward, str) else None

    return (province, ward)


def _norm_for_match(text: str) -> str:
    """Normalize spaces + dots cho fuzzy match."""
    return (
        text.strip().lower()
        .replace(".", "")
        .replace(",", "")
        .replace(" ", "")
    )


def _match_whitelist(
    province: str,
    province_list: list[str],
) -> Optional[str]:
    """Match province text với whitelist, return canonical name hoặc None."""
    if not province or not isinstance(province, str):
        return None
    target_norm = _norm_for_match(province)
    # 1. Exact match (after norm)
    for canonical in province_list:
        if _norm_for_match(canonical) == target_norm:
            return canonical
    # 2. Fuzzy substring match
    for canonical in province_list:
        canonical_norm = _norm_for_match(canonical)
        if canonical_norm in target_norm or target_norm in canonical_norm:
            return canonical
    return None
