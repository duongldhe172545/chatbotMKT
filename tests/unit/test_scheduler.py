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
        """Session > 1h → close + flag REQUIRED_MISSING (vì profile chưa fill)."""
        s = create_session()
        s.stage = Stage.ASKING
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
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
        """Session CONFIRMING > 1h + PENDING → flag CONSENT_UNCLEAR."""
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
        """Profile đã có owner_name + phone → KHÔNG flag REQUIRED_MISSING."""
        s = create_session()
        s.stage = Stage.ASKING
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
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
        """ADVERSARIAL: 3 session — 1 fresh + 2 stale → close 2, fresh giữ."""
        # Fresh
        s1 = create_session()
        s1.stage = Stage.ASKING
        s1.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        tmp_store.save_session(s1)
        tmp_store.save_profile(s1.session_id, DealerProfileRaw())

        # Stale
        s2 = create_session()
        s2.stage = Stage.GREETING
        s2.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        tmp_store.save_session(s2)
        tmp_store.save_profile(s2.session_id, DealerProfileRaw())

        s3 = create_session()
        s3.stage = Stage.ASKING
        s3.updated_at = datetime.now(timezone.utc) - timedelta(hours=3)
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
