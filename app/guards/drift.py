"""G3 — Drift guard: forbidden vocab + auto-rewrite.

Refer LUAT_2B § F2B.8 G3 + CORE § C.1 + GLOSSARY § 6.

Mục đích:
- LLM hay slip vocab cấm vào bot response (Tier, BRANDKIT, Profile...)
- Hoặc dùng English thay vì Việt hóa
- Drift guard check + auto-rewrite trước khi gửi reply cho dealer

Data: data/forbidden_vocab.json (load qua data_loaders).
- scoring_internal[]: cấm tuyệt đối → REMOVE
- english_to_vietnamese{}: mapping → REWRITE

API:
- check_drift(text) → list[str] violations (vocab cấm tìm thấy)
- auto_rewrite(text) → cleaned text (REWRITE + REMOVE applied)
- has_forbidden_scoring_vocab(text) → bool (chỉ check scoring vocab —
  dùng cho admin queue trigger "drift" flag, không trigger cho english)
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from app.cache.data_loaders import _load_json_file

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_vocab() -> dict:
    """Load forbidden_vocab.json (cache 1 lần)."""
    return _load_json_file("forbidden_vocab.json")


@lru_cache(maxsize=1)
def _get_scoring_vocab() -> list[str]:
    """Vocab Backend Scoring nội bộ — TUYỆT ĐỐI cấm."""
    data = _load_vocab()
    return data.get("scoring_internal", {}).get("keywords", [])


@lru_cache(maxsize=1)
def _get_rewrite_mapping() -> dict[str, str]:
    """English → Việt mapping."""
    data = _load_vocab()
    return data.get("english_to_vietnamese", {}).get("mapping", {})


def check_drift(text: str) -> list[str]:
    """Trả list vocab cấm tìm thấy trong text.

    Args:
        text: Bot response candidate

    Returns:
        List vocab vi phạm (có thể empty). Match case-insensitive
        substring.

    Note: dùng cho LOG + flag drift. Caller (conversation orchestrator)
    nên gọi auto_rewrite() để fix output trước khi gửi dealer.
    """
    if not text or not isinstance(text, str):
        return []
    violations: list[str] = []
    text_lower = text.lower()
    # Scoring vocab
    for vocab in _get_scoring_vocab():
        if vocab.lower() in text_lower:
            violations.append(vocab)
    # English vocab (cũng count vào drift để log)
    for english_vocab in _get_rewrite_mapping().keys():
        if english_vocab.lower() in text_lower:
            violations.append(english_vocab)
    return violations


def has_forbidden_scoring_vocab(text: str) -> bool:
    """True nếu text chứa scoring vocab (Tier/C-score/...).

    Đây là drift NGHIÊM TRỌNG — admin queue trigger.
    Khác với English vocab (chỉ là drift nhẹ, auto-rewrite xử được).
    """
    if not text:
        return False
    text_lower = text.lower()
    for vocab in _get_scoring_vocab():
        if vocab.lower() in text_lower:
            return True
    return False


def auto_rewrite(text: str) -> str:
    """Auto-rewrite vocab cấm:
    - English vocab → Việt thuần (vd "BRANDKIT" → "bộ thương hiệu")
    - Scoring vocab → REMOVE (xóa khỏi text)

    Args:
        text: Bot response

    Returns:
        Text đã rewrite. Multi-space sau REMOVE được collapse về 1.
    """
    if not text or not isinstance(text, str):
        return text

    result = text

    # 1. REWRITE English → Việt (case-sensitive replace để giữ
    # capitalization context — nhưng vocab dài hơn được thay trước)
    mapping = _get_rewrite_mapping()
    # Sort by length desc để "Mini App" thay trước "App" (nếu có)
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    for english in sorted_keys:
        if english.lower() in result.lower():
            # Case-insensitive replace, giữ Việt hóa form
            pattern = re.compile(re.escape(english), re.IGNORECASE)
            result = pattern.sub(mapping[english], result)

    # 2. REMOVE scoring vocab
    for vocab in _get_scoring_vocab():
        pattern = re.compile(r"\b" + re.escape(vocab) + r"\b", re.IGNORECASE)
        if pattern.search(result):
            logger.warning(
                "Drift REMOVE scoring vocab: %r trong text: %r",
                vocab, text[:200],
            )
            result = pattern.sub("", result)

    # 3. Collapse multi-space + strip stray punctuation
    result = re.sub(r"\s+", " ", result).strip()
    # Bỏ space trước dấu câu
    result = re.sub(r"\s+([,.!?;:])", r"\1", result)
    return result


def clear_cache() -> None:
    """Clear lru_cache — dùng cho test."""
    _load_vocab.cache_clear()
    _get_scoring_vocab.cache_clear()
    _get_rewrite_mapping.cache_clear()
