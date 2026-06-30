"""Auto-derive Scope 2 — derive_main_category (từ main_product raw text →
1 trong 7 enum code). LLM-driven, KHÔNG substring keyword match
(refer feedback_no_case_lock).

(2026-06-24) Đã bỏ gen brand_short/initials/slogan — tàn dư luồng tự-gen-logo cũ.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.cache.data_loaders import (
    get_category_codes,
    get_main_category_list,
)
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)


# ============================================================
# Tool schema cho LLM derive main_category
# ============================================================

def _build_main_category_schema() -> dict:
    """Build JSON schema với enum dynamic từ data file."""
    codes = get_category_codes()
    return {
        "name": "derive_main_category",
        "description": (
            "Suy ra main_category code từ main_product raw text + context. "
            "KHÔNG substring keyword match — phải dùng hiểu biết về ngành "
            "để chọn 1 trong 7 enum code phù hợp nhất. Null nếu không xác "
            "định được."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "main_category": {
                    "type": ["string", "null"],
                    "enum": codes + [None],
                    "description": (
                        "1 trong 7 code: cua_cuon, cua_nhom_kinh, cua_thep, "
                        "tu_bep, solar, bao_tri_sua_chua, vlxd_tong_hop. "
                        "Null nếu main_product không rõ thuộc loại nào."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def _build_derive_prompt() -> str:
    """System prompt ngắn — chuyên cho derive task, không cần persona Em Linh."""
    cats = get_main_category_list()
    cat_lines = "\n".join(f"- `{c['code']}`: {c['name']}" for c in cats)
    return (
        "Bạn là module phân loại main_category cho dealer ngành cửa / nhôm "
        "kính / tủ bếp / VLXD Việt Nam.\n\n"
        f"7 enum code có sẵn:\n{cat_lines}\n\n"
        "Quy tắc:\n"
        "- Suy luận dựa context, KHÔNG substring keyword.\n"
        "- Vd 'cửa sổ nhôm kính hệ Xingfa' → cua_nhom_kinh.\n"
        "- Vd 'cửa cuốn motor tự động' → cua_cuon.\n"
        "- Vd 'tủ bếp gỗ MDF + acrylic' → tu_bep.\n"
        "- Vd 'pin năng lượng mặt trời' → solar.\n"
        "- Vd 'bảo trì cửa cuốn cũ' → bao_tri_sua_chua.\n"
        "- Vd 'bán đa ngành VLXD' → vlxd_tong_hop.\n"
        "- Nếu mơ hồ ('em đa ngành', 'bán linh tinh') → null hoặc "
        "vlxd_tong_hop tuỳ context.\n"
        "Trả về JSON đúng schema."
    )


# ============================================================
# Main function
# ============================================================


def derive_main_category(
    main_product: Optional[str],
    client: LLMClient,
    additional_context: str = "",
) -> Optional[str]:
    """Derive main_category code từ main_product raw text qua LLM_FAST.

    Args:
        main_product: Raw text từ slot 2.1 (vd "cửa nhôm kính hệ Xingfa").
                      None → return None (không có gì để derive).
        client: LLMClient.
        additional_context: Context bổ sung tuỳ chọn để LLM hiểu rõ hơn.

    Returns:
        1 trong 7 category code, hoặc None nếu LLM không xác định được /
        LLM fail.

    Nguyên tắc: KHÔNG substring keyword match. LLM dùng context để suy.
    """
    if not main_product or not isinstance(main_product, str) or not main_product.strip():
        return None

    tool = _build_main_category_schema()
    system = _build_derive_prompt()

    user_text = f"main_product: {main_product.strip()}"
    if additional_context:
        user_text += f"\n\nadditional context: {additional_context}"

    try:
        result = client.extract_fast(
            system_prompt=system,
            conversation_text=user_text,
            tool_name=tool["name"],
            tool_description=tool["description"],
            input_schema=tool["input_schema"],
        )
    except Exception as e:
        logger.exception("LLM derive_main_category fail: %s", e)
        return None

    if not isinstance(result, dict):
        return None

    code = result.get("main_category")
    if code is None:
        return None
    if code not in get_category_codes():
        logger.warning("LLM trả main_category invalid: %r", code)
        return None
    return code

