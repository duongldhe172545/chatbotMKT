"""SQLite storage adapter v8 — 3 bảng (sessions, dealer_profile_raw, admin_queue).

Refer:
- F2C.1 (LUAT_2C_infra v0.1.4) — schema + atomic write
- KE_HOACH § 2.4 — canonical DDL
- app/storage/migrations/001_init.sql — schema source of truth
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.schema import (
    AdminQueueEntry,
    DealerProfileRaw,
    DeferredSlot,
    HistoryMessage,
    SessionState,
    SlotAttempts,
)

logger = logging.getLogger(__name__)


# JSON-serialized columns trong sessions table
_SESSION_JSON_COLUMNS = {
    "slot_attempts",
    "deferred_slots",
    "skipped_slots",
    "flags",
    "flag_counts",
    "queue_triggers_fired",
    "dealer_type_history",
    "history",
    "recent_bridges",
    "partial_retried_slots",
    "last_ref_filled_fields",
    "acked_direct_keys",
}

_SESSION_JSON_DEFAULTS = {
    "slot_attempts": "{}",
    "deferred_slots": "{}",
    "skipped_slots": "[]",
    "flags": "[]",
    "flag_counts": "{}",
    "queue_triggers_fired": "[]",
    "dealer_type_history": "[]",
    "history": "[]",
    "recent_bridges": "[]",
    "partial_retried_slots": "[]",
    "last_ref_filled_fields": "[]",
    "acked_direct_keys": "[]",
}

# JSON-serialized columns trong dealer_profile_raw table
_PROFILE_JSON_COLUMNS = {"category_stack", "supplier_brands", "slogan_options"}

_PROFILE_JSON_DEFAULTS = {
    "category_stack": "[]",
    "supplier_brands": "[]",
    "slogan_options": "[]",
}

_SESSION_COLUMN_SPECS = {
    "stage": "TEXT NOT NULL DEFAULT 'GREETING'",
    "current_slot": "TEXT",
    "slot_attempts": "TEXT NOT NULL DEFAULT '{}'",
    "deferred_slots": "TEXT NOT NULL DEFAULT '{}'",
    "skipped_slots": "TEXT NOT NULL DEFAULT '[]'",
    "flags": "TEXT NOT NULL DEFAULT '[]'",
    "flag_counts": "TEXT NOT NULL DEFAULT '{}'",
    "queue_triggers_fired": "TEXT NOT NULL DEFAULT '[]'",
    "detected_dealer_type": "TEXT",
    "dealer_type_history": "TEXT NOT NULL DEFAULT '[]'",
    "confirmation_status": "TEXT NOT NULL DEFAULT 'PENDING'",
    "review_status": "TEXT NOT NULL DEFAULT 'RAW'",
    "history": "TEXT NOT NULL DEFAULT '[]'",
    "turn_count": "INTEGER NOT NULL DEFAULT 0",
    "paused_for": "TEXT",
    "consecutive_optional_refusal": "INTEGER NOT NULL DEFAULT 0",
    "rush_mode": "INTEGER NOT NULL DEFAULT 0",
    "consecutive_tam_su": "INTEGER NOT NULL DEFAULT 0",
    "recent_bridges": "TEXT NOT NULL DEFAULT '[]'",
    "partial_retried_slots": "TEXT NOT NULL DEFAULT '[]'",
    "last_acked_name": "TEXT",
    "last_ref_filled_fields": "TEXT NOT NULL DEFAULT '[]'",
    "pending_address_text": "TEXT",
    "pending_address_canonical": "TEXT",
    "acked_direct_keys": "TEXT NOT NULL DEFAULT '[]'",
    "address_form": "TEXT NOT NULL DEFAULT 'anh'",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    "closed_at": "TEXT",
    "channel": "TEXT NOT NULL DEFAULT 'web'",
    "ip_address": "TEXT",
    "user_agent": "TEXT",
}

_PROFILE_COLUMN_SPECS = {
    "dealer_name": "TEXT",
    "owner_name": "TEXT",
    "address": "TEXT",
    "phone_or_zalo": "TEXT",
    "phone_secondary": "TEXT",
    "main_product": "TEXT",
    "brandkit_consent": "TEXT",
    "category_stack": "TEXT NOT NULL DEFAULT '[]'",
    "business_model_signal": "TEXT",
    "est_team_size": "INTEGER",
    "team_stability_signal": "TEXT",
    "supplier_brands": "TEXT NOT NULL DEFAULT '[]'",
    "customer_segment_signal": "TEXT",
    "zalo": "TEXT",
    "facebook": "TEXT",
    "primary_contact_channel": "TEXT",
    "fb_marketing_status": "TEXT",
    "customer_old_percentage": "TEXT",
    "customer_storage_method": "TEXT",
    "customer_pain": "TEXT",
    "payment_terms_signal": "TEXT",
    "color_accent": "TEXT",
    "feng_shui_signal": "TEXT",
    "local_dominance_signal": "TEXT",
    "supplier_negotiation_signal": "TEXT",
    "community_network_signal": "TEXT",
    "motivation_signal": "TEXT",
    "warranty_responsibility_signal": "TEXT",
    "usp_signal": "TEXT",
    "province": "TEXT",
    "district": "TEXT",
    "province_specialty": "TEXT",
    "main_category": "TEXT",
    "dealer_type": "TEXT",
    "brand_name_short": "TEXT",
    "initials_full": "TEXT",
    "initial_single": "TEXT",
    "contact_name": "TEXT",
    "contact_role": "TEXT",
    "hotline": "TEXT",
    "slogan_options": "TEXT NOT NULL DEFAULT '[]'",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

_ADMIN_QUEUE_COLUMN_SPECS = {
    "trigger": "TEXT",
    "priority": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'PENDING'",
    "assigned_to": "TEXT",
    "notes": "TEXT",
    "profile_snapshot": "TEXT",
    "created_at": "TEXT",
    "resolved_at": "TEXT",
}


class SQLiteStore:
    """SQLite store cho 3 bảng v8."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _ensure_connection(self) -> sqlite3.Connection:
        """Return one persistent connection per store instance.

        Opening/closing a WAL SQLite connection is very slow on this Windows
        dev machine (close can take ~3s). Keeping the connection open removes
        that per-request tax while still serializing access with `_lock`.
        """
        if self._conn is None:
            conn = sqlite3.connect(
                self.db_path,
                isolation_level=None,
                check_same_thread=False,
                timeout=30,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._conn = conn
        return self._conn

    def _init_schema(self) -> None:
        """Apply migrations/001_init.sql (idempotent — CREATE IF NOT EXISTS)."""
        migration_path = Path(__file__).parent / "migrations" / "001_init.sql"
        if not migration_path.exists():
            logger.warning("Migration file không tồn tại: %s", migration_path)
            return
        with self._connect() as conn:
            # Existing Railway volumes may contain older tables. Ensure columns
            # referenced by CREATE INDEX statements exist before executescript.
            self._ensure_runtime_columns(conn)
            sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(sql)
            self._ensure_runtime_columns(conn)
            conn.commit()

    def _ensure_runtime_columns(self, conn: sqlite3.Connection) -> None:
        """Add columns introduced after initial SQLite DB creation."""
        self._add_missing_columns(conn, "sessions", _SESSION_COLUMN_SPECS)
        self._backfill_json_defaults(conn, table="sessions", defaults=_SESSION_JSON_DEFAULTS)
        self._backfill_session_scalar_defaults(conn)

        self._add_missing_columns(conn, "dealer_profile_raw", _PROFILE_COLUMN_SPECS)
        self._backfill_json_defaults(
            conn, table="dealer_profile_raw", defaults=_PROFILE_JSON_DEFAULTS
        )
        self._backfill_profile_scalar_defaults(conn)

        self._add_missing_columns(conn, "admin_queue", _ADMIN_QUEUE_COLUMN_SPECS)
        self._backfill_admin_queue_scalar_defaults(conn)

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None

    @classmethod
    def _add_missing_columns(
        cls,
        conn: sqlite3.Connection,
        table: str,
        specs: dict[str, str],
    ) -> None:
        """Add all current runtime columns to legacy tables if missing."""
        if not cls._table_exists(conn, table):
            return
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, spec in specs.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
                logger.info("Added legacy column %s.%s", table, column)

    @staticmethod
    def _backfill_json_defaults(
        conn: sqlite3.Connection,
        *,
        table: str,
        defaults: dict[str, str],
    ) -> None:
        """Backfill JSON columns introduced after a DB already existed.

        SQLite ALTER TABLE without a default leaves old rows as NULL. Pydantic
        list/dict fields do not accept NULL, so old production sessions would
        fail to load and make /api/chat return 500.
        """
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, default_json in defaults.items():
            if column in existing:
                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {column} IS NULL",
                    (default_json,),
                )

    @staticmethod
    def _backfill_session_scalar_defaults(conn: sqlite3.Connection) -> None:
        if not SQLiteStore._table_exists(conn, "sessions"):
            return
        scalar_defaults = {
            "stage": "GREETING",
            "confirmation_status": "PENDING",
            "review_status": "RAW",
            "address_form": "anh",
            "channel": "web",
        }
        for column, value in scalar_defaults.items():
            conn.execute(
                f"UPDATE sessions SET {column} = ? WHERE {column} IS NULL",
                (value,),
            )
        conn.execute("UPDATE sessions SET turn_count = 0 WHERE turn_count IS NULL")
        conn.execute(
            "UPDATE sessions SET consecutive_optional_refusal = 0 "
            "WHERE consecutive_optional_refusal IS NULL"
        )
        conn.execute("UPDATE sessions SET rush_mode = 0 WHERE rush_mode IS NULL")
        conn.execute(
            "UPDATE sessions SET consecutive_tam_su = 0 "
            "WHERE consecutive_tam_su IS NULL"
        )
        conn.execute(
            "UPDATE sessions SET created_at = datetime('now') WHERE created_at IS NULL"
        )
        conn.execute(
            "UPDATE sessions SET updated_at = datetime('now') WHERE updated_at IS NULL"
        )

    @staticmethod
    def _backfill_profile_scalar_defaults(conn: sqlite3.Connection) -> None:
        if not SQLiteStore._table_exists(conn, "dealer_profile_raw"):
            return
        conn.execute(
            "UPDATE dealer_profile_raw SET contact_role = ? WHERE contact_role IS NULL",
            ("Chủ cửa hàng",),
        )
        conn.execute(
            "UPDATE dealer_profile_raw SET created_at = datetime('now') "
            "WHERE created_at IS NULL"
        )
        conn.execute(
            "UPDATE dealer_profile_raw SET updated_at = datetime('now') "
            "WHERE updated_at IS NULL"
        )

    @staticmethod
    def _backfill_admin_queue_scalar_defaults(conn: sqlite3.Connection) -> None:
        if not SQLiteStore._table_exists(conn, "admin_queue"):
            return
        conn.execute("UPDATE admin_queue SET status = 'PENDING' WHERE status IS NULL")
        conn.execute(
            "UPDATE admin_queue SET created_at = datetime('now') "
            "WHERE created_at IS NULL"
        )

    @contextmanager
    def _connect(self):
        with self._lock:
            yield self._ensure_connection()

    def close(self) -> None:
        """Close persistent connection, mainly for tests/shutdown hooks."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ============================================================
    # Session CRUD
    # ============================================================

    def save_session(self, session: SessionState) -> None:
        """Save session: INSERT nếu mới, UPDATE nếu đã tồn tại.

        Note: KHÔNG dùng INSERT OR REPLACE vì SQLite implement = DELETE+INSERT,
        sẽ trigger ON DELETE CASCADE trên admin_queue (FK ref session_id)
        → xóa mất queue entries. Refer F2C.1 (LUAT_2C v0.1.5).
        """
        row = self._session_to_row(session)
        cols = list(row.keys())
        # UPSERT pattern: INSERT ... ON CONFLICT(session_id) DO UPDATE SET ...
        # Tránh DELETE+INSERT cascade.
        update_cols = [c for c in cols if c != "session_id"]
        set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        sql = (
            f"INSERT INTO sessions ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(session_id) DO UPDATE SET {set_clause}"
        )
        with self._connect() as conn:
            conn.execute(sql, row)

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Load session by id. None nếu không tồn tại."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_session(row)

    def delete_session(self, session_id: str) -> bool:
        """Delete session + dealer_profile_raw + admin_queue cascade.

        Returns True nếu deleted, False nếu không tồn tại.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            return cursor.rowcount > 0

    # ============================================================
    # Profile CRUD
    # ============================================================

    def save_profile(self, session_id: str, profile: DealerProfileRaw) -> None:
        """Save profile: UPSERT (INSERT or UPDATE) — tránh DELETE+INSERT cascade."""
        row = self._profile_to_row(profile, session_id)
        cols = list(row.keys())
        update_cols = [c for c in cols if c != "session_id"]
        set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        sql = (
            f"INSERT INTO dealer_profile_raw ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(session_id) DO UPDATE SET {set_clause}"
        )
        with self._connect() as conn:
            conn.execute(sql, row)

    def get_profile(self, session_id: str) -> Optional[DealerProfileRaw]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM dealer_profile_raw WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_profile(row)

    def find_profile_by_phone(self, phone: str) -> Optional[DealerProfileRaw]:
        """Cross-session dealer return detect (refer CORE § K.3)."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM dealer_profile_raw WHERE phone_or_zalo = ? LIMIT 1",
                (phone,),
            )
            row = cursor.fetchone()
            return self._row_to_profile(row) if row else None

    def find_confirmed_session_by_phone(
        self,
        phone: str,
        exclude_session_id: Optional[str] = None,
    ) -> Optional[tuple[str, DealerProfileRaw]]:
        """Cross-session dealer return detect — chỉ trả session CONFIRMED khác.

        Phase 5 R2 Gap 9: bot greet "em nhớ anh" khi phone match session cũ
        đã CONFIRMED. Loại session hiện tại để tránh self-match.

        Args:
            phone: phone_or_zalo dealer vừa fill
            exclude_session_id: session ID hiện tại (skip self-match)

        Returns:
            (other_session_id, profile) nếu có session khác CONFIRMED match,
            None nếu không.
        """
        if not phone:
            return None
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT p.session_id, p.* "
                "FROM dealer_profile_raw p "
                "JOIN sessions s ON s.session_id = p.session_id "
                "WHERE p.phone_or_zalo = ? "
                "  AND s.confirmation_status = 'CONFIRMED' "
                "  AND p.session_id != ? "
                "ORDER BY s.updated_at DESC LIMIT 1",
                (phone, exclude_session_id or ""),
            )
            row = cursor.fetchone()
            if not row:
                return None
            other_sid = row["session_id"]
            return (other_sid, self._row_to_profile(row))

    # ============================================================
    # Admin queue
    # ============================================================

    def push_admin_queue(self, entry: AdminQueueEntry) -> None:
        """Push entry vào admin_queue."""
        row = {
            "queue_id": entry.queue_id,
            "session_id": entry.session_id,
            "trigger": entry.trigger.value,
            "priority": entry.priority.value,
            "status": entry.status.value,
            "assigned_to": entry.assigned_to,
            "notes": entry.notes,
            "profile_snapshot": (
                entry.profile_snapshot.model_dump_json()
                if entry.profile_snapshot
                else None
            ),
            "created_at": entry.created_at.isoformat(),
            "resolved_at": entry.resolved_at.isoformat() if entry.resolved_at else None,
        }
        sql = (
            "INSERT INTO admin_queue (queue_id, session_id, trigger, priority, "
            "status, assigned_to, notes, profile_snapshot, created_at, resolved_at) "
            "VALUES (:queue_id, :session_id, :trigger, :priority, :status, "
            ":assigned_to, :notes, :profile_snapshot, :created_at, :resolved_at)"
        )
        with self._connect() as conn:
            conn.execute(sql, row)

    def list_queue(self, status: str = "PENDING", limit: int = 50) -> list[dict]:
        """List admin queue entries."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM admin_queue WHERE status = ? "
                "ORDER BY priority DESC, created_at ASC LIMIT ?",
                (status, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ============================================================
    # Helpers — Pydantic ↔ SQLite row
    # ============================================================

    @staticmethod
    def _session_to_row(session: SessionState) -> dict:
        """Convert SessionState → dict cho SQL bind."""
        # Pydantic v2: model_dump exclude None để dùng default values
        d = session.model_dump(mode="json")
        # Serialize complex fields → JSON string
        row = {}
        for key, value in d.items():
            if key in _SESSION_JSON_COLUMNS:
                row[key] = json.dumps(value, ensure_ascii=False)
            elif key in ("detected_dealer_type", "confirmation_status",
                         "review_status", "address_form", "channel", "stage"):
                row[key] = value  # enum → str via mode="json"
            else:
                row[key] = value
        return row

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionState:
        """Convert SQLite row → SessionState."""
        d = dict(row)
        # Deserialize JSON columns
        for col in _SESSION_JSON_COLUMNS:
            if col in d:
                raw = d[col] if d[col] is not None else _SESSION_JSON_DEFAULTS.get(col)
                if raw is not None:
                    d[col] = json.loads(raw)
        for key, value in {
            "stage": "GREETING",
            "confirmation_status": "PENDING",
            "review_status": "RAW",
            "address_form": "anh",
            "channel": "web",
            "turn_count": 0,
            "consecutive_optional_refusal": 0,
            "rush_mode": 0,
            "consecutive_tam_su": 0,
        }.items():
            if d.get(key) is None:
                d[key] = value
        # Pydantic v2: parse_obj-like via model_validate
        return SessionState.model_validate(d)

    @staticmethod
    def _profile_to_row(profile: DealerProfileRaw, session_id: str) -> dict:
        """Convert DealerProfileRaw → dict + session_id FK."""
        d = profile.model_dump(mode="json")
        row = {"session_id": session_id}
        for key, value in d.items():
            if key in _PROFILE_JSON_COLUMNS:
                row[key] = json.dumps(value, ensure_ascii=False)
            else:
                row[key] = value
        return row

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> DealerProfileRaw:
        """Convert SQLite row → DealerProfileRaw (drop session_id FK)."""
        d = dict(row)
        d.pop("session_id", None)  # FK, không thuộc schema profile
        for col in _PROFILE_JSON_COLUMNS:
            if col in d:
                raw = d[col] if d[col] is not None else _PROFILE_JSON_DEFAULTS.get(col)
                if raw is not None:
                    d[col] = json.loads(raw)
        if d.get("contact_role") is None:
            d["contact_role"] = "Chủ cửa hàng"
        return DealerProfileRaw.model_validate(d)
