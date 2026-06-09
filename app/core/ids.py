"""Prefixed ID generator + UTC timestamp utility.

Follows LINHMKT pattern: all IDs = "{prefix}_{uuid4_hex}".
Deterministic, no external dependency.
"""
from __future__ import annotations

from datetime import datetime, timezone
import secrets
import uuid


def new_id(prefix: str) -> str:
    """Generate a prefixed unique ID.

    Examples:
        new_id("ses")  → "ses_a1b2c3d4..."
        new_id("msg")  → "msg_e5f6g7h8..."
        new_id("turn") → "turn_i9j0k1l2..."
    """
    return f"{prefix}_{uuid.uuid4().hex}"


def new_session_token() -> str:
    """Generate a cryptographically secure session token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


def utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format with 'Z' suffix.

    Example: "2026-06-08T03:10:00.123456Z"
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
