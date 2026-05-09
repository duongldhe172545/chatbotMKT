"""Pydantic schemas — mirror mục 10 và 11 trong tài liệu MVP."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["LOW", "MEDIUM", "HIGH"]


class DealerProfileRaw(BaseModel):
    """Schema mục 10 — bản profile RAW chưa human review."""
    dealer_name: str | None = None
    owner_name: str | None = None
    phone_or_zalo: str | None = None
    province: str | None = None
    district: str | None = None
    main_category: str | None = None
    dealer_type: str | None = None
    customer_base_estimate: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    dl0_priority: list[str] = Field(default_factory=list)
    recommended_group: str | None = None
    confirmation_status: Literal["PENDING", "CONFIRMED", "EDITED"] = "PENDING"
    review_status: Literal["RAW", "UNDER_REVIEW", "APPROVED", "REJECTED"] = "RAW"
    flags: list[str] = Field(default_factory=list)


class ExtractResult(BaseModel):
    """Output extractor mục 11 — voice_intake_result với 3 lớp:
    raw_transcript / cleaned_summary / extracted_fields + confidence + missing + confirm.
    """
    raw_transcript: str = ""  # Toàn bộ tin nhắn dealer ghép lại (không qua LLM)
    cleaned_summary: str = ""
    extracted_fields: dict = Field(default_factory=dict)
    confidence: dict[str, ConfidenceLevel] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    confirm_questions: list[str] = Field(default_factory=list)


class Stage(str, Enum):
    GREETING = "GREETING"
    ASKING = "ASKING"
    CONFIRMING = "CONFIRMING"
    DONE = "DONE"


class ChatRole(str, Enum):
    BOT = "bot"
    DEALER = "dealer"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    ts: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    session_id: str
    stage: Stage = Stage.GREETING
    messages: list[ChatMessage] = Field(default_factory=list)
    profile_raw: DealerProfileRaw = Field(default_factory=DealerProfileRaw)
    confidence: dict[str, ConfidenceLevel] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    current_question_idx: int = 0
    # Track số lần đã hỏi mỗi field — sau MAX_RETRY thì skip để không loop vô tận
    field_attempts: dict[str, int] = Field(default_factory=dict)
    skipped_fields: list[str] = Field(default_factory=list)
    # Re-ask logic: khi field bị skip, lưu count field đã fill tại thời điểm skip.
    # Sau khi dealer fill thêm ≥2 field NEW (signal cooperation) → field skip
    # được phép hỏi lại 1 lần (ghi vào skipped_retried để không loop).
    skipped_at_filled_count: dict[str, int] = Field(default_factory=dict)
    skipped_retried: list[str] = Field(default_factory=list)
    # Cờ tích luỹ qua các turn (abuse, prompt injection, escalation, ...)
    flag_history: list[str] = Field(default_factory=list)
    # Nhóm cụm mở đầu của turn bot gần nhất (A/B/C/D/X) — dùng để inject
    # directive "TURN NÀY CẤM nhóm X" vào extractor prompt, ép luân phiên.
    last_opener_group: str | None = None
    # True nếu phone của dealer match profile cũ → bot greet kiểu returning.
    is_returning_dealer: bool = False
    # Xưng hô: "anh" (mặc định) hoặc "chị" (sau khi detect dealer là nữ).
    # Một khi chốt → giữ nhất quán suốt phiên.
    address_form: str = "anh"
    # Spam protection — Layer 1+5
    llm_call_count: int = 0  # tổng số LLM call đã dùng trong session
    quota_warned: bool = False  # đã cảnh báo tại ngưỡng 30 chưa
    mode: Literal["normal", "template_only", "soft_ended"] = "normal"
    consecutive_clean_messages: int = 0  # đếm clean msg để recovery template_only
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# API request/response
class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    # Max 1000 chars/message — chống spam tốn token. Pydantic reject với
    # 422 nếu vượt. Dealer chat tự nhiên hiếm khi vượt 500 chars/turn.
    message: str = Field(max_length=1000)
    # Idempotency key (frontend tự sinh UUID) — chống double-submit do
    # network retry / multi-tab. Optional vì client cũ không có vẫn chạy.
    message_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    session_id: str
    bot_message: str
    stage: Stage
    profile_snapshot: DealerProfileRaw
    messages: list[ChatMessage] = Field(default_factory=list)
    done: bool = False
