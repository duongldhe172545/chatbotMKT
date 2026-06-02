"""Checklist coverage for the LLM-first intake engine."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.schema import DealerProfileRaw, SessionState
from app.slots.definitions import (
    OPTIONAL_SLOTS,
    SLOT_PRIORITY_ORDER,
    SLOT_TO_ALL_FIELDS,
    SLOT_TO_REQUIRED_FIELDS,
)

PRE_CONSENT_OPTIONAL_SLOTS = [slot_id for slot_id in OPTIONAL_SLOTS if slot_id != "4.2"]
POST_CONSENT_OPTIONAL_SLOTS = ["4.2"]
BRANDING_FIELD_TO_SLOT = {
    "logo_initials": "4.3",
    "slogan_preference": "4.4",
    "logo_style": "4.5",
}
OPTIONAL_SLOT_RESOLUTION_FIELDS = {
    # Field-level contract from legacy Linh. These are still guardrails for the
    # LLM-first flow, not a hard script for the assistant response.
    "2.3": ["est_team_size", "team_stability_signal"],
    "2.4": ["supplier_brands", "customer_segment_signal", "supplier_negotiation_signal"],
    "2.5": ["primary_contact_channel"],
    "2.6": ["facebook", "fb_marketing_status", "community_network_signal"],
    "3.1": ["customer_old_percentage"],
    "3.2": ["customer_storage_method"],
    "3.3": ["customer_pain"],
    "3.4": ["payment_terms_signal"],
    "3.5": ["warranty_responsibility_signal"],
    "4.2": ["color_accent"],
}


class IntakeCoverage(BaseModel):
    """Profile coverage used as a guardrail, not as a script."""

    required_missing: list[str] = Field(default_factory=list)
    useful_optional_missing: list[str] = Field(default_factory=list)
    open_optional_slots: list[str] = Field(default_factory=list)
    open_branding_fields: list[str] = Field(default_factory=list)
    filled_fields: list[str] = Field(default_factory=list)
    can_summarize: bool = False
    recommended_focus: str | None = None
    recommended_slot: str | None = None
    reason: str = ""


def compute_intake_coverage(
    profile: DealerProfileRaw,
    session: SessionState | None = None,
) -> IntakeCoverage:
    """Compute missing profile fields without driving the conversation by slot."""
    required_order = _ordered_required_fields()
    all_order = _ordered_all_fields()

    filled_fields = [
        field
        for field in [*all_order, *BRANDING_FIELD_TO_SLOT]
        if _field_filled(profile, field)
    ]
    required_missing = [
        field for field in required_order
        if not _field_filled(profile, field)
    ]
    useful_optional_missing = [
        field for field in all_order
        if field not in required_order and not _field_filled(profile, field)
    ]
    open_branding_fields = [
        field
        for field in BRANDING_FIELD_TO_SLOT
        if profile.brandkit_consent == "yes" and not _field_filled(profile, field)
    ]
    useful_optional_missing.extend(open_branding_fields)
    skipped_slots = set(session.skipped_slots if session else [])
    open_optional_slots = [
        slot_id
        for slot_id in OPTIONAL_SLOTS
        if not _optional_slot_resolved(profile, slot_id, skipped_slots)
    ]

    pre_consent_required_missing = [
        field for field in required_missing if field != "brandkit_consent"
    ]
    pre_consent_optional_open = [
        slot_id for slot_id in PRE_CONSENT_OPTIONAL_SLOTS
        if slot_id in open_optional_slots
    ]
    post_consent_optional_open = [
        slot_id for slot_id in POST_CONSENT_OPTIONAL_SLOTS
        if slot_id in open_optional_slots
    ]

    if pre_consent_required_missing:
        recommended_focus = pre_consent_required_missing[0]
        recommended_slot = field_to_slot(recommended_focus)
    elif pre_consent_optional_open:
        recommended_slot = pre_consent_optional_open[0]
        recommended_focus = _first_unfilled_field(profile, recommended_slot)
    elif "brandkit_consent" in required_missing:
        recommended_focus = "brandkit_consent"
        recommended_slot = "4.0"
    elif post_consent_optional_open:
        recommended_slot = post_consent_optional_open[0]
        recommended_focus = _first_unfilled_field(profile, recommended_slot)
    elif open_branding_fields:
        recommended_focus = open_branding_fields[0]
        recommended_slot = BRANDING_FIELD_TO_SLOT[recommended_focus]
    else:
        recommended_focus = None
        recommended_slot = None

    can_summarize = (
        not required_missing
        and not open_optional_slots
        and not open_branding_fields
    )

    if pre_consent_required_missing:
        reason = f"Con thieu required field: {pre_consent_required_missing[0]}"
    elif pre_consent_optional_open:
        reason = f"Can hoi them nghiep vu Linh slot: {pre_consent_optional_open[0]}"
    elif "brandkit_consent" in required_missing:
        reason = "Da hoi xong nghiep vu, can xin consent bo thuong hieu"
    elif post_consent_optional_open:
        reason = f"Can hoi them nghiep vu Linh slot: {post_consent_optional_open[0]}"
    elif open_branding_fields:
        reason = f"Can chot preference logo: {open_branding_fields[0]}"
    else:
        reason = "Profile da du de tom tat va xin xac nhan"

    return IntakeCoverage(
        required_missing=required_missing,
        useful_optional_missing=useful_optional_missing,
        open_optional_slots=open_optional_slots,
        open_branding_fields=open_branding_fields,
        filled_fields=filled_fields,
        can_summarize=can_summarize,
        recommended_focus=recommended_focus,
        recommended_slot=recommended_slot,
        reason=reason,
    )


def field_to_slot(field: str | None) -> str | None:
    if not field:
        return None
    if field in BRANDING_FIELD_TO_SLOT:
        return BRANDING_FIELD_TO_SLOT[field]
    for slot_id in SLOT_PRIORITY_ORDER:
        if field in SLOT_TO_ALL_FIELDS.get(slot_id, []):
            return slot_id
    return None


def summarize_coverage(coverage: IntakeCoverage) -> str:
    """Compact text form for the conversation prompt."""
    return (
        f"required_missing={coverage.required_missing}; "
        f"useful_optional_missing={coverage.useful_optional_missing[:10]}; "
        f"open_optional_slots={coverage.open_optional_slots}; "
        f"open_branding_fields={coverage.open_branding_fields}; "
        f"filled_fields={coverage.filled_fields}; "
        f"can_summarize={coverage.can_summarize}; "
        f"recommended_slot={coverage.recommended_slot}; "
        f"recommended_focus={coverage.recommended_focus}; "
        f"reason={coverage.reason}"
    )


def _ordered_required_fields() -> list[str]:
    fields: list[str] = []
    for slot_id in SLOT_PRIORITY_ORDER:
        for field in SLOT_TO_REQUIRED_FIELDS.get(slot_id, []):
            if field not in fields:
                fields.append(field)
    return fields


def _ordered_all_fields() -> list[str]:
    fields: list[str] = []
    for slot_id in SLOT_PRIORITY_ORDER:
        for field in SLOT_TO_ALL_FIELDS.get(slot_id, []):
            if field not in fields:
                fields.append(field)
    return fields


def _field_filled(profile: DealerProfileRaw, field: str) -> bool:
    value = getattr(profile, field, None)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return True


def _optional_slot_resolved(
    profile: DealerProfileRaw,
    slot_id: str,
    skipped_slots: set[str],
) -> bool:
    if slot_id in skipped_slots:
        return True
    if slot_id == "4.2" and profile.brandkit_consent == "no":
        return True
    return all(_effective_field_filled(profile, field) for field in _slot_resolution_fields(slot_id))


def _first_unfilled_field(profile: DealerProfileRaw, slot_id: str) -> str | None:
    fields = _slot_resolution_fields(slot_id)
    return next(
        (field for field in fields if not _effective_field_filled(profile, field)),
        fields[0] if fields else None,
    )


def _slot_resolution_fields(slot_id: str) -> list[str]:
    return OPTIONAL_SLOT_RESOLUTION_FIELDS.get(
        slot_id,
        SLOT_TO_ALL_FIELDS.get(slot_id, []),
    )


def _effective_field_filled(profile: DealerProfileRaw, field: str) -> bool:
    if field == "zalo":
        return _field_filled(profile, "zalo") or _field_filled(profile, "phone_or_zalo")
    return _field_filled(profile, field)
