"""Sanity check 5-point trước khi save profile CONFIRMED.

Refer:
- F2A.7 (LUAT_2A_core v0.2.4) — 5-point check algorithm
- CORE § J.4 — luật khóa save (6 REQUIRED slot không null hoặc flag required_missing)
- 1C § 10 — address blacklist check
"""
from __future__ import annotations

from typing import Optional

from app.core.validators import (
    validate_address,
    validate_brandkit_consent,
    validate_phone,
)
from app.models.enums import Flag
from app.models.schema import DealerProfileRaw, SessionState
from app.slots.definitions import REQUIRED_SLOTS, SLOT_TO_REQUIRED_FIELDS


# Forbidden vocab leak — Scope 4 fields (refer F2A.7 check 5)
_SCOPE_4_FORBIDDEN_FIELDS = [
    "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9",
    "c_score", "tier", "batch", "dealer_id",
    "dealer_status", "admin_area_code", "editor_name",
]


def check_sanity(
    session: SessionState,
    profile: DealerProfileRaw,
) -> tuple[bool, list[str]]:
    """Sanity check 5-point. Refer F2A.7.

    Args:
        session: Current session state (cho flags check)
        profile: DealerProfileRaw cần validate

    Returns:
        (passed, failed_reasons).
        - passed=True nếu pass cả 5 check
        - failed_reasons: list lý do fail (empty nếu passed)
    """
    failed: list[str] = []

    # Check 1: 6 REQUIRED slot không null HOẶC có flag required_missing
    if not _check_required_fields(session, profile):
        failed.append("Check 1: 6 REQUIRED slot không null hoặc flag required_missing")

    # Check 2: Phone digits-only, len 10-11
    if not _check_phone_format(profile):
        failed.append("Check 2: Phone format (digits-only, len 10-11)")

    # Check 3: Address ≥ 3 char, không blacklist
    if not _check_address(profile):
        failed.append("Check 3: Address ≥ 3 char + không blacklist")

    # Check 4: brandkit_consent rõ ràng
    if not _check_brandkit_consent(session, profile):
        failed.append("Check 4: brandkit_consent rõ ràng (không null trừ flag consent_unclear)")

    # Check 5: Không có Scope 4 field leak
    if not _check_no_scope_4_leak(profile):
        failed.append("Check 5: Scope 4 field (c_score, tier, dealer_id...) leak")

    return (len(failed) == 0, failed)


def _check_required_fields(session: SessionState, profile: DealerProfileRaw) -> bool:
    """Check 1: 6 REQUIRED slot có data HOẶC có flag required_missing.

    Slot 1.1 fill 2 field (owner_name + dealer_name) — cả 2 đều REQUIRED.
    """
    has_required_missing_flag = Flag.REQUIRED_MISSING in session.flags

    for slot_id in REQUIRED_SLOTS:
        required_fields = SLOT_TO_REQUIRED_FIELDS.get(slot_id, [])
        for field in required_fields:
            value = getattr(profile, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                # Field null/empty — chỉ OK nếu session đã flag
                if not has_required_missing_flag:
                    return False
                # Có flag → skip (admin sẽ review thủ công)
    return True


def _check_phone_format(profile: DealerProfileRaw) -> bool:
    """Check 2: Phone digits-only, len 10-11 (nếu có)."""
    phone = profile.phone_or_zalo
    if phone is None:
        # Phone null là OK — chỉ check nếu có data
        return True
    ok, _ = validate_phone(phone)
    return ok


def _check_address(profile: DealerProfileRaw) -> bool:
    """Check 3: Address valid (nếu có)."""
    address = profile.address
    if address is None:
        return True
    ok, _ = validate_address(address)
    return ok


def _check_brandkit_consent(
    session: SessionState,
    profile: DealerProfileRaw,
) -> bool:
    """Check 4: brandkit_consent rõ ràng yes/no, không null trừ flag."""
    consent = profile.brandkit_consent
    if consent is None:
        # Null OK chỉ nếu có flag consent_unclear
        return Flag.CONSENT_UNCLEAR in session.flags
    ok, _ = validate_brandkit_consent(consent)
    return ok


def _check_no_scope_4_leak(profile: DealerProfileRaw) -> bool:
    """Check 5: profile KHÔNG có Scope 4 field (c_score, tier, etc.).

    Refer D7 STRATEGY: Backend Scoring service riêng, chatbot không ghi.
    """
    # Pydantic schema strict — không có Scope 4 field, sanity check
    # chỉ verify nếu có attribute lạ
    profile_dict = profile.model_dump()
    for forbidden in _SCOPE_4_FORBIDDEN_FIELDS:
        if forbidden in profile_dict and profile_dict[forbidden] is not None:
            return False
    return True
