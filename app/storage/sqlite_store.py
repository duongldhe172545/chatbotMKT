"""SQLite storage — file local cho MVP."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from app.models.schema import DealerProfileRaw, Session

from .base import StorageAdapter


class SQLiteStore(StorageAdapter):
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dealer_profile_raw (
                    session_id TEXT PRIMARY KEY,
                    dealer_name TEXT,
                    owner_name TEXT,
                    phone_or_zalo TEXT,
                    province TEXT,
                    district TEXT,
                    main_category TEXT,
                    dealer_type TEXT,
                    customer_base_estimate TEXT,
                    main_pain_point TEXT,
                    dl0_priority TEXT,
                    recommended_group TEXT,
                    confirmation_status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._run_migrations(conn)

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row[1] == column for row in rows)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Migration tường minh — check cột trước khi ALTER, log rõ thay vì swallow."""
        logger = logging.getLogger(__name__)

        # Migration 1: thêm cột flags
        if not self._column_exists(conn, "dealer_profile_raw", "flags"):
            try:
                conn.execute(
                    "ALTER TABLE dealer_profile_raw ADD COLUMN flags TEXT DEFAULT '[]'"
                )
                logger.info("Migration: added 'flags' column to dealer_profile_raw")
            except sqlite3.OperationalError as exc:
                logger.error("Migration thêm cột 'flags' fail: %s", exc)
                raise

        # Migration 2: thêm cột pain_points (JSON array thay cho main_pain_point str)
        if not self._column_exists(conn, "dealer_profile_raw", "pain_points"):
            try:
                conn.execute(
                    "ALTER TABLE dealer_profile_raw ADD COLUMN pain_points TEXT DEFAULT '[]'"
                )
                logger.info("Migration: added 'pain_points' column")
                # Convert dữ liệu cũ: main_pain_point str → pain_points [str]
                rows = conn.execute(
                    "SELECT session_id, main_pain_point FROM dealer_profile_raw "
                    "WHERE main_pain_point IS NOT NULL AND main_pain_point != ''"
                ).fetchall()
                for r in rows:
                    sid = r[0]
                    old_value = r[1]
                    new_value = json.dumps([old_value], ensure_ascii=False)
                    conn.execute(
                        "UPDATE dealer_profile_raw SET pain_points = ? WHERE session_id = ?",
                        (new_value, sid),
                    )
                logger.info("Migration: converted %d rows main_pain_point → pain_points", len(rows))
            except sqlite3.OperationalError as exc:
                logger.error("Migration pain_points fail: %s", exc)
                raise

    def save_session(self, session: Session) -> None:
        session.updated_at = datetime.utcnow()
        payload = session.model_dump_json()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, stage, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    stage = excluded.stage,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.stage.value,
                    payload,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )

    def load_session(self, session_id: str) -> Session | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return Session.model_validate_json(row["data_json"])

    def list_profiles(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dealer_profile_raw ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for key in ("dl0_priority", "flags", "pain_points"):
                try:
                    d[key] = json.loads(d.get(key) or "[]")
                except (TypeError, ValueError):
                    d[key] = []
            # Backward compat: nếu pain_points rỗng nhưng main_pain_point cũ có value
            if not d.get("pain_points") and d.get("main_pain_point"):
                d["pain_points"] = [d["main_pain_point"]]
            result.append(d)
        return result

    def list_sessions(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT session_id, stage, created_at, updated_at, data_json
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            data = json.loads(r["data_json"])
            result.append(
                {
                    "session_id": r["session_id"],
                    "stage": r["stage"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "message_count": len(data.get("messages", [])),
                    "dealer_name": data.get("profile_raw", {}).get("dealer_name"),
                    "phone_or_zalo": data.get("profile_raw", {}).get("phone_or_zalo"),
                    "data": data,
                }
            )
        return result

    def save_profile_raw(self, session_id: str, profile: DealerProfileRaw) -> None:
        # main_pain_point cũ giữ NULL — schema mới dùng pain_points (JSON array)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO dealer_profile_raw (
                    session_id, dealer_name, owner_name, phone_or_zalo,
                    province, district, main_category, dealer_type,
                    customer_base_estimate, main_pain_point, pain_points, dl0_priority,
                    recommended_group, confirmation_status, review_status,
                    flags, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    dealer_name = excluded.dealer_name,
                    owner_name = excluded.owner_name,
                    phone_or_zalo = excluded.phone_or_zalo,
                    province = excluded.province,
                    district = excluded.district,
                    main_category = excluded.main_category,
                    dealer_type = excluded.dealer_type,
                    customer_base_estimate = excluded.customer_base_estimate,
                    pain_points = excluded.pain_points,
                    dl0_priority = excluded.dl0_priority,
                    recommended_group = excluded.recommended_group,
                    confirmation_status = excluded.confirmation_status,
                    review_status = excluded.review_status,
                    flags = excluded.flags
                """,
                (
                    session_id,
                    profile.dealer_name,
                    profile.owner_name,
                    profile.phone_or_zalo,
                    profile.province,
                    profile.district,
                    profile.main_category,
                    profile.dealer_type,
                    profile.customer_base_estimate,
                    None,  # main_pain_point cũ — không dùng nữa, để NULL
                    json.dumps(profile.pain_points, ensure_ascii=False),
                    json.dumps(profile.dl0_priority, ensure_ascii=False),
                    profile.recommended_group,
                    profile.confirmation_status,
                    profile.review_status,
                    json.dumps(profile.flags, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                ),
            )
