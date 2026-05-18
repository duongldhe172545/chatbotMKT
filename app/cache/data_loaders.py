"""Load + cache JSON data files in-memory. Refer F2C.5 + F2C.7.

Phase 1: in-memory cache đơn giản (load 1 lần khi import).
Phase 4+: thêm file-watch reload nếu cần hot-reload dev.

Nguyên tắc "không khoá case":
- Chỉ giữ data file là LUẬT/ENUM hạt nhân (vd 63 tỉnh VN validation,
  7 main_category code).
- BỎ mọi lookup table case-specific (vd province → đặc sản,
  keyword substring → category code). Phase 2 thay = LLM auto-derive.
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
# Province list — 63 tỉnh VN (LUẬT enum validation)
# ============================================================


@lru_cache(maxsize=1)
def get_province_list() -> list[str]:
    """List 63 tỉnh VN (refer F2B.6 + C3 batch 4). LUẬT enum."""
    data = _load_json_file("province_list.json")
    return data.get("provinces", [])


def is_valid_province(province: str) -> bool:
    """Check province có trong whitelist 63 tỉnh không."""
    return province in get_province_list()


# ============================================================
# Main category enum — 7 loại ngành (LUẬT enum, KHÔNG keyword match)
# ============================================================


@lru_cache(maxsize=1)
def get_main_category_list() -> list[dict]:
    """7 category {code, name}. KHÔNG có keywords array (bỏ vì khoá case).

    Suy main_category code từ free text → Phase 2 dùng LLM auto-derive
    với context, KHÔNG substring match.
    """
    data = _load_json_file("main_category_enum.json")
    return data.get("categories", [])


def get_category_codes() -> list[str]:
    """Code list (cua_cuon, cua_nhom_kinh, ...)."""
    return [c["code"] for c in get_main_category_list()]


def get_category_name(code: str) -> str | None:
    """Display name cho 1 category code."""
    for cat in get_main_category_list():
        if cat.get("code") == code:
            return cat.get("name")
    return None


# ============================================================
# Cache invalidation (test only)
# ============================================================


def clear_cache() -> None:
    """Clear all lru_cache — dùng cho test reload data."""
    get_province_list.cache_clear()
    get_main_category_list.cache_clear()
