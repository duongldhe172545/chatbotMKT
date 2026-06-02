"""Planner-first ASKING handler for Em Linh MKT."""
from __future__ import annotations

import logging
import unicodedata

from pydantic import ValidationError

from app.core._conv_derive import merge_extracted
from app.core._conv_confirming import enter_confirming
from app.core._conv_helpers import summarize_history
from app.core.address_blacklist import check_address_blacklist
from app.core.intent import detect_intent, detect_technical_inquiry
from app.core.missing_fields import compute_missing_fields, field_to_slot
from app.core.profile_merge import merge_planner_result
from app.llm.client import LLMClient
from app.llm.planner_prompt import (
    PLANNER_RESULT_SCHEMA,
    PLANNER_TOOL_DESCRIPTION,
    PLANNER_TOOL_NAME,
    build_planner_conversation_text,
    build_planner_system_prompt,
)
from app.models.enums import Intent, Stage
from app.models.planner import PlannerResult
from app.models.schema import DealerProfileRaw, SessionState

logger = logging.getLogger(__name__)

LEGACY_ONLY_SLOTS = {"4.0", "4.1"}
PLANNER_EXCLUDED_INTENTS = {Intent.REFUSAL}
_YES_CONFIRMATIONS = {
    "o",
    "o e",
    "o em",
    "u",
    "u e",
    "u em",
    "uh",
    "uh e",
    "uh em",
    "ua",
    "uk",
    "da",
    "da em",
    "vang",
    "vang em",
    "ok",
    "oke",
    "okay",
    "yes",
    "yep",
    "duoc",
    "duoc em",
    "dung",
    "dung roi",
    "phai",
    "phai roi",
    "chuan",
    "chuan roi",
    "chinh xac",
}
_NO_CONFIRMATIONS = {"khong", "khong phai", "sai", "chua dung", "khong dung"}


class PlannerError(RuntimeError):
    """Planner output is unusable; caller should fallback legacy."""


def is_planner_eligible(session: SessionState, message: str) -> bool:
    """True when planner may safely handle the ASKING happy path."""
    if session.stage != Stage.ASKING:
        return False
    if session.current_slot in LEGACY_ONLY_SLOTS:
        return False
    intent = detect_intent(message)
    if intent in PLANNER_EXCLUDED_INTENTS:
        return False
    if detect_technical_inquiry(message, current_slot=session.current_slot):
        return False
    if session.current_slot == "1.2" and check_address_blacklist(message):
        return False
    return True


def plan_intake_turn(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> PlannerResult:
    """Call the LLM planner and return a validated PlannerResult."""
    missing = compute_missing_fields(profile, session)
    raw = client.extract_quality(
        system_prompt=build_planner_system_prompt(),
        conversation_text=build_planner_conversation_text(
            history_summary=summarize_history(session, max_turns=8),
            profile_summary=_profile_summary(profile),
            missing_summary=_missing_summary(missing),
            current_focus=_current_focus_summary(session, missing),
            user_message=message,
        ),
        tool_name=PLANNER_TOOL_NAME,
        tool_description=PLANNER_TOOL_DESCRIPTION,
        input_schema=PLANNER_RESULT_SCHEMA,
    )
    try:
        result = PlannerResult.model_validate(raw)
    except ValidationError as exc:
        raise PlannerError(f"planner_validation_failed: {exc}") from exc

    if not result.assistant_reply.strip():
        raise PlannerError("planner_empty_reply")
    if not result.next_focus_fields and missing.next_focus_field:
        result.next_focus_fields = [missing.next_focus_field]
    return result


def handle_asking_with_planner(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> str:
    """Planner-first ASKING happy path."""
    _apply_pending_address_confirmation(session, profile, message)
    result = plan_intake_turn(session, profile, message, client)
    merge_summary = merge_planner_result(profile, result)
    missing = compute_missing_fields(profile, session)

    focus_field = result.next_focus_fields[0] if result.next_focus_fields else missing.next_focus_field
    session.current_slot = field_to_slot(focus_field) if focus_field else missing.next_focus_slot

    logger.info(
        "Planner turn applied: session=%s fields=%s skipped=%s next_slot=%s move=%s",
        session.session_id,
        sorted(merge_summary.applied.keys()),
        merge_summary.skipped,
        session.current_slot,
        result.move,
    )

    if result.move == "summarize_confirm" and missing.can_confirm:
        session.stage = Stage.CONFIRMING
        return enter_confirming(profile, session=session)

    return result.assistant_reply.strip()


def _profile_summary(profile: DealerProfileRaw) -> str:
    data = profile.model_dump()
    parts = []
    for key, value in data.items():
        if _has_value(value):
            parts.append(f"{key}={value}")
    return "; ".join(parts) if parts else "(chưa có)"


def _missing_summary(missing) -> str:
    return (
        f"required_missing={missing.required_missing}; "
        f"optional_missing={missing.optional_missing[:12]}; "
        f"next_focus={missing.next_focus_field}; "
        f"can_confirm={missing.can_confirm}"
    )


def _current_focus_summary(session: SessionState, missing) -> str:
    return (
        f"current_slot={session.current_slot}; "
        f"next_focus_field={missing.next_focus_field}; "
        f"next_focus_slot={missing.next_focus_slot}; "
        f"pending_address_text={session.pending_address_text}; "
        f"pending_address_canonical={session.pending_address_canonical}"
    )


def _apply_pending_address_confirmation(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
) -> None:
    """Resolve short confirmations to the previous pending address guess."""
    if not session.pending_address_canonical:
        return

    msg_fold = _fold_vn(message).strip(" .,!?:;")
    if _is_yes_confirmation(msg_fold):
        canonical = session.pending_address_canonical
        merge_extracted(profile, {"address": canonical}, client=None)
        session.pending_address_text = None
        session.pending_address_canonical = None
        logger.info(
            "Planner accepted pending address confirmation: session=%s address=%r",
            session.session_id,
            canonical,
        )
        return

    if _is_no_confirmation(msg_fold):
        session.pending_address_text = None
        session.pending_address_canonical = None


def _is_yes_confirmation(msg_fold: str) -> bool:
    return msg_fold in _YES_CONFIRMATIONS or any(
        msg_fold.startswith(word + " ") for word in _YES_CONFIRMATIONS
    )


def _is_no_confirmation(msg_fold: str) -> bool:
    return msg_fold in _NO_CONFIRMATIONS or any(
        msg_fold.startswith(word + " ") for word in _NO_CONFIRMATIONS
    )


def _fold_vn(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _has_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True
