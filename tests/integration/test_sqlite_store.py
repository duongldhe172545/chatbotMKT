"""Test SQLiteStore — CRUD cho 3 bảng. Refer F2C.1."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.enums import (
    ConfirmationStatus,
    DealerType,
    Flag,
    Priority,
    QueueStatus,
    Stage,
)
from app.models.schema import (
    AdminQueueEntry,
    DealerProfileRaw,
    DealerTypeHistoryEntry,
    DeferredSlot,
    HistoryMessage,
    SessionState,
    SlotAttempts,
)
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    """SQLiteStore với DB tạm cho test."""
    db_path = tmp_path / "test_chatbot.db"
    return SQLiteStore(str(db_path))


# ============================================================
# Schema init
# ============================================================


class TestSchemaInit:
    def test_creates_3_tables(self, store: SQLiteStore):
        """Migration tạo 3 bảng."""
        with store._connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in cursor.fetchall()]
        assert "sessions" in tables
        assert "dealer_profile_raw" in tables
        assert "admin_queue" in tables

    def test_indexes_created(self, store: SQLiteStore):
        with store._connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%'"
            )
            indexes = {r[0] for r in cursor.fetchall()}
        # Refer migration 001
        assert "idx_session_stage" in indexes
        assert "idx_dealer_phone" in indexes
        assert "idx_queue_status" in indexes


# ============================================================
# Session CRUD
# ============================================================


class TestSessionCRUD:
    def test_save_and_get_basic(self, store: SQLiteStore):
        session = SessionState(session_id="test-uuid-1")
        store.save_session(session)
        loaded = store.get_session("test-uuid-1")
        assert loaded is not None
        assert loaded.session_id == "test-uuid-1"
        assert loaded.stage == Stage.GREETING

    def test_save_with_complex_fields(self, store: SQLiteStore):
        """Verify JSON serialize/deserialize: slot_attempts, flags, history, etc."""
        session = SessionState(
            session_id="test-uuid-2",
            stage=Stage.ASKING,
            current_slot="1.1",
            slot_attempts={
                "1.1": SlotAttempts(consecutive=1, total=2),
            },
            deferred_slots={
                "2.1": DeferredSlot(defer_at_turn=5, recheck_after_n_slots=2),
            },
            skipped_slots=["2.3", "2.4"],
            flags=[Flag.REQUIRED_MISSING, Flag.HALLUCINATE],
            detected_dealer_type=DealerType.KHOE,
            dealer_type_history=[
                DealerTypeHistoryEntry(turn=3, type=DealerType.UNKNOWN),
                DealerTypeHistoryEntry(turn=8, type=DealerType.KHOE),
            ],
            history=[
                HistoryMessage(role="dealer", content="hi", ts=datetime.now(timezone.utc)),
                HistoryMessage(role="bot", content="Dạ chào anh", ts=datetime.now(timezone.utc)),
            ],
            turn_count=10,
        )
        store.save_session(session)
        loaded = store.get_session("test-uuid-2")
        assert loaded.stage == Stage.ASKING
        assert loaded.current_slot == "1.1"
        assert loaded.slot_attempts["1.1"].consecutive == 1
        assert loaded.slot_attempts["1.1"].total == 2
        assert "2.1" in loaded.deferred_slots
        assert loaded.deferred_slots["2.1"].defer_at_turn == 5
        assert loaded.skipped_slots == ["2.3", "2.4"]
        assert Flag.REQUIRED_MISSING in loaded.flags
        assert loaded.detected_dealer_type == DealerType.KHOE
        assert len(loaded.dealer_type_history) == 2
        assert len(loaded.history) == 2
        assert loaded.turn_count == 10

    def test_get_nonexistent_returns_none(self, store: SQLiteStore):
        assert store.get_session("nonexistent-id") is None

    def test_save_replaces_existing(self, store: SQLiteStore):
        """INSERT OR REPLACE — same session_id → update."""
        s1 = SessionState(session_id="same-id", stage=Stage.GREETING)
        store.save_session(s1)
        s2 = SessionState(session_id="same-id", stage=Stage.ASKING)
        store.save_session(s2)
        loaded = store.get_session("same-id")
        assert loaded.stage == Stage.ASKING

    def test_delete_session(self, store: SQLiteStore):
        session = SessionState(session_id="to-delete")
        store.save_session(session)
        assert store.delete_session("to-delete") is True
        assert store.get_session("to-delete") is None

    def test_delete_nonexistent_returns_false(self, store: SQLiteStore):
        assert store.delete_session("nonexistent") is False


# ============================================================
# Profile CRUD
# ============================================================


class TestProfileCRUD:
    def test_save_and_get_basic(self, store: SQLiteStore):
        # Cần có session trước (FK constraint)
        session = SessionState(session_id="profile-test-1")
        store.save_session(session)

        profile = DealerProfileRaw(
            owner_name="Tùng",
            dealer_name="Nhôm Kính Thanh Tùng",
            phone_or_zalo="0912345678",
        )
        store.save_profile("profile-test-1", profile)
        loaded = store.get_profile("profile-test-1")
        assert loaded is not None
        assert loaded.owner_name == "Tùng"
        assert loaded.dealer_name == "Nhôm Kính Thanh Tùng"

    def test_save_with_list_fields(self, store: SQLiteStore):
        session = SessionState(session_id="profile-test-2")
        store.save_session(session)

        profile = DealerProfileRaw(
            category_stack=["cua_nhom_kinh", "tu_bep"],
            supplier_brands=["Xingfa", "Việt Pháp"],
            slogan_options=["A", "B", "C", "D", "E"],
        )
        store.save_profile("profile-test-2", profile)
        loaded = store.get_profile("profile-test-2")
        assert loaded.category_stack == ["cua_nhom_kinh", "tu_bep"]
        assert loaded.supplier_brands == ["Xingfa", "Việt Pháp"]
        assert len(loaded.slogan_options) == 5

    def test_load_repairs_legacy_text_team_size_range(self, store: SQLiteStore):
        session = SessionState(session_id="profile-team-range")
        store.save_session(session)
        store.save_profile("profile-team-range", DealerProfileRaw())
        with store._connect() as conn:
            conn.execute(
                "UPDATE dealer_profile_raw SET est_team_size = ? WHERE session_id = ?",
                ("6-7", "profile-team-range"),
            )

        loaded = store.get_profile("profile-team-range")

        assert loaded is not None
        assert loaded.est_team_size == 6

    def test_find_by_phone(self, store: SQLiteStore):
        """Refer CORE § K.3 cross-session detect."""
        session = SessionState(session_id="phone-1")
        store.save_session(session)
        profile = DealerProfileRaw(phone_or_zalo="0912345678", owner_name="Tùng")
        store.save_profile("phone-1", profile)

        found = store.find_profile_by_phone("0912345678")
        assert found is not None
        assert found.owner_name == "Tùng"

    def test_find_by_phone_not_found(self, store: SQLiteStore):
        assert store.find_profile_by_phone("0000000000") is None

    def test_find_confirmed_session_by_phone(self, store: SQLiteStore):
        """Phase 5 R2 Gap 9: cross-session detect CHỈ trả session CONFIRMED."""
        # Session A: CONFIRMED
        s_a = SessionState(
            session_id="old-confirmed",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        )
        store.save_session(s_a)
        store.save_profile(
            "old-confirmed",
            DealerProfileRaw(phone_or_zalo="0912345678", owner_name="Tùng"),
        )

        # Session B: PENDING (chưa CONFIRMED — không match)
        s_b = SessionState(
            session_id="old-pending",
            confirmation_status=ConfirmationStatus.PENDING,
        )
        store.save_session(s_b)
        store.save_profile(
            "old-pending",
            DealerProfileRaw(phone_or_zalo="0987654321", owner_name="Vinh"),
        )

        # Phone match CONFIRMED session
        match = store.find_confirmed_session_by_phone(
            "0912345678", exclude_session_id="current-session"
        )
        assert match is not None
        old_sid, old_profile = match
        assert old_sid == "old-confirmed"
        assert old_profile.owner_name == "Tùng"

        # Phone match nhưng session PENDING → không trả
        no_match = store.find_confirmed_session_by_phone(
            "0987654321", exclude_session_id="current-session"
        )
        assert no_match is None

    def test_find_confirmed_excludes_self(self, store: SQLiteStore):
        """ADVERSARIAL: exclude_session_id loại self-match."""
        s = SessionState(
            session_id="self-session",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        )
        store.save_session(s)
        store.save_profile(
            "self-session",
            DealerProfileRaw(phone_or_zalo="0912345678"),
        )
        # Tự match → return None (exclude self)
        assert store.find_confirmed_session_by_phone(
            "0912345678", exclude_session_id="self-session"
        ) is None

    def test_find_confirmed_empty_phone(self, store: SQLiteStore):
        assert store.find_confirmed_session_by_phone("") is None
        assert store.find_confirmed_session_by_phone(None) is None


# ============================================================
# Admin queue
# ============================================================


class TestAdminQueue:
    def test_push_and_list(self, store: SQLiteStore):
        # Need session first (FK)
        session = SessionState(session_id="queue-test-1")
        store.save_session(session)

        entry = AdminQueueEntry(
            queue_id="q-1",
            session_id="queue-test-1",
            trigger=Flag.HALLUCINATE,
            priority=Priority.HIGH,
        )
        store.push_admin_queue(entry)

        items = store.list_queue(status="PENDING")
        assert len(items) == 1
        assert items[0]["queue_id"] == "q-1"
        assert items[0]["trigger"] == "hallucinate"
        assert items[0]["priority"] == "HIGH"

    def test_list_empty(self, store: SQLiteStore):
        assert store.list_queue() == []


# ============================================================
# Cascade delete (FK ON DELETE CASCADE)
# ============================================================


class TestCascadeDelete:
    def test_delete_session_cascades_profile(self, store: SQLiteStore):
        """Delete session → profile cũng bị xóa (FK CASCADE)."""
        session = SessionState(session_id="cascade-1")
        store.save_session(session)
        profile = DealerProfileRaw(owner_name="Tùng")
        store.save_profile("cascade-1", profile)

        store.delete_session("cascade-1")

        assert store.get_profile("cascade-1") is None
