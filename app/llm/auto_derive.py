"""Auto-derive Scope 2 fields qua LLM_FAST.

Refer:
- F2B.7 (LUAT_2B_llm) — auto-derive brand_short/initials/slogan
- F2A.3 Scope 2 — chatbot derive fields

Phase 2 implement: derive_main_category (từ main_product raw text →
1 trong 7 enum code). LLM-driven, KHÔNG substring keyword match
(refer feedback_no_case_lock).

Phase 5 R0: brand_name_short, initials_full, initial_single, slogan_options.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Optional

from app.cache.data_loaders import (
    _load_json_file,
    get_category_codes,
    get_main_category_list,
)
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)


# ============================================================
# Common words filter cho initials
# ============================================================


@lru_cache(maxsize=1)
def _load_common_words() -> set[str]:
    """Load common ngành words → set lowercase."""
    data = _load_json_file("common_words_filter.json")
    words = data.get("common_words", [])
    return {w.lower().strip() for w in words if w}


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
        additional_context: Context bổ sung (vd category_stack từ slot 2.1)
                            để LLM hiểu rõ hơn.

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


# ============================================================
# Phase 5 R0: brand_name_short + initials + slogan
# ============================================================


_INITIALS_MAX_LEN = 6  # Refer F2B.7 constraint


def gen_initials_full(dealer_name: Optional[str]) -> Optional[str]:
    """Sinh initials từ dealer_name. Pure Python, không LLM.

    Args:
        dealer_name: vd "Nhôm Kính Thanh Tùng"

    Returns:
        Initials uppercase (vd "TT" sau filter common words "Nhôm"/"Kính").
        None nếu input empty / sau filter còn 0 word.

    Algorithm:
    1. Tokenize lower
    2. Filter common words (data/common_words_filter.json)
    3. Concat first char each remaining → uppercase
    4. Limit ≤ INITIALS_MAX_LEN (6 chữ)
    """
    if not dealer_name or not isinstance(dealer_name, str):
        return None
    common = _load_common_words()
    # Split tokens — preserve diacritic
    tokens = re.findall(r"\w+", dealer_name, flags=re.UNICODE)
    filtered = [t for t in tokens if t.lower() not in common]
    if not filtered:
        # Fallback: dùng all tokens nếu filter sạch hết
        filtered = tokens
    initials = "".join(t[0].upper() for t in filtered if t)
    if not initials:
        return None
    return initials[:_INITIALS_MAX_LEN]


def gen_initial_single(initials_full: Optional[str]) -> Optional[str]:
    """Lấy 1 chữ biểu trưng. Default = chữ cái cuối initials (thường là
    tên riêng người chủ, vd "NKTT" → "T").

    Args:
        initials_full: vd "NKTT"

    Returns:
        1 ký tự uppercase, None nếu empty.
    """
    if not initials_full or not isinstance(initials_full, str):
        return None
    cleaned = initials_full.strip().upper()
    if not cleaned:
        return None
    return cleaned[-1]   # last char — thường là chữ cái tên riêng cuối


# ============================================================
# LLM-driven: derive_brand_short + gen_slogans
# ============================================================


_BRAND_SHORT_SCHEMA = {
    "name": "derive_brand_short",
    "description": (
        "Rút gọn dealer_name thành brand_short ngắn (1-3 từ). Giữ phần "
        "định danh (tên riêng người/từ riêng), bỏ từ chung ngành "
        "(Nhôm Kính, Cửa Cuốn, Tủ Bếp, Công Ty TNHH, ...)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "brand_short": {
                "type": ["string", "null"],
                "description": (
                    "1-3 từ định danh. Vd 'Thanh Tùng' từ 'Nhôm Kính "
                    "Thanh Tùng'. Null nếu không rút được."
                ),
                "maxLength": 50,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


_SLOGAN_SCHEMA = {
    "name": "gen_slogans",
    "description": (
        "Sinh 5 slogan ngắn (≤ 10 từ mỗi câu) cho cửa hàng. Tiếng Việt, "
        "dễ nhớ, KHÔNG dùng 'best/number 1/tốt nhất' (claim sai sự thật). "
        "Không quá sến."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slogans": {
                "type": "array",
                "items": {"type": "string", "maxLength": 100},
                "minItems": 3,
                "maxItems": 5,
                "description": "3-5 slogan tiếng Việt, ≤ 10 từ/câu.",
            },
        },
        "required": ["slogans"],
        "additionalProperties": False,
    },
}


def derive_brand_short(
    dealer_name: Optional[str],
    client: LLMClient,
) -> Optional[str]:
    """LLM rút gọn dealer_name → brand_short.

    Args:
        dealer_name: vd "Nhôm Kính Thanh Tùng"
        client: LLMClient

    Returns:
        brand_short ngắn (vd "Thanh Tùng"). None nếu LLM fail / null.
    """
    if not dealer_name or not isinstance(dealer_name, str):
        return None

    system = (
        "Bạn là module rút gọn tên thương hiệu cho dealer ngành cửa nhôm "
        "kính / cửa cuốn / tủ bếp / VLXD Việt Nam.\n\n"
        "Quy tắc:\n"
        "- Rút thành 1-3 từ định danh.\n"
        "- Giữ tên riêng người (vd 'Thanh Tùng', 'Quốc Vinh'), từ riêng "
        "địa danh (vd 'Sài Gòn').\n"
        "- BỎ từ chung ngành: 'Nhôm Kính', 'Cửa Cuốn', 'Tủ Bếp', "
        "'Công Ty', 'TNHH', 'CP', 'Cổ Phần', 'Đại Lý'.\n"
        "- Nếu dealer_name CHỈ chứa từ ngành (vd 'Tủ Bếp Đẹp') → trả "
        "phần còn lại (vd 'Đẹp').\n"
        "- KHÔNG bịa tên không có trong dealer_name."
    )

    try:
        result = client.extract_fast(
            system_prompt=system,
            conversation_text=f"dealer_name: {dealer_name}",
            tool_name=_BRAND_SHORT_SCHEMA["name"],
            tool_description=_BRAND_SHORT_SCHEMA["description"],
            input_schema=_BRAND_SHORT_SCHEMA["input_schema"],
        )
    except Exception as e:
        logger.exception("derive_brand_short fail: %s", e)
        return None

    if not isinstance(result, dict):
        return None
    short = result.get("brand_short")
    if not short or not isinstance(short, str):
        return None
    return short.strip()


def gen_slogans(
    dealer_name: Optional[str],
    main_product: Optional[str],
    client: LLMClient,
    province: Optional[str] = None,
    use_quality: bool = True,
) -> list[str]:
    """LLM gen 5 slogan options.

    Args:
        dealer_name: Tên cửa hàng (required)
        main_product: Sản phẩm chính (required)
        client: LLMClient
        province: Optional context — tỉnh
        use_quality: True dùng LLM_QUALITY (sáng tạo). False = LLM_FAST.

    Returns:
        List 3-5 slogan. Empty nếu LLM fail.
    """
    if not dealer_name or not main_product:
        return []

    system = (
        "Bạn là copywriter Việt Nam sinh slogan cho cửa hàng ngành cửa "
        "nhôm kính / cửa cuốn / tủ bếp / VLXD.\n\n"
        "Quy tắc:\n"
        "- 5 slogan tiếng Việt thuần.\n"
        "- Mỗi slogan ≤ 10 từ, dễ nhớ.\n"
        "- CẤM dùng 'best', 'number 1', 'tốt nhất', 'hàng đầu', 'số 1' "
        "(claim sai sự thật, vi phạm Luật Quảng cáo).\n"
        "- KHÔNG quá sến/cliché ('thay đổi cuộc đời', 'biến giấc mơ thành "
        "sự thật').\n"
        "- Có thể nhắc tên ngắn của cửa hàng hoặc sản phẩm.\n"
        "- KHÔNG bịa địa danh không có trong context."
    )

    user_text = (
        f"dealer_name: {dealer_name}\n"
        f"main_product: {main_product}\n"
    )
    if province:
        user_text += f"province: {province}\n"

    extract_fn = client.extract_quality if use_quality else client.extract_fast
    try:
        result = extract_fn(
            system_prompt=system,
            conversation_text=user_text,
            tool_name=_SLOGAN_SCHEMA["name"],
            tool_description=_SLOGAN_SCHEMA["description"],
            input_schema=_SLOGAN_SCHEMA["input_schema"],
        )
    except Exception as e:
        logger.exception("gen_slogans fail: %s", e)
        return []

    if not isinstance(result, dict):
        return []
    slogans = result.get("slogans")
    if not isinstance(slogans, list):
        return []
    # Filter empty + dedupe
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in slogans:
        if not isinstance(s, str) or not s.strip():
            continue
        normalized = s.strip()
        if normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        cleaned.append(normalized)
    return cleaned


def clear_cache() -> None:
    """Clear lru_cache (test)."""
    _load_common_words.cache_clear()
