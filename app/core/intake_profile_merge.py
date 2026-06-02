"""Safe profile merge for LLM-first intake facts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

from app.core.address_parser import parse_address
from app.llm.client import LLMClient
from app.llm.extractors.validators import validate_field
from app.llm.intake_fact_extractor import INTAKE_ALLOWED_FIELDS, IntakeFact, IntakeFacts
from app.models.schema import DealerProfileRaw


LIST_FIELDS = {"category_stack", "supplier_brands"}
_REFERENCE_PLACEHOLDER_RE = re.compile(
    r"^(?:\d+|hai|ba|cả)\s*(?:hãng|loại|cái)?(?:\s+vật\s+tư)?\s*(?:đó|đấy|này|trên)?$|"
    r"^(?:như\s+trên|cả\s+hai|hai\s+hãng\s+(?:đó|đấy))$",
    re.IGNORECASE,
)


@dataclass
class IntakeMergeSummary:
    applied: dict[str, Any] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)


def merge_intake_facts(
    profile: DealerProfileRaw,
    facts: IntakeFacts,
    *,
    client: LLMClient | None = None,
) -> IntakeMergeSummary:
    """Validate and merge LLM-first facts without location case-locking."""
    summary = IntakeMergeSummary()
    for fact in facts.facts:
        _merge_fact(profile, fact, summary)

    if summary.applied:
        _apply_legacy_derives(profile, summary.applied, client=client)

    return summary


def _apply_legacy_derives(
    profile: DealerProfileRaw,
    applied: dict[str, Any],
    *,
    client: LLMClient | None = None,
) -> None:
    """Reuse legacy Scope 2 derives after safe LLM-first validation."""
    try:
        from app.core._conv_derive import merge_extracted

        merge_extracted(profile, applied, client=client)
    except Exception:
        _apply_basic_derives(profile, applied)


def _merge_fact(
    profile: DealerProfileRaw,
    fact: IntakeFact,
    summary: IntakeMergeSummary,
) -> None:
    field_name = fact.field
    if field_name not in INTAKE_ALLOWED_FIELDS or not hasattr(profile, field_name):
        summary.skipped[field_name] = "field_not_allowed"
        return
    if fact.confidence == "low":
        summary.skipped[field_name] = "low_confidence"
        return

    current = getattr(profile, field_name, None)
    if field_name in LIST_FIELDS:
        values = _clean_list_field(field_name, fact.value)
        if not values:
            summary.skipped[field_name] = "invalid_value"
            return
        merged = _merge_unique(current, values)
        setattr(profile, field_name, merged)
        summary.applied[field_name] = merged
        return

    ok, cleaned = validate_field(field_name, fact.value)
    if not ok:
        summary.skipped[field_name] = "invalid_value"
        return
    if field_name == "address" and not _address_has_province(str(cleaned or "")):
        summary.skipped[field_name] = "address_needs_province_confirmation"
        return

    if _has_value(current) and not (fact.is_correction and fact.confidence == "high"):
        summary.skipped[field_name] = "already_filled"
        return

    setattr(profile, field_name, cleaned)
    summary.applied[field_name] = cleaned


def _apply_basic_derives(profile: DealerProfileRaw, applied: dict[str, Any]) -> None:
    """Apply generic derives only; do not map specific neighborhoods."""
    if "address" in applied and profile.address and not profile.province:
        province, district = parse_address(profile.address, client=None)
        if province:
            profile.province = province
        if district:
            profile.district = district

    if "owner_name" in applied and profile.owner_name and not profile.contact_name:
        profile.contact_name = profile.owner_name

    if "phone_or_zalo" in applied and profile.phone_or_zalo and not profile.hotline:
        profile.hotline = profile.phone_or_zalo


def _address_has_province(address: str) -> bool:
    """Only persist addresses that include a clear province/city.

    District-only or phonetically guessed locations should stay in the
    conversation context so the LLM asks for confirmation first.
    """
    province, _district = parse_address(address, client=None)
    return bool(province)


def _clean_list_field(field_name: str, value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else _split_list_text(str(value))
    cleaned: list[str] = []
    for item in raw_items:
        if _REFERENCE_PLACEHOLDER_RE.match(str(item).strip()):
            continue
        ok, valid = validate_field(field_name, item)
        if ok and valid is not None:
            if isinstance(valid, list):
                cleaned.extend(str(v).strip() for v in valid if str(v).strip())
            else:
                text = str(valid).strip()
                if text:
                    cleaned.append(text)
    return cleaned


def _split_list_text(text: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"[,;/]|\s+(?:và|voi|với|cùng)\s+", text, flags=re.IGNORECASE)
        if item.strip()
    ]


def _merge_unique(current: Any, values: list[str]) -> list[str]:
    existing = current if isinstance(current, list) else []
    result: list[str] = []
    seen: set[str] = set()
    for item in [*existing, *values]:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True
