"""Background scheduler — Phase 4 R1.

Refer:
- F2A.1 + F2C.1 — lazy timeout (mỗi request check) → R1 thêm
  proactive sweep mỗi 5 phút (cover case dealer không gửi message
  nhưng session active vượt SESSION_TIMEOUT_S).
- KICH_BAN_1C § 9 — im lặng kéo dài: 1h → soft-close.
- KICH_BAN_1C § 9 sub-rule: stage=CONFIRMING + 3 phút → push nudge
  (Phase 4 R2 wire khi có Zalo channel).
"""
from app.scheduler.timeout_worker import (
    create_scheduler,
    sweep_timeouts,
)

__all__ = ["create_scheduler", "sweep_timeouts"]
