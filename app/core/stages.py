"""Stage transitions table — forward-only.

Refer:
- F2A.1 (LUAT_2A_core v0.2.4) — Stages + transitions
- D2 STRATEGY — 4 stage forward-only, không cho back
- GLOSSARY § 1 — định nghĩa 4 stage
"""
from __future__ import annotations

from app.models.enums import Stage


# Forward-only transition table — refer F2A.1
# Mỗi key là from_stage, value là set các stage hợp lệ chuyển tới.
STAGE_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.GREETING: {Stage.ASKING, Stage.DONE},       # DONE = greeting_declined path (dealer từ chối greeting)
    Stage.ASKING: {Stage.CONFIRMING, Stage.DONE},     # DONE = timeout / soft-end (escalation L3)
    Stage.CONFIRMING: {Stage.DONE},                   # CONFIRMING → DONE sau confirm/edit/refuse
    Stage.DONE: set(),                                # Terminal — không transition
}


def is_valid_transition(from_stage: Stage, to_stage: Stage) -> bool:
    """Check 1 stage transition có hợp lệ không.

    Refer F2A.1: forward-only, không cho back.

    Args:
        from_stage: Stage hiện tại
        to_stage: Stage muốn chuyển tới

    Returns:
        True nếu transition hợp lệ. False nếu:
        - Backward transition (vd ASKING → GREETING)
        - Self-transition (vd ASKING → ASKING)
        - Từ DONE (terminal)
    """
    if from_stage == to_stage:
        return False                                  # Không self-transition
    return to_stage in STAGE_TRANSITIONS.get(from_stage, set())


def get_allowed_transitions(from_stage: Stage) -> set[Stage]:
    """Trả về set stage hợp lệ từ from_stage. Empty set nếu terminal."""
    return STAGE_TRANSITIONS.get(from_stage, set())
