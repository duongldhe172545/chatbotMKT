"""Security utilities — token hashing + Bearer extraction.

Follows LINHMKT pattern. Used by session_service for token auth
and by API routes for Bearer token extraction.
"""
from __future__ import annotations

import hashlib
import hmac


def hash_token(raw_token: str, secret: str) -> str:
    """HMAC-SHA256 hash of a raw token using a secret key.

    Used to store session tokens securely — raw token is returned to client
    once, only hash is persisted in DB.
    """
    return hmac.new(
        secret.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_client_signal(value: str | None, secret: str) -> str | None:
    """Hash a client signal (IP, User-Agent) for privacy-safe storage.

    Returns None if value is None/empty.
    """
    if not value:
        return None
    return hash_token(value, secret)


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """Extract raw token from 'Bearer <token>' header.

    Returns None if header is missing, malformed, or scheme is not 'bearer'.
    """
    if not authorization_header:
        return None
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer" or not token:
        return None
    return token
