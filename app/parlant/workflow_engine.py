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

# Optional fields in priority order (slot 2.3 → 3.5).
# prompt_hint (phần tử 3) được bơm vào câu hỏi LLM — đã chỉnh để gặng ĐÚNG
# tín hiệu rubric C1-C9 (P4 audit 2026-06-10). Mỗi hint = 1 câu hỏi tự nhiên
# (1 ý chính + 1 vế phụ cùng chủ đề), KHÔNG phải 2 field rời.
OPTIONAL_FIELDS_PRIORITY = [
    # Fix 2026-06-11: MỖI hint = ĐÚNG 1 câu hỏi (trước gộp 2 vế "X — và Y" gây
    # khó chịu). Tín hiệu phụ (đàm phán C8, mạng lưới C9, ổn định C3...) vẫn bắt
    # được nếu khách tự nhắc (luật extractor), KHÔNG hỏi dồn.
    ("est_team_size", "quy mô đội thợ",
     "đội thợ mình hiện có khoảng mấy người ạ"),  # C3
    ("supplier_brands", "nhà cung cấp chính",
     "anh nhập hàng (nhôm / phụ kiện) chủ yếu từ hãng nào ạ"),  # C8
    ("primary_contact_channel", "kênh liên hệ chính",
     "khách hay liên hệ với mình qua kênh nào nhất ạ (Zalo / gọi điện / Facebook)"),
    ("facebook", "Facebook",
     "cửa hàng mình đã có trang Facebook / Fanpage riêng chưa ạ"),  # C9
    ("customer_old_percentage", "tỷ lệ khách cũ giới thiệu",
     "khách cũ quay lại hoặc giới thiệu khách mới chiếm khoảng bao nhiêu % tổng đơn ạ"),  # C1
    ("local_dominance_signal", "độ phủ địa bàn",
     "khách quanh khu mình có hay tự tìm tới / gọi anh đầu tiên không, hay phải chạy quảng cáo mới có ạ"),  # C6
    ("customer_storage_method", "cách lưu thông tin khách",
     "danh sách khách mình đang lưu ở đâu ạ (sổ / Zalo / Excel / phần mềm)"),  # C7
    ("customer_pain", "điều mong cải thiện",
     "điều anh mong muốn cải thiện nhất cho cửa hàng trong thời gian tới là gì ạ"),  # C5
    ("payment_terms_signal", "tự chủ vốn (ký gửi / mua đứt)",
     "hàng nhập anh chủ yếu mua đứt hay được nhà cung cấp cho ký gửi / công nợ ạ"),  # C2
    ("warranty_responsibility_signal", "trách nhiệm bảo hành",
     "khi sản phẩm lỗi sau lắp, bên mình đứng ra xử và chịu chi phí hay đẩy về nhà cung cấp ạ"),  # C4
]

# A (fix 2026-06-11): 1 optional coi là XONG nếu field chính HOẶC 1 field anh em
# (signal) của slot đã được điền. Trước đây chỉ check field chính → khi câu trả
# lời rơi vào signal field (vd "thêm khách" → motivation_signal thay customer_pain,
# hay nguồn khách → local_dominance_signal thay customer_old_percentage), field
# chính mãi rỗng → workflow KẸT vĩnh viễn, không tới được review/handoff.
_OPTIONAL_SIBLINGS: dict[str, list[str]] = {
    "est_team_size": ["team_stability_signal"],
    "supplier_brands": ["supplier_negotiation_signal"],
    "facebook": ["community_network_signal", "fb_marketing_status"],
    "customer_pain": ["motivation_signal", "usp_signal"],
}
# Lưu ý: local_dominance_signal (C6) giờ là câu hỏi RIÊNG trong
# OPTIONAL_FIELDS_PRIORITY — không còn là sibling của customer_old_percentage.


