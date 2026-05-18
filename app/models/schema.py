"""Em Linh MKT v8 — Pydantic schemas.

Refer:
- F2A.3 (LUAT_2A_core v0.2.4) — schema 4 scope
- F2C.1 (LUAT_2C_infra v0.1.4) — DB 3 bảng
- CORE § H.1 v3.0.5 — 28 trường Scope 1+2 (6 REQUIRED + 16 OPTIONAL + 6 RAW + 12 derive)

Note: Pydantic KHÔNG enforce REQUIRED ở schema level. REQUIRED field trong
Scope 1 (slot 1.1/1.2/1.3/2.1/2.2/4.0) có thể null nếu SKIP với flag
`required_missing` — sanity check 5-point F2A.7 job để validate.

Scope 4 (c1..c9, c_score, tier, dealer_id) KHÔNG ở đây — Backend Scoring
service riêng (STRATEGY D7).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AddressForm,
    Channel,
    ConfirmationStatus,
    DealerType,
    Flag,
    Priority,
    QueueStatus,
    ReviewStatus,
    Stage,
)


def _utcnow() -> datetime:
    """Helper: datetime.now(timezone.utc) — replaces deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


# ============================================================
# Sub-models cho state tracking
# ============================================================


class SlotAttempts(BaseModel):
    """Tracker per-slot retry. Refer D11 STRATEGY + F2A.4 step 2.7.

    `consecutive`: reset = 0 sau ADVANCE hoặc DEFER (sau khi gác slot)
    `total`: tăng qua mỗi RETRY hoặc DEFER, hardcap = MAX_RETRY_TOTAL (3)
    """
    consecutive: int = 0
    total: int = 0


class DeferredSlot(BaseModel):
    """Slot tạm gác sau 2-lần-liên-tiếp chưa fill. Refer F2A.4 step 2.7-2.8."""
    defer_at_turn: int
    recheck_after_n_slots: int = 2     # Config DEFER_RECHECK_AFTER_N_SLOTS


class HistoryMessage(BaseModel):
    """1 message trong history. Role: 'dealer' / 'bot'."""
    role: str
    content: str
    ts: datetime


class DealerTypeHistoryEntry(BaseModel):
    """Detect dealer type per turn. Refer F2A.6 turn 3/8/13."""
    turn: int
    dealer_type: DealerType


# ============================================================
# Scope 1 + 2 — DealerProfileRaw
# 6 REQUIRED + 16 OPTIONAL + 6 RAW SIGNAL (Scope 1) + 12 auto-derive (Scope 2)
# = 28 + 12 = 40 trường (cộng metadata 2 + session_id FK ở DB layer)
# ============================================================


