"""Test background scheduler — Phase 4 R1."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import get_settings, reset_settings
from app.models.enums import Flag, Stage
from app.models.schema import DealerProfileRaw
from app.scheduler.timeout_worker import sweep_timeouts
from app.core.session import create_session
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture
def tmp_store(tmp_path):
    """Tmp SQLiteStore — không animal sang real DB."""
    db = tmp_path / "test_scheduler.db"
    return SQLiteStore(str(db))


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_settings()
    yield
    reset_settings()


# ============================================================
# sweep_timeouts logic
# ============================================================


class TestSweepTimeouts:
    def test_no_active_sessions_returns_zero(self, tmp_store):
        result = sweep_timeouts(tmp_store)
        assert result["checked"] == 0
        assert result["closed"] == 0

    def test_fresh_session_not_closed(self, tmp_store):
        """Session vừa active < timeout → KHÔNG close."""
        s = create_session()
        s.stage = Stage.ASKING
        s.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        tmp_store.save_session(s)
        result = sweep_timeouts(tmp_store)
        assert result["checked"] == 1
        assert result["closed"] == 0

    def test_stale_session_closed(self, tmp_store):
        """Phase 6 R+ 2026-05-22: SESSION_TIMEOUT_S = 999 ngày (vĩnh viễn).
        Session > 1100 ngày → close + flag REQUIRED_MISSING (vì profile chưa fill).
        """
        s = create_session()
        s.stage = Stage.ASKING
        s.updated_at = datetime.now(timezone.utc) - timedelta(days=1100)
        tmp_store.save_session(s)
        tmp_store.save_profile(s.session_id, DealerProfileRaw())

        result = sweep_timeouts(tmp_store)
        assert result["closed"] == 1

        # Reload + verify
        loaded = tmp_store.get_session(s.session_id)
        assert loaded.stage == Stage.DONE
        assert loaded.closed_at is not None
        assert Flag.REQUIRED_MISSING in loaded.flags

    def test_stale_confirming_flags_consent_unclear(self, tmp_store):
        """Session CONFIRMING > 1h + PENDING → flag CONSENT_UNCLEAR.

        Note: CONFIRMING dùng SESSION_TIMEOUT_CONFIRMING_S = 600s (10 phút,
        không đổi). Test 2h vẫn fire OK.
        """
        s = create_session()
        s.stage = Stage.CONFIRMING
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        tmp_store.save_session(s)
        tmp_store.save_profile(
            s.session_id,
            DealerProfileRaw(owner_name="Tùng", phone_or_zalo="0912345678"),
        )

        sweep_timeouts(tmp_store)
        loaded = tmp_store.get_session(s.session_id)
        assert loaded.stage == Stage.DONE
        assert Flag.CONSENT_UNCLEAR in loaded.flags

    def test_already_closed_session_skipped(self, tmp_store):
        """ADVERSARIAL: session đã closed_at IS NOT NULL → skip (không count)."""
        s = create_session()
        s.stage = Stage.DONE
        s.closed_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        tmp_store.save_session(s)

        result = sweep_timeouts(tmp_store)
        # Đã DONE + closed_at NOT NULL → query filter loại
        assert result["checked"] == 0

    def test_filled_profile_no_required_missing_flag(self, tmp_store):
        """Profile đã có owner_name + phone → KHÔNG flag REQUIRED_MISSING.
        Phase 6 R+: session > 1100 ngày để qua threshold 999 ngày."""
        s = create_session()
        s.stage = Stage.ASKING
        s.updated_at = datetime.now(timezone.utc) - timedelta(days=1100)
        tmp_store.save_session(s)
        tmp_store.save_profile(
            s.session_id,
            DealerProfileRaw(owner_name="Tùng", phone_or_zalo="0912345678"),
        )

        sweep_timeouts(tmp_store)
        loaded = tmp_store.get_session(s.session_id)
        assert loaded.stage == Stage.DONE
        assert Flag.REQUIRED_MISSING not in loaded.flags

    def test_multiple_sessions_mix(self, tmp_store):
        """ADVERSARIAL: 3 session — 1 fresh + 2 stale → close 2, fresh giữ.
        Phase 6 R+: stale = > 1100 ngày (qua threshold 999 ngày vĩnh viễn).
        """
        # Fresh
        s1 = create_session()
        s1.stage = Stage.ASKING
        s1.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        tmp_store.save_session(s1)
        tmp_store.save_profile(s1.session_id, DealerProfileRaw())

        # Stale (> 999 ngày để trigger timeout)
        s2 = create_session()
        s2.stage = Stage.GREETING
        s2.updated_at = datetime.now(timezone.utc) - timedelta(days=1100)
        tmp_store.save_session(s2)
        tmp_store.save_profile(s2.session_id, DealerProfileRaw())

        s3 = create_session()
        s3.stage = Stage.ASKING
        s3.updated_at = datetime.now(timezone.utc) - timedelta(days=1200)
        tmp_store.save_session(s3)
        tmp_store.save_profile(s3.session_id, DealerProfileRaw())

        result = sweep_timeouts(tmp_store)
        assert result["checked"] == 3
        assert result["closed"] == 2

        # Verify s1 giữ ASKING
        assert tmp_store.get_session(s1.session_id).stage == Stage.ASKING
        # s2 + s3 đã DONE
        assert tmp_store.get_session(s2.session_id).stage == Stage.DONE
        assert tmp_store.get_session(s3.session_id).stage == Stage.DONE


class TestCreateScheduler:
    def test_scheduler_created_with_job(self, tmp_store):
        from app.scheduler.timeout_worker import create_scheduler
        sched = create_scheduler(tmp_store)
        jobs = sched.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "session_timeout_sweep"



# ============================================================
# Phase 5 R5 Gap 15 — CONFIRMING nudge 3 phút + soft-close 10 phút
# ============================================================


class TestConfirmingNudge:
    def test_confirming_stale_3min_marks_nudge_pending(self, tmp_store):
        """CONFIRMING gap ≥ 3 phút → flag NUDGE_PENDING (1C § 9)."""
        s = create_session()
        s.stage = Stage.CONFIRMING
        # 4 phút trước (> 3 phút threshold, < 10 phút close)
        s.updated_at = datetime.now(timezone.utc) - timedelta(seconds=240)
        tmp_store.save_session(s)

        result = sweep_timeouts(tmp_store)
        assert result["nudged"] == 1
        assert result["closed"] == 0

        # Verify flag set
        loaded = tmp_store.get_session(s.session_id)
        assert Flag.NUDGE_PENDING in loaded.flags
        # Stage vẫn CONFIRMING (chưa close)
        assert loaded.stage == Stage.CONFIRMING

    def test_confirming_stale_10min_soft_closes(self, tmp_store):
        """CONFIRMING gap ≥ 10 phút → soft-close + CONSENT_UNCLEAR."""
        s = create_session()
        s.stage = Stage.CONFIRMING
        s.updated_at = datetime.now(timezone.utc) - timedelta(seconds=700)
        tmp_store.save_session(s)
        profile = DealerProfileRaw(owner_name="Tùng", phone_or_zalo="0912345678")
        tmp_store.save_profile(s.session_id, profile)

        result = sweep_timeouts(tmp_store)
        assert result["closed"] == 1

        loaded = tmp_store.get_session(s.session_id)
        assert loaded.stage == Stage.DONE
        assert Flag.CONSENT_UNCLEAR in loaded.flags

    def test_confirming_1min_no_action(self, tmp_store):
        """ADVERSARIAL: CONFIRMING gap < 3 phút → KHÔNG nudge, KHÔNG close."""
        s = create_session()
        s.stage = Stage.CONFIRMING
        s.updated_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        tmp_store.save_session(s)

        result = sweep_timeouts(tmp_store)
        assert result["closed"] == 0
        assert result["nudged"] == 0

    def test_nudge_idempotent(self, tmp_store):
        """ADVERSARIAL: sweep 2 lần → nudge chỉ raise 1 lần."""
        s = create_session()
        s.stage = Stage.CONFIRMING
        s.updated_at = datetime.now(timezone.utc) - timedelta(seconds=240)
        tmp_store.save_session(s)

        sweep_timeouts(tmp_store)  # lần 1: nudge
        result2 = sweep_timeouts(tmp_store)  # lần 2: KHÔNG nudge lại
        assert result2["nudged"] == 0

    def test_asking_3min_no_nudge(self, tmp_store):
        """ADVERSARIAL: ASKING stage KHÔNG bị nudge (chỉ CONFIRMING)."""
        s = create_session()
        s.stage = Stage.ASKING
        s.updated_at = datetime.now(timezone.utc) - timedelta(seconds=240)
        tmp_store.save_session(s)

        result = sweep_timeouts(tmp_store)
        assert result["nudged"] == 0
        assert result["closed"] == 0
