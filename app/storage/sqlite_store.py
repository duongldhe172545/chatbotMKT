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
            # WAL mode: read/write song song không block nhau (H5 fix). Tạo
            # thêm .db-wal + .db-shm files cạnh db chính — Railway volume
            # mount cả folder nên không cần config thêm.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
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

                -- H6 fix: index phone để find_profile_by_phone O(log n) thay vì
                -- full table scan. phone_or_zalo lưu digits-only sau extractor
                -- HIGH (xem prompts.py) → so sánh equality nhanh.
                CREATE INDEX IF NOT EXISTS idx_dealer_phone
                    ON dealer_profile_raw (phone_or_zalo);
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

        # Migration 3 (v7): thêm các cột mới cho Em Linh MKT v7.
        # Tất cả nullable, không break data v6. Cột list (category_stack,
        # supplier_brands) lưu JSON string.
        v7_columns = [
            # Identity
            ("address", "TEXT"),
            ("province_specialty", "TEXT"),
            # Business
            ("category_stack", "TEXT DEFAULT '[]'"),
            ("main_product", "TEXT"),
            ("product_portfolio_signal", "TEXT"),
            ("business_model_signal", "TEXT"),
            ("est_team_size", "INTEGER"),
            ("team_stability_signal", "TEXT"),
            ("supplier_brands", "TEXT DEFAULT '[]'"),
            ("customer_segment_signal", "TEXT"),
            # Channels
            ("zalo", "TEXT"),
            ("facebook", "TEXT"),
            ("primary_contact_channel", "TEXT"),
            ("fb_marketing_status", "TEXT"),
            # Customer Gold Mine
            ("customer_old_percentage", "TEXT"),
            ("customer_storage_method", "TEXT"),
            ("customer_pain", "TEXT"),
            ("usp_signal", "TEXT"),
            ("payment_terms_signal", "TEXT"),
            # Brandkit
            ("brandkit_consent", "TEXT"),
            ("slogan", "TEXT"),
            ("color_accent", "TEXT"),
            ("feng_shui_signal", "TEXT"),
        ]
        for col_name, col_def in v7_columns:
            if not self._column_exists(conn, "dealer_profile_raw", col_name):
                try:
                    conn.execute(
                        f"ALTER TABLE dealer_profile_raw ADD COLUMN {col_name} {col_def}"
                    )
                    logger.info("Migration v7: added '%s' column", col_name)
                except sqlite3.OperationalError as exc:
                    logger.error("Migration v7 thêm cột '%s' fail: %s", col_name, exc)
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

    def find_profile_by_phone(self, phone: str) -> DealerProfileRaw | None:
        """Tìm profile RAW đã CONFIRMED có cùng phone_or_zalo.

        Dùng cho cross-session memory: dealer cũ chat lại → resume context.
        - Filter status=CONFIRMED: profile EDITED (chưa duyệt xong) KHÔNG
          trigger returning dealer flow để tránh greet sai khi dealer cũ
          chưa hoàn tất profile.
        - Index trên phone_or_zalo (xem _init_schema) → O(log n).
        - phone_or_zalo lưu digits-only (extractor strict pattern) — match
          equality nhanh.
        """
        # Normalize input: chỉ giữ chữ số
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if len(digits) < 9:
            return None

        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM dealer_profile_raw
                WHERE phone_or_zalo = ?
                  AND confirmation_status = 'CONFIRMED'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (digits,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        # Parse JSON cho list fields (v6 + v7).
        for key in ("dl0_priority", "flags", "pain_points", "category_stack", "supplier_brands"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except (TypeError, ValueError):
                d[key] = []
        if not d.get("pain_points") and d.get("main_pain_point"):
            d["pain_points"] = [d["main_pain_point"]]
        # Strip fields không thuộc DealerProfileRaw schema
        profile_kwargs = {
            k: v for k, v in d.items()
            if k in DealerProfileRaw.model_fields
        }
        return DealerProfileRaw(**profile_kwargs)

    def list_profiles(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dealer_profile_raw ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for key in ("dl0_priority", "flags", "pain_points", "category_stack", "supplier_brands"):
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
        """Persist profile RAW — gồm cả v6 fields (cũ) + v7 fields (mới).

        main_pain_point cũ giữ NULL — schema mới dùng pain_points + customer_pain.
        """
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO dealer_profile_raw (
                    session_id, dealer_name, owner_name, phone_or_zalo,
                    province, district, main_category, dealer_type,
                    customer_base_estimate, main_pain_point, pain_points, dl0_priority,
                    recommended_group, confirmation_status, review_status,
                    flags, created_at,
                    -- v7 columns
                    address, province_specialty,
                    category_stack, main_product, product_portfolio_signal,
                    business_model_signal, est_team_size, team_stability_signal,
                    supplier_brands, customer_segment_signal,
                    zalo, facebook, primary_contact_channel, fb_marketing_status,
                    customer_old_percentage, customer_storage_method, customer_pain,
                    usp_signal, payment_terms_signal,
                    brandkit_consent, slogan, color_accent, feng_shui_signal
                ) VALUES (
                    ?, ?, ?, ?,  ?, ?, ?, ?,  ?, ?, ?, ?,  ?, ?, ?,  ?, ?,
                    ?, ?,  ?, ?, ?,  ?, ?, ?,  ?, ?,
                    ?, ?, ?, ?,  ?, ?, ?,  ?, ?,
                    ?, ?, ?, ?
                )
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
                    flags = excluded.flags,
                    address = excluded.address,
                    province_specialty = excluded.province_specialty,
                    category_stack = excluded.category_stack,
                    main_product = excluded.main_product,
                    product_portfolio_signal = excluded.product_portfolio_signal,
                    business_model_signal = excluded.business_model_signal,
                    est_team_size = excluded.est_team_size,
                    team_stability_signal = excluded.team_stability_signal,
                    supplier_brands = excluded.supplier_brands,
                    customer_segment_signal = excluded.customer_segment_signal,
                    zalo = excluded.zalo,
                    facebook = excluded.facebook,
                    primary_contact_channel = excluded.primary_contact_channel,
                    fb_marketing_status = excluded.fb_marketing_status,
                    customer_old_percentage = excluded.customer_old_percentage,
                    customer_storage_method = excluded.customer_storage_method,
                    customer_pain = excluded.customer_pain,
                    usp_signal = excluded.usp_signal,
                    payment_terms_signal = excluded.payment_terms_signal,
                    brandkit_consent = excluded.brandkit_consent,
                    slogan = excluded.slogan,
                    color_accent = excluded.color_accent,
                    feng_shui_signal = excluded.feng_shui_signal
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
                    # v7
                    profile.address,
                    profile.province_specialty,
                    json.dumps(profile.category_stack, ensure_ascii=False),
                    profile.main_product,
                    profile.product_portfolio_signal,
                    profile.business_model_signal,
                    profile.est_team_size,
                    profile.team_stability_signal,
                    json.dumps(profile.supplier_brands, ensure_ascii=False),
                    profile.customer_segment_signal,
                    profile.zalo,
                    profile.facebook,
                    profile.primary_contact_channel,
                    profile.fb_marketing_status,
                    profile.customer_old_percentage,
                    profile.customer_storage_method,
                    profile.customer_pain,
                    profile.usp_signal,
                    profile.payment_terms_signal,
                    profile.brandkit_consent,
                    profile.slogan,
                    profile.color_accent,
                    profile.feng_shui_signal,
                ),
            )
