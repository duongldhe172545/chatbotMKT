"""Agent reply generator — LLM-based reply generation.

Parlant concept: The agent takes the assembled context and generates
a natural reply. It uses:
1. System prompt (built from context)
2. Recent conversation history
3. Matched guidelines
4. Suggested objective

Phase 3 implementation: Stub that returns deterministic replies.
Phase 4+ will wire real LLM (Gemini) calls.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# System prompt — loads rules from config/rules.yaml
# ============================================================

_SYSTEM_PROMPT_TEMPLATE = """\
{rules_context}

NGỮ CẢNH HỘI THOẠI:
- Thông tin đại lý hiện tại: {profile_summary}
- Lịch sử chat gần đây: {history_summary}

TRẠNG THÁI THU THẬP:
{collection_status}
{style_override}
NHIỆM VỤ HIỆN TẠI:
{task}
"""


class AgentReplyGenerator:
    """Generate replies using LLM or stub logic."""

    def __init__(self, *, runtime: str = "stub"):
        """
        Args:
            runtime: "stub" for deterministic replies, "gemini" for LLM (Phase 4+)
        """
        self.runtime = runtime

    def generate(self, context: dict[str, Any]) -> AgentResult:
        """Generate a reply from the assembled context.

        Args:
            context: Full context dict from ContextBuilder.build()

        Returns:
            AgentResult with reply text + metadata
        """
        if self.runtime == "stub":
            return self._generate_stub(context)

        # Real LLM generation
        try:
            from app.core.config_v2 import get_settings
            settings = get_settings()
            if settings.gemini_api_key and settings.gemini_api_key.strip() and settings.gemini_api_key != "your-gemini-api-key-here":
                from app.llm.client import get_default_client
                client = get_default_client()
                
                # Construct system prompt
                system_prompt = self.build_system_prompt(context)
                
                # Convert recent_messages to LLM format
                llm_messages = []
                for msg in context.get("recent_messages", []):
                    role = "user" if msg.get("source") == "user" else "assistant"
                    llm_messages.append({"role": role, "content": msg.get("text", "")})
                
                # Call chat_quality for generation.
                # max_tokens 512 (P3/M1): reply chuẩn 25-80 từ tự dừng sớm —
                # đây là cap chặn output dài bất thường, không phải tăng tốc.
                reply = client.chat_quality(
                    system_prompt=system_prompt,
                    messages=llm_messages,
                    max_tokens=512
                )
                if reply:
                    reply = self._append_card_if_needed(reply, context)
                    return AgentResult(
                        text=reply,
                        model_id=client.quality_provider.model,
                        system_prompt=system_prompt,
                        usage={"input_tokens": 0, "output_tokens": 0},
                    )
        except Exception as e:
            logger.error("Agent LLM generation failed: %s", e)

        return self._generate_stub(context)

    def build_system_prompt(self, context: dict[str, Any]) -> str:
        """Build system prompt from context — rules loaded from config/rules.yaml."""
        from app.core.rules import build_rules_context_for_prompt

        address_form = context.get("address_form", "anh")
        dealer_type = context.get("dealer_type", "unknown")

        # Build rules context from unified rules.yaml
        rules_context = build_rules_context_for_prompt(
            dealer_type=dealer_type,
            address_form=address_form,
        )

        # Profile summary
        snapshot = context.get("profile_snapshot", {})
        all_fields = snapshot.get("all_fields", {})
        if all_fields:
            profile_parts = []
            for name, info in all_fields.items():
                if isinstance(info, dict):
                    val = info.get("normalized_value") or info.get("raw_value")
                else:
                    val = info
                if val:
                    profile_parts.append(f"{name}={val}")
            profile_summary = ", ".join(profile_parts) if profile_parts else "(chua co)"
        else:
            profile_summary = "(chua co)"

        # Style override based on observations
        obs = context.get("observations", {})
        style_override = ""
        if obs.get("wants_brief"):
            style_override = "\nPHONG CÁCH YÊU CẦU: Khách hàng yêu cầu nói ngắn gọn! Trả lời cực kỳ ngắn gọn và súc tích (tối đa 10-15 từ, 1-2 câu), đi thẳng vào câu hỏi, KHÔNG dông dài, KHÔNG nịnh bợ hay khen ngợi dư thừa.\n"
        elif obs.get("is_busy"):
            style_override = "\nPHONG CÁCH YÊU CẦU: Khách hàng đang bận rộn/vội vã! Trả lời nhanh, ngắn gọn, súc tích.\n"

        return _SYSTEM_PROMPT_TEMPLATE.format(
            rules_context=rules_context,
            profile_summary=profile_summary,
            history_summary=context.get("history_summary", "(chua co)"),
            collection_status=context.get("collection_status", "(chưa có dữ liệu)"),
            style_override=style_override,
            task=context.get("task", "Tiep tuc tro chuyen."),
        )

    def _generate_stub(self, context: dict[str, Any]) -> "AgentResult":
        """Deterministic reply from objective (no LLM)."""
        objective = context.get("suggested_objective", {})
        address_form = context.get("address_form", "anh")
        changed = []  # Phase 4 will pass changed_fields

        reply = _stub_reply(objective, address_form, changed)
        reply = self._append_card_if_needed(reply, context)

        return AgentResult(
            text=reply,
            model_id="stub",
            system_prompt=self.build_system_prompt(context),
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def _append_card_if_needed(self, reply: str, context: dict[str, Any]) -> str:
        objective = context.get("suggested_objective", {})
        if objective.get("type") == "show_profile_review":
            try:
                from app.models.schema import DealerProfileRaw
                from app.core.card_renderer import render_card
                
                snapshot = context.get("profile_snapshot", {})
                all_fields = snapshot.get("all_fields", {})
                profile_dict = {}
                for field_name in DealerProfileRaw.model_fields:
                    if field_name in all_fields:
                        profile_dict[field_name] = all_fields[field_name]
                profile_raw = DealerProfileRaw(**profile_dict)
                card_text = render_card(profile_raw, address_form=context.get("address_form", "anh"))
                return f"{reply}\n\n{card_text}"
            except Exception as e:
                logger.warning("Failed to render confirmation card: %s", e)
        return reply


class AgentResult:
    """Result from agent reply generation."""

    def __init__(
        self,
        *,
        text: str,
        model_id: str = "stub",
        system_prompt: str = "",
        usage: dict[str, int] | None = None,
    ):
        self.text = text
        self.model_id = model_id
        self.system_prompt = system_prompt
        self.usage = usage or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model_id": self.model_id,
            "usage": self.usage,
        }


# Field labels for Vietnamese
_FIELD_LABELS: dict[str, str] = {
    "owner_name": "tên {af}",
    "dealer_name": "tên xưởng/cửa hàng",
    "address": "địa chỉ hoặc khu vực",
    "phone_or_zalo": "số điện thoại/Zalo",
    "main_product": "sản phẩm chính",
    "business_model_signal": "loại hình: xưởng, đại lý, thi công hay phân phối",
    "est_team_size": "quy mô đội thợ của mình",
    "supplier_brands": "nhãn hiệu nhà cung cấp nhập hàng chính",
    "primary_contact_channel": "kênh liên hệ chính với khách hàng",
    "facebook": "kênh Facebook của xưởng mình",
    "customer_old_percentage": "tỷ lệ khách hàng cũ giới thiệu",
    "customer_storage_method": "phương pháp lưu trữ danh sách khách hàng",
    "customer_pain": "vướng mắc hoặc khó khăn lớn nhất gặp phải",
    "payment_terms_signal": "quy trình đặt cọc và thanh toán",
    "warranty_responsibility_signal": "trách nhiệm xử lý bảo hành",
    "brandkit_consent": "sự đồng ý nhận bộ thương hiệu miễn phí",
    "color_accent": "màu sắc chủ đạo hoặc phong thủy",
    "logo_existing_intent": "nhu cầu với logo hiện có — nâng cấp, thiết kế lại bố cục/màu hay làm mới hoàn toàn",
}


def _stub_reply(
    objective: dict[str, Any],
    address_form: str,
    changed_fields: list[str],
) -> str:
    """Generate deterministic reply from objective."""
    obj_type = objective.get("type", "continue_conversation")
    af = address_form

    if obj_type == "resolve_blocking_flag":
        flag = objective.get("target_flag", "")
        if flag == "phone_invalid_after_retry":
            return (
                f"Dạ {af} ơi, số điện thoại {af} cung cấp dường như chưa đúng định dạng hoặc bên em không liên lạc được ạ. "
                f"{af.capitalize()} kiểm tra lại giúp em hoặc cho em xin số điện thoại khác nhé. 😊"
            )
        return (
            f"Dạ em thấy có thông tin cần kiểm tra an toàn. "
            f"{af.capitalize()} cho em lại địa chỉ hoặc khu vực gọn hơn nhé."
        )

    if obj_type in ("collect_required_field", "collect_optional_field"):
        target = objective.get("target_field", "")
        label = _FIELD_LABELS.get(target, target).replace("{af}", af)
        if changed_fields:
            fields_text = ", ".join(changed_fields)
            return (
                f"Dạ em ghi nhận {fields_text} rồi ạ. "
                f"Em xin thêm {label} để làm hồ sơ và logo cho chuẩn nhé."
            )
        return f"Dạ em cần thêm {label} để làm hồ sơ và logo cho {af} nhé."

    if obj_type == "show_profile_review":
        return (
            f"Dạ em đã gom đủ thông tin chính rồi ạ. "
            f"{af.capitalize()} xem lại thẻ hồ sơ này, đúng thì bấm xác nhận giúp em nhé."
        )

    if obj_type == "show_logo_brief":
        return (
            f"Dạ hồ sơ đã xác nhận rồi ạ. "
            f"Em chuẩn bị brief logo để {af} duyệt tiếp nhé."
        )

    return "Dạ em ghi nhận rồi ạ."
