"""Data store — CRUD operations on the Parlant-style tables.

Follows LINHMKT Store pattern: all methods take a sqlite3.Connection
as first arg (caller manages transaction boundary via Database.transaction).

Methods cover:
- Sessions + access tokens
- Messages (event-sourced, cursor-based)
- Conversation turns (full trace)
- Idempotency records
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.core.ids import new_id, utc_now_iso


class Store:
    """Data access layer for all Parlant-style tables."""

    def __init__(self, database):
        self.database = database

    # ============================================================
    # Sessions
    # ============================================================

    def get_session(self, conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    def create_session(
        self,
        conn: sqlite3.Connection,
        *,
        channel: str,
        token_hash: str,
        ip_hash: str | None,
        user_agent_hash: str | None,
        metadata: dict[str, Any],
    ) -> sqlite3.Row:
        """Create a new session + its access token row.

        Returns the created session row.
        """
        now = utc_now_iso()
        session_id = new_id("ses")
        conn.execute(
            """
            INSERT INTO sessions (
                id, channel, status, workflow_state, session_token_hash,
                ip_hash, user_agent_hash, started_at, metadata_json
            )
            VALUES (?, ?, 'ACTIVE', 'SESSION_STARTED', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                channel,
                token_hash,
                ip_hash,
                user_agent_hash,
                now,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.execute(
            """
            INSERT INTO session_access_tokens (
                id, session_id, token_hash, status, created_at
            )
            VALUES (?, ?, ?, 'ACTIVE', ?)
            """,
            (new_id("tok"), session_id, token_hash, now),
        )
        session = self.get_session(conn, session_id)
        if session is None:
            raise RuntimeError("Session insert failed.")
        return session

    def token_is_active(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        token_hash: str,
    ) -> bool:
        """Check if a token is active for a given session."""
        row = conn.execute(
            """
            SELECT 1 AS ok
            FROM session_access_tokens
            WHERE session_id = ? AND token_hash = ? AND status = 'ACTIVE'
            """,
            (session_id, token_hash),
        ).fetchone()
        return bool(row and row["ok"] == 1)

    def touch_session_after_message(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        workflow_state: str,
    ) -> None:
        """Update last_message_at + workflow_state after processing a message."""
        conn.execute(
            """
            UPDATE sessions
            SET last_message_at = ?, workflow_state = ?
            WHERE id = ?
            """,
            (utc_now_iso(), workflow_state, session_id),
        )

    # ============================================================
    # Messages (event-sourced)
    # ============================================================

    def next_event_cursor(self, conn: sqlite3.Connection) -> int:
        """Get next monotonic cursor value for message ordering."""
        row = conn.execute(
            "SELECT COALESCE(MAX(event_cursor), 0) + 1 AS next_cursor FROM messages"
        ).fetchone()
        return int(row["next_cursor"])

    def insert_message(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        source: str,
        message_type: str,
        text: str | None,
        raw_payload: dict[str, Any] | None = None,
        voice_artifact: dict[str, Any] | None = None,
        turn_id: str | None = None,
    ) -> sqlite3.Row:
        """Insert a new message with auto-incremented event_cursor.

        Args:
            source: "user" | "linh_mkt" | "system"
            message_type: "text" | "component" | "profile_review_card" | "logo_brief_card" | etc.
        """
        message_id = new_id("msg")
        now = utc_now_iso()
        cursor = self.next_event_cursor(conn)
        conn.execute(
            """
            INSERT INTO messages (
                id, event_cursor, session_id, turn_id, source, message_type,
                text, raw_payload_json, voice_artifact_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                cursor,
                session_id,
                turn_id,
                source,
                message_type,
                text,
                json.dumps(raw_payload or {}, ensure_ascii=False, sort_keys=True),
                json.dumps(voice_artifact or {}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        return self.get_message(conn, message_id)

    def get_message(self, conn: sqlite3.Connection, message_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Message not found: {message_id}")
        return row

    def update_message_turn(
        self, conn: sqlite3.Connection, *, message_id: str, turn_id: str
    ) -> None:
        """Associate a message with its conversation turn after turn creation."""
        conn.execute(
            "UPDATE messages SET turn_id = ? WHERE id = ?", (turn_id, message_id)
        )

    def list_messages(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        after_cursor: int | None = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        """List messages for a session, optionally after a cursor (long-polling)."""
        if after_cursor is None:
            return list(
                conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM messages
                        WHERE session_id = ?
                        ORDER BY event_cursor DESC
                        LIMIT ?
                    )
                    ORDER BY event_cursor ASC
                    """,
                    (session_id, limit),
                ).fetchall()
            )
        return list(
            conn.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ? AND event_cursor > ?
                ORDER BY event_cursor ASC
                LIMIT ?
                """,
                (session_id, after_cursor, limit),
            ).fetchall()
        )

    def latest_cursor(self, conn: sqlite3.Connection, *, session_id: str) -> int:
        """Get the latest event_cursor for a session."""
        row = conn.execute(
            "SELECT COALESCE(MAX(event_cursor), 0) AS cursor FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["cursor"])

    # ============================================================
    # Conversation Turns
    # ============================================================

    def create_turn(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        user_message_id: str,
        active_rules_version: str,
        backend_turn_trace: dict[str, Any],
        profile_snapshot: dict[str, Any],
        suggested_objective: dict[str, Any],
        profile_id: str | None = None,
        observations: list[str] | None = None,
        matched_guideline_ids: list[str] | None = None,
        active_journey_id: str | None = None,
        canned_response_ids: list[str] | None = None,
        field_status_summary: dict[str, Any] | None = None,
        model_id: str | None = None,
        backend_latency_ms: int | None = None,
        turn_aggregation_latency_ms: int | None = None,
        final_reply_hash: str | None = None,
    ) -> sqlite3.Row:
        """Create a conversation turn with full trace data."""
        turn_id = new_id("turn")
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO conversation_turns (
                id, session_id, user_message_id, profile_id, active_rules_version,
                backend_turn_trace_json, dealer_profile_snapshot_json,
                field_status_summary_json, suggested_objective_json,
                observations_json, matched_guideline_ids_json,
                active_journey_id, canned_response_ids_json,
                model_id, backend_latency_ms, turn_aggregation_latency_ms,
                message_event_count, final_reply_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                turn_id,
                session_id,
                user_message_id,
                profile_id,
                active_rules_version,
                json.dumps(backend_turn_trace, ensure_ascii=False, sort_keys=True),
                json.dumps(profile_snapshot, ensure_ascii=False, sort_keys=True),
                json.dumps(field_status_summary or {}, ensure_ascii=False, sort_keys=True),
                json.dumps(suggested_objective, ensure_ascii=False, sort_keys=True),
                json.dumps(observations or [], ensure_ascii=False, sort_keys=True),
                json.dumps(matched_guideline_ids or [], ensure_ascii=False, sort_keys=True),
                active_journey_id,
                json.dumps(canned_response_ids or [], ensure_ascii=False, sort_keys=True),
                model_id,
                backend_latency_ms,
                turn_aggregation_latency_ms,
                final_reply_hash,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM conversation_turns WHERE id = ?", (turn_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Turn insert failed.")
        return row

    def get_or_create_profile(self, conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        """Get the profile for a session, or create one if it doesn't exist."""
        session = conn.execute("SELECT profile_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise RuntimeError(f"Session {session_id} not found")
        if session["profile_id"]:
            prof = conn.execute("SELECT * FROM dealer_profiles WHERE id = ?", (session["profile_id"],)).fetchone()
            if prof:
                return prof
        
        # Create profile
        profile_id = new_id("prof")
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO dealer_profiles (
                id, canonical_key, review_status, logo_issued_status,
                created_from_session_id, current_version, created_at, updated_at
            )
            VALUES (?, ?, 'DRAFT', 'NONE', ?, 1, ?, ?)
            """,
            (profile_id, None, session_id, now, now)
        )
        conn.execute("UPDATE sessions SET profile_id = ? WHERE id = ?", (profile_id, session_id))
        prof = conn.execute("SELECT * FROM dealer_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not prof:
            raise RuntimeError("Profile insert failed.")
        return prof

    def get_profile_fields(self, conn: sqlite3.Connection, profile_id: str) -> list[sqlite3.Row]:
        """Get all profile fields for a profile."""
        return conn.execute("SELECT * FROM profile_fields WHERE profile_id = ?", (profile_id,)).fetchall()

    def upsert_profile_field(
        self,
        conn: sqlite3.Connection,
        *,
        profile_id: str,
        field_name: str,
        raw_value: Any,
        normalized_value: Any,
        status: str,
        source_type: str,
        confidence: float,
        evidence_message_ids: list[str] = None,
        validation_errors: list[str] = None,
        provenance: dict[str, Any] = None,
    ) -> None:
        """Upsert a profile field with version and audit log event."""
        now = utc_now_iso()
        evidence_json = json.dumps(evidence_message_ids or [], ensure_ascii=False)
        errors_json = json.dumps(validation_errors or [], ensure_ascii=False)
        provenance_json = json.dumps(provenance or {}, ensure_ascii=False)
        
        # Get old field to determine version
        old_field = conn.execute(
            "SELECT raw_value, normalized_value, version FROM profile_fields WHERE profile_id = ? AND field_name = ?",
            (profile_id, field_name),
        ).fetchone()
        
        version = 1
        old_raw = None
        old_norm = None
        if old_field:
            version = old_field["version"] + 1
            old_raw = old_field["raw_value"]
            old_norm = old_field["normalized_value"]
        
        # Upsert field
        conn.execute(
            """
            INSERT INTO profile_fields (
                id, profile_id, field_name, raw_value, normalized_value, status,
                source_type, confidence, evidence_message_ids_json,
                validation_errors_json, provenance_json, version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, field_name) DO UPDATE SET
                raw_value = excluded.raw_value,
                normalized_value = excluded.normalized_value,
                status = excluded.status,
                source_type = excluded.source_type,
                confidence = excluded.confidence,
                evidence_message_ids_json = excluded.evidence_message_ids_json,
                validation_errors_json = excluded.validation_errors_json,
                provenance_json = excluded.provenance_json,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (
                new_id("fld"),
                profile_id,
                field_name,
                str(raw_value) if raw_value is not None else None,
                str(normalized_value) if normalized_value is not None else None,
                status,
                source_type,
                confidence,
                evidence_json,
                errors_json,
                provenance_json,
                version,
                now,
            ),
        )
        
        # Update profile's version and updated_at
        conn.execute(
            "UPDATE dealer_profiles SET current_version = current_version + 1, updated_at = ? WHERE id = ?",
            (now, profile_id),
        )
        
        # Insert event
        conn.execute(
            """
            INSERT INTO profile_field_events (
                id, profile_id, field_name, operation, old_raw_value, old_normalized_value,
                new_raw_value, new_normalized_value, source_type, evidence_message_id,
                validation_errors_json, actor_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'system', ?)
            """,
            (
                new_id("fevt"),
                profile_id,
                field_name,
                "UPDATE" if old_field else "CREATE",
                old_raw,
                old_norm,
                str(raw_value) if raw_value is not None else None,
                str(normalized_value) if normalized_value is not None else None,
                source_type,
                evidence_message_ids[0] if evidence_message_ids else None,
                errors_json,
                now,
            ),
        )

    def get_active_flags(self, conn: sqlite3.Connection, *, session_id: str | None = None, profile_id: str | None = None) -> list[sqlite3.Row]:
        """Get active flags for a profile or session."""
        if profile_id:
            return conn.execute("SELECT * FROM flags WHERE profile_id = ? AND status = 'ACTIVE'", (profile_id,)).fetchall()
        if session_id:
            return conn.execute("SELECT * FROM flags WHERE session_id = ? AND status = 'ACTIVE'", (session_id,)).fetchall()
        return []

    def insert_flag(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str | None = None,
        profile_id: str | None = None,
        message_id: str | None = None,
        field_name: str | None = None,
        flag_name: str,
        severity: str,
        status: str = "ACTIVE",
        evidence: dict[str, Any] = None,
    ) -> sqlite3.Row:
        """Insert a safety/quality flag."""
        flag_id = new_id("flg")
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO flags (
                id, session_id, profile_id, message_id, field_name,
                flag_name, severity, status, evidence_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                flag_id,
                session_id,
                profile_id,
                message_id,
                field_name,
                flag_name,
                severity,
                status,
                json.dumps(evidence or {}, ensure_ascii=False),
                now,
            ),
        )
        return conn.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()

    def resolve_flag(self, conn: sqlite3.Connection, flag_id: str) -> None:
        """Mark a flag as resolved."""
        conn.execute(
            "UPDATE flags SET status = 'RESOLVED', resolved_at = ? WHERE id = ?",
            (utc_now_iso(), flag_id),
        )

    def update_profile_status(self, conn: sqlite3.Connection, *, profile_id: str, review_status: str, logo_issued_status: str) -> None:
        """Update review and logo issuance status of a profile."""
        now = utc_now_iso()
        conn.execute(
            "UPDATE dealer_profiles SET review_status = ?, logo_issued_status = ?, updated_at = ? WHERE id = ?",
            (review_status, logo_issued_status, now, profile_id),
        )

    def update_turn_event_count(
        self, conn: sqlite3.Connection, *, turn_id: str, count: int
    ) -> None:
        conn.execute(
            "UPDATE conversation_turns SET message_event_count = ? WHERE id = ?",
            (count, turn_id),
        )

    # ============================================================
    # Idempotency
    # ============================================================

    def get_idempotency_record(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        method: str,
        path: str,
        idempotency_key: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM idempotency_records
            WHERE session_id = ? AND method = ? AND path = ? AND idempotency_key = ?
            """,
            (session_id, method, path, idempotency_key),
        ).fetchone()

    def insert_idempotency_record(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        method: str,
        path: str,
        idempotency_key: str,
        payload_hash: str,
        response: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO idempotency_records (
                id, session_id, method, path, idempotency_key,
                payload_hash, response_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("idem"),
                session_id,
                method,
                path,
                idempotency_key,
                payload_hash,
                json.dumps(response, ensure_ascii=False, sort_keys=True),
                utc_now_iso(),
            ),
        )
