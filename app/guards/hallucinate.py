"""G2 — Hallucinate guard: value_in_message check.

Refer LUAT_2B § F2B.8 G2.

Mục đích: LLM hay bịa data dealer chưa cho (vd dealer chỉ nói "Tùng" mà
LLM extract "Tùng Nguyễn Văn 35 tuổi"). Engine reject value không xuất
hiện trong user message.

Soft rule (refer F2B.8 G2):
- Field cần INFERENCE (enum như dealer_type, main_category, brandkit_consent)
  → SKIP hallucinate check (LLM được phép suy từ context, không cần
  match raw text).
- Field RAW (owner_name, address, phone, supplier_brands...) → bắt buộc
  appear in message.

API:
- value_appears_in_message(value, message) → bool — substring check
- check_hallucinate(extracted, message, inference_fields) → list[str]
  field hallucinate (caller flag + có thể null các field này)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# Field enum/inference — SKIP hallucinate check (LLM được phép suy)
_INFERENCE_FIELDS_DEFAULT: set[str] = {
    "brandkit_consent",       # enum yes/no — LLM suy từ "ok"/"có"
    "main_category",          # enum 7 code — LLM auto-derive
    "dealer_type",            # enum suy từ business_model_signal
    "primary_contact_channel",  # có thể normalize "kênh chính" raw text
    "fb_marketing_status",    # status raw, normalize OK
}


def value_appears_in_message(
    value: Any,
    message: str,
    *,
    min_match_ratio: float = 0.5,
) -> bool:
    """Check value (str/list/int) có xuất hiện trong message không.

    Args:
        value: Value LLM extract — str / int / list / None
        message: User raw message
        min_match_ratio: Cho str, % char match tối thiểu (default 50%).
            Cho phép LLM normalize (vd "Tung" → "Tùng" — bỏ dấu OK,
            nhưng KHÔNG cho phép bịa hoàn toàn).

    Returns:
        True nếu value match đủ trong message (case-insensitive, có
        normalize space).

    Logic per type:
    - None / empty str / empty list → True (không có gì để check)
    - int → check value as string xuất hiện trong message
    - list → tất cả items phải appear (recursive)
    - str dài → check token overlap ≥ min_match_ratio
    - str ngắn (≤ 3 char) → exact substring (lowercase)
    """
    if value is None:
        return True
    msg_lower = (message or "").lower()

    if isinstance(value, (int, float)):
        return str(value) in msg_lower

    if isinstance(value, list):
        if not value:
            return True
        return all(value_appears_in_message(v, message, min_match_ratio=min_match_ratio) for v in value)

    if not isinstance(value, str) or not value:
        return True

    value_lower = value.lower().strip()
    if len(value_lower) <= 3:
        return value_lower in msg_lower

    # Long str → token overlap
    # Tokenize đơn giản: split bằng non-word chars
    msg_tokens = set(_tokenize(msg_lower))
    value_tokens = [t for t in _tokenize(value_lower) if t]
    if not value_tokens:
        return True
    matched = sum(1 for t in value_tokens if t in msg_tokens)
    ratio = matched / len(value_tokens)
    return ratio >= min_match_ratio


def _tokenize(text: str) -> list[str]:
    """Tokenize giữ ký tự Việt + digit."""
    # Word = alphanumeric + Việt + 1 ký tự
    return re.findall(r"\w+", text, flags=re.UNICODE)


def check_hallucinate(
    extracted: dict,
    message: str,
    inference_fields: Optional[Iterable[str]] = None,
) -> list[str]:
    """Trả list field hallucinate.

    Args:
        extracted: dict field LLM trả về
        message: user raw message
        inference_fields: override set field skip check (default = enum/inference)

    Returns:
        List field hallucinate (caller có thể null các field này +
        flag `hallucinate` cho admin queue).
    """
    if not extracted or not message:
        return []

    skip_set = set(inference_fields) if inference_fields else _INFERENCE_FIELDS_DEFAULT
    hallucinated: list[str] = []

    for field, value in extracted.items():
        if value is None:
            continue
        if field in skip_set:
            continue
        if not value_appears_in_message(value, message):
            logger.warning(
                "Hallucinate detected: field=%s value=%r message=%r",
                field, value, message[:200],
            )
            hallucinated.append(field)

    return hallucinated
