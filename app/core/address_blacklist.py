"""Address blacklist — chính trị / tôn giáo / vùng miền slur.

Refer:
- KICH_BAN_1C § 10 — Address blacklist edge case
- LUAT_2A § F2A.7 — Sanity check 5-point (point 3)
- data/address_blacklist.json — keywords data file

Phase 3 R1: extract logic từ validators.py ra module riêng. Validator
vẫn dùng hàm này để check, nhưng giờ data từ JSON (admin update không
cần deploy).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from app.cache.data_loaders import _load_json_file

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_blacklist() -> dict[str, list[str]]:
    """Load keywords từ JSON, group theo category.

    Returns:
        {"chinh_tri": [...], "ton_giao": [...], "vung_mien_slur": [...]}
    """
    data = _load_json_file("address_blacklist.json")
    categories = data.get("categories", {})
    result: dict[str, list[str]] = {}
    for cat_name, cat_data in categories.items():
        keywords = cat_data.get("keywords", [])
        result[cat_name] = [k.lower() for k in keywords if k]
    return result


def get_all_keywords() -> list[str]:
    """Trả flat list tất cả blacklist keywords (lowercase)."""
    flat: list[str] = []
    for keywords in _load_blacklist().values():
        flat.extend(keywords)
    return flat


def check_address_blacklist(text: Optional[str]) -> Optional[str]:
    """Check text có match keyword trong blacklist không.

    Args:
        text: Address (hoặc bất kỳ text nào) cần check

    Returns:
        Category name nếu match ("chinh_tri" / "ton_giao" / "vung_mien_slur"),
        None nếu clean.

    Logic: case-insensitive substring match. Match category trả về SỚM
    NHẤT (priority: chinh_tri > ton_giao > vung_mien_slur — theo thứ tự
    dict trong JSON).
    """
    if not text or not isinstance(text, str):
        return None
    text_lower = text.lower()
    for cat_name, keywords in _load_blacklist().items():
        for kw in keywords:
            if kw in text_lower:
                logger.warning(
                    "Address blacklist hit: category=%s keyword=%r text=%r",
                    cat_name, kw, text[:100],
                )
                return cat_name
    return None


def is_blacklisted(text: Optional[str]) -> bool:
    """Convenience wrapper: True nếu match blacklist."""
    return check_address_blacklist(text) is not None


def clear_cache() -> None:
    """Clear lru_cache — dùng cho test."""
    _load_blacklist.cache_clear()
