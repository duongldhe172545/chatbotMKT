"""STT brand correction — refer LUAT_2B § F2B.5 + KICH_BAN_1C § 8.

Mục đích: dealer nói qua voice → STT phiên âm → tên brand bị nhầm
(vd "Xingfa" → "xinhpha", "Schüco" → "su cô"). Module này:
1. Load mapping từ data/stt_corrections.json
2. Correct text trước khi pass cho extractor LLM
3. Phase 5+ wire voice channel thật

API:
- correct_stt(text) → corrected_text (apply mapping)
- correct_brand(brand_name) → tên chuẩn nếu có mapping, else giữ nguyên
- get_corrections_count() → debug

Note: dùng cho cả TEXT input nếu dealer gõ sai chính tả brand (vd
"Vi gla xê ra" → "Viglacera"). Phase 4 R2 chỉ implement Layer 1
dictionary substitution. Phase 5 wire Layer 2 LLM fuzzy match.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from app.cache.data_loaders import _load_json_file

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_corrections() -> dict[str, str]:
    """Flat dict: lowercase typo → correct (giữ case Việt hoa thường)."""
    data = _load_json_file("stt_corrections.json")
    flat: dict[str, str] = {}
    for group_key in ("brand_corrections", "common_vn_corrections"):
        group = data.get(group_key, {})
        mapping = group.get("mapping", {})
        for typo, correct in mapping.items():
            if not isinstance(typo, str) or not isinstance(correct, str):
                continue
            flat[typo.lower().strip()] = correct
    return flat


def correct_stt(text: str | None) -> str:
    """Apply STT corrections cho text.

    Args:
        text: Raw text (có thể từ STT hoặc dealer gõ)

    Returns:
        Text đã correct (case-insensitive match, longest-first).
        Match boundary ranh word để tránh false replace giữa từ.
    """
    if not text or not isinstance(text, str):
        return text or ""

    corrections = _load_corrections()
    if not corrections:
        return text

    result = text
    # Sort longest typo first (avoid "vi gla xê ra" bị "xê" replace trước)
    sorted_typos = sorted(corrections.keys(), key=len, reverse=True)

    for typo in sorted_typos:
        correct = corrections[typo]
        # Word-boundary case-insensitive replace
        pattern = re.compile(
            r"\b" + re.escape(typo) + r"\b",
            re.IGNORECASE,
        )
        if pattern.search(result):
            result = pattern.sub(correct, result)
            logger.debug("STT correct: %r → %r", typo, correct)

    return result


def get_correction_candidates(
    text: str | None,
    *,
    brands_only: bool = False,
) -> list[tuple[str, str]]:
    """Return dictionary corrections present in raw text, longest-first.

    The voice pipeline may apply these automatically. The LLM-first typed
    intake flow also uses this list to ask for confirmation before persisting
    a phonetically guessed supplier brand.
    """
    if not text or not isinstance(text, str):
        return []
    corrections = _load_corrections()
    if brands_only:
        data = _load_json_file("stt_corrections.json")
        corrections = {
            typo.lower().strip(): correct
            for typo, correct in data.get("brand_corrections", {}).get("mapping", {}).items()
            if isinstance(typo, str) and isinstance(correct, str)
        }
    candidates: list[tuple[str, str]] = []
    for typo, correct in sorted(corrections.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(r"\b" + re.escape(typo) + r"\b", re.IGNORECASE)
        if pattern.search(text):
            candidates.append((typo, correct))
    return candidates


def correct_brand(brand_name: str | None) -> str:
    """Correct 1 brand name (exact match trong mapping).

    Args:
        brand_name: Brand từ STT/extractor

    Returns:
        Brand chuẩn nếu có mapping, else giữ nguyên (trim).
    """
    if not brand_name or not isinstance(brand_name, str):
        return brand_name or ""
    key = brand_name.lower().strip()
    return _load_corrections().get(key, brand_name.strip())


def get_corrections_count() -> int:
    """Số mapping load được (debug)."""
    return len(_load_corrections())


def clear_cache() -> None:
    """Clear lru_cache — dùng cho test reload data file."""
    _load_corrections.cache_clear()
