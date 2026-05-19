"""Brand whitelist check — refer KICH_BAN_1C § 11 + LUAT_2B § F2B.5.

Mục đích:
- Compare extracted supplier_brands vs whitelist (load từ brand_list.json).
- Nếu có brand KHÔNG trong whitelist → flag BRAND_NOT_IN_WHITELIST cho admin
  review (có thể bổ sung whitelist sau).
- VẪN save raw brand vào profile (KHÔNG suspicion với dealer — refer 1C § 11).

API:
- is_brand_known(brand_name) → True nếu trong whitelist
- get_unknown_brands(brands: list[str]) → list brand lạ
- get_all_brands() → flat list whitelist (debug)
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

from app.cache.data_loaders import _load_json_file

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_brand_whitelist() -> set[str]:
    """Load brand whitelist từ JSON, flatten 6 category → 1 set lowercase."""
    data = _load_json_file("brand_list.json")
    categories = data.get("categories", {})
    flat: set[str] = set()
    for cat_data in categories.values():
        brands = cat_data.get("brands", [])
        for b in brands:
            if b and isinstance(b, str):
                flat.add(b.lower().strip())
    return flat


def is_brand_known(brand_name: str | None) -> bool:
    """True nếu brand trong whitelist. Match case-insensitive.

    Args:
        brand_name: Brand name dealer cho (vd "Xingfa", "PMA")

    Returns:
        True nếu khớp 1 entry trong whitelist (case-insensitive).
    """
    if not brand_name or not isinstance(brand_name, str):
        return False
    normalized = brand_name.strip().lower()
    if not normalized:
        return False
    return normalized in _load_brand_whitelist()


def get_unknown_brands(brands: Iterable[str] | None) -> list[str]:
    """Trả list brand KHÔNG có trong whitelist.

    Args:
        brands: List brand names từ extractor (vd ["Xingfa", "XYZ Premium"])

    Returns:
        List brand lạ. Empty nếu tất cả known.
    """
    if not brands:
        return []
    unknown: list[str] = []
    for b in brands:
        if not is_brand_known(b):
            unknown.append(b)
    return unknown


def get_all_brands() -> list[str]:
    """Flat list whitelist (debug)."""
    return sorted(_load_brand_whitelist())


def clear_cache() -> None:
    """Clear lru_cache — dùng cho test."""
    _load_brand_whitelist.cache_clear()
