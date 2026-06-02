"""Finalize judge for the LLM-first intake flow."""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.core.intake_coverage import IntakeCoverage, summarize_coverage
from app.llm.client import LLMClient
from app.models.schema import DealerProfileRaw


class FinalizeDecision(BaseModel):
    should_finalize: bool = False
    reason: str = ""
    missing_blockers: list[str] = Field(default_factory=list)


FINALIZE_TOOL_NAME = "judge_linh_intake_finalize"
FINALIZE_TOOL_DESCRIPTION = (
    "Decide whether the dealer has confirmed the final intake summary."
)
FINALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "should_finalize": {"type": "boolean"},
        "reason": {"type": "string"},
        "missing_blockers": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["should_finalize", "reason", "missing_blockers"],
}


class FinalizeJudgeError(RuntimeError):
    """Finalize judge output is invalid."""


def judge_intake_finalize(
    *,
    history_text: str,
    user_message: str,
    profile: DealerProfileRaw,
    coverage: IntakeCoverage,
    client: LLMClient,
) -> FinalizeDecision:
    """Use conversation context to decide final confirmation."""
    if not coverage.can_summarize:
        return FinalizeDecision(
            should_finalize=False,
            reason="Required fields are still missing.",
            missing_blockers=coverage.required_missing,
        )

    raw = client.extract_quality(
        system_prompt=build_finalize_judge_prompt(),
        conversation_text=build_finalize_judge_input(
            history_text=history_text,
            user_message=user_message,
            profile=profile,
            coverage=coverage,
        ),
        tool_name=FINALIZE_TOOL_NAME,
        tool_description=FINALIZE_TOOL_DESCRIPTION,
        input_schema=FINALIZE_SCHEMA,
    )
    try:
        return FinalizeDecision.model_validate(raw)
    except ValidationError as exc:
        raise FinalizeJudgeError(f"finalize_judge_validation_failed: {exc}") from exc


def build_finalize_judge_prompt() -> str:
    return """Bạn là bộ phân tích chốt hội thoại của Em Linh MKT.

Chỉ trả should_finalize=true khi:
- Bot vừa đưa bản tóm tắt/hỏi xác nhận đúng đủ trong lịch sử gần đây.
- Dealer mới nhất xác nhận bản tóm tắt đó là đúng/đủ/chốt/làm tiếp.
- Coverage không còn required_missing.

Không finalize nếu:
- Dealer chỉ nói "ok" để bắt đầu hoặc đồng ý trả lời tiếp.
- Dealer đang chọn phương án, hỏi lại, sửa thông tin, hoặc chưa thấy bản tóm tắt.
- Required field còn thiếu.

Trả JSON đúng schema, không markdown.
"""


def build_finalize_judge_input(
    *,
    history_text: str,
    user_message: str,
    profile: DealerProfileRaw,
    coverage: IntakeCoverage,
) -> str:
    return f"""Profile:
{profile.model_dump()}

Coverage:
{summarize_coverage(coverage)}

Lịch sử gần đây:
{history_text}

Tin nhắn mới nhất:
{user_message}
"""
