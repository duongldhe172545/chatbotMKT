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
}

# JSON-serialized columns trong dealer_profile_raw table
_PROFILE_JSON_COLUMNS = {"category_stack", "supplier_brands", "slogan_options"}


class SQLiteStore:
    """SQLite store cho 3 bảng v8."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Apply migrations/001_init.sql (idempotent — CREATE IF NOT EXISTS)."""
        migration_path = Path(__file__).parent / "migrations" / "001_init.sql"
        if not migration_path.exists():
            logger.warning("Migration file không tồn tại: %s", migration_path)
            return
        with self._connect() as conn:
            sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.commit()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

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
            if col in d and d[col] is not None:
                d[col] = json.loads(d[col])
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
            if col in d and d[col] is not None:
                d[col] = json.loads(d[col])
        return DealerProfileRaw.model_validate(d)
