"""Context builder — assemble rich context for the agent.

Parlant concept: Before generating a reply, the system assembles a
"context" dict containing everything the agent needs:
- Profile snapshot (what we know about the dealer)
- Suggested objective (what we need next)
- Matched guidelines (rules to follow)
- Observations (behavioral signals)
- Conversation history (recent messages)
- Canned response candidates (if any)

This context dict is passed to the AgentReplyGenerator.
"""
from __future__ import annotations

import json
from typing import Any


class ContextBuilder:
    """Assembles context dict for agent reply generation."""

    def build(
        self,
        *,
        profile_snapshot: dict[str, Any],
        suggested_objective: dict[str, Any],
        observations: dict[str, Any],
        matched_guidelines: list[dict[str, Any]],
        recent_messages: list[dict[str, Any]],
        canned_candidates: list[dict[str, Any]] | None = None,
        address_form: str = "anh",
        dealer_type: str = "unknown",
    ) -> dict[str, Any]:
        """Build the full context dict.

        Returns a dict suitable for:
        1. System prompt construction
        2. Agent reply generation
        3. Turn trace logging
        """
        # Build history summary (last 15 turns)
        history_summary = _build_history_summary(recent_messages, limit=15)

        # Build missing fields list
        missing = profile_snapshot.get("missing_required_fields", [])

        # Build guideline instructions
        guideline_instructions = [
            {"id": g["id"], "action": g["action"]}
            for g in matched_guidelines
        ]

        # Determine current task
        task = _task_from_objective(suggested_objective, address_form)

        return {
            # Core
            "profile_snapshot": profile_snapshot,
            "suggested_objective": suggested_objective,
            "observations": observations,
            "matched_guidelines": guideline_instructions,

            # Conversation
            "history_summary": history_summary,
            "recent_messages": recent_messages[-30:],  # last 30 messages (15 turns)

            # Agent hints
            "address_form": address_form,
            "dealer_type": dealer_type,
            "task": task,
            "missing_fields": missing,

            # Canned responses
            "canned_candidates": canned_candidates or [],
        }


def _build_history_summary(
    messages: list[dict[str, Any]], limit: int = 15
) -> str:
    """Build a compact history summary from recent messages."""
    if not messages:
        return "(chua co)"

    lines = []
    for msg in messages[-limit:]:
        source = msg.get("source", "?")
        text = msg.get("text", "")
        if text:
            # Truncate long messages
            display = text[:80] + "..." if len(text) > 80 else text
            label = "Dealer" if source == "user" else "Em Linh"
            lines.append(f"- {label}: {display}")

    return "\n".join(lines) if lines else "(chua co)"


def _task_from_objective(
    objective: dict[str, Any], address_form: str
) -> str:
    """Convert suggested objective to a task instruction for the agent."""
    obj_type = objective.get("type", "continue_conversation")

    if obj_type in ("collect_required_field", "collect_optional_field"):
        field = objective.get("target_field", "")
        hint = objective.get("prompt_hint", field)
        return (
            f"Hoi {address_form} thong tin: {hint}. "
            f"Ack cu the chi tiet {address_form} vua cho + giai thich ly do hoi + dat 1 cau hoi."
        )

    if obj_type == "resolve_blocking_flag":
        flag = objective.get("target_flag", "")
        return (
            f"Co flag can giai quyet: {flag}. "
            f"Tran an {address_form} + yeu cau bo sung thong tin an toan."
        )

    if obj_type == "show_profile_review":
        return (
            f"Du thong tin roi. Moi {address_form} xem lai ho so va bam xac nhan."
        )

    if obj_type == "show_logo_brief":
        return f"Ho so xac nhan. Gui brief logo de {address_form} duyet."

    if obj_type == "zalo_handoff":
        from app.core.config_v2 import get_settings
        settings = get_settings()
        zalo_url = settings.zalo_group_url or "[Link Zalo Cộng Đồng Thợ 4.0]"
        return (
            f"Ho so da duoc xac nhan hoan toan. Khong can gen logo/tra logo. "
            f"Hay cam on va chuc {address_form} kinh doanh phat dat, chot duoc nhieu cong trinh. "
            f"Huong dan {address_form} bam vao link Zalo sau de gap doi ngu va nhan bo thuong hieu mien phi: {zalo_url}."
        )

    return f"Tiep tuc tro chuyen tu nhien voi {address_form}."