def optional_satisfied(field: str, all_fields: dict[str, Any], skipped: list[str]) -> bool:
    """True nếu optional probe coi như đã xử lý: field chính đã điền/đã skip,
    HOẶC 1 field anh em (signal) cùng slot đã điền."""
    if field in all_fields or field in skipped:
        return True
    return any(sib in all_fields for sib in _OPTIONAL_SIBLINGS.get(field, []))


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
            # Check optional fields (up to 3.5) — slot coi như xong nếu field
            # chính HOẶC field anh em (signal) đã có (A fix).
            for field_name, label, hint in OPTIONAL_FIELDS_PRIORITY:
                if not optional_satisfied(field_name, all_fields, skipped):
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

            consent_val = all_fields.get("brandkit_consent")
            if consent_val == "yes" or consent_val is True:
                # Dealer đã có logo nhưng chưa rõ nhu cầu → hỏi ngược TRƯỚC màu
                # (feedback 2026-06-10: không tự kết luận thay dealer)
                if (
                    all_fields.get("logo_existing_intent") == "unclarified"
                    and "logo_existing_intent" not in skipped
                ):
                    return {
                        "type": "collect_optional_field",
                        "target_field": "logo_existing_intent",
                        "target_field_label": "nhu cầu với logo hiện có",
                        "prompt_hint": (
                            "dealer đã có logo — hỏi nhu cầu thật với 3 lựa chọn: "
                            "nâng cấp/tinh chỉnh logo cũ, thiết kế lại bố cục/màu, "
                            "hay làm mới hoàn toàn"
                        ),
                    }

                # Check color_accent (Slot 4.2)
                if "color_accent" not in all_fields and "color_accent" not in skipped:
                    return {
                        "type": "collect_optional_field",
                        "target_field": "color_accent",
                        "target_field_label": "màu chủ đạo phong thủy",
                        "prompt_hint": "màu chủ đạo phong thủy",
                    }

                # P4.4 — brandkit thu thêm phong cách + slogan (OPTIONAL, như màu).
                if "logo_style" not in all_fields and "logo_style" not in skipped:
                    return {
                        "type": "collect_optional_field",
                        "target_field": "logo_style",
                        "target_field_label": "phong cách logo",
                        "prompt_hint": (
                            "phong cách logo anh thích (hiện đại / mạnh mẽ / tối giản / "
                            "sang trọng...) — nếu chưa rõ thì để em chọn theo ngành cho hợp"
                        ),
                    }
                if "slogan_preference" not in all_fields and "slogan_preference" not in skipped:
                    return {
                        "type": "collect_optional_field",
                        "target_field": "slogan_preference",
                        "target_field_label": "slogan",
                        "prompt_hint": (
                            "anh có sẵn slogan hay câu tâm đắc cho thương hiệu không, "
                            "hay để em đề xuất vài câu rồi anh chọn"
                        ),
                    }

        # 4. Check if profile needs review
        review_status = profile_snapshot.get("review_status", "DRAFT")
        if review_status == "DRAFT":
            return {
                "type": "show_profile_review",
                "target_field": None,
                "prompt_hint": "Show profile review card",
            }

        # 5. Check if Zalo handoff
        if review_status == "CONFIRMED":
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
            
            # Check optional fields (up to 3.5) — slot-level satisfied (A fix)
            has_missing_optional = False
            for f_name, _, _ in OPTIONAL_FIELDS_PRIORITY:
                if not optional_satisfied(f_name, all_fields, skipped):
                    has_missing_optional = True
                    break
            
            # Check brandkit_consent (Slot 4.0)
            has_missing_consent = "brandkit_consent" not in all_fields and "brandkit_consent" not in skipped
            
            # Check color_accent (Slot 4.2) + logo_existing_intent chưa rõ
            # + brandkit phụ (phong cách / slogan — P4.4)
            has_missing_color = False
            has_unclarified_logo = False
            has_missing_brandkit_extra = False
            if all_fields.get("brandkit_consent") == "yes" or all_fields.get("brandkit_consent") is True:
                if "color_accent" not in all_fields and "color_accent" not in skipped:
                    has_missing_color = True
                if (
                    all_fields.get("logo_existing_intent") == "unclarified"
                    and "logo_existing_intent" not in skipped
                ):
                    has_unclarified_logo = True
                for _bk in ("logo_style", "slogan_preference"):
                    if _bk not in all_fields and _bk not in skipped:
                        has_missing_brandkit_extra = True

            if (
                blocking or missing or has_missing_optional or has_missing_consent
                or has_missing_color or has_unclarified_logo or has_missing_brandkit_extra
            ):
                return "WAITING_REQUIRED_FIELD"
        else:
            missing = profile_snapshot.get("missing_required_fields", [])
            if blocking or missing:
                return "WAITING_REQUIRED_FIELD"

        review_status = profile_snapshot.get("review_status", "DRAFT")
        if review_status == "DRAFT":
            return "READY_FOR_REVIEW"

        return "CONFIRMED"