class DealerProfileRaw(BaseModel):
    """Schema profile RAW dealer.

    Refer: CORE § H.1 + F2A.3 + KE_HOACH § 2.1 + DB schema F2C.1 (3 bảng).
    """
    # ================================================================
    # SCOPE 1: chatbot thu trực tiếp qua 17 slot
    # ================================================================

    # ----- REQUIRED (6) — sanity check F2A.7 validate -----
    dealer_name: Optional[str] = None              # slot 1.1
    owner_name: Optional[str] = None               # slot 1.1
    address: Optional[str] = None                  # slot 1.2
    phone_or_zalo: Optional[str] = None            # slot 1.3 (digits-only, len 9-11)
    main_product: Optional[str] = None             # slot 2.1
    brandkit_consent: Optional[str] = None         # slot 4.0 — "yes" / "no"

    # ----- OPTIONAL (16) — "không biết" → null + flag dealer_declined -----
    category_stack: list[str] = Field(default_factory=list)    # slot 2.1
    business_model_signal: Optional[str] = None                # slot 2.2
    est_team_size: Optional[int] = None                        # slot 2.3
    team_stability_signal: Optional[str] = None                # slot 2.3
    supplier_brands: list[str] = Field(default_factory=list)   # slot 2.4
    customer_segment_signal: Optional[str] = None              # slot 2.4
    zalo: Optional[str] = None                                 # slot 2.5
    facebook: Optional[str] = None                             # slot 2.6
    primary_contact_channel: Optional[str] = None              # slot 2.5
    fb_marketing_status: Optional[str] = None                  # slot 2.6
    customer_old_percentage: Optional[str] = None              # slot 3.1
    customer_storage_method: Optional[str] = None              # slot 3.2
    customer_pain: Optional[str] = None                        # slot 3.3 (open question text dài)
    payment_terms_signal: Optional[str] = None                 # slot 3.4
    color_accent: Optional[str] = None                         # slot 4.2
    feng_shui_signal: Optional[str] = None                     # slot 4.2

    # ----- RAW SIGNAL (6) — mining cho Backend Scoring chấm C1-C9 -----
    local_dominance_signal: Optional[str] = None               # C6 (slot 1.2)
    supplier_negotiation_signal: Optional[str] = None          # C8 (slot 2.4)
    community_network_signal: Optional[str] = None             # C9 (slot 2.6)
    motivation_signal: Optional[str] = None                    # C5 (slot 3.3)
    warranty_responsibility_signal: Optional[str] = None       # C4 NEW (slot 3.5)
    usp_signal: Optional[str] = None                           # bonus slogan (slot 3.3)

    # ================================================================
    # SCOPE 2: chatbot auto-derive (parse + LLM gen)
    # ================================================================
    province: Optional[str] = None                             # parse từ address
    district: Optional[str] = None                             # parse từ address
    main_category: Optional[str] = None                        # enum chuẩn hóa từ main_product (LLM auto-derive Phase 2)
    dealer_type: Optional[str] = None                          # enum dai_ly/chu_xuong/...

    brand_name_short: Optional[str] = None                     # LLM rút gọn
    initials_full: Optional[str] = None
    initial_single: Optional[str] = None
    contact_name: Optional[str] = None                         # default = owner_name
    contact_role: str = "Chủ cửa hàng"                         # fix default
    hotline: Optional[str] = None                              # default = phone_or_zalo
    slogan_options: list[str] = Field(default_factory=list)    # LLM gen 5 phương án


# ============================================================
# Scope 3 — SessionState (state machine + history)
# Refer F2A.1 + F2C.1
# ============================================================


class SessionState(BaseModel):
    """State machine + lifecycle metadata."""
    session_id: str                                            # uuid v4
    stage: Stage = Stage.GREETING
    current_slot: Optional[str] = None                         # vd "2.3"

    # Retry tracking — refer D11 + F2A.4
    slot_attempts: dict[str, SlotAttempts] = Field(default_factory=dict)
    deferred_slots: dict[str, DeferredSlot] = Field(default_factory=dict)
    skipped_slots: list[str] = Field(default_factory=list)

    # Flags + admin tracking (15 enum)
    flags: list[Flag] = Field(default_factory=list)

    # Dealer type detection — refer F2A.6
    detected_dealer_type: Optional[DealerType] = None
    dealer_type_history: list[DealerTypeHistoryEntry] = Field(default_factory=list)

    # Confirmation + review status
    confirmation_status: ConfirmationStatus = ConfirmationStatus.PENDING
    review_status: ReviewStatus = ReviewStatus.RAW

    # History + counter
    history: list[HistoryMessage] = Field(default_factory=list)
    turn_count: int = 0
    paused_for: Optional[str] = None                           # None / "defensive" / "tam_su"

    # Persona config
    address_form: AddressForm = AddressForm.ANH

    # Lifecycle timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None

    # Source
    channel: Channel = Channel.WEB
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# ============================================================
# Admin queue entry (F2C.8)
# ============================================================


class AdminQueueEntry(BaseModel):
    """Entry trong admin queue cho human review. Refer F2C.8."""
    queue_id: str                                  # uuid v4
    session_id: str
    trigger: Flag                                  # 15 enum
    priority: Priority
    status: QueueStatus = QueueStatus.PENDING
    assigned_to: Optional[str] = None              # admin username
    notes: Optional[str] = None
    profile_snapshot: Optional[DealerProfileRaw] = None
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: Optional[datetime] = None
