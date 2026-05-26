"""Test session lifecycle + lazy timeout. Refer F2A.1 + F2C.1 + KE_HOACH § 0.4."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.session import (
    SESSION_TIMEOUT_S,
    create_session,
    is_session_timeout,
    mark_session_closed,
    touch_session,
)
from app.models.enums import Channel, Stage


class TestCreateSession:
    def test_default_session(self):
        s = create_session()
        assert s.session_id is not None
        assert len(s.session_id) > 0
        assert s.stage == Stage.GREETING
        assert s.channel == Channel.WEB
        assert s.closed_at is None
        assert s.ip_address is None

    def test_session_with_metadata(self):
        s = create_session(
            channel="zalo",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )
        assert s.channel == Channel.ZALO
        assert s.ip_address == "192.168.1.1"
        assert s.user_agent == "Mozilla/5.0"

    def test_unique_session_ids(self):
        s1 = create_session()
        s2 = create_session()
        assert s1.session_id != s2.session_id

    def test_session_id_is_uuid_format(self):
        """uuid v4 có 36 ký tự (8-4-4-4-12 + 4 hyphen)."""
        s = create_session()
        assert len(s.session_id) == 36
        assert s.session_id.count("-") == 4


class TestIsSessionTimeout:
    """Lazy timeout check — refer F2A.1 + KE_HOACH § 0.4."""

    def test_active_session_not_timeout(self):
        """Vừa tạo → updated_at = now → không timeout."""
        s = create_session()
        assert not is_session_timeout(s)

    def test_timeout_after_threshold(self):
        """Phase 6 R+ 2026-05-22: SESSION_TIMEOUT_S = 999 ngày (effectively
        vĩnh viễn). Test với explicit 1h threshold để verify function logic."""
        s = create_session()
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        # Explicit threshold 1h (3600s) — KHÔNG dùng SESSION_TIMEOUT_S vì giờ vĩnh viễn
        assert is_session_timeout(s, timeout_s=3600)

    def test_not_timeout_before_threshold(self):
        """updated_at 30 phút trước, threshold 1h → không timeout."""
        s = create_session()
        s.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert not is_session_timeout(s, timeout_s=3600)

    def test_session_persists_long_term(self):
        """Phase 6 R+ 2026-05-22: session lưu vĩnh viễn — 30 ngày inactive
        vẫn KHÔNG timeout với SESSION_TIMEOUT_S = 999 ngày."""
        s = create_session()
        s.updated_at = datetime.now(timezone.utc) - timedelta(days=30)
        assert not is_session_timeout(s, timeout_s=SESSION_TIMEOUT_S)

    def test_done_session_never_timeout(self):
        """Session đã DONE = đóng explicit, không phải timeout."""
        s = create_session()
        s.stage = Stage.DONE
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=10)
        assert not is_session_timeout(s)

    def test_closed_session_never_timeout(self):
        """Session có closed_at = đóng explicit, không phải timeout."""
        s = create_session()
        s.closed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=10)
        assert not is_session_timeout(s)

    def test_custom_timeout_threshold(self):
        """Param `timeout_s` override default."""
        s = create_session()
        s.updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        # 30s threshold → timeout (20 phút > 30s)
        assert is_session_timeout(s, timeout_s=30)
        # 1h threshold → không timeout (20 phút < 1h)
        assert not is_session_timeout(s, timeout_s=3600)

    def test_explicit_now_param(self):
        """Param `now` override datetime.now() — cho test deterministic."""
        s = create_session()
        s.updated_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # 2h sau → timeout
        now_2h = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        assert is_session_timeout(s, now=now_2h, timeout_s=3600)
        # 30 phút sau → không timeout
        now_30m = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
        assert not is_session_timeout(s, now=now_30m, timeout_s=3600)

    def test_naive_datetime_handled(self):
        """Nếu updated_at là naive (no tz), function tự gán UTC."""
        s = create_session()
        s.updated_at = datetime.utcnow() - timedelta(hours=2)  # naive
        # Phải không raise + check đúng
        result = is_session_timeout(s, timeout_s=3600)
        assert result is True


class TestMarkSessionClosed:
    def test_mark_closed_sets_stage_done(self):
        s = create_session()
        assert s.stage == Stage.GREETING
        mark_session_closed(s)
        assert s.stage == Stage.DONE
        assert s.closed_at is not None

    def test_mark_closed_updates_timestamps(self):
        s = create_session()
        before = s.updated_at
        # Sleep 1ms tránh same timestamp
        import time
        time.sleep(0.001)
        mark_session_closed(s)
        assert s.updated_at > before
        assert s.closed_at == s.updated_at

    def test_mark_closed_with_explicit_now(self):
        s = create_session()
        target = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        mark_session_closed(s, now=target)
        assert s.closed_at == target
        assert s.updated_at == target


class TestTouchSession:
    def test_touch_updates_timestamp(self):
        s = create_session()
        before = s.updated_at
        import time
        time.sleep(0.001)
        touch_session(s)
        assert s.updated_at > before

    def test_touch_does_not_change_stage(self):
        s = create_session()
        s.stage = Stage.ASKING
        touch_session(s)
        assert s.stage == Stage.ASKING
