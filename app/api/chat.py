"""Chat endpoint — channel-agnostic. Sau Zalo OA cũng plug vào đây."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_conversation_service
from app.core.conversation import ConversationService
from app.models.schema import ChatRequest, ChatResponse, Stage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ChatResponse:
    try:
        session, bot_msg = service.handle_message(payload.session_id, payload.message)
    except Exception:
        # Log đầy đủ ở server, KHÔNG echo exception ra client.
        # Tránh leak path file, biến config, hay key qua trace string.
        logger.exception("Chat handler error")
        raise HTTPException(
            status_code=500,
            detail="Em đang gặp lỗi kỹ thuật, anh thử lại giúp em sau ít phút nhé ạ.",
        )

    return ChatResponse(
        session_id=session.session_id,
        bot_message=bot_msg,
        stage=session.stage,
        profile_snapshot=session.profile_raw,
        messages=session.messages,
        done=session.stage == Stage.DONE,
    )
