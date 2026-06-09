"""Workflow engine — compute suggested objective from profile state.

Replaces legacy state_machine.decide_action() with a declarative,
Parlant-style objective system. Instead of returning (next_slot, action),
the workflow engine returns a suggested_objective dict that tells the
agent what to do next.

Objectives:
- collect_required_field: ask for a missing required field
- collect_optional_field: ask for a missing optional field
- resolve_blocking_flag: address a safety/quality flag
- show_profile_review: all required fields filled, show review card
- show_logo_brief: profile confirmed, prepare logo brief
- zalo_handoff: logo done, offer Zalo group
- continue_conversation: no specific objective
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Required fields in priority order (from legacy SLOT_PRIORITY_ORDER mapping)
REQUIRED_FIELDS_PRIORITY = [
    ("owner_name", "tên anh/chị"),
    ("dealer_name", "tên xưởng/cửa hàng"),
    ("address", "địa chỉ hoặc khu vực"),
    ("phone_or_zalo", "số điện thoại/Zalo"),
    ("main_product", "sản phẩm chính"),
    ("business_model_signal", "loại hình kinh doanh"),
]

# Optional fields in priority order (from 2.3 to 3.5, and 4.2)
OPTIONAL_FIELDS_PRIORITY = [
    ("est_team_size", "quy mô đội thợ", "quy mô đội thợ"),
    ("supplier_brands", "nhãn hiệu nhà cung cấp", "nhãn hiệu nhà cung cấp"),
    ("primary_contact_channel", "kênh liên hệ chính", "kênh liên hệ chính"),
    ("facebook", "kênh Facebook của xưởng", "kênh Facebook của xưởng"),
    ("customer_old_percentage", "tỷ lệ khách hàng cũ giới thiệu", "tỷ lệ khách hàng cũ giới thiệu"),
    ("customer_storage_method", "phương pháp lưu trữ danh sách khách", "phương pháp lưu trữ danh sách khách"),
    ("customer_pain", "khó khăn/vướng mắc chính của khách hàng", "khó khăn/vướng mắc chính của khách hàng"),
    ("payment_terms_signal", "quy trình đặt cọc/thanh toán", "quy trình đặt cọc/thanh toán"),
    ("warranty_responsibility_signal", "trách nhiệm bảo hành", "trách nhiệm bảo hành"),
]


class WorkflowEngine:
    """Compute the next suggested objective for a conversation turn."""

    def compute_objective(
        self,
        *,
        profile_snapshot: dict[str, Any],
        observations: dict[str, Any],
        turn_count: int = 0,
    ) -> dict[str, Any]:
        """Determine what the agent should focus on this turn.

        Priority order:
        1. Resolve blocking flags (safety first)
        2. Collect missing required fields
        3. Collect missing optional fields (if real snapshot)
        4. Show profile review card
        5. Show logo brief
        6. Zalo handoff
        7. Continue conversation
        """
        # 1. Check blocking flags
        blocking = profile_snapshot.get("blocking_flags", [])
        if blocking:
            flag = blocking[0]
            return {
                "type": "resolve_blocking_flag",
                "target_flag": flag,
                "target_field": None,
                "prompt_hint": f"Flag: {flag}",
            }

        # 2. Check missing required fields
        missing = profile_snapshot.get("missing_required_fields", [])
        if missing:
            # Find first missing field in priority order
            for field_name, label in REQUIRED_FIELDS_PRIORITY:
                if field_name in missing:
                    return {
                        "type": "collect_required_field",
                        "target_field": field_name,
                        "target_field_label": label,
                        "prompt_hint": label,
                    }
            # Fallback: first missing field
            field = missing[0]
            return {
                "type": "collect_required_field",
                "target_field": field,
                "target_field_label": field,
                "prompt_hint": field,
            }

        # 3. Check optional and design fields if all_fields is in snapshot
        all_fields = profile_snapshot.get("all_fields")
        skipped = profile_snapshot.get("skipped_fields", [])
        if all_fields is not None:
            # Check optional fields (up to 3.5)
            for field_name, label, hint in OPTIONAL_FIELDS_PRIORITY:
                if field_name not in all_fields and field_name not in skipped:
                    return {
                        "type": "collect_optional_field",
                        "target_field": field_name,
                        "target_field_label": label,
                        "prompt_hint": hint,
                    }

            # Check brandkit_consent (Slot 4.0)
            if "brandkit_consent" not in all_fields and "brandkit_consent" not in skipped:
                return {
                    "type": "collect_required_field",
                    "target_field": "brandkit_consent",
                    "target_field_label": "đồng ý nhận bộ thương hiệu",
                    "prompt_hint": "đồng ý nhận bộ thương hiệu",
                }

            # Check color_accent (Slot 4.2)
            consent_val = all_fields.get("brandkit_consent")
            if consent_val == "yes" or consent_val is True:
                if "color_accent" not in all_fields and "color_accent" not in skipped:
                    return {
                        "type": "collect_optional_field",
                        "target_field": "color_accent",
                        "target_field_label": "màu chủ đạo phong thủy",
                        "prompt_hint": "màu chủ đạo phong thủy",
                    }

        # 4. Check if profile needs review
        review_status = profile_snapshot.get("review_status", "DRAFT")
        if review_status == "DRAFT":
            return {
                "type": "show_profile_review",
                "target_field": None,
                "prompt_hint": "Show profile review card",
            }

        # 5. Check if logo brief needed
        logo_status = profile_snapshot.get("logo_issued_status", "NONE")
        if review_status == "CONFIRMED" and logo_status == "NONE":
            return {
                "type": "show_logo_brief",
                "target_field": None,
                "prompt_hint": "Show logo brief",
            }

        # 6. Check if Zalo handoff
        if logo_status in ("ISSUED", "BLOCKED_DUPLICATE"):
            return {
                "type": "zalo_handoff",
                "target_field": None,
                "prompt_hint": "Offer Zalo group",
            }

        # 7. Default: continue
        return {
            "type": "continue_conversation",
            "target_field": None,
            "prompt_hint": "Continue natural conversation",
        }

    def compute_workflow_state(
        self, profile_snapshot: dict[str, Any]
    ) -> str:
        """Compute workflow state string from profile snapshot.

        Maps to the workflow_state column in sessions table.
        """
        logo_status = profile_snapshot.get("logo_issued_status", "NONE")
        if logo_status == "BLOCKED_DUPLICATE":
            return "ESCALATED"

        blocking = profile_snapshot.get("blocking_flags", [])
        
        # Check if we are still asking fields (required or optional)
        all_fields = profile_snapshot.get("all_fields")
        if all_fields is not None:
            missing = profile_snapshot.get("missing_required_fields", [])
            skipped = profile_snapshot.get("skipped_fields", [])
            
            # Check optional fields (up to 3.5)
            has_missing_optional = False
            for f_name, _, _ in OPTIONAL_FIELDS_PRIORITY:
                if f_name not in all_fields and f_name not in skipped:
                    has_missing_optional = True
                    break
            
            # Check brandkit_consent (Slot 4.0)
            has_missing_consent = "brandkit_consent" not in all_fields and "brandkit_consent" not in skipped
            
            # Check color_accent (Slot 4.2)
            has_missing_color = False
            if all_fields.get("brandkit_consent") == "yes" or all_fields.get("brandkit_consent") is True:
                if "color_accent" not in all_fields and "color_accent" not in skipped:
                    has_missing_color = True

            if blocking or missing or has_missing_optional or has_missing_consent or has_missing_color:
                return "WAITING_REQUIRED_FIELD"
        else:
            missing = profile_snapshot.get("missing_required_fields", [])
            if blocking or missing:
                return "WAITING_REQUIRED_FIELD"

        review_status = profile_snapshot.get("review_status", "DRAFT")
        if review_status == "DRAFT":
            return "READY_FOR_REVIEW"

        if review_status == "CONFIRMED" and logo_status == "NONE":
            return "LOGO_PENDING"

        if logo_status == "ISSUED":
            return "LOGO_READY"

        return "CONFIRMED"
