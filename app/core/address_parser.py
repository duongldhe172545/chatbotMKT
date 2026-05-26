"""Address parser — auto-derive province + district từ raw address.

Layer 1: regex match với whitelist 63 tỉnh VN (LUẬT enum).
Layer 2 LLM fallback: defer Phase 3.

Refer:
- F2B.6 (LUAT_2B_llm) — address parser
- LUAT_2A § F2A.3 Scope 2 — province + district auto-derive

Nguyên tắc "không khoá case":
- Province match từ whitelist 63 tỉnh (LUẬT validation).
- District: extract pattern "Quận X" / "Huyện Y" / "Thành phố Z" / "Thị xã W".
- KHÔNG hard-code mapping quận-tỉnh (cho phép quận Hoàn Kiếm ở HN, quận 1 ở TP.HCM, etc.)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.cache.data_loaders import get_province_list


# ============================================================
# Province alias map — chỉ là LUẬT chuẩn hóa, không phải case-lock
# (HCM/Sài Gòn → TP.HCM là chuẩn hoá tên tỉnh, không phải mapping case)
# ============================================================

# Một số tỉnh có nhiều cách viết phổ biến — chuẩn hóa về tên chuẩn trong province_list.json
_PROVINCE_ALIASES: dict[str, str] = {
    # TP.HCM aliases
    "tp.hcm": "TP.HCM",
    "tp hcm": "TP.HCM",
    "tphcm": "TP.HCM",
    "hcm": "TP.HCM",
    "sài gòn": "TP.HCM",
    "saigon": "TP.HCM",
    "hồ chí minh": "TP.HCM",
    "thành phố hồ chí minh": "TP.HCM",
    # HN aliases
    "hn": "Hà Nội",
    "ha noi": "Hà Nội",
    "hanoi": "Hà Nội",
    # ĐN aliases
    "đn": "Đà Nẵng",
    "da nang": "Đà Nẵng",
    "danang": "Đà Nẵng",
    # Cần Thơ
    "cần thơ": "Cần Thơ",
    "can tho": "Cần Thơ",
    # Hải Phòng
    "hải phòng": "Hải Phòng",
    "hp": "Hải Phòng",
    "hai phong": "Hải Phòng",
}

# District pattern: "Quận X", "Huyện Y", "TP X", "TX Y"
# Capture chars không phải , ; . cho district name (giới hạn 2 từ)
_DISTRICT_NAME = r"([^,;\.\d]+?(?:\s+[^,;\.\s]+)?)(?=[,;\.\n]|\s+$|$)"
_DISTRICT_PATTERN = re.compile(
    r"\b(?:"
    r"Q\.?\s*(\d{1,2})|"                          # Q.1, Q1, Q 1
    r"[Qq]uận\s+(\d{1,2})|"                       # Quận 1, Quận 12
    r"[Qq]uận\s+" + _DISTRICT_NAME + r"|"         # Quận Hoàn Kiếm
    r"[Hh]uyện\s+" + _DISTRICT_NAME + r"|"        # Huyện Đông Anh
    r"TP\.?\s+" + _DISTRICT_NAME + r"|"           # TP. Thủ Đức
    r"[Tt]hành\s+[Pp]hố\s+" + _DISTRICT_NAME + r"|"
    r"TX\.?\s+" + _DISTRICT_NAME + r"|"
    r"[Tt]hị\s+[Xx]ã\s+" + _DISTRICT_NAME +
    r")"
)


def _normalize(text: str) -> str:
    """Lowercase + strip diacritic-aware for matching."""
    return text.strip().lower()


def extract_province(address: Optional[str]) -> Optional[str]:
    """Extract province từ raw address. Match whitelist 63 tỉnh.

    Args:
        address: Raw address text. Có thể là "123 Lê Lợi, Quận 1, TP.HCM"
                 hoặc "Hà Nội" hoặc "Hoàn Kiếm Hà Nội".

    Returns:
        Province chuẩn (đúng case trong province_list.json) hoặc None nếu
        không match.
    """
    if not address or not isinstance(address, str):
        return None

    normalized = _normalize(address)

    # 1. Check aliases trước (TP.HCM, HCM, Sài Gòn...)
    for alias, canonical in _PROVINCE_ALIASES.items():
        if alias in normalized:
            return canonical

    # 2. Substring match với 63 tỉnh whitelist
    provinces = get_province_list()
    # Sort descending by length để match tên dài trước (vd "Hà Nội" trước "Hà")
    sorted_provinces = sorted(provinces, key=len, reverse=True)
    for province in sorted_provinces:
        if province.lower() in normalized:
            return province

    return None


def extract_district(address: Optional[str]) -> Optional[str]:
    """Extract district (quận/huyện/TP/TX) từ raw address.

    Args:
        address: Raw address text.

    Returns:
        District string (vd "Quận 1", "Hoàn Kiếm", "Thủ Đức") hoặc None.
    """
    if not address or not isinstance(address, str):
        return None

    m = _DISTRICT_PATTERN.search(address)
    if not m:
        return None

    # Groups: 0=Q.X digit, 1=Quận digit, 2=Quận name, 3=Huyện, 4=TP,
    #         5=Thành phố, 6=TX, 7=Thị xã
    groups = m.groups()
    for i, value in enumerate(groups):
        if value is None:
            continue
        cleaned = value.strip().rstrip(",.")
        # Q.1 / Q1 → "Quận 1"
        if i == 0 or i == 1:
            return f"Quận {cleaned}"
        return cleaned

    return None


def parse_address(
    address: Optional[str],
    client=None,
) -> tuple[Optional[str], Optional[str]]:
    """Parse address → (province, district).

    3-layer:
    - Layer 1: regex match whitelist 63 tỉnh + aliases
    - Layer 2: LLM_FAST fuzzy nếu Layer 1 fail (client passed)
    - District: regex pattern (luôn áp)

    Args:
        address: Raw address text
        client: Optional LLMClient. Nếu provided + Layer 1 fail → Layer 2 LLM.

    Returns:
        (province_or_None, district_or_None)
    """
    if not address or not isinstance(address, str):
        return (None, None)

    province = extract_province(address)
    district = extract_district(address)

    # Layer 2 LLM fallback nếu Layer 1 không match province
    if province is None and client is not None:
        try:
            from app.llm.address_llm import llm_parse_address
            llm_province, llm_district, _ = llm_parse_address(address, client)
            if llm_province:
                province = llm_province
            if district is None and llm_district:
                district = llm_district
        except Exception:
            # Layer 2 fail → giữ Layer 1 result (None)
            pass

    return (province, district)
