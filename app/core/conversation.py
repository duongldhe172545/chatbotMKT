"""Main conversation orchestrator — F2A.1 stage dispatcher.

Refer:
- F2A.1 (LUAT_2A_core) — stage transitions
- F2A.4 — state machine decide_action
- CORE § G — khung chạy 4 stage
- KE_HOACH § action 20 — orchestrator ≤ 300 dòng

Phase 6 R2 refactor: file gốc 979 dòng → split thành submodules:
- `_conv_greeting.py`: GREETING handler + start_session
- `_conv_asking.py`: ASKING handler (extract + state machine + reply gen)
- `_conv_confirming.py`: CONFIRMING + DONE + edit handler
- `_conv_derive.py`: merge_extracted + auto-derive Scope 2
- `_conv_helpers.py`: ack/partial question/variant rotate/summarize/PAUSE fallback
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.admin.queue import increment_flag_count
from app.core._conv_asking import handle_asking
from app.core._conv_confirming import handle_confirming, handle_done
from app.core._conv_greeting import handle_greeting, start_session
from app.core.abuse_detector import (
    handle_abuse_escalation,
    is_personal_abuse,
)
from app.core.bridge_rotation import record_bridge
from app.core.closing import render_soft_end_closing
from app.core.edge_cases import (
    handle_voice_fail_escalation,
    is_voice_fail_message,
)
from app.core.garbage_detector import is_garbage, is_meaningful_short
from app.core.session import is_session_timeout, mark_session_closed, touch_session
from app.guards import (
    auto_rewrite,
    check_ack_hallucinate,
    check_parrot,
    check_prompt_injection,
    has_forbidden_scoring_vocab,
    sanitize_injection,
)
from app.llm.brand_correction import correct_stt
from app.llm.client import LLMClient
from app.models.enums import AddressForm, Channel, Flag, Stage
from app.models.schema import (
    DealerProfileRaw,
    HistoryMessage,
    SessionState,
)

__all__ = ["handle_message", "start_session"]

logger = logging.getLogger(__name__)


def handle_message(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> tuple[str, SessionState, DealerProfileRaw]:
    """Process 1 dealer message. Stage-based dispatch.

    Args:
        session: SessionState (mutated in-place)
        profile: DealerProfileRaw (mutated in-place)
        message: Text từ dealer
        client: LLMClient

    Returns:
        (reply_text, updated_session, updated_profile).

    Side effects:
        - Mutate session: turn_count, history, current_slot, stage, flags,
          flag_counts (qua guards + state machine)
        - Mutate profile: extracted fields từ message
    """
    # Lazy timeout check (1C § 9)
    if is_session_timeout(session):
        mark_session_closed(session)
        return (render_soft_end_closing(address_form=session.address_form), session, profile)

    # Touch session timestamp + increment turn
    touch_session(session)
    session.turn_count += 1

    # Voice channel preprocess (1C § 8 — Phase 4 R2)
    voice_reply = _check_voice_fail(session, message)
    if voice_reply is not None:
        now = datetime.now(timezone.utc)
        session.history.append(HistoryMessage(role="dealer", content=message, ts=now))
        session.history.append(HistoryMessage(role="bot", content=voice_reply, ts=now))
        return (voice_reply, session, profile)
    # Brand/STT correction also helps typed text in chat tests, e.g. dealer
    # corrects "ốt đo" -> Austdoor. Apply before guards/extractors.
    message = correct_stt(message) or message

    # GLOBAL address_form detection — chạy ở MỌI stage, MỌI turn.
    # Nếu dealer nói "tao là chị", "chị tên X", "em là nữ" ở bất kỳ đâu
    # (greeting, asking, confirming) → set address_form = CHI ngay lập tức.
    # Chỉ UPGRADE ANH→CHI, KHÔNG BAO GIỜ downgrade CHI→ANH.
    if session.address_form == AddressForm.ANH:
        from app.core.address_form import detect_address_form
        _detected_af = detect_address_form(message, owner_name=None)
        if _detected_af == "chị":
            session.address_form = AddressForm.CHI

    # G1: Prompt injection guard (Layer 1 regex)
    injection_match = check_prompt_injection(message)
    if injection_match:
        increment_flag_count(session, Flag.PROMPT_INJECTION)
        message = sanitize_injection(message) or message

    # Garbage input detect (1C § 7) — flag nếu lặp 2 lần cùng slot
    if (
        not is_meaningful_short(message)
        and is_garbage(message)
        and session.stage == Stage.ASKING
    ):
        count = increment_flag_count(session, Flag.GARBAGE_INPUT)
        if count >= 2:
            logger.warning(
                "Garbage input lặp ≥ 2 lần: session=%s msg=%r",
                session.session_id, message[:80],
            )

    # Personal abuse detect (1C § 5) — short-circuit
    abuse_reply: Optional[str] = None
    if is_personal_abuse(message) and session.stage == Stage.ASKING:
        increment_flag_count(session, Flag.ABUSIVE_LANGUAGE)
        abuse_reply, should_close = handle_abuse_escalation(session)
        if should_close:
            session.stage = Stage.DONE
            mark_session_closed(session)

    # Add dealer message to history
    now = datetime.now(timezone.utc)
    session.history.append(HistoryMessage(role="dealer", content=message, ts=now))

    # Nếu abuse handled, short-circuit return
    if abuse_reply is not None:
        abuse_reply = auto_rewrite(abuse_reply)
        session.history.append(HistoryMessage(role="bot", content=abuse_reply, ts=now))
        return (abuse_reply, session, profile)

    stage_before_dispatch = session.stage

    # Stage-based dispatch
    if session.stage == Stage.GREETING:
        reply = handle_greeting(session, message, client, profile=profile)
    elif session.stage == Stage.ASKING:
        reply = handle_asking(session, profile, message, client)
    elif session.stage == Stage.CONFIRMING:
        reply = handle_confirming(session, profile, message, client)
    else:  # Stage.DONE
        reply = handle_done(session=session, message=message, client=client)

    # G3: Drift guard — auto-rewrite vocab cấm trong bot reply
    if reply:
        if stage_before_dispatch == Stage.ASKING:
            reply = _soften_repeated_opening(reply, session)
        if has_forbidden_scoring_vocab(reply):
            logger.error(
                "Scoring vocab LEAK trong bot reply session=%s reply=%r",
                session.session_id, reply[:200],
            )
        reply = auto_rewrite(reply)

        # Bug 11: fix LLM missing-space (e.g. "nàyđể" → "này để")
        reply = _fix_missing_spaces(reply)

        # GLOBAL address_form post-processing — CRITICAL FIX.
        # LLM thường bỏ qua system prompt instruction về address_form.
        # Áp dụng _adapt_address_form lên TOÀN BỘ reply để đảm bảo
        # "anh" → "chị" khi session.address_form == CHI.
        from app.core._conv_helpers import _adapt_address_form
        reply = _adapt_address_form(reply, session) or reply

        # B.4 luật #2 (Phase 6 R+): parrot guard — KHÔNG lặp y nguyên
        # đoạn ≥ 4 từ liên tiếp từ dealer message. Chỉ flag để admin
        # review, không tự rewrite (LLM nên rephrase tự nhiên — code
        # rewrite có thể phá ý).
        if check_parrot(reply, message, min_ngram=4):
            increment_flag_count(session, Flag.HALLUCINATE)
            logger.warning(
                "Drift parrot detect: session=%s reply head=%r",
                session.session_id, reply[:100],
            )

        # Phase 6 R+ fix 2026-05-22 (user feedback Lỗi 6c): check ack
        # hallucinate adjective "cao cấp / sang trọng / quy mô lớn" mà
        # dealer chưa nói. Flag HALLUCINATE để admin review (KHÔNG tự
        # rewrite vì có thể phá ý câu — LLM cần được hint qua prompt).
        dealer_history_text = " ".join(
            h.content for h in session.history if h.role == "dealer" and h.content
        )
        ack_hallucinated = check_ack_hallucinate(
            ack_text=reply,
            dealer_message=message,
            dealer_history=dealer_history_text,
        )
        if ack_hallucinated:
            increment_flag_count(session, Flag.HALLUCINATE)
            logger.warning(
                "Ack hallucinate adjective: session=%s adjective=%s reply head=%r",
                session.session_id, ack_hallucinated, reply[:120],
            )

    # Record bridge phrase used (1A § 2.2)
    record_bridge(session, reply)

    # Add bot reply to history
    session.history.append(HistoryMessage(role="bot", content=reply, ts=now))

    return (reply, session, profile)


# ============================================================
# Internal helpers
# ============================================================


import re as _re

# Common Vietnamese function words that often get stuck to preceding syllable
_STUCK_WORDS = (
    "để", "mà", "và", "thì", "là", "với", "cho", "từ", "của", "này",
    "đó", "ạ", "nhé", "nha", "rồi", "được", "không", "thêm", "qua",
    "trong", "ngoài", "trên", "dưới", "cùng", "theo", "về",
)
_STUCK_PATTERN = _re.compile(
    r"([a-zà-ỹ])(" + "|".join(_re.escape(w) for w in _STUCK_WORDS) + r")\b",
    _re.IGNORECASE,
)


def _fix_missing_spaces(text: str) -> str:
    """Fix LLM missing spaces: 'nàyđể' → 'này để'."""
    if not text:
        return text
    return _STUCK_PATTERN.sub(r"\1 \2", text)


def _is_voice_channel(session: SessionState) -> bool:
    """True nếu session channel = VOICE."""
    return session.channel == Channel.VOICE


def _check_voice_fail(
    session: SessionState,
    message: str,
) -> Optional[str]:
    """Check voice fail (1C § 8). Returns voice escalation reply nếu fail, None nếu ok."""
    if not _is_voice_channel(session) or session.stage != Stage.ASKING:
        return None
    if not is_voice_fail_message(message, is_voice_channel=True):
        return None
    increment_flag_count(session, Flag.VOICE_QUALITY_POOR)
    voice_reply, should_close = handle_voice_fail_escalation(session)
    if should_close:
        session.stage = Stage.DONE
        mark_session_closed(session)
    return voice_reply


def _soften_repeated_opening(reply: str, session: SessionState) -> str:
    """Avoid every ASKING reply starting with "Dạ".

    Fix Lỗi 13: đảm bảo có dấu cách sau khi strip prefix.
    Fix Lỗi 21: mở rộng prefix list cho 'chị'.
    """
    if not reply:
        return reply
    stripped = reply.lstrip()
    if not stripped.startswith("Dạ"):
        return reply
    previous_bot = next((h.content for h in reversed(session.history) if h.role == "bot"), "")
    if not previous_bot.lstrip().startswith("Dạ"):
        return reply

    af = session.address_form.value if session else "anh"
    prefixes = [
        f"Dạ vâng {af}, ", "Dạ vâng, ",
        f"Dạ {af}, ", f"Dạ {af} ",
        "Dạ, ", "Dạ ",
    ]
    for prefix in prefixes:
        if stripped.startswith(prefix):
            softened = stripped[len(prefix):].lstrip()
            break
    else:
        softened = stripped[2:].lstrip(" ,")
    if not softened:
        return reply
    result = softened[:1].upper() + softened[1:]
    # Fix Lỗi 13: đảm bảo có space sau từ đầu tiên nếu bị dính
    import re as _re
    stuck = _re.match(r'^(Vâng|Vângạ|\u1ede|\u1eea|Ok|Oke)(\S)', result)
    if stuck:
        result = stuck.group(1) + ' ' + stuck.group(2) + result[stuck.end():]
    return result
