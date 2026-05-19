"""Chat endpoint v8 — POST /api/chat.

Refer:
- F2C.1 — session lifecycle
- F2A.1 — stage transitions
- KE_HOACH action 21
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.conversation import handle_message, start_session
from app.core.session import create_session
from app.llm.client import LLMClient, get_default_client
from app.models.schema import DealerProfileRaw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ============================================================
# Request / Response models
# ============================================================


class ChatRequest(BaseModel):
    """Incoming chat message."""
    session_id: Optional[str] = None      # None → tạo session mới
    message: str = ""                     # Empty OK khi session_id=None (init turn)
    channel: str = "web"
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat reply + session_id (cho dealer track)."""
    session_id: str
    reply: str
    stage: str
    current_slot: Optional[str] = None
    is_first_turn: bool = False           # True nếu vừa tạo session (return greeting)


# ============================================================
# Endpoint
# ============================================================


def _get_store():
    """Lazy import store + singleton — refer KE_HOACH § 0.4."""
    from app.config import get_settings
    from app.storage.sqlite_store import SQLiteStore

    if not hasattr(_get_store, "_instance"):
        settings = get_settings()
        _get_store._instance = SQLiteStore(settings.SQLITE_PATH)
    return _get_store._instance


@router.post("/chat", response_model=ChatResponse)
def post_chat(req: ChatRequest) -> ChatResponse:
    """Chat endpoint.

    Flow:
    1. Rate limit check (Phase 4 R4) — IP / session
    2. Load (hoặc tạo) session + profile từ DB
    3. Nếu session mới: return greeting (is_first_turn=True)
    4. Nếu session có: call handle_message → reply (qua PII guard)
    5. Save session + profile back to DB
    6. Admin queue trigger
    """
    # Empty message OK khi tạo session mới (init turn — trả greeting)
    # Nhưng KHÔNG OK khi session_id có (đang trong flow)
    if req.session_id and (not req.message or not req.message.strip()):
        raise HTTPException(400, detail="Message rỗng")

    # Phase 4 R4: Rate limit — refer F2C.2
    from app.config import get_settings as _get_cfg
    from app.guards.rate_limit import check_rate_limit
    cfg = _get_cfg()
    rate_key = f"session:{req.session_id}" if req.session_id else f"ip:{req.ip_address or 'unknown'}"
    allowed, retry_after = check_rate_limit(
        rate_key,
        max_requests=cfg.RATE_LIMIT_MSG_PER_MINUTE,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry sau {retry_after:.0f}s.",
            headers={"Retry-After": str(int(retry_after))},
        )

    store = _get_store()
    client: LLMClient = get_default_client()

    # ----- Tạo session mới hoặc load existing -----
    session_id = req.session_id
    is_first_turn = False
    if not session_id:
        # Session mới
        session = create_session(
            channel=req.channel,
            ip_address=req.ip_address,
            user_agent=req.user_agent,
        )
        profile = DealerProfileRaw()
        # Render greeting + append vào history (để admin xem được full conversation)
        from datetime import datetime, timezone
        from app.models.schema import HistoryMessage

        greeting = start_session(session)
        session.history.append(
            HistoryMessage(
                role="bot",
                content=greeting,
                ts=datetime.now(timezone.utc),
            )
        )
        store.save_session(session)
        store.save_profile(session.session_id, profile)
        return ChatResponse(
            session_id=session.session_id,
            reply=greeting,
            stage=session.stage.value,
            current_slot=session.current_slot,
            is_first_turn=True,
        )

    # Load session existing
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, detail=f"Session {session_id} không tồn tại")
    profile = store.get_profile(session_id) or DealerProfileRaw()

    # ----- Process message -----
    reply, session, profile = handle_message(
        session=session,
        profile=profile,
        message=req.message,
        client=client,
    )

    # ----- G4: PII leak guard (Phase 4 R3) -----
    # Scan reply có chứa PII từ session khác không (cross-session leak).
    # Nếu hit → log error + override reply + flag (admin queue HIGH).
    from app.llm.intent_classifier import check_pii_leak
    from app.admin.queue import increment_flag_count
    from app.models.enums import Flag

    leaked = check_pii_leak(reply, session.session_id, store)
    if leaked:
        increment_flag_count(session, Flag.PII_LEAK)
        # Override reply với safe response (KHÔNG show leaked data)
        reply = (
            "Dạ em xin lỗi, em đang có chút trục trặc. Anh nhắn lại "
            "giúp em sau ít phút nhé."
        )
        # Update last bot message in history (đã append trong handle_message)
        if session.history and session.history[-1].role == "bot":
            session.history[-1].content = reply

    # ----- Save -----
    store.save_session(session)
    store.save_profile(session_id, profile)

    # ----- Admin queue trigger (sau save để tránh FK constraint) -----
    from app.admin.queue import trigger_queue_if_needed
    trigger_queue_if_needed(session, profile, store)
    # Save lại session sau khi update queue_triggers_fired
    store.save_session(session)

    return ChatResponse(
        session_id=session.session_id,
        reply=reply,
        stage=session.stage.value,
        current_slot=session.current_slot,
        is_first_turn=False,
    )


@router.get("/chat/{session_id}/status")
def get_session_status(session_id: str) -> dict:
    """Lightweight status check cho frontend (poll/debug)."""
    store = _get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, detail="Session không tồn tại")
    return {
        "session_id": session.session_id,
        "stage": session.stage.value,
        "current_slot": session.current_slot,
        "turn_count": session.turn_count,
        "confirmation_status": session.confirmation_status.value,
        "flags": [f.value for f in session.flags],
    }
