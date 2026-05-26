"""Session lifecycle + lazy timeout check.

Refer:
- F2A.1 (LUAT_2A_core v0.2.4) — Stages + transitions
- F2C.1 (LUAT_2C_infra v0.1.4) — Session lifecycle + storage
- KE_HOACH § 0.4 — Phase 1 dùng lazy timeout (không background scheduler)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.enums import Channel, Stage
from app.models.schema import SessionState


# Default config — refer F2A.4 tham số config + 2C F2C.1
# Phase 6 R+ 2026-05-22 (user feedback): set vĩnh viễn (999 ngày).
# Session chỉ DONE qua: (1) confirm card → CONFIRMING, (2) escalate L3.
# Scheduler nudge (3 phút sau Card render) vẫn chạy nhưng KHÔNG close session.
SESSION_TIMEOUT_S = 999 * 24 * 3600     # ~ vĩnh viễn (refer GLOSSARY § Session)


def create_session(
    channel: str = "web",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> SessionState:
    """Tạo session mới với uuid + default state.

    Args:
        channel: web / zalo / fb (default web)
        ip_address: IP dealer (cho rate limit)
        user_agent: User agent dealer (debug)

    Returns:
        SessionState với session_id mới, stage = GREETING, các state default.
    """
    return SessionState(
        session_id=str(uuid.uuid4()),
        channel=Channel(channel),
        ip_address=ip_address,
        user_agent=user_agent,
    )


def is_session_timeout(
    session: SessionState,
    now: Optional[datetime] = None,
    timeout_s: int = SESSION_TIMEOUT_S,
) -> bool:
    """Lazy timeout check — refer F2A.1 + KE_HOACH § 0.4.

    Mỗi lần dealer gửi message mới, engine gọi function này để check:
        now - session.updated_at > timeout_s

    Phase 1-3: dùng lazy check (KHÔNG background scheduler).
    Phase 4: chuyển sang background sweep (F2C.1).

    Args:
        session: Session state hiện tại
        now: Datetime để compare (default: datetime.now(UTC))
        timeout_s: Threshold giây (default 3600 = 1h)

    Returns:
        True nếu session đã timeout (inactive quá threshold).
        False nếu session đã DONE/closed (không phải timeout, đã end explicit).
    """
    if session.stage == Stage.DONE:
        return False                                  # Đã đóng explicit, không phải timeout
    if session.closed_at is not None:
        return False                                  # Đã đóng explicit

    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure tz-aware compare — pydantic Field default_factory đã trả tz-aware,
    # nhưng test có thể set updated_at = naive datetime → safety check.
    updated_at = session.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    delta = now - updated_at
    return delta.total_seconds() > timeout_s


def mark_session_closed(
    session: SessionState,
    now: Optional[datetime] = None,
) -> SessionState:
    """Mark session DONE + set closed_at. Mutate session in-place, return cùng object.

    Args:
        session: Session để mark closed
        now: Datetime để set (default: datetime.now(UTC))

    Returns:
        Session đã updated (stage=DONE, closed_at=now, updated_at=now).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    session.stage = Stage.DONE
    session.closed_at = now
    session.updated_at = now
    return session


def touch_session(session: SessionState, now: Optional[datetime] = None) -> SessionState:
    """Update `updated_at` = now. Gọi sau mỗi message từ dealer/bot.

    Returns session đã updated (mutate in-place).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    session.updated_at = now
    return session
