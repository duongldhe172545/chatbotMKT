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
from dataclasses import dataclass
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
#
# PHÂN LOẠI (9.4 — 2026-06-17): danh sách = 9 TIÊU CHÍ C1-C9 (mỗi field có nhãn # Cx)
# + 1 FIELD PHỤ `primary_contact_channel` (KHÔNG có nhãn C — không thuộc bộ chấm
# điểm, chỉ là tín hiệu vận hành). Đừng gộp field phụ vào "rubric C1-C9".
OPTIONAL_FIELDS_PRIORITY = [
    # Fix 2026-06-11: MỖI hint = ĐÚNG 1 câu hỏi (trước gộp 2 vế "X — và Y" gây
    # khó chịu). Tín hiệu phụ (đàm phán C8, mạng lưới C9, ổn định C3...) vẫn bắt
    # được nếu khách tự nhắc (luật extractor), KHÔNG hỏi dồn.
    ("est_team_size", "quy mô đội thợ",
     "đội thợ mình hiện có khoảng mấy người ạ"),  # C3
    ("supplier_brands", "nhà cung cấp chính",
     "anh nhập hàng (nhôm / phụ kiện) chủ yếu từ hãng nào ạ"),  # C8
    ("primary_contact_channel", "kênh liên hệ chính",  # FIELD PHỤ (không phải tiêu chí C)
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


@dataclass
class PendingStep:
    """1 bước còn phải thu thập. Nguồn dữ liệu chung cho compute_objective /
    compute_workflow_state / _build_collection_status (tránh sync tay 3 nơi)."""

    objective_type: str           # collect_required_field | collect_optional_field
    target_field: str
    label: str                    # target_field_label
    prompt_hint: str
    is_required: bool = False
    display_label: str | None = None  # override cho list "Còn phải hỏi" (nếu khác label)

    def to_objective(self) -> dict[str, Any]:
        return {
            "type": self.objective_type,
            "target_field": self.target_field,
            "target_field_label": self.label,
            "prompt_hint": self.prompt_hint,
        }

    def status_label(self) -> str:
        """Nhãn hiển thị trong TRẠNG THÁI THU THẬP (prompt LLM)."""
        if self.display_label is not None:
            return self.display_label
        return f"{self.label} (BẮT BUỘC)" if self.is_required else self.label


def iter_pending_steps(profile_snapshot: dict[str, Any]) -> list[PendingStep]:
    """NGUỒN DUY NHẤT cho thứ tự thu thập. KHÔNG gồm blocking flag (xử lý riêng,
    ưu tiên cao hơn).

    Thứ tự (9.4 reorder 2026-06-17 — brandkit-first):
      1. required (6 field cơ bản)
      2. BRANDKIT: brandkit_consent → (nếu yes) logo_existing_intent / màu / phong cách / slogan
      3. TƯ VẤN (bonus, sau brandkit): 9 tiêu chí C1-C9 + 1 field PHỤ primary_contact_channel
    consent=no/skip → khối brandkit không sinh step phụ → rơi thẳng xuống tư vấn (C1-C9).
    Khách đổi ý (consent no→yes) → khối brandkit tự hiện lại (tính mỗi lượt từ snapshot)."""
    steps: list[PendingStep] = []

    # 1. Required fields (theo priority)
    missing = profile_snapshot.get("missing_required_fields", [])
    for field_name, label in REQUIRED_FIELDS_PRIORITY:
        if field_name in missing:
            steps.append(PendingStep("collect_required_field", field_name, label, label, is_required=True))
    known_required = {f for f, _ in REQUIRED_FIELDS_PRIORITY}
    for field_name in missing:  # an toàn: missing lạ ngoài priority (thực tế không xảy ra)
        if field_name not in known_required:
            steps.append(PendingStep("collect_required_field", field_name, field_name, field_name, is_required=True))

    all_fields = profile_snapshot.get("all_fields")
    skipped = profile_snapshot.get("skipped_fields", [])
    if all_fields is None:
        return steps

    # 2. BRANDKIT (đảo LÊN TRƯỚC tư vấn) — brandkit_consent (Slot 4.0)
    if "brandkit_consent" not in all_fields and "brandkit_consent" not in skipped:
        steps.append(PendingStep(
            "collect_required_field", "brandkit_consent",
            "đồng ý nhận bộ thương hiệu", "đồng ý nhận bộ thương hiệu", is_required=True,
        ))

    consent_val = all_fields.get("brandkit_consent")
    if consent_val == "yes" or consent_val is True:
        brandkit_sub: list[PendingStep] = []
        # Dealer đã có logo nhưng chưa rõ nhu cầu → hỏi ngược TRƯỚC màu
        if (
            all_fields.get("logo_existing_intent") == "unclarified"
            and "logo_existing_intent" not in skipped
        ):
            brandkit_sub.append(PendingStep(
                "collect_optional_field", "logo_existing_intent", "nhu cầu với logo hiện có",
                (
                    "dealer đã có logo — hỏi nhu cầu thật với 3 lựa chọn: "
                    "nâng cấp/tinh chỉnh logo cũ, thiết kế lại bố cục/màu, "
                    "hay làm mới hoàn toàn"
                ),
                display_label="nhu cầu với logo hiện có (nâng cấp / thiết kế lại / làm mới)",
            ))
        if "color_accent" not in all_fields and "color_accent" not in skipped:
            brandkit_sub.append(PendingStep(
                "collect_optional_field", "color_accent",
                "màu chủ đạo phong thủy", "màu chủ đạo phong thủy",
            ))
        if "logo_style" not in all_fields and "logo_style" not in skipped:
            brandkit_sub.append(PendingStep(
                "collect_optional_field", "logo_style", "phong cách logo",
                (
                    "phong cách logo anh thích (hiện đại / mạnh mẽ / tối giản / "
                    "sang trọng...) — nếu chưa rõ thì để em chọn theo ngành cho hợp"
                ),
            ))
        if "slogan_preference" not in all_fields and "slogan_preference" not in skipped:
            brandkit_sub.append(PendingStep(
                "collect_optional_field", "slogan_preference", "slogan",
                (
                    "anh có sẵn slogan hay câu tâm đắc cho thương hiệu không, "
                    "hay để em đề xuất vài câu rồi anh chọn"
                ),
            ))
        steps.extend(brandkit_sub)

        # 9.4b — Sau khi xong màu/phong cách/slogan → SHOW MẪU THAM KHẢO (1 lần).
        # Gate bằng marker brandkit_preview_shown (set sau khi đã show).
        if not brandkit_sub and not (
            "brandkit_preview_shown" in all_fields or "brandkit_preview_shown" in skipped
        ):
            steps.append(PendingStep(
                "show_brandkit_preview", "brandkit_preview", "xem mẫu tham khảo",
                "trình vài mẫu logo + danh thiếp tham khảo khớp phong cách/màu",
                display_label="xem mẫu tham khảo",
            ))

    # 3. TƯ VẤN bonus (SAU brandkit): 9 tiêu chí C1-C9 + 1 field phụ — slot-level satisfied (A fix)
    for field_name, label, hint in OPTIONAL_FIELDS_PRIORITY:
        if not optional_satisfied(field_name, all_fields, skipped):
            steps.append(PendingStep("collect_optional_field", field_name, label, hint))

    return steps


# Field thuộc giai đoạn TƯ VẤN bonus (C1-C9 + phụ) — KHÔNG gồm required/brandkit.
_CONSULTATION_FIELDS = {f for f, _l, _h in OPTIONAL_FIELDS_PRIORITY}


def pending_consultation_fields(profile_snapshot: dict[str, Any]) -> list[str]:
    """Các field tư vấn (C1-C9 + phụ) còn PENDING — để bỏ qua nốt khi khách 'đủ rồi'."""
    return [
        s.target_field
        for s in iter_pending_steps(profile_snapshot)
        if s.target_field in _CONSULTATION_FIELDS
    ]


def is_consultation_phase(profile_snapshot: dict[str, Any]) -> bool:
    """True nếu đã xong required + brandkit, chỉ còn các bước TƯ VẤN bonus pending.

    Dùng để GATE tín hiệu 'đủ rồi': chỉ cho wrap-up khi thật sự đang tư vấn
    (không phải lúc còn thiếu field cơ bản / brandkit)."""
    steps = iter_pending_steps(profile_snapshot)
    return bool(steps) and all(s.target_field in _CONSULTATION_FIELDS for s in steps)


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
        # 1. Check blocking flags (ưu tiên cao nhất — KHÔNG nằm trong iter_pending_steps)
        blocking = profile_snapshot.get("blocking_flags", [])
        if blocking:
            flag = blocking[0]
            return {
                "type": "resolve_blocking_flag",
                "target_flag": flag,
                "target_field": None,
                "prompt_hint": f"Flag: {flag}",
            }

        # 2-3. Required → optional C1-C9 → brandkit (nguồn DUY NHẤT)
        steps = iter_pending_steps(profile_snapshot)
        if steps:
            return steps[0].to_objective()

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

        # Còn blocking flag HOẶC còn bước thu thập (required/optional/brandkit) → WAITING.
        # Dùng chung iter_pending_steps với compute_objective để 2 bên không lệch.
        blocking = profile_snapshot.get("blocking_flags", [])
        if blocking or iter_pending_steps(profile_snapshot):
            return "WAITING_REQUIRED_FIELD"

        review_status = profile_snapshot.get("review_status", "DRAFT")
        if review_status == "DRAFT":
            return "READY_FOR_REVIEW"

        return "CONFIRMED"
