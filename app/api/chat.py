"""Chat endpoint — channel-agnostic. Sau Zalo OA cũng plug vào đây.

Concurrency:
- Per-session lock: 2 request cùng session_id sẽ serialize.
- Idempotency cache: msg_id duplicate → trả cached response, không gọi LLM.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_conversation_service
from app.core.concurrency import get_session_lock, idem_get, idem_set
from app.core.conversation import ConversationService
from app.models.schema import ChatRequest, ChatResponse, Stage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ChatResponse:
    # Idempotency check — duplicate request (network retry / multi-tab) trả
    # cached response, không gọi LLM.
    if payload.message_id:
        cached = idem_get(payload.message_id)
        if cached is not None:
            return cached

    # Per-session lock — chống race khi 2 request cùng session_id song song.
    # Lock theo session_id (hoặc "new" nếu chưa có) — khác session KHÔNG block.
    lock_key = payload.session_id or "_new_session"
    with get_session_lock(lock_key):
        try:
            session, bot_msg = service.handle_message(
                payload.session_id, payload.message
            )
        except Exception:
            # Log đầy đủ ở server, KHÔNG echo exception ra client.
            logger.exception("Chat handler error")
            raise HTTPException(
                status_code=500,
                detail="Em đang gặp lỗi kỹ thuật, anh thử lại giúp em sau ít phút nhé ạ.",
            )

    response = ChatResponse(
        session_id=session.session_id,
        bot_message=bot_msg,
        stage=session.stage,
        profile_snapshot=session.profile_raw,
        messages=session.messages,
        done=session.stage == Stage.DONE,
    )

    # Cache response cho msg_id (5 phút TTL) → request lặp sẽ hit cache.
    if payload.message_id:
        idem_set(payload.message_id, response)
    return response
