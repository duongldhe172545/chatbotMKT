"""Profile checklist helpers for planner-first intake."""
from __future__ import annotations

from app.models.planner import MissingFieldState, PLANNER_ALLOWED_FIELDS
from app.models.schema import DealerProfileRaw, SessionState
from app.slots.definitions import (
    SLOT_PRIORITY_ORDER,
    SLOT_TO_ALL_FIELDS,
    SLOT_TO_REQUIRED_FIELDS,
)


def compute_missing_fields(
    profile: DealerProfileRaw,
    session: SessionState | None = None,
) -> MissingFieldState:
    """Compute intake checklist state from the current profile.

    `current_slot` remains a debug/focus pointer; it does not drive the
    conversation here.
    """
    required_order = _ordered_required_fields()
    all_order = _ordered_all_fields()

    filled_fields = [
        field for field in all_order
        if _field_filled(profile, field)
    ]
    required_missing = [
        field for field in required_order
        if not _field_filled(profile, field)
    ]
    optional_missing = [
        field for field in all_order
        if field not in required_order and not _field_filled(profile, field)
    ]

    next_focus_field = required_missing[0] if required_missing else (
        optional_missing[0] if optional_missing else None
    )
    next_focus_slot = field_to_slot(next_focus_field) if next_focus_field else None

    return MissingFieldState(
        required_missing=required_missing,
        optional_missing=optional_missing,
        filled_fields=filled_fields,
        next_focus_field=next_focus_field,
        next_focus_slot=next_focus_slot,
        can_confirm=not required_missing,
    )


def field_to_slot(field: str | None) -> str | None:
    if not field:
        return None
    for slot_id in SLOT_PRIORITY_ORDER:
        if field in SLOT_TO_ALL_FIELDS.get(slot_id, []):
            return slot_id
    return None


def _ordered_required_fields() -> list[str]:
    fields: list[str] = []
    for slot_id in SLOT_PRIORITY_ORDER:
        for field in SLOT_TO_REQUIRED_FIELDS.get(slot_id, []):
            if field in PLANNER_ALLOWED_FIELDS and field not in fields:
                fields.append(field)
    return fields


def _ordered_all_fields() -> list[str]:
    fields: list[str] = []
    for slot_id in SLOT_PRIORITY_ORDER:
        for field in SLOT_TO_ALL_FIELDS.get(slot_id, []):
            if field in PLANNER_ALLOWED_FIELDS and field not in fields:
                fields.append(field)
    return fields


def _field_filled(profile: DealerProfileRaw, field: str) -> bool:
    value = getattr(profile, field, None)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_item_filled(item) for item in value)
    return True


def _item_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True

