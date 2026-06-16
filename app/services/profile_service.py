"""Profile service — manages profile fields, flags, and auto-derivation.

Follows LINHMKT pattern. Interacts with dealer_profiles, profile_fields,
profile_field_events, and flags tables.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from app.core.ids import new_id, utc_now_iso
from app.core.validators import validate_field
from app.core._conv_derive import (
    derive_business_dealer_type,
    derive_known_local_address,
    parse_address,
)
from app.services.serializers import REQUIRED_PROFILE_FIELDS, DESIGN_PROFILE_FIELDS

logger = logging.getLogger(__name__)


class ProfileService:
    """Manages profile state, validation, field upserts, and flags."""

    def __init__(self, store, settings):
        self.store = store
        self.settings = settings

    def get_profile_snapshot(self, conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
        """Load profile and compute profile snapshot with required/missing fields."""
        profile = self.store.get_or_create_profile(conn, session_id)
        profile_id = profile["id"]

        # Sync logo job status with database
        from app.core.logo_jobs import get_logo_job
        job = get_logo_job(session_id)
        if job and job.get("status") == "completed" and profile["logo_issued_status"] != "ISSUED":
            self.store.update_profile_status(conn, profile_id=profile_id, review_status=profile["review_status"], logo_issued_status="ISSUED")
            # Reload profile row
            profile = self.store.get_or_create_profile(conn, session_id)
        fields = self.store.get_profile_fields(conn, profile_id)

        # Get active flags for this session or profile
        active_flags = self.store.get_active_flags(conn, profile_id=profile_id)
        blocking_flags = [f["flag_name"] for f in active_flags if f["severity"] == "BLOCKING"]
        open_flags = [f["flag_name"] for f in active_flags]
        active_flag_details = [
            {
                "id": f["id"],
                "flag_name": f["flag_name"],
                "field_name": f["field_name"],
                "severity": f["severity"],
            }
            for f in active_flags
        ]

        required_fields = {}
        design_fields = {}
        all_fields = {}
        skipped_fields = []

        for f in fields:
            name = f["field_name"]
            val = f["normalized_value"]
            status = f["status"]
            if status == "SKIPPED":
                skipped_fields.append(name)
            elif status == "PROVIDED" and val is not None:
                # Deserialize if json array
                if val.startswith("[") and val.endswith("]"):
                    try:
                        val = json.loads(val)
                    except Exception:
                        pass

                all_fields[name] = val
                if name in REQUIRED_PROFILE_FIELDS:
                    required_fields[name] = val
                elif name in DESIGN_PROFILE_FIELDS:
                    design_fields[name] = val

        missing_required = [f for f in REQUIRED_PROFILE_FIELDS if f not in required_fields]

        return {
            "profile_id": profile_id,
            "review_status": profile["review_status"],
            "logo_issued_status": profile["logo_issued_status"],
            "profile_version": profile["current_version"],
            "required_fields": required_fields,
            "design_fields": design_fields,
            "all_fields": all_fields,
            "missing_required_fields": missing_required,
            "skipped_fields": skipped_fields,
            "blocking_flags": blocking_flags,
            "open_flags": open_flags,
            "active_flag_details": active_flag_details,
        }

    def save_extracted_fields(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        extracted_fields: dict[str, Any],
        evidence_message_id: str,
        accept_phone_unverified: bool = False,
    ) -> dict[str, Any]:
        """Validate, upsert, and run auto-derivatives for extracted facts."""
        profile = self.store.get_or_create_profile(conn, session_id)
        profile_id = profile["id"]

        for field_name, raw_value in extracted_fields.items():
            if raw_value is None:
                continue

            # 1. Validate field value
            is_valid, cleaned_value = validate_field(field_name, raw_value)

            if is_valid:
                # Save field as PROVIDED
                norm_val = cleaned_value
                if isinstance(norm_val, list):
                    norm_val = json.dumps(norm_val, ensure_ascii=False)

                self.store.upsert_profile_field(
                    conn,
                    profile_id=profile_id,
                    field_name=field_name,
                    raw_value=raw_value,
                    normalized_value=norm_val,
                    status="PROVIDED",
                    source_type="extraction",
                    confidence=1.0,
                    evidence_message_ids=[evidence_message_id],
                )

                # Check for auto-derives
                self._run_auto_derives(conn, profile_id, field_name, cleaned_value, evidence_message_id)

                # Resolve active flags for this field when a valid value is provided
                active_flags = self.store.get_active_flags(conn, profile_id=profile_id)
                for f in active_flags:
                    if f["field_name"] == field_name or (field_name in ("phone_or_zalo", "phone_secondary") and f["flag_name"] == "phone_invalid_after_retry"):
                        self.store.resolve_flag(conn, f["id"])
            else:
                # 10.1 VAN AN TOÀN: SĐT bắt buộc gõ sai nhiều lần liên tiếp (chat_service
                # báo qua accept_phone_unverified) → NHẬN TẠM (giữ chữ số khách gõ) +
                # cờ phone_unverified cho admin xác minh → KHÔNG kẹt luồng / mất lead.
                if field_name == "phone_or_zalo" and accept_phone_unverified:
                    digits = "".join(ch for ch in str(raw_value or "") if ch.isdigit()) or str(raw_value or "")
                    self.store.upsert_profile_field(
                        conn,
                        profile_id=profile_id,
                        field_name="phone_or_zalo",
                        raw_value=raw_value,
                        normalized_value=digits,
                        status="PROVIDED",
                        source_type="unverified",
                        confidence=0.5,
                        evidence_message_ids=[evidence_message_id],
                    )
                    self.store.insert_flag(
                        conn,
                        session_id=session_id,
                        profile_id=profile_id,
                        message_id=evidence_message_id,
                        field_name="phone_or_zalo",
                        flag_name="phone_unverified",
                        severity="WARNING",
                    )
                    for f in self.store.get_active_flags(conn, profile_id=profile_id):
                        if f["flag_name"] == "phone_invalid_after_retry":
                            self.store.resolve_flag(conn, f["id"])
                    continue

                # Save field as INVALID
                self.store.upsert_profile_field(
                    conn,
                    profile_id=profile_id,
                    field_name=field_name,
                    raw_value=raw_value,
                    normalized_value=None,
                    status="INVALID",
                    source_type="extraction",
                    confidence=0.0,
                    evidence_message_ids=[evidence_message_id],
                    validation_errors=["Validation failed"],
                )
                # 10.1: SĐT sai KHÔNG còn là cờ BLOCKING — chỉ WARNING. Phone chưa PROVIDED
                # nên vẫn nằm trong missing_required → workflow tự hỏi lại (collect_required
                # + luật slot 1.3), KHÔNG cướp luồng sang resolve_blocking_flag mù mờ.
                flag_name = "phone_invalid_after_retry" if field_name == "phone_or_zalo" else "sanity_check_failed"
                self.store.insert_flag(
                    conn,
                    session_id=session_id,
                    profile_id=profile_id,
                    message_id=evidence_message_id,
                    field_name=field_name,
                    flag_name=flag_name,
                    severity="WARNING",
                )

        return self.get_profile_snapshot(conn, session_id)

    def _run_auto_derives(
        self,
        conn: sqlite3.Connection,
        profile_id: str,
        field_name: str,
        value: Any,
        evidence_message_id: str,
    ) -> None:
        """Helper to run derivations for province, ward, dealer_type, contact_name, hotline."""
        # Province + Ward from address
        if field_name == "address" and value:
            # Local parser
            local_prov, local_ward = derive_known_local_address(value)
            if local_prov:
                self.store.upsert_profile_field(
                    conn,
                    profile_id=profile_id,
                    field_name="province",
                    raw_value=value,
                    normalized_value=local_prov,
                    status="PROVIDED",
                    source_type="auto_derive",
                    confidence=1.0,
                    evidence_message_ids=[evidence_message_id],
                )
            if local_ward:
                self.store.upsert_profile_field(
                    conn,
                    profile_id=profile_id,
                    field_name="ward",
                    raw_value=value,
                    normalized_value=local_ward,
                    status="PROVIDED",
                    source_type="auto_derive",
                    confidence=1.0,
                    evidence_message_ids=[evidence_message_id],
                )

            # LLM address parsing / Regex fallback
            if not local_prov:
                prov, ward = parse_address(value, client=None)
                if prov:
                    self.store.upsert_profile_field(
                        conn,
                        profile_id=profile_id,
                        field_name="province",
                        raw_value=value,
                        normalized_value=prov,
                        status="PROVIDED",
                        source_type="auto_derive",
                        confidence=1.0,
                        evidence_message_ids=[evidence_message_id],
                    )
                if ward:
                    self.store.upsert_profile_field(
                        conn,
                        profile_id=profile_id,
                        field_name="ward",
                        raw_value=value,
                        normalized_value=ward,
                        status="PROVIDED",
                        source_type="auto_derive",
                        confidence=1.0,
                        evidence_message_ids=[evidence_message_id],
                    )

        # contact_name = owner_name
        if field_name == "owner_name" and value:
            self.store.upsert_profile_field(
                conn,
                profile_id=profile_id,
                field_name="contact_name",
                raw_value=value,
                normalized_value=value,
                status="PROVIDED",
                source_type="auto_derive",
                confidence=1.0,
                evidence_message_ids=[evidence_message_id],
            )

        # hotline = phone_or_zalo
        if field_name == "phone_or_zalo" and value:
            self.store.upsert_profile_field(
                conn,
                profile_id=profile_id,
                field_name="hotline",
                raw_value=value,
                normalized_value=value,
                status="PROVIDED",
                source_type="auto_derive",
                confidence=1.0,
                evidence_message_ids=[evidence_message_id],
            )

        # dealer_type from business_model_signal
        if field_name == "business_model_signal" and value:
            dtype = derive_business_dealer_type(value)
            if dtype:
                self.store.upsert_profile_field(
                    conn,
                    profile_id=profile_id,
                    field_name="dealer_type",
                    raw_value=value,
                    normalized_value=dtype,
                    status="PROVIDED",
                    source_type="auto_derive",
                    confidence=1.0,
                    evidence_message_ids=[evidence_message_id],
                )

        # phone_or_zalo fallback from phone_secondary
        if field_name == "phone_secondary" and value:
            fields = self.store.get_profile_fields(conn, profile_id)
            has_valid_primary = any(f["field_name"] == "phone_or_zalo" and f["status"] == "PROVIDED" for f in fields)
            if not has_valid_primary:
                self.store.upsert_profile_field(
                    conn,
                    profile_id=profile_id,
                    field_name="phone_or_zalo",
                    raw_value=value,
                    normalized_value=value,
                    status="PROVIDED",
                    source_type="auto_derive",
                    confidence=1.0,
                    evidence_message_ids=[evidence_message_id],
                )
