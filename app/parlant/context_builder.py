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

        # Build collection status block (chống LLM tự chốt sớm khi còn slot pending)
        collection_status = _build_collection_status(profile_snapshot)

        # Build guideline instructions
        guideline_instructions = [
            {"id": g["id"], "action": g["action"]}
            for g in matched_guidelines
        ]

        # Determine current task — báo cho task biết SĐT vừa nhập không hợp lệ (10.1)
        phone_invalid = "phone_invalid_after_retry" in profile_snapshot.get("open_flags", [])
        task = _task_from_objective(suggested_objective, address_form, phone_invalid=phone_invalid)

        return {
            # Core
            "profile_snapshot": profile_snapshot,
            "suggested_objective": suggested_objective,
            "observations": observations,
            "matched_guidelines": guideline_instructions,

            # Conversation
            "history_summary": history_summary,
            "recent_messages": recent_messages[-30:],  # last 30 messages (15 turns)
            "collection_status": collection_status,

            # Agent hints
            "address_form": address_form,
            "dealer_type": dealer_type,
            "task": task,
            "missing_fields": missing,

            # Canned responses
            "canned_candidates": canned_candidates or [],
        }


def _build_collection_status(profile_snapshot: dict[str, Any]) -> str:
    """Build bảng trạng thái thu thập cho prompt — LLM phải thấy slot nào còn pending.

    Fix bug "xong logo là ngừng hỏi": LLM không biết còn field chưa thu nên
    tự chốt + gửi link Zalo sau khi bàn xong màu logo (slot cuối).
    Dùng chung priority order với WorkflowEngine để 2 bên không lệch nhau.
    """
    from app.parlant.workflow_engine import (
        OPTIONAL_FIELDS_PRIORITY,
        REQUIRED_FIELDS_PRIORITY,
        optional_satisfied,
    )

    all_fields = profile_snapshot.get("all_fields") or {}
    skipped = profile_snapshot.get("skipped_fields", [])
    missing_required = profile_snapshot.get("missing_required_fields", [])

    filled = [name for name in all_fields if all_fields.get(name)]

    pending: list[str] = []
    for field_name, label in REQUIRED_FIELDS_PRIORITY:
        if field_name in missing_required:
            pending.append(f"{label} (BẮT BUỘC)")
    for field_name, label, _hint in OPTIONAL_FIELDS_PRIORITY:
        if not optional_satisfied(field_name, all_fields, skipped):
            pending.append(label)
    if "brandkit_consent" not in all_fields and "brandkit_consent" not in skipped:
        pending.append("đồng ý nhận bộ thương hiệu (BẮT BUỘC)")
    consent_val = all_fields.get("brandkit_consent")
    if consent_val == "yes" or consent_val is True:
        if all_fields.get("logo_existing_intent") == "unclarified":
            pending.append("nhu cầu với logo hiện có (nâng cấp / thiết kế lại / làm mới)")
        if "color_accent" not in all_fields and "color_accent" not in skipped:
            pending.append("màu chủ đạo phong thủy")
        if "logo_style" not in all_fields and "logo_style" not in skipped:
            pending.append("phong cách logo")
        if "slogan_preference" not in all_fields and "slogan_preference" not in skipped:
            pending.append("slogan")

    lines = [
        f"- Đã thu: {', '.join(filled) if filled else '(chưa có)'}",
        f"- Đã bỏ qua (dealer từ chối/không biết): {', '.join(skipped) if skipped else '(không có)'}",
    ]
    if pending:
        lines.append(f"- Còn phải hỏi (theo thứ tự): {' → '.join(pending)}")
        lines.append("- Còn mục chưa thu ở trên → tiếp tục hỏi cho hết rồi mới chốt.")
    else:
        lines.append("- Đã thu xong toàn bộ thông tin cần hỏi.")
    return "\n".join(lines)


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
    objective: dict[str, Any], address_form: str, phone_invalid: bool = False
) -> str:
    """Convert suggested objective to a task instruction for the agent."""
    obj_type = objective.get("type", "continue_conversation")

    if obj_type in ("collect_required_field", "collect_optional_field"):
        field = objective.get("target_field", "")
        hint = objective.get("prompt_hint", field)
        # 10.1: SĐT khách vừa đưa KHÔNG hợp lệ → báo rõ cho LLM xin lại, cấm "đã ghi nhận"
        # (nếu không LLM tưởng số hợp lệ → nói "đã ghi nhận" rồi lảng sang việc khác).
        if field == "phone_or_zalo" and phone_invalid:
            return (
                f"SĐT {address_form} vừa đưa CHƯA hợp lệ (cần 10-11 chữ số, bắt đầu bằng 0). "
                f"Báo nhẹ là số chưa đúng rồi xin lại đúng SĐT/Zalo. "
                "TUYỆT ĐỐI KHÔNG nói 'đã ghi nhận/đã lưu số', KHÔNG hỏi sang việc khác."
            )
        return (
            f"Hoi {address_form} ve: {hint}. "
            f"Phan hoi tu nhien dieu {address_form} vua noi (neu ngan ly do hoi neu hop) roi hoi."
        )

    if obj_type == "resolve_blocking_flag":
        flag = objective.get("target_flag", "")
        return (
            f"Co flag can giai quyet: {flag}. "
            f"Tran an {address_form} + yeu cau bo sung thong tin an toan."
        )

    if obj_type == "show_profile_review":
        return (
            f"Du thong tin roi. Moi {address_form} xem lai ho so va xac nhan. "
            "CHỈ mời xem lại + xác nhận — CHƯA gửi link Zalo, CHƯA nói 'đã xong/đủ "
            f"thông tin', CHƯA chào kết thúc (việc đó để bước bàn giao SAU khi {address_form} đã duyệt)."
        )

    if obj_type == "show_logo_brief":
        return f"Ho so xac nhan. Gui brief logo de {address_form} duyet."

    if obj_type == "zalo_handoff":
        from app.core.config_v2 import get_settings
        settings = get_settings()
        zalo_url = settings.zalo_group_url
        if zalo_url:
            link_part = (
                f"Mời {address_form} BẤM VÀO ĐÚNG link nhóm Zalo này để gặp đội ngũ "
                f"và nhận bộ thương hiệu miễn phí: {zalo_url}. "
                "TUYỆT ĐỐI chỉ dùng link này — KHÔNG dùng số điện thoại của khách, "
                "KHÔNG bảo khách 'kết bạn theo số', KHÔNG bịa số/link nào khác."
            )
        else:
            link_part = (
                f"Báo {address_form} rằng đội ngũ sẽ chủ động kết nối lại để gửi bộ "
                "thương hiệu. TUYỆT ĐỐI KHÔNG bịa số điện thoại hay link Zalo, "
                "KHÔNG dùng số điện thoại của khách làm Zalo."
            )
        return (
            f"Hồ sơ đã được xác nhận hoàn toàn. Không cần gen logo / trả logo. "
            f"Hãy cảm ơn và chúc {address_form} kinh doanh phát đạt, chốt được nhiều "
            f"công trình. " + link_part
        )

    return f"Tiep tuc tro chuyen tu nhien voi {address_form}."
