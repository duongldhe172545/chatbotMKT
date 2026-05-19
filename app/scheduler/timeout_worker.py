"""Background sweep worker — close session timeout + flag stale CONFIRMING.

Refer:
- 1C § 9 — Im lặng kéo dài
- F2A.1 stage logic + F2C.1 lifecycle
- Phase 4 R1

Logic mỗi sweep (default 5 phút):
1. Query DB: session active (stage ∈ {GREETING, ASKING, CONFIRMING}) + closed_at IS NULL
2. Với mỗi session:
   - Gap = now - updated_at
   - Nếu gap >= SESSION_TIMEOUT_S (1h) → soft-close:
       stage = DONE, closed_at = now
       Nếu stage cũ = CONFIRMING → flag CONSENT_UNCLEAR (đề chốt nhưng dealer biến mất)
       Nếu stage cũ ∈ {GREETING, ASKING} → flag REQUIRED_MISSING nếu chưa fill xong
   - Nếu stage = CONFIRMING + gap >= SESSION_TIMEOUT_NUDGE_CARD_S (3 phút) +
     chưa flag nudge_pending → flag NUDGE pending (Phase 4 R2 push qua Zalo)

Note: Phase 4 R1 chỉ implement sweep timeout 1h. Nudge 3 phút defer R2
khi có push channel (HTTP request-response không push được).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.admin.queue import increment_flag_count, trigger_queue_if_needed
from app.config import get_settings
from app.models.enums import ConfirmationStatus, Flag, Stage
from app.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


def sweep_timeouts(store: SQLiteStore) -> dict:
    """Sweep 1 lần — close timeout session + flag.

    Args:
        store: SQLiteStore instance

    Returns:
        {"checked": int, "closed": int, "errors": int} — metrics
    """
    settings = get_settings()
    timeout_s = settings.SESSION_TIMEOUT_S
    now = datetime.now(timezone.utc)
    metrics = {"checked": 0, "closed": 0, "errors": 0}

    # Query active sessions
    with store._connect() as conn:
        cursor = conn.execute(
            "SELECT session_id, stage, updated_at, confirmation_status "
            "FROM sessions WHERE closed_at IS NULL "
            "AND stage IN ('GREETING', 'ASKING', 'CONFIRMING')"
        )
        active_rows = [dict(r) for r in cursor.fetchall()]

    metrics["checked"] = len(active_rows)
    for row in active_rows:
        sid = row["session_id"]
        try:
            updated_at = datetime.fromisoformat(row["updated_at"])
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            gap_s = (now - updated_at).total_seconds()
            if gap_s < timeout_s:
                continue
            # Timeout — load session, set closed + flag
            session = store.get_session(sid)
            if session is None:
                continue
            profile = store.get_profile(sid)
            old_stage = session.stage

            session.stage = Stage.DONE
            session.closed_at = now

            # Flag theo stage cũ
            if old_stage == Stage.CONFIRMING:
                if session.confirmation_status == ConfirmationStatus.PENDING:
                    increment_flag_count(session, Flag.CONSENT_UNCLEAR)
            elif old_stage == Stage.ASKING:
                # Có thể required missing nếu chưa xong slot REQUIRED
                # Lazy: chỉ flag nếu profile thiếu owner_name + phone
                if profile and not (profile.owner_name and profile.phone_or_zalo):
                    increment_flag_count(session, Flag.REQUIRED_MISSING)

            store.save_session(session)
            # Trigger admin queue sau khi save
            if profile:
                trigger_queue_if_needed(session, profile, store)
                store.save_session(session)

            metrics["closed"] += 1
            logger.info(
                "Sweep: closed timeout session=%s old_stage=%s gap_s=%.0f",
                sid, old_stage.value, gap_s,
            )
        except Exception as e:
            metrics["errors"] += 1
            logger.exception("Sweep error session=%s: %s", sid, e)

    if metrics["closed"] > 0 or metrics["errors"] > 0:
        logger.info(
            "Sweep done: checked=%d closed=%d errors=%d",
            metrics["checked"], metrics["closed"], metrics["errors"],
        )
    return metrics


def create_scheduler(store: SQLiteStore) -> BackgroundScheduler:
    """Tạo APScheduler với 1 job sweep_timeouts mỗi N giây.

    Args:
        store: SQLiteStore (passed vào job)

    Returns:
        BackgroundScheduler (chưa start — caller gọi .start()).
    """
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        sweep_timeouts,
        trigger="interval",
        seconds=settings.SCHEDULER_SWEEP_INTERVAL_S,
        args=[store],
        id="session_timeout_sweep",
        name="Sweep session timeout (1h soft-close)",
        max_instances=1,           # Tránh overlap
        coalesce=True,             # Bỏ job miss khi sleep
        misfire_grace_time=60,
    )
    logger.info(
        "Scheduler created: sweep interval=%ds timeout=%ds",
        settings.SCHEDULER_SWEEP_INTERVAL_S, settings.SESSION_TIMEOUT_S,
    )
    return scheduler
