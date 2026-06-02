"""Safe merge layer for planner facts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core._conv_derive import merge_extracted
from app.llm.extractors.validators import validate_field
from app.models.planner import PlannedFact, PlannerResult, PLANNER_ALLOWED_FIELDS
from app.models.schema import DealerProfileRaw


LIST_FIELDS = {
    "category_stack",
    "supplier_brands",
}


@dataclass
class MergeSummary:
    applied: dict[str, Any] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)


def merge_planner_result(
    profile: DealerProfileRaw,
    result: PlannerResult,
) -> MergeSummary:
    """Validate planner facts and merge them without clobbering good data."""
    summary = MergeSummary()

    for fact in result.facts:
        _merge_fact(profile, fact, summary, is_correction=False)

    for fact in result.corrections:
        _merge_fact(profile, fact, summary, is_correction=True)

    if summary.applied:
        # Keep existing deterministic derives that do not require an extra LLM call.
        merge_extracted(profile, summary.applied, client=None)

    return summary


def _merge_fact(
    profile: DealerProfileRaw,
    fact: PlannedFact,
    summary: MergeSummary,
    *,
    is_correction: bool,
) -> None:
    field_name = fact.field
    if field_name not in PLANNER_ALLOWED_FIELDS or not hasattr(profile, field_name):
        summary.skipped[field_name] = "field_not_allowed"
        return
    if fact.confidence == "low":
        summary.skipped[field_name] = "low_confidence"
        return

    current = getattr(profile, field_name, None)
    if field_name in LIST_FIELDS:
        cleaned_list = _clean_list_field(field_name, fact.value)
        if not cleaned_list:
            summary.skipped[field_name] = "invalid_value"
            return
        merged = _merge_unique_list(current, cleaned_list)
        setattr(profile, field_name, merged)
        summary.applied[field_name] = merged
        return

    ok, cleaned = validate_field(field_name, fact.value)
    if not ok:
        summary.skipped[field_name] = "invalid_value"
        return

    if _has_value(current) and not (is_correction and fact.confidence == "high"):
        summary.skipped[field_name] = "already_filled"
        return

    setattr(profile, field_name, cleaned)
    summary.applied[field_name] = cleaned


def _clean_list_field(field_name: str, value) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else _split_list_text(str(value))
    cleaned: list[str] = []
    for item in raw_items:
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
    import re

    return [
        item.strip()
        for item in re.split(r"[,;/]|\s+(?:và|voi|với|cùng)\s+", text, flags=re.IGNORECASE)
        if item.strip()
    ]


def _merge_unique_list(current, new_items: list[str]) -> list[str]:
    existing = current if isinstance(current, list) else []
    result: list[str] = []
    seen: set[str] = set()
    for item in [*existing, *new_items]:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _has_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True
