"""Admin queue trigger logic — 13 rule. Refer LUAT_2C § F2C.8.

Mỗi rule = 1 mapping `flag → (priority, min_count)`. Khi flag được
raise (single shot) hoặc count đạt threshold → push entry vào admin_queue.

Pattern dùng:
1. Conversation gọi `increment_flag_count(session, Flag.X)` mỗi lần raise.
2. Sau khi xử reply, gọi `trigger_queue_if_needed(session, profile, store)`.
3. Module check 13 rule → push entry (nếu chưa trigger trong session).
4. Track `session.queue_triggers_fired` để không duplicate.

Refer F2C.8 table:
- HIGH:   escalation L3, sanity_check_failed, hallucinate≥2, pii_leak≥1,
          abusive_language L2, prompt_injection≥3, address_blacklist L2
- MEDIUM: consent_unclear, required_missing, phone_invalid_after_retry,
          brand_not_in_whitelist
- LOW:    multiple_refusal_in_row, voice_quality_poor≥3

KHÔNG trigger (chỉ log):
- garbage_input (bot tự handle qua spam guard)
- dealer_too_defensive (trigger qua escalation thay)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.models.enums import Flag, Priority
from app.models.schema import AdminQueueEntry, DealerProfileRaw, SessionState

if TYPE_CHECKING:
    from app.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriggerRule:
    """1 rule: flag → priority + threshold count."""
    flag: Flag
    priority: Priority
    min_count: int = 1   # default 1 = single-shot trigger


# 13 trigger rule theo F2C.8 (refer LUAT_2C v0.1.5)
QUEUE_TRIGGER_RULES: list[TriggerRule] = [
    # HIGH (7)
    # `escalation` L3 — chưa có Flag riêng, sẽ thêm khi implement R4
    TriggerRule(Flag.SANITY_CHECK_FAILED, Priority.HIGH, min_count=1),
    TriggerRule(Flag.HALLUCINATE, Priority.HIGH, min_count=2),
    TriggerRule(Flag.PII_LEAK, Priority.HIGH, min_count=1),
    TriggerRule(Flag.ABUSIVE_LANGUAGE, Priority.HIGH, min_count=2),
    TriggerRule(Flag.PROMPT_INJECTION, Priority.HIGH, min_count=3),
    TriggerRule(Flag.ADDRESS_BLACKLIST, Priority.HIGH, min_count=1),

    # MEDIUM (4)
    TriggerRule(Flag.CONSENT_UNCLEAR, Priority.MEDIUM, min_count=1),
    TriggerRule(Flag.REQUIRED_MISSING, Priority.MEDIUM, min_count=1),
    TriggerRule(Flag.PHONE_INVALID_AFTER_RETRY, Priority.MEDIUM, min_count=1),
    TriggerRule(Flag.BRAND_NOT_IN_WHITELIST, Priority.MEDIUM, min_count=1),

    # LOW (2)
    TriggerRule(Flag.MULTIPLE_REFUSAL_IN_ROW, Priority.LOW, min_count=1),
    TriggerRule(Flag.VOICE_QUALITY_POOR, Priority.LOW, min_count=3),
]

# Flag KHÔNG trigger queue (chỉ log) — refer F2C.8 note
NON_TRIGGER_FLAGS: set[Flag] = {
    Flag.GARBAGE_INPUT,
    Flag.DEALER_TOO_DEFENSIVE,
}


def increment_flag_count(session: SessionState, flag: Flag) -> int:
    """Tăng counter cho 1 flag + append vào flags list (nếu chưa có).

    Args:
        session: SessionState
        flag: Flag cần raise

    Returns:
        Count sau khi tăng.
    """
    key = flag.value
    current = session.flag_counts.get(key, 0)
    new_count = current + 1
    session.flag_counts[key] = new_count
    if flag not in session.flags:
        session.flags.append(flag)
    return new_count


def trigger_queue_if_needed(
    session: SessionState,
    profile: DealerProfileRaw,
    store: "SQLiteStore",
) -> list[str]:
    """Check 13 rule + push admin_queue entry nếu match.

    Args:
        session: SessionState (mutate `queue_triggers_fired`)
        profile: DealerProfileRaw (snapshot lúc trigger)
        store: SQLiteStore để push entry

    Returns:
        List trigger name vừa fire (có thể empty).
    """
    fired: list[str] = []

    for rule in QUEUE_TRIGGER_RULES:
        flag_name = rule.flag.value
        # Skip nếu trigger đã fire trong session
        if flag_name in session.queue_triggers_fired:
            continue
        # Check threshold
        count = session.flag_counts.get(flag_name, 0)
        if count >= rule.min_count:
            _push_queue_entry(session, profile, rule, store)
            session.queue_triggers_fired.append(flag_name)
            fired.append(flag_name)
            logger.info(
                "Admin queue triggered: session=%s flag=%s priority=%s count=%d",
                session.session_id, flag_name, rule.priority.value, count,
            )

    return fired


def _push_queue_entry(
    session: SessionState,
    profile: DealerProfileRaw,
    rule: TriggerRule,
    store: "SQLiteStore",
) -> None:
    """Tạo + push 1 AdminQueueEntry vào DB."""
    try:
        entry = AdminQueueEntry(
            queue_id=str(uuid.uuid4()),
            session_id=session.session_id,
            trigger=rule.flag,
            priority=rule.priority,
            profile_snapshot=profile.model_copy(deep=True),
            created_at=datetime.now(timezone.utc),
        )
        store.push_admin_queue(entry)
    except Exception as e:
        # Không raise — admin queue lỗi không nên block conversation
        logger.exception(
            "Push admin queue FAIL session=%s flag=%s: %s",
            session.session_id, rule.flag.value, e,
        )


def get_priority_for_flag(flag: Flag) -> Optional[Priority]:
    """Convenience: trả priority của flag (nếu có rule). None nếu KHÔNG trigger."""
    for rule in QUEUE_TRIGGER_RULES:
        if rule.flag == flag:
            return rule.priority
    return None
