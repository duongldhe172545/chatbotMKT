"""Address parser — auto-derive province + ward từ raw address.

Layer 1: regex match với whitelist 63 tỉnh VN (LUẬT enum).
Layer 2: LLM fuzzy fallback (app/llm/address_llm.py) khi Layer 1 fail.

Refer:
- F2B.6 (LUAT_2B_llm) — address parser
- LUAT_2A § F2A.3 Scope 2 — province + ward auto-derive

Nguyên tắc "không khoá case":
- Province match từ whitelist 63 tỉnh (LUẬT validation).
- Ward: extract phường/xã/thị trấn.
- KHÔNG hard-code mapping (cho phép mọi tổ hợp ward-tỉnh).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.cache.data_loaders import get_province_list

# Ward pattern: "Phường X", "Xã Y", "Thị trấn Z"
_WARD_NAME = r"([^,;\.\d]+?(?:\s+[^,;\.\s]+)?)(?=[,;\.\n]|\s+$|$)"
_WARD_PATTERN = re.compile(
    r"\b(?:"
    r"[Pp]\.?\s*(\d{1,2})|"                       # P.1, P1, P 1
    r"[Pp]hường\s+(\d{1,2})|"                     # Phường 1, Phường 12
    r"[Pp]hường\s+" + _WARD_NAME + r"|"           # Phường Cát Linh
    r"[Xx]ã\s+" + _WARD_NAME + r"|"               # Xã Đại Thịnh
    r"[Tt]hị\s+[Tt]rấn\s+" + _WARD_NAME +
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

    # Substring match với 63 tỉnh whitelist
    provinces = get_province_list()
    # Sort descending by length để match tên dài trước (vd "Hà Nội" trước "Hà")
    sorted_provinces = sorted(provinces, key=len, reverse=True)
    for province in sorted_provinces:
        if province.lower() in normalized:
            return province

    return None


def extract_ward(address: Optional[str]) -> Optional[str]:
    """Extract ward (phường/xã/thị trấn) từ raw address.

    Args:
        address: Raw address text.

    Returns:
        Ward string (vd "Phường 1", "Cát Linh", "Đại Thịnh") hoặc None.
    """
    if not address or not isinstance(address, str):
        return None

    m = _WARD_PATTERN.search(address)
    if not m:
        return None

    # Groups: 0=P.X digit, 1=Phường digit, 2=Phường name, 3=Xã, 4=Thị trấn
    groups = m.groups()
    for i, value in enumerate(groups):
        if value is None:
            continue
        cleaned = value.strip().rstrip(",.")
        # P.1 / P1 → "Phường 1"
        if i == 0 or i == 1:
            return f"Phường {cleaned}"
        return cleaned

    return None


def parse_address(
    address: Optional[str],
    client=None,
) -> tuple[Optional[str], Optional[str]]:
    """Parse address → (province, ward).

    3-layer:
    - Layer 1: regex match whitelist 63 tỉnh + aliases
    - Layer 2: LLM_FAST fuzzy nếu Layer 1 fail (client passed)
    - Ward: regex pattern (luôn áp)

    Args:
        address: Raw address text
        client: Optional LLMClient. Nếu provided + Layer 1 fail → Layer 2 LLM.

    Returns:
        (province_or_None, ward_or_None)
    """
    if not address or not isinstance(address, str):
        return (None, None)

    province = extract_province(address)
    ward = extract_ward(address)

    # Layer 2 LLM fallback nếu Layer 1 không match province
    if province is None and client is not None:
        try:
            from app.llm.address_llm import llm_parse_address
            llm_province, llm_ward = llm_parse_address(address, client)
            if llm_province:
                province = llm_province
            if ward is None and llm_ward:
                ward = llm_ward
        except Exception:
            # Layer 2 fail → giữ Layer 1 result (None)
            pass

    return (province, ward)
