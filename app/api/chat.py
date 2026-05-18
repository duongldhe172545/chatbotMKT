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
    1. Load (hoặc tạo) session + profile từ DB
    2. Nếu session mới: return greeting (is_first_turn=True), client gọi lại với message
    3. Nếu session có: call handle_message → reply
    4. Save session + profile back to DB
    """
    # Empty message OK khi tạo session mới (init turn — trả greeting)
    # Nhưng KHÔNG OK khi session_id có (đang trong flow)
    if req.session_id and (not req.message or not req.message.strip()):
        raise HTTPException(400, detail="Message rỗng")

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
        store.save_session(session)
        store.save_profile(session.session_id, profile)
        # Return greeting (turn 0)
        greeting = start_session(session)
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

    # ----- Save -----
    store.save_session(session)
    store.save_profile(session_id, profile)

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
