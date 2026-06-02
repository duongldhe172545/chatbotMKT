"""Validators cho field sau LLM extract. Refer F2A.7 sanity check + F2B.2.

Mọi validator có pattern:
    validate_X(value: str | None) -> tuple[bool, str | None]
        - (True, cleaned_value): valid + cleaned
        - (False, None): invalid hoặc empty
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ============================================================
# Phone — refer F2A.7 check 2 + F2B.2 strict validation
# ============================================================

# VN active mobile prefixes: 03/05/07/08/09. Landline starts with 02.
# Keep 84 country-code variants for the same ranges. Reject old retired 01x
# prefixes such as 014, which otherwise look valid by length only.
_PHONE_NUMERIC = re.compile(r"^((?:0(?:[35789]\d{8}|2\d{8,9}))|(?:84(?:[35789]\d{8}|2\d{8,9})))$")


def validate_phone(value: Optional[str]) -> tuple[bool, Optional[str]]:
    """Phone digits-only, len 10-11, start '0' hoặc '84'.

    Args:
        value: Raw phone string từ LLM (có thể có space, dash, dấu chấm)

    Returns:
        (True, cleaned_phone) nếu valid (digits-only).
        (False, None) nếu invalid hoặc empty.

    Examples:
        validate_phone("0912 345 678") → (True, "0912345678")
        validate_phone("0912-345-678") → (True, "0912345678")
        validate_phone("abc123") → (False, None)
        validate_phone(None) → (False, None)
    """
    if value is None:
        return (False, None)
    if not isinstance(value, str):
        return (False, None)
    # Strip whitespace, dash, dot, parens
    cleaned = re.sub(r"[\s\-\.\(\)]+", "", value)
    if _PHONE_NUMERIC.match(cleaned):
        return (True, cleaned)
    return (False, None)


# ============================================================
# Address — refer F2A.7 check 3
# ============================================================


def validate_address(value: Optional[str]) -> tuple[bool, Optional[str]]:
    """Address ≥ 3 char, ≤ 500 char, không chứa blacklist keyword.

    Refer F2A.7 check 3 + 1C § 10 (address blacklist).
    Blacklist logic delegate sang `app/core/address_blacklist.py` (load
    từ `data/address_blacklist.json`).

    Returns:
        (True, cleaned_address) nếu valid.
        (False, None) nếu < 3 char, > 500, empty, hoặc chứa blacklist.
    """
    # Local import để tránh circular (validators được import sớm)
    from app.core.address_blacklist import is_blacklisted

    if value is None or not isinstance(value, str):
        return (False, None)
    cleaned = value.strip()
    if not cleaned:
        return (False, None)
    if len(cleaned) < 3 or len(cleaned) > 500:
        return (False, None)
    if is_blacklisted(cleaned):
        return (False, None)
    return (True, cleaned)


# ============================================================
# Brandkit consent — refer F2A.7 check 4
# ============================================================


def validate_brandkit_consent(value: Optional[str]) -> tuple[bool, Optional[str]]:
    """brandkit_consent must be 'yes' or 'no' (enum strict)."""
    if value not in ("yes", "no"):
        return (False, None)
    return (True, value)


# ============================================================
# Name (owner_name, dealer_name) — không enforce regex, chỉ length
# ============================================================


def validate_name(value: Optional[str]) -> tuple[bool, Optional[str]]:
    """Name ≥ 1 char, ≤ 200 char (cho dealer_name dài). Strip whitespace.

    Note: Pydantic schema đã enforce maxLength. Đây là defensive validation.
    """
    if value is None or not isinstance(value, str):
        return (False, None)
    cleaned = value.strip()
    if not cleaned:
        return (False, None)
    if len(cleaned) > 200:
        return (False, None)
    return (True, cleaned)


# ============================================================
# Free-form text (raw signal, customer_pain, etc.) — generic
# ============================================================


def validate_free_text(
    value: Optional[str],
    max_len: int = 1000,
) -> tuple[bool, Optional[str]]:
    """Free text ≥ 1 char, ≤ max_len. Default 1000 cho customer_pain dài."""
    if value is None or not isinstance(value, str):
        return (False, None)
    cleaned = value.strip()
    if not cleaned:
        return (False, None)
    if len(cleaned) > max_len:
        return (False, None)
    return (True, cleaned)


# ============================================================
# Team size — LLM-first extractor uses one generic string value
# ============================================================


def validate_est_team_size(value) -> tuple[bool, Optional[int]]:
    """Normalize a dealer's approximate team size to one integer estimate.

    The legacy slot extractor already emits an integer. The LLM-first fact
    extractor intentionally uses one generic string value for heterogeneous
    fields, so ranges such as ``"6-7"`` must be normalized at the merge edge.
    """
    if value is None or isinstance(value, bool):
        return (False, None)
    if isinstance(value, int):
        return (True, value) if 0 <= value <= 200 else (False, None)
    if isinstance(value, float):
        return (True, int(value)) if value.is_integer() and 0 <= value <= 200 else (False, None)
    if not isinstance(value, str):
        return (False, None)

    cleaned = value.strip().lower()
    if not cleaned:
        return (False, None)
    folded = "".join(
        ch for ch in unicodedata.normalize("NFD", cleaned)
        if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d")

    range_match = re.search(
        r"(?<!\d)(\d{1,3})\s*(?:[-–—]|den|toi)\s*(\d{1,3})(?!\d)",
        folded,
    )
    if range_match:
        low, high = sorted((int(range_match.group(1)), int(range_match.group(2))))
        estimate = (low + high) // 2
        return (True, estimate) if 0 <= estimate <= 200 else (False, None)

    number_match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", folded)
    if number_match:
        estimate = int(number_match.group(1))
        return (True, estimate) if 0 <= estimate <= 200 else (False, None)
    return (False, None)


# ============================================================
# Master validator dispatch — field name → validator
# ============================================================

_FIELD_VALIDATORS: dict[str, callable] = {
    "phone_or_zalo": validate_phone,
    "zalo": validate_phone,
    "address": validate_address,
    "brandkit_consent": validate_brandkit_consent,
    "owner_name": validate_name,
    "dealer_name": validate_name,
    "est_team_size": validate_est_team_size,
    # RAW signal + free text fields → free_text validator
    "local_dominance_signal": validate_free_text,
    "main_product": validate_free_text,
    "business_model_signal": validate_free_text,
    "team_stability_signal": validate_free_text,
    "primary_contact_channel": validate_free_text,
    "facebook": validate_free_text,
    "fb_marketing_status": validate_free_text,
    "customer_old_percentage": validate_free_text,
    "customer_storage_method": validate_free_text,
    "customer_pain": validate_free_text,
    "motivation_signal": validate_free_text,
    "usp_signal": validate_free_text,
    "supplier_negotiation_signal": validate_free_text,
    "community_network_signal": validate_free_text,
    "warranty_responsibility_signal": validate_free_text,
    "payment_terms_signal": validate_free_text,
    "color_accent": validate_free_text,
    "feng_shui_signal": validate_free_text,
    "logo_initials": validate_free_text,
    "slogan_preference": validate_free_text,
    "logo_style": validate_free_text,
}


def validate_field(field_name: str, value):
    """Dispatch validator theo field name.

    Args:
        field_name: tên field từ schema
        value: raw value từ LLM (str/int/list/None)

    Returns:
        (True, cleaned) nếu valid.
        (False, None) nếu invalid.

    Note: với field không có validator dedicated (vd category_stack list,
    supplier_brands list), passthrough giữ NGUYÊN
    type — Pydantic JSON schema đã enforce type ở LLM call.
    """
    validator = _FIELD_VALIDATORS.get(field_name)
    if validator is None:
        if value is None:
            return (False, None)
        # Passthrough non-string types (int, list, bool, dict) giữ nguyên
        # — không ép str() để tránh hỏng array/int.
        if not isinstance(value, str):
            return (True, value)
        return (True, value)
    return validator(value)
