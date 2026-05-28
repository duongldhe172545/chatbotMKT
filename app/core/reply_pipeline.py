"""Central reply pipeline for turn analysis, composition, and validation.

This module is an adapter layer around the current string-returning handlers.
It gives every non-opening bot reply a common path without forcing a large
handler rewrite in one step.
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.abuse_detector import is_personal_abuse
from app.core.garbage_detector import is_garbage, is_meaningful_short
from app.core.intent import detect_intent, detect_technical_inquiry
from app.models.enums import Intent, Stage
from app.models.schema import DealerProfileRaw, SessionState


class CustomerSignal(str, Enum):
    DATA_ANSWER = "data_answer"
    PARTIAL_ANSWER = "partial_answer"
    CORRECTION = "correction"
    AFFIRMATIVE = "affirmative"
    REFUSAL = "refusal"
    SKEPTICAL = "skeptical"
    CONFUSED = "confused"
    ANGRY = "angry"
    JOKING_TESTING = "joking_testing"
    SMALLTALK = "smalltalk"
    OFF_TOPIC = "off_topic"
    TECHNICAL_INQUIRY = "technical_inquiry"
    UNKNOWN = "unknown"


class ReplyKind(str, Enum):
    NORMAL = "normal"
    RETRY = "retry"
    CLARIFY = "clarify"
    DIRECT_ANSWER = "direct_answer"
    CONFIRMING = "confirming"
    CLOSING = "closing"
    SECURITY_OVERRIDE = "security_override"
    ERROR = "error"


class TurnAnalysis(BaseModel):
    customer_summary: str
    signal: CustomerSignal
    confidence: float = 0.5
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    suggested_visible_ack: Optional[str] = None


class PolicyDecision(BaseModel):
    reply_kind: ReplyKind = ReplyKind.NORMAL
    requires_visible_ack: bool = True
    allow_multiple_questions: bool = False
    is_security_override: bool = False
    safety_flags: list[str] = Field(default_factory=list)


class ReplyPlan(BaseModel):
    kind: ReplyKind = ReplyKind.NORMAL
    analysis: TurnAnalysis
    ack_point: Optional[str] = None
    direct_answer: Optional[str] = None
    next_question: Optional[str] = None
    body: Optional[str] = None
    raw_reply: Optional[str] = None
    safety_flags: list[str] = Field(default_factory=list)
    requires_visible_ack: bool = True
    allow_multiple_questions: bool = False
    is_security_override: bool = False


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: str = "warning"


class ComposedReply(BaseModel):
    text: str
    analysis: TurnAnalysis
    issues: list[ValidationIssue] = Field(default_factory=list)
    repaired: bool = False


_QUESTION_SLOT_PREFIX_RE = re.compile(
    r"^\s*(anh|chị|em|mình|cho em|em xin|xin)\b.*\?",
    re.IGNORECASE | re.UNICODE,
)
_BANNED_NAME_PRAISE_RE = re.compile(
    r"cái\s+tên\b.{0,80}\bnghe\s+rất\b",
    re.IGNORECASE | re.UNICODE,
)
_LOCAL_CLAIM_RE = re.compile(
    r"\b(khu vực|ecopark|hà đông|thanh xuân|hưng yên|hà nội|tp\.?\s*hcm)"
    r".{0,120}\b(hạ tầng|phát triển|tiềm năng|công trình hiện đại|khách hàng kỹ tính|"
    r"mật độ cư dân|giao thương|trung tâm)\b",
    re.IGNORECASE | re.UNICODE,
)
_ADDRESS_CLARIFY_RE = re.compile(
    r"(thuộc\s+tỉnh/thành|thuộc\s+tỉnh|thuộc\s+thành\s+phố|đúng\s+không)",
    re.IGNORECASE | re.UNICODE,
)
_PROFANITY_RE = re.compile(
    r"\b(mẹ\s*mày|me\s*may|địt|dit|đm|dm|đéo|deo|vãi|wtf|cút|ngu)\b",
    re.IGNORECASE | re.UNICODE,
)
_JOKING_TESTING_RE = re.compile(
    r"\b(a\s*lô|a\s*lo|alo|test|tét|tet|thử|thu|wtf|ví\s*dụ|vi\s*du|"
    r"chịu\s*đấy|chiu\s*day|haha|hihi|đùa|dua|em\s*xinh|"
    r"đi\s*cafe|di\s*cafe|đi\s+chơi|di\s+choi)\b",
    re.IGNORECASE | re.UNICODE,
)
_OFF_TOPIC_RE = re.compile(
    r"\b(thời\s*tiết|bóng\s*đá|nhậu|golf|chứng\s*khoán|crypto|coin)\b",
    re.IGNORECASE | re.UNICODE,
)


def analyze_turn(
    message: str,
    session: SessionState,
    profile: DealerProfileRaw,
    stage_before: Stage,
) -> TurnAnalysis:
    """Classify the customer turn into a broad reusable signal."""
    msg = (message or "").strip()
    folded = _fold_vn(msg)
    risk_flags: list[str] = []

    if not msg:
        return _analysis(CustomerSignal.UNKNOWN, "Khách chưa gửi nội dung rõ.", 0.3)

    if detect_technical_inquiry(msg, current_slot=session.current_slot):
        return _analysis(
            CustomerSignal.TECHNICAL_INQUIRY,
            "Khách đang hỏi ngoài phạm vi thu thập thông tin.",
            0.85,
            "Phần này em không tư vấn chuyên môn trực tiếp được.",
        )

    if is_personal_abuse(msg) or _PROFANITY_RE.search(folded):
        return _analysis(
            CustomerSignal.ANGRY,
            "Khách đang khó chịu hoặc dùng lời nặng.",
            0.9,
            "Em hiểu anh đang khó chịu.",
            ["abusive_or_angry"],
        )

    if _looks_like_correction(folded):
        return _analysis(
            CustomerSignal.CORRECTION,
            "Khách đang sửa lại thông tin đã nói trước đó.",
            0.8,
            "Em hiểu anh đang sửa lại thông tin trước đó.",
        )

    if _JOKING_TESTING_RE.search(folded):
        return _analysis(
            CustomerSignal.JOKING_TESTING,
            "Khách đang thử bot, đùa hoặc nói ngoài flow.",
            0.75,
            "Em hiểu anh đang thử em một chút.",
            ["joking_or_testing"],
        )

    intent = detect_intent(msg)
    if intent == Intent.DEFENSIVE:
        return _analysis(
            CustomerSignal.SKEPTICAL,
            "Khách đang nghi ngờ hoặc cần được giải thích rõ.",
            0.85,
            "Em hiểu anh cần chắc chắn trước khi chia sẻ thêm.",
        )
    if intent == Intent.CONFUSION:
        return _analysis(
            CustomerSignal.CONFUSED,
            "Khách chưa hiểu câu hỏi hoặc mục đích đang hỏi.",
            0.8,
            "Em hiểu đoạn này anh chưa rõ.",
        )
    if intent == Intent.REFUSAL:
        return _analysis(
            CustomerSignal.REFUSAL,
            "Khách chưa muốn chia sẻ phần đang hỏi.",
            0.8,
            "Em hiểu là anh chưa tiện chia sẻ phần đó.",
        )
    if intent == Intent.AFFIRMATIVE:
        return _analysis(
            CustomerSignal.AFFIRMATIVE,
            "Khách đang xác nhận hoặc đồng ý tiếp tục.",
            0.75,
            "Dạ vâng.",
        )
    if intent == Intent.TAM_SU:
        return _analysis(
            CustomerSignal.SMALLTALK,
            "Khách đang chia sẻ chuyện ngoài dữ liệu chính.",
            0.7,
            "Em nghe anh chia sẻ rồi.",
        )

    if _OFF_TOPIC_RE.search(folded):
        return _analysis(
            CustomerSignal.OFF_TOPIC,
            "Khách đang nói ngoài mục tiêu thu thập thông tin.",
            0.7,
            "Em nghe anh nói rồi.",
        )

    if not is_meaningful_short(msg) and is_garbage(msg):
        risk_flags.append("garbage")
        return _analysis(
            CustomerSignal.UNKNOWN,
            "Khách gửi nội dung chưa rõ nghĩa.",
            0.45,
            "Em chưa nắm chắc ý anh ở đoạn này.",
            risk_flags,
        )

    if stage_before == Stage.ASKING and session.current_slot:
        return _analysis(
            CustomerSignal.DATA_ANSWER,
            "Khách có vẻ đang trả lời câu hỏi hiện tại.",
            0.65,
        )

    return _analysis(
        CustomerSignal.UNKNOWN,
        "Chưa phân loại chắc ý của khách.",
        0.45,
        "Em chưa nắm chắc ý anh ở đoạn này.",
    )


def compose_and_validate_reply(
    raw_reply: str,
    message: str,
    session: SessionState,
    profile: DealerProfileRaw,
    stage_before: Stage,
    *,
    is_security_override: bool = False,
) -> ComposedReply:
    """Adapter entrypoint: raw handler text -> analyzed, composed, validated text."""
    analysis = analyze_turn(message, session, profile, stage_before)
    decision = decide_policy(
        raw_reply=raw_reply or "",
        analysis=analysis,
        session=session,
        stage_before=stage_before,
        is_security_override=is_security_override,
    )
    plan = ReplyPlan(
        kind=decision.reply_kind,
        analysis=analysis,
        raw_reply=raw_reply or "",
        safety_flags=decision.safety_flags,
        requires_visible_ack=decision.requires_visible_ack,
        allow_multiple_questions=decision.allow_multiple_questions,
        is_security_override=decision.is_security_override,
    )
    text = compose_reply(plan, session)
    issues = validate_reply(text, plan, session, profile)
    repaired = text != (raw_reply or "").strip()
    if issues:
        repaired_text = repair_reply(text, plan, session, profile, issues)
        if repaired_text != text:
            repaired = True
            text = repaired_text
            issues = validate_reply(text, plan, session, profile)
    if issues and _has_blocking_issue(issues):
        text = fallback_reply(plan, session)
        repaired = True
        issues = validate_reply(text, plan, session, profile)
    return ComposedReply(text=text, analysis=analysis, issues=issues, repaired=repaired)


def decide_policy(
    raw_reply: str,
    analysis: TurnAnalysis,
    session: SessionState,
    stage_before: Stage,
    *,
    is_security_override: bool = False,
) -> PolicyDecision:
    """Choose reply policy from turn analysis and current legacy output."""
    return PolicyDecision(
        reply_kind=_infer_reply_kind(raw_reply, stage_before, session),
        requires_visible_ack=stage_before not in (Stage.GREETING, Stage.DONE),
        is_security_override=is_security_override,
        safety_flags=list(analysis.risk_flags),
    )


def compose_reply(plan: ReplyPlan, session: SessionState) -> str:
    """Compose a reply while preserving current handler output when valid."""
    raw = (plan.raw_reply or "").strip()
    if not raw:
        return fallback_reply(plan, session)
    if plan.is_security_override:
        return raw
    if _should_replace_address_clarify(raw, plan):
        return _ack_with_current_question(plan, session)
    if _should_prefix_ack(raw, plan):
        ack = plan.ack_point or plan.analysis.suggested_visible_ack
        if ack:
            return f"{ack.strip()}\n\n{raw}"
    return raw


def validate_reply(
    text: str,
    plan: ReplyPlan,
    session: SessionState,
    profile: DealerProfileRaw,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not text.strip():
        return [ValidationIssue(code="empty_reply", message="Reply is empty", severity="error")]
    if not plan.allow_multiple_questions and text.count("?") > 1:
        issues.append(ValidationIssue(code="too_many_questions", message="Reply has more than one question"))
    if _BANNED_NAME_PRAISE_RE.search(text):
        issues.append(ValidationIssue(code="banned_name_praise", message="Reply uses banned name-praise pattern"))
    if _LOCAL_CLAIM_RE.search(text):
        issues.append(ValidationIssue(code="unsupported_local_claim", message="Reply makes unsupported local claim"))
    if _should_replace_address_clarify(text, plan):
        issues.append(ValidationIssue(code="bad_address_clarify", message="Bad signal was treated as address data"))
    if (
        plan.requires_visible_ack
        and not plan.is_security_override
        and _needs_visible_ack(plan.analysis)
        and not _has_visible_ack(text, plan.analysis)
    ):
        issues.append(ValidationIssue(code="missing_customer_ack", message="Reply does not reflect customer turn"))
    if _asks_filled_current_slot(text, session, profile):
        issues.append(ValidationIssue(code="asks_filled_slot", message="Reply appears to ask an already-filled slot"))
    return issues


def repair_reply(
    text: str,
    plan: ReplyPlan,
    session: SessionState,
    profile: DealerProfileRaw,
    issues: list[ValidationIssue],
) -> str:
    codes = {i.code for i in issues}
    if "bad_address_clarify" in codes:
        return _ack_with_current_question(plan, session)
    if "banned_name_praise" in codes:
        return _replace_first_paragraph(
            text,
            "Em ghi nhận tên anh và tên cửa hàng rồi ạ.",
        )
    if "unsupported_local_claim" in codes:
        return _replace_first_paragraph(text, _location_ack(profile))
    if "missing_customer_ack" in codes:
        ack = plan.analysis.suggested_visible_ack
        if ack and not text.startswith(ack):
            return f"{ack}\n\n{text.strip()}"
    if "too_many_questions" in codes:
        return _keep_only_last_question(text)
    return text


def fallback_reply(plan: ReplyPlan, session: SessionState) -> str:
    ack = plan.analysis.suggested_visible_ack or "Em ghi nhận ý anh rồi."
    question = _current_slot_question(session)
    if question:
        return f"{ack}\n\n{question}"
    return ack


def _analysis(
    signal: CustomerSignal,
    summary: str,
    confidence: float,
    suggested_ack: Optional[str] = None,
    risk_flags: Optional[list[str]] = None,
) -> TurnAnalysis:
    return TurnAnalysis(
        customer_summary=summary,
        signal=signal,
        confidence=confidence,
        suggested_visible_ack=suggested_ack,
        risk_flags=risk_flags or [],
    )


def _infer_reply_kind(raw_reply: str, stage_before: Stage, session: SessionState) -> ReplyKind:
    text = raw_reply or ""
    if stage_before == Stage.CONFIRMING:
        return ReplyKind.CONFIRMING
    if session.stage == Stage.DONE:
        return ReplyKind.CLOSING
    if _ADDRESS_CLARIFY_RE.search(text):
        return ReplyKind.CLARIFY
    if _QUESTION_SLOT_PREFIX_RE.search(text.strip()):
        return ReplyKind.RETRY
    return ReplyKind.NORMAL


def _needs_visible_ack(analysis: TurnAnalysis) -> bool:
    return analysis.signal in {
        CustomerSignal.ANGRY,
        CustomerSignal.JOKING_TESTING,
        CustomerSignal.OFF_TOPIC,
        CustomerSignal.UNKNOWN,
        CustomerSignal.SKEPTICAL,
        CustomerSignal.CONFUSED,
        CustomerSignal.REFUSAL,
        CustomerSignal.TECHNICAL_INQUIRY,
    }


def _should_prefix_ack(raw_reply: str, plan: ReplyPlan) -> bool:
    if not plan.requires_visible_ack or plan.is_security_override:
        return False
    if not _needs_visible_ack(plan.analysis):
        return False
    return not _has_visible_ack(raw_reply, plan.analysis)


def _has_visible_ack(text: str, analysis: TurnAnalysis) -> bool:
    low = _fold_vn(text)
    signal = analysis.signal
    if signal == CustomerSignal.ANGRY:
        return any(p in low for p in ("kho chiu", "buc", "lam phien", "xin loi", "nang loi"))
    if signal == CustomerSignal.JOKING_TESTING:
        return any(p in low for p in ("thu em", "thu", "dua", "quay lai", "cong viec", "alo", "nghe day"))
    if signal == CustomerSignal.SKEPTICAL:
        return any(p in low for p in ("khong lua dao", "khong mat phi", "bao mat", "yen tam", "chac chan"))
    if signal == CustomerSignal.CONFUSED:
        return any(p in low for p in ("chua ro", "khong hieu", "y em", "em giai thich", "doan nay"))
    if signal == CustomerSignal.REFUSAL:
        return any(p in low for p in ("chua tien", "khong tien", "bo qua", "hoi sau", "khong sao"))
    if signal == CustomerSignal.TECHNICAL_INQUIRY:
        return any(p in low for p in ("chuyen team", "chuyen mon", "khong tu van", "tu van ky"))
    if signal == CustomerSignal.OFF_TOPIC:
        return any(p in low for p in ("em nghe", "quay lai", "phan thong tin"))
    if signal == CustomerSignal.UNKNOWN:
        return any(
            p in low
            for p in (
                "chua ro",
                "chua nghe ro",
                "chua nam",
                "noi lai",
                "thu nhan lai",
                "em nghe",
                "cap nhat",
                "sua lai",
                "ghi lai",
                "ghi nhan",
                "khong ep",
                "uy tin",
                "tu tim den",
                "khach tu tim",
            )
        )
    return True


def _should_replace_address_clarify(raw_reply: str, plan: ReplyPlan) -> bool:
    if not _ADDRESS_CLARIFY_RE.search(raw_reply or ""):
        return False
    return plan.analysis.signal in {
        CustomerSignal.ANGRY,
        CustomerSignal.JOKING_TESTING,
        CustomerSignal.OFF_TOPIC,
        CustomerSignal.UNKNOWN,
        CustomerSignal.REFUSAL,
        CustomerSignal.SKEPTICAL,
        CustomerSignal.CONFUSED,
    }


def _ack_with_current_question(plan: ReplyPlan, session: SessionState) -> str:
    ack = plan.analysis.suggested_visible_ack or "Em chưa nắm chắc ý anh ở đoạn này."
    question = _current_slot_question(session)
    if question:
        return f"{ack}\n\n{question}"
    return ack


def _current_slot_question(session: SessionState) -> Optional[str]:
    try:
        from app.core._conv_helpers import get_slot_question_for_attempt

        return get_slot_question_for_attempt(session.current_slot, session)
    except Exception:
        return None


def _asks_filled_current_slot(text: str, session: SessionState, profile: DealerProfileRaw) -> bool:
    if not session.current_slot or not text:
        return False
    try:
        from app.slots.definitions import SLOT_TO_ALL_FIELDS
    except Exception:
        return False
    fields = SLOT_TO_ALL_FIELDS.get(session.current_slot, [])
    if not fields:
        return False
    has_value = False
    for field in fields:
        value = getattr(profile, field, None)
        if value is None or value == "" or value == []:
            continue
        has_value = True
        break
    if not has_value:
        return False
    question = _current_slot_question(session)
    if not question:
        return False
    return _fold_vn(question[:30]) in _fold_vn(text)


def _replace_first_paragraph(text: str, replacement: str) -> str:
    parts = text.strip().split("\n\n", 1)
    if len(parts) == 1:
        return replacement
    return f"{replacement}\n\n{parts[1].strip()}"


def _location_ack(profile: DealerProfileRaw) -> str:
    location = profile.address or profile.province or profile.district
    if location:
        return f"Em ghi nhận cửa hàng mình ở {location} rồi ạ."
    return "Em ghi nhận khu vực rồi ạ."


def _keep_only_last_question(text: str) -> str:
    stripped = text.strip()
    if stripped.count("?") <= 1:
        return stripped
    last_q = stripped.rfind("?")
    before = stripped[:last_q]
    prev_q = before.rfind("?")
    if prev_q == -1:
        return stripped
    return (before[:prev_q].rstrip("? ").strip() + "\n\n" + before[prev_q + 1:].strip() + "?").strip()


def _has_blocking_issue(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)


def _looks_like_correction(folded_message: str) -> bool:
    patterns = (
        "khong phai",
        "sai roi",
        "ghi sai",
        "nham",
        "chinh lai",
        "sua lai",
        "moi dung",
    )
    return any(p in folded_message for p in patterns)


def _fold_vn(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D").casefold()
