"""Turn processor — the Parlant-style conversation orchestrator.

Replaces legacy conversation.py handle_message() with a clean pipeline:

1. PRE-TURN GUARDS: injection, garbage, abuse detection
2. OBSERVE: detect behavioral signals (intent, dealer_type)
3. EXTRACT: extract profile fields from message (stub → Phase 4+)
4. WORKFLOW: compute suggested objective from profile state
5. MATCH GUIDELINES: find applicable rules for this turn
6. BUILD CONTEXT: assemble full context for agent
7. GENERATE REPLY: agent produces reply text
8. POST-TURN GUARDS: drift rewrite, parrot check, emoji limit
9. PERSIST: create turn record + bot message

This is the central orchestrator that replaces:
- conversation.py (stage dispatch)
- _conv_asking.py (extract + state machine + reply)
- _conv_confirming.py (confirm/edit flow)
- state_machine.py (decide_action)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.parlant.agent import AgentReplyGenerator
from app.parlant.canned_responses import CannedResponseRegistry
from app.parlant.context_builder import ContextBuilder
from app.parlant.guideline_registry import GuidelineRegistry
from app.parlant.observation_detector import Observations, detect_observations
from app.parlant.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


# Objective đang THU THẬP — chưa được phép chốt hội thoại / gửi link Zalo
_COLLECTING_OBJECTIVES = {
    "collect_required_field",
    "collect_optional_field",
    "resolve_blocking_flag",
}

# Marker đóng-sớm — THU GỌN còn lõi (2026-06-12): chỉ giữ dấu hiệu chốt-THẬT
# gần như không bao giờ bắt nhầm — link Zalo thật / placeholder link / bot tự
# tuyên bố "đã đủ thông tin". Cái nguy hiểm là bot dán LINK NHÓM ZALO + bảo
# "xong rồi" giữa chừng → khách bấm link rời đi sớm.
#
# ĐÃ BỎ 6 marker "hành vi" (kết bạn zalo / zalo theo số / đội ngũ thiết kế /
# bắt tay vào làm / gửi…qua zalo / kết nối qua zalo) vì chúng bắt NHẦM câu
# gửi-mẫu / giới-thiệu tử tế ("em gửi mẫu qua Zalo cho anh xem nhé") → đá AI
# sang stub cộc lốc (bug "cho anh xem mẫu" 2026-06-12). Workflow vẫn không cho
# kết thúc thật khi còn field thiếu, nên rủi ro bỏ 6 marker này là rất thấp.
_PREMATURE_CLOSING_PATTERNS = [
    r"link\s*zalo",
    r"zalo\.me/",
    r"\[link",
    r"(thu\s*thập|gom|nắm)\s*(đủ|đầy\s*đủ)",
    r"đã\s*đủ\s*thông\s*tin",
]


def _has_premature_closing(reply: str) -> bool:
    """True nếu reply chứa marker chốt hội thoại trong khi objective còn thu thập."""
    if not reply:
        return False
    low = reply.lower()
    return any(re.search(p, low) for p in _PREMATURE_CLOSING_PATTERNS)


@dataclass
class TurnTrace:
    """Full trace of a single turn — stored in conversation_turns.backend_turn_trace_json."""

    phase: str = "parlant_pipeline"
    observations: dict[str, Any] = field(default_factory=dict)
    suggested_objective: dict[str, Any] = field(default_factory=dict)
    matched_guideline_ids: list[str] = field(default_factory=list)
    canned_response_id: str | None = None
    agent_model_id: str = "stub"
    pre_guard_flags: list[str] = field(default_factory=list)
    post_guard_flags: list[str] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    reply_text: str = ""
    workflow_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "observations": self.observations,
            "suggested_objective": self.suggested_objective,
            "matched_guideline_ids": self.matched_guideline_ids,
            "canned_response_id": self.canned_response_id,
            "agent_model_id": self.agent_model_id,
            "pre_guard_flags": self.pre_guard_flags,
            "post_guard_flags": self.post_guard_flags,
            "extracted_fields": self.extracted_fields,
            "reply_text": self.reply_text,
            "workflow_state": self.workflow_state,
        }


@dataclass
class TurnResult:
    """Output of processing a single turn."""

    reply_text: str
    observations: Observations
    suggested_objective: dict[str, Any]
    profile_snapshot: dict[str, Any]
    workflow_state: str
    trace: TurnTrace
    extracted_fields: dict[str, Any]



class TurnProcessor:
    """Process a single dealer message through the Parlant pipeline."""

    def __init__(
        self,
        *,
        guideline_registry: GuidelineRegistry,
        canned_registry: CannedResponseRegistry,
        workflow_engine: WorkflowEngine,
        context_builder: ContextBuilder,
        agent: AgentReplyGenerator,
    ):
        self.guidelines = guideline_registry
        self.canned = canned_registry
        self.workflow = workflow_engine
        self.context_builder = context_builder
        self.agent = agent

    def process(
        self,
        *,
        message: str,
        profile_snapshot: dict[str, Any],
        recent_messages: list[dict[str, Any]],
        address_form: str = "anh",
        turn_count: int = 0,
    ) -> TurnResult:
        """Process a single dealer message through the full pipeline.

        Args:
            message: Current user message text
            profile_snapshot: Current profile state
            recent_messages: Recent message history (for context)
            address_form: "anh" or "chi"
            turn_count: Current turn number

        Returns:
            TurnResult with reply, observations, objective, trace
        """
        trace = TurnTrace()

        # ── 1. PRE-TURN GUARDS ──────────────────────────────────
        pre_flags = self._pre_turn_guards(message)
        trace.pre_guard_flags = pre_flags

        # ── 2. EXTRACTION & OBSERVATION (Gộp Subgraph 2 & 3) ────
        extracted = {}
        observations = None
        
        # Sắp xếp bản đồ field -> slot id
        field_to_slot = {
            "owner_name": "1.1",
            "dealer_name": "1.1",
            "address": "1.2",
            "phone_or_zalo": "1.3",
            "main_product": "2.1",
            "business_model_signal": "2.2",
            "brandkit_consent": "4.0",
            "est_team_size": "2.3",
            "supplier_brands": "2.4",
            "primary_contact_channel": "2.5",
            "facebook": "2.6",
            "customer_old_percentage": "3.1",
            "customer_storage_method": "3.2",
            "customer_pain": "3.3",
            "payment_terms_signal": "3.4",
            "warranty_responsibility_signal": "3.5",
            "color_accent": "4.2",
        }
        
        # Xác định mục tiêu và field/slot đang hỏi từ profile state trước lượt chat
        prev_obj = self.workflow.compute_objective(
            profile_snapshot=profile_snapshot,
            observations={},
            turn_count=turn_count,
        )
        focus_field = prev_obj.get("target_field")
        focus_slot = field_to_slot.get(focus_field) if focus_field else None

        workflow_state = self.workflow.compute_workflow_state(profile_snapshot)
        stage = "ASKING"
        if workflow_state == "READY_FOR_REVIEW":
            stage = "CONFIRMING"
        elif workflow_state in ("LOGO_READY", "LOGO_PENDING", "CONFIRMED", "ESCALATED"):
            stage = "DONE"

        # Khởi tạo mô hình LLM nếu API key hoạt động
        llm_client = None
        from app.core.config_v2 import get_settings
        settings = get_settings()
        if settings.gemini_api_key and settings.gemini_api_key.strip() and settings.gemini_api_key != "your-gemini-api-key-here":
            try:
                from app.llm.client import get_default_client
                llm_client = get_default_client()
            except Exception:
                pass

        # Gọi _extract_fields gộp
        extraction_result = self._extract_fields(
            message=message,
            profile_snapshot=profile_snapshot,
            recent_messages=recent_messages,
            focus_slot=focus_slot,
            focus_field=focus_field,
            llm_client=llm_client,
            stage=stage,
        )
        
        # Hỗ trợ tương thích với Mock trong unit test (nếu test mock _extract_fields trả về dict thay vì tuple)
        if isinstance(extraction_result, tuple):
            extracted, observations = extraction_result
        else:
            extracted = extraction_result
            from app.parlant.observation_detector import detect_observations
            observations = detect_observations(
                message,
                history_length=turn_count,
                llm_client=None,
                stage=stage,
                current_slot=focus_slot
            )

        trace.observations = observations.to_dict()

        # ── 3b. (7.1) GUARD BRANDKIT CHOICE — strip TRƯỚC merge + objective ──
        # Field màu/phong cách/slogan: khách "tùy em / gợi ý đi" (khong_biet) =
        # NHỜ ĐỀ XUẤT, không phải đưa giá trị. LLM hay tự bịa value (vd slogan="auto").
        # Nếu nhận → brandkit "đủ" sớm → objective nhảy show_profile_review → CARD
        # bung ngay trên lượt bot vừa đề xuất (bug "card hiện trước khi chốt slogan").
        # → strip ở ĐÂY (trước merge dưới + compute_objective) để field ở PENDING,
        # bot chỉ đề xuất; khách chọn cụ thể lượt sau mới chốt + ra card.
        _BRANDKIT_CHOICE_FIELDS = {"color_accent", "logo_style", "slogan_preference"}
        if focus_field in _BRANDKIT_CHOICE_FIELDS and observations.intent == "khong_biet":
            extracted.pop(focus_field, None)
            if focus_field == "color_accent":
                extracted.pop("feng_shui_signal", None)

        trace.extracted_fields = extracted

        # Merge extracted fields in-memory so workflow engine and agent see updated state
        from app.services.serializers import REQUIRED_PROFILE_FIELDS, DESIGN_PROFILE_FIELDS
        from app.core.validators import validate_field
        for k, v in extracted.items():
            if v is not None:
                # Validate in-memory too!
                is_valid, cleaned_value = validate_field(k, v)
                if is_valid:
                    if "all_fields" not in profile_snapshot:
                        profile_snapshot["all_fields"] = {}
                    if "required_fields" not in profile_snapshot:
                        profile_snapshot["required_fields"] = {}
                    if "design_fields" not in profile_snapshot:
                        profile_snapshot["design_fields"] = {}
                    
                    profile_snapshot["all_fields"][k] = cleaned_value
                    if k in REQUIRED_PROFILE_FIELDS:
                        profile_snapshot["required_fields"][k] = cleaned_value
                        if k in profile_snapshot.get("missing_required_fields", []):
                            profile_snapshot["missing_required_fields"].remove(k)
                    elif k in DESIGN_PROFILE_FIELDS:
                        profile_snapshot["design_fields"][k] = cleaned_value

                    # If we just validated a valid phone_secondary, and phone_or_zalo is missing/invalid, copy it!
                    if k == "phone_secondary":
                        primary_val = profile_snapshot.get("all_fields", {}).get("phone_or_zalo")
                        is_primary_valid = False
                        if primary_val:
                            is_primary_valid, _ = validate_field("phone_or_zalo", primary_val)
                        if not is_primary_valid:
                            profile_snapshot["all_fields"]["phone_or_zalo"] = cleaned_value
                            if "required_fields" not in profile_snapshot:
                                profile_snapshot["required_fields"] = {}
                            profile_snapshot["required_fields"]["phone_or_zalo"] = cleaned_value
                            if "phone_or_zalo" in profile_snapshot.get("missing_required_fields", []):
                                profile_snapshot["missing_required_fields"].remove("phone_or_zalo")

                    # In-memory flag resolution
                    details = profile_snapshot.get("active_flag_details", [])
                    to_remove = []
                    for fd in details:
                        if fd["field_name"] == k or (k in ("phone_or_zalo", "phone_secondary") and fd["flag_name"] == "phone_invalid_after_retry"):
                            to_remove.append(fd)
                    for fd in to_remove:
                        details.remove(fd)
                    profile_snapshot["blocking_flags"] = [fd["flag_name"] for fd in details if fd["severity"] == "BLOCKING"]
                    profile_snapshot["open_flags"] = [fd["flag_name"] for fd in details]
                else:
                    # If invalid, raise blocking flags or warning flags in-memory immediately!
                    flag_name = "sanity_check_failed"
                    if k == "phone_or_zalo":
                        flag_name = "phone_invalid_after_retry"
                    
                    if "blocking_flags" not in profile_snapshot:
                        profile_snapshot["blocking_flags"] = []
                    if "open_flags" not in profile_snapshot:
                        profile_snapshot["open_flags"] = []
                    
                    if flag_name not in profile_snapshot["open_flags"]:
                        profile_snapshot["open_flags"].append(flag_name)
                    if k == "phone_or_zalo" and flag_name not in profile_snapshot["blocking_flags"]:
                        profile_snapshot["blocking_flags"].append(flag_name)

        # ── 4. WORKFLOW — compute suggested objective ────────────
        if not message.strip():
            suggested_objective = {
                "type": "greet_user",
                "target_field": None,
                "prompt_hint": "Chào mừng người dùng",
            }
        else:
            suggested_objective = self.workflow.compute_objective(
                profile_snapshot=profile_snapshot,
                observations=observations.to_dict(),
                turn_count=turn_count,
            )
        trace.suggested_objective = suggested_objective
        workflow_state = self.workflow.compute_workflow_state(profile_snapshot)
        trace.workflow_state = workflow_state

        # ── 5. MATCH GUIDELINES ─────────────────────────────────
        match_context = {
            **observations.to_dict(),
            "objective_type": suggested_objective.get("type", ""),
            "turn_count": turn_count,
        }
        matched = self.guidelines.match(match_context)
        trace.matched_guideline_ids = [g.id for g in matched]

        # ── 6. CHECK CANNED RESPONSE ────────────────────────────
        canned = None
        if self.agent.runtime == "stub":
            canned = self.canned.match(
                objective_type=suggested_objective.get("type", ""),
                target_field=suggested_objective.get("target_field"),
                intent=observations.intent,
                target_flag=suggested_objective.get("target_flag"),
            )
        else:
            # LLM mode: only use canned response for greet_user (greeting template)
            if suggested_objective.get("type") == "greet_user":
                canned = self.canned.match(
                    objective_type="greet_user",
                    target_field=None,
                    intent=observations.intent,
                )

        if canned:
            reply_text = self.canned.render(canned, address_form)
            trace.canned_response_id = canned.id
            trace.agent_model_id = "canned"
        else:
            # ── 7. BUILD CONTEXT + GENERATE REPLY ───────────────
            context = self.context_builder.build(
                profile_snapshot=profile_snapshot,
                suggested_objective=suggested_objective,
                observations=observations.to_dict(),
                matched_guidelines=[
                    {"id": g.id, "action": g.action} for g in matched
                ],
                recent_messages=recent_messages,
                address_form=address_form,
                dealer_type=observations.dealer_type,
            )
            agent_result = self.agent.generate(context)
            reply_text = agent_result.text
            trace.agent_model_id = agent_result.model_id

        # ── 7b. PREMATURE CLOSING GUARD ─────────────────────────
        # Objective còn thu thập mà reply chốt/gửi Zalo → retry 1 lần với
        # chỉ thị nghiêm hơn; vẫn vi phạm → fallback stub reply deterministic.
        guard_extra_flags: list[str] = []
        if (
            not canned
            and suggested_objective.get("type") in _COLLECTING_OBJECTIVES
            and _has_premature_closing(reply_text)
        ):
            logger.warning(
                "Premature closing detected (objective=%s) — regenerating",
                suggested_objective.get("type"),
            )
            retry_context = dict(context)
            retry_context["task"] = context.get("task", "") + (
                "\n\nCẢNH BÁO — câu trả lời trước đã VI PHẠM: tự chốt hội thoại / "
                "gửi link Zalo / nói 'đã thu thập đủ' trong khi còn thông tin phải hỏi. "
                "Viết lại: KHÔNG link, KHÔNG chốt, kết thúc bằng đúng 1 câu hỏi "
                "cho thông tin đang cần."
            )
            retry_result = self.agent.generate(retry_context)
            if _has_premature_closing(retry_result.text):
                from app.parlant.agent import _stub_reply
                reply_text = _stub_reply(suggested_objective, address_form, [])
                trace.agent_model_id = "guard_fallback"
                guard_extra_flags.append("premature_closing_fallback")
            else:
                reply_text = retry_result.text
                trace.agent_model_id = retry_result.model_id
                guard_extra_flags.append("premature_closing_regenerated")

        # ── 8. POST-TURN GUARDS ─────────────────────────────────
        reply_text, post_flags = self._post_turn_guards(
            reply_text, message, address_form
        )
        trace.post_guard_flags = guard_extra_flags + post_flags
        trace.reply_text = reply_text

        return TurnResult(
            reply_text=reply_text,
            observations=observations,
            suggested_objective=suggested_objective,
            profile_snapshot=profile_snapshot,
            workflow_state=workflow_state,
            trace=trace,
            extracted_fields=extracted,
        )

    # ================================================================
    # Pre-turn guards
    # ================================================================

    def _pre_turn_guards(self, message: str) -> list[str]:
        """Run pre-turn safety checks.

        Returns list of flag names triggered.
        """
        flags = []
        if not message.strip():
            return flags

        # 1. Simple injection detection (stub)
        injection_patterns = [
            r"ignore.*previous.*instructions",
            r"system\s*prompt",
            r"you\s*are\s*now",
            r"forget.*everything",
        ]
        for pattern in injection_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                flags.append("prompt_injection")
                break

        return flags

    def _extract_fields(
        self,
        *,
        message: str,
        profile_snapshot: dict[str, Any],
        recent_messages: list[dict[str, Any]],
        focus_slot: str | None,
        focus_field: str | None,
        llm_client: Any | None,
        stage: str,
    ) -> tuple[dict[str, Any], Observations]:
        """Extract profile facts and behavioral observations in a single LLM call."""
        extracted = {}
        observations = None
        llm_ran_successfully = False

        if llm_client:
            try:
                from app.llm.intake_fact_extractor import extract_intake_facts
                from app.models.schema import DealerProfileRaw
                
                # Tạo DealerProfileRaw từ snapshot hiện tại
                all_fields = profile_snapshot.get("all_fields", {})
                profile_dict = {}
                for field_name in DealerProfileRaw.model_fields:
                    if field_name in all_fields:
                        profile_dict[field_name] = all_fields[field_name]
                profile_raw = DealerProfileRaw(**profile_dict)
                
                # Tạo lịch sử hội thoại dạng text
                history_parts = []
                for msg in recent_messages:
                    role = "bot" if msg.get("source") == "linh_mkt" else "dealer"
                    history_parts.append(f"{role}: {msg.get('text', '')}")
                history_text = "\n".join(history_parts)
                
                # Gọi 1 lượt LLM duy nhất trả về cả facts và observations
                intake_facts = extract_intake_facts(
                    history_text=history_text,
                    current_profile=profile_raw,
                    user_message=message,
                    client=llm_client,
                    current_focus_slot=focus_slot,
                    current_focus_field=focus_field,
                )
                
                for fact in intake_facts.facts:
                    extracted[fact.field] = fact.value
                
                word_count = len(message.lower().split())
                msg_length = "short" if word_count <= 3 else ("long" if word_count > 15 else "medium")
                
                observations = Observations(
                    dealer_type=intake_facts.dealer_type,
                    intent=intake_facts.intent,
                    is_busy=intake_facts.is_busy,
                    is_emotional=intake_facts.is_emotional,
                    is_skeptical=intake_facts.is_skeptical,
                    message_length=msg_length,
                    wants_brief=intake_facts.wants_brief,
                    raw_signals=intake_facts.uncertainty_notes,
                )
                llm_ran_successfully = True
            except Exception as e:
                logger.warning("Combined LLM extraction & observation failed, falling back: %s", e)

        # Fallback nếu LLM offline hoặc lỗi mạng
        if not llm_ran_successfully:
            # 1. Regex trích xuất SĐT
            phone_match = re.search(r"\d{9,12}", message)
            if phone_match:
                extracted["phone_or_zalo"] = phone_match.group()

            # 2. Regex fallback cho tên cá nhân (owner_name)
            name_match = re.search(
                r"(?:tên|chủ là)\s+([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƠƯỨỨỪỬỮỰđàáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựỷỳỷỹỵ]\w*(?:\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƠƯỨỨỪỬỮỰđàáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựỷỳỷỹỵ]\w*)*)",
                message,
                re.IGNORECASE
            )
            if name_match:
                extracted["owner_name"] = name_match.group(1).strip()

            # 3. Regex fallback cho tên cửa hàng (dealer_name)
            dealer_match = re.search(r"(?:cửa hàng|xưởng)\s+([^,;\.\n]+)", message, re.IGNORECASE)
            if dealer_match:
                extracted["dealer_name"] = dealer_match.group(1).strip()
            
            # 4. Heuristics code cứng cho Observations
            from app.parlant.observation_detector import detect_observations
            observations = detect_observations(
                message,
                history_length=len(recent_messages),
                llm_client=None,
                stage=stage,
                current_slot=focus_slot
            )
            # Quét lịch sử gần đây để duy trì trạng thái wants_brief trong fallback (có hỗ trợ tắt đi nếu user muốn nói dài)
            wants_brief_patterns = [
                r"ngắn thôi", r"ngắn gọn", r"ngắn lại",
                r"đừng dài dòng", r"đừng nói dài",
                r"nói ngắn", r"ít chữ", r"không dài dòng"
            ]
            wants_long_patterns = [
                r"dài dòng", r"chi tiết", r"dài ra",
                r"nói dài", r"nói nhiều", r"cụ thể",
                r"bình thường"
            ]
            is_brief = False
            for msg in recent_messages:
                if msg.get("source") == "user":
                    text = msg.get("text", "")
                    if any(re.search(pat, text, re.IGNORECASE) for pat in wants_brief_patterns):
                        is_brief = True
                    elif any(re.search(pat, text, re.IGNORECASE) for pat in wants_long_patterns):
                        if not any(re.search(pat, text, re.IGNORECASE) for pat in wants_brief_patterns):
                            is_brief = False
            observations.wants_brief = is_brief

        return extracted, observations

    # ================================================================
    # Post-turn guards
    # ================================================================

    def _post_turn_guards(
        self,
        reply: str,
        dealer_message: str,
        address_form: str,
    ) -> tuple[str, list[str]]:
        """Run post-turn quality checks on bot reply.

        Returns (cleaned_reply, list_of_flags).
        Phase 4+ will wire: drift rewrite, parrot check, hallucinate check.
        """
        flags = []
        if not reply:
            return reply, flags

        # Emoji limit (7.3: max 2 — cho phép icon sinh động, vẫn chặn spam)
        emoji_count = len(re.findall(r"[\U0001F300-\U0001F9FF]", reply))
        if emoji_count > 2:
            # Keep first 2 emojis, remove rest
            found = 0
            chars = []
            for ch in reply:
                if re.match(r"[\U0001F300-\U0001F9FF]", ch):
                    found += 1
                    if found <= 2:
                        chars.append(ch)
                else:
                    chars.append(ch)
            reply = "".join(chars)
            flags.append("emoji_trimmed")

        # Collapse multiple spaces
        reply = re.sub(r" {2,}", " ", reply).strip()

        # Address form enforcement (9.1) — khách xưng "chị" mà reply lỡ "anh" → sửa.
        # Bắt mọi "anh" đứng riêng (kể cả "Anh," / "anh." / đầu câu), giữ hoa/thường.
        if address_form == "chi" and re.search(r"\banh\b", reply, flags=re.IGNORECASE):
            def _to_chi(m: re.Match) -> str:
                return "Chị" if m.group(0)[:1].isupper() else "chị"
            reply = re.sub(r"\banh\b", _to_chi, reply, flags=re.IGNORECASE)
            flags.append("address_form_repaired")

        return reply, flags
