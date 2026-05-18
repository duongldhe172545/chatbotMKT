"""Load + cache JSON data files in-memory. Refer F2C.5 + F2C.7.

Phase 1: in-memory cache đơn giản (load 1 lần khi import).
Phase 4+: thêm file-watch reload nếu cần hot-reload dev.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


# Data folder (relative to project root)
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_json_file(filename: str) -> dict:
    """Load JSON file từ data/ directory."""
    path = _DATA_DIR / filename
    if not path.exists():
        logger.warning("Data file không tồn tại: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Lỗi load %s: %s", filename, e)
        return {}


# ============================================================
# Province list — 63 tỉnh VN
# ============================================================


@lru_cache(maxsize=1)
def get_province_list() -> list[str]:
    """List 63 tỉnh VN cũ (refer F2B.6 + C3 batch 4)."""
    data = _load_json_file("province_list.json")
    return data.get("provinces", [])


def is_valid_province(province: str) -> bool:
    """Check province có trong whitelist 63 tỉnh không."""
    return province in get_province_list()


# ============================================================
# Province specialty — 50/63 tỉnh có specialty
# ============================================================


@lru_cache(maxsize=1)
def get_province_specialty_map() -> dict[str, str]:
    """Map {province: specialty_text}. 50 tỉnh có, 13 không.

    Dùng cho hook đặc sản trong Closing (F2A.8 + 1A § 7).
    """
    data = _load_json_file("province_specialty.json")
    return data.get("specialties", {})


def get_specialty(province: str) -> str | None:
    """Trả specialty cho province. None nếu không có (Closing fallback generic)."""
    return get_province_specialty_map().get(province)


# ============================================================
# Main category enum — 7 loại ngành
# ============================================================


@lru_cache(maxsize=1)
def get_main_category_list() -> list[dict]:
    """7 category {code, name, keywords}."""
    data = _load_json_file("main_category_enum.json")
    return data.get("categories", [])


def get_category_codes() -> list[str]:
    """Code list (cua_cuon, cua_nhom_kinh, ...)."""
    return [c["code"] for c in get_main_category_list()]


def find_category_by_keyword(text: str) -> str | None:
    """Match text với keywords để suy main_category code.

    Phase 1 simple: substring match (case-insensitive).
    Phase 2+: LLM auto-derive với fuzzy + context.

    Returns category code hoặc None.
    """
    if not text:
        return None
    text_lower = text.lower()
    for cat in get_main_category_list():
        for kw in cat.get("keywords", []):
            if kw.lower() in text_lower:
                return cat["code"]
    return None


# ============================================================
# Cache invalidation (test only)
# ============================================================


def clear_cache() -> None:
    """Clear all lru_cache — dùng cho test reload data."""
    get_province_list.cache_clear()
    get_province_specialty_map.cache_clear()
    get_main_category_list.cache_clear()
