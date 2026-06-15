"""Serializers — convert DB rows to API-safe dicts.

Follows LINHMKT pattern. Defines field classifications and
helper functions for converting DB rows to JSON-serializable dicts.
"""
from __future__ import annotations

import json
from typing import Any


# ============================================================
# Field classifications (from slots/definitions.py mapping)
# ============================================================

REQUIRED_PROFILE_FIELDS = [
    "owner_name",
    "dealer_name",
    "address",
    "phone_or_zalo",
    "main_product",
    "business_model_signal",
]

DESIGN_PROFILE_FIELDS = [
    "brandkit_consent",
    "logo_initials",
    "slogan_preference",   # FIX P4.3: field "slogan" không tồn tại trong schema
    "slogan_options",      # slogan LLM gen sẵn (hiển thị/dùng cho logo)
    "color_accent",
    "logo_style",
    "logo_existing_intent",
]

LOGO_VISIBLE_FIELDS = [
    "dealer_name",
    "logo_initials",
    "slogan_preference",   # FIX P4.3 (was "slogan" — không tồn tại)
    "phone_or_zalo",
]


def empty_profile_snapshot() -> dict[str, Any]:
    """Return an empty profile snapshot for sessions without a profile yet."""
    return {
        "profile_id": None,
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
        "profile_version": 0,
        "required_fields": {},
        "design_fields": {},
        "all_fields": {},
        "missing_required_fields": list(REQUIRED_PROFILE_FIELDS),
        "blocking_flags": [],
        "open_flags": [],
    }


def chat_event_from_message(row) -> dict[str, Any]:
    """Convert a messages DB row to a frontend chat event.

    Shape:
        {
            "event_id": "evt_msg_...",
            "cursor": "42",
            "session_id": "ses_...",
            "turn_id": "turn_...",
            "source": "user" | "linh_mkt" | "system",
            "event_type": "message",
            "message_type": "text" | "profile_review_card" | ...,
            "text": "...",
            "component": null | { ... },
            "created_at": "2026-..."
        }
    """
    component = None
    try:
        raw_payload = json.loads(row["raw_payload_json"] or "{}")
    except json.JSONDecodeError:
        raw_payload = {}
    if row["message_type"] not in {"text", "voice"}:
        component = raw_payload.get("component") or raw_payload

    return {
        "event_id": f"evt_{row['id']}",
        "cursor": str(row["event_cursor"]),
        "session_id": row["session_id"],
        "turn_id": row["turn_id"],
        "source": row["source"],
        "event_type": "message",
        "message_type": row["message_type"],
        "text": row["text"],
        "component": component,
        "created_at": row["created_at"],
    }


def session_public_state(row, *, events_cursor: int) -> dict[str, Any]:
    """Convert a sessions DB row to a public state dict."""
    return {
        "session_id": row["id"],
        "status": row["status"],
        "workflow_state": row["workflow_state"],
        "events_cursor": str(events_cursor),
    }
