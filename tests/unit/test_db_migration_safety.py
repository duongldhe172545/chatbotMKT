"""P1 — An toàn DATA khi khởi tạo/migrate DB (2026-06-10).

Bug cũ (H1): `Database.initialize()` tự DROP TẤT CẢ bảng nếu phát hiện schema
thiếu cột `session_token_hash` → 1 lần deploy nhầm version cũ là xoá sạch
data production. Đã thay bằng reconcile cột ADDITIVE (chỉ ADD COLUMN, không drop).

Test ở đây CHỐT 2 việc:
1. DB cũ thiếu cột + đang có data → initialize() GIỮ NGUYÊN data, chỉ thêm cột.
2. config production từ chối fallback vào ổ ephemeral (mất data khi restart).
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from app.core.config_v2 import Settings
from app.db.connection import (
    SCHEMA_VERSION,
    Database,
    _parse_schema_columns,
    _reconcile_columns,
)
from app.db.schema import SCHEMA_SQL


# ============================================================
# Parser SCHEMA_SQL → cột
# ============================================================


class TestSchemaParser:
    def test_extracts_real_columns(self):
        tables = _parse_schema_columns(SCHEMA_SQL)
        assert "sessions" in tables
        assert "session_token_hash" in tables["sessions"]
        assert "id" in tables["sessions"]
        assert "metadata_json" in tables["sessions"]

    def test_skips_table_level_constraints(self):
        tables = _parse_schema_columns(SCHEMA_SQL)
        # UNIQUE(profile_id, field_name) KHÔNG được coi là cột
        assert "UNIQUE" not in tables["profile_fields"]
        assert "field_name" in tables["profile_fields"]
        # idempotency_records có UNIQUE(...) multi-col — không lọt vào cột
        assert "UNIQUE" not in tables["idempotency_records"]
        assert "idempotency_key" in tables["idempotency_records"]

    def test_all_15_tables_parsed(self):
        tables = _parse_schema_columns(SCHEMA_SQL)
        assert len(tables) >= 15
        for t in ("messages", "conversation_turns", "logo_jobs", "flags"):
            assert t in tables and len(tables[t]) > 0


# ============================================================
# CỐT LÕI: data sống sót khi migrate
# ============================================================


def _make_legacy_db(path: str) -> None:
    """Tạo DB 'cũ' — sessions thiếu nhiều cột (kể cả session_token_hash) + 1 row."""
    raw = sqlite3.connect(path)
    raw.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            workflow_state TEXT NOT NULL,
            started_at TEXT NOT NULL
        )
        """
    )
    raw.execute(
        "INSERT INTO sessions (id, channel, status, workflow_state, started_at) "
        "VALUES ('ses_legacy', 'web', 'ACTIVE', 'GREETING', '2026-01-01T00:00:00')"
    )
    raw.commit()
    raw.close()


class TestDataSurvivesMigration:
    def test_legacy_db_keeps_data_and_gains_columns(self, tmp_path):
        db_file = str(tmp_path / "legacy.sqlite3")
        _make_legacy_db(db_file)

        Database(db_file).initialize()  # KHÔNG được drop

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        try:
            # 1. Data CŨ còn nguyên
            row = conn.execute(
                "SELECT id, channel FROM sessions WHERE id = 'ses_legacy'"
            ).fetchone()
            assert row is not None, "DATA BỊ MẤT — migrate đã drop bảng!"
            assert row["channel"] == "web"

            # 2. Cột thiếu đã được thêm (additive)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
            assert "session_token_hash" in cols  # cột từng kích hoạt auto-drop
            assert "metadata_json" in cols

            # 3. Các bảng khác được tạo mới
            tables = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert {"messages", "conversation_turns", "dealer_profiles"} <= tables
        finally:
            conn.close()

    def test_initialize_idempotent(self, tmp_path):
        db = Database(str(tmp_path / "x.sqlite3"))
        db.initialize()
        db.initialize()  # chạy lại không lỗi, không mất gì
        assert db.health_check() is True

    def test_fresh_db_sets_schema_version(self, tmp_path):
        db_file = str(tmp_path / "fresh.sqlite3")
        Database(db_file).initialize()
        conn = sqlite3.connect(db_file)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == SCHEMA_VERSION
        finally:
            conn.close()

    def test_reconcile_is_noop_on_current_schema(self, tmp_path):
        """DB đã đủ cột → reconcile không thêm gì (không lỗi)."""
        db = Database(str(tmp_path / "cur.sqlite3"))
        db.initialize()
        conn = db.connect()
        try:
            before = {
                r["name"] for r in conn.execute("PRAGMA table_info(sessions)")
            }
            _reconcile_columns(conn)
            after = {
                r["name"] for r in conn.execute("PRAGMA table_info(sessions)")
            }
            assert before == after
        finally:
            conn.close()


# ============================================================
# config — production không được fallback ổ ephemeral
# ============================================================


_HAS_DATA_VOLUME = os.path.exists("/data") and os.access("/data", os.W_OK)


class TestConfigDataSafety:
    @pytest.mark.skipif(_HAS_DATA_VOLUME, reason="/data tồn tại trên máy này")
    def test_production_refuses_ephemeral_path(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLITE_PATH", raising=False)
        with pytest.raises(ValueError, match="production"):
            Settings.from_env()

    def test_production_accepts_explicit_sqlite_path(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("SQLITE_PATH", "/data/chatbot_v2.sqlite3")
        # các validate production khác
        monkeypatch.setenv("SESSION_TOKEN_SECRET", "prod-secret")
        monkeypatch.setenv("ADMIN_API_TOKEN", "prod-admin")
        monkeypatch.setenv("ZALO_GROUP_URL", "https://zalo.me/g/abc")
        s = Settings.from_env()  # KHÔNG raise = chấp nhận path tường minh
        # (sqlite_path bị OS chuẩn hoá trên Windows; kiểm database_url cho cross-platform)
        assert "/data/chatbot_v2.sqlite3" in s.database_url

    def test_nonprod_falls_back_without_error(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLITE_PATH", raising=False)
        s = Settings.from_env()  # KHÔNG raise
        assert s.sqlite_path.endswith("chatbot_v2.sqlite3")

    def test_explicit_database_url_memory_unaffected(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        s = Settings.from_env()
        assert s.sqlite_path == ":memory:"
