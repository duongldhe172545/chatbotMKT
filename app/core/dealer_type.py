"""Dealer type detection — F2A.6 (LUAT_2A_core v0.2.5).

Layer 1: regex + count-based scoring, KHÔNG dùng LLM (tiết kiệm cost).
Phase 2 có thể thêm Layer 2 LLM fallback nếu Layer 1 confidence thấp.

4 dealer type theo File 1B:
- LỬA LÒ: caps + chửi bậy + cộc câu
- KHOE: số liệu + "anh có" + emoji + kể dài
- LO: defensive marker + hỏi ngược + "an toàn/phí"
- BẬN: message ngắn ≤5 chữ + không follow-up
- UNKNOWN/default: BẬN (conservative, không nịnh)

Detect tại turn 3, 8, 13 (DETECT_AT_TURNS). Re-detect chỉ dời nếu
confidence cao (HIGH_THRESH_SWITCH).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.models.enums import DealerType
from app.models.schema import DealerTypeHistoryEntry, SessionState


# ============================================================
# Config — refer F2A.6 tham số
# ============================================================

DETECT_AT_TURNS: tuple[int, ...] = (3, 8, 13)
MIN_CONFIDENCE_SCORE = 2.0   # Dưới → fallback "ban"
HIGH_THRESH_SWITCH = 5.0     # Re-detect chỉ dời nếu cao hơn ngưỡng này

# ============================================================
# Signal regex
# ============================================================

# Lửa Lò: chửi bậy + caps + cụt câu
_PROFANITY_PATTERN = re.compile(
    r"\b(đm|đụ|đéo|đjt|đcm|cmm|vl|vcl|vãi|cl|cc|đm|đmm|đ\.m|ĐM|CMNL)\b",
    re.IGNORECASE,
)
_ALL_CAPS_PATTERN = re.compile(r"\b[A-ZĐÁÀẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÉÈẺẼẸÊỀẾỂỄỆÍÌỈĨỊÓÒỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÚÙỦŨỤƯỪỨỬỮỰÝỲỶỸỴ]{3,}\b")
_NO_PUNCT_PATTERN = re.compile(r"^[^.!?,;]+$")  # Không dấu câu

# Khoe: số liệu + cụm "anh có/đứng đầu" + emoji nhiệt
_NUMERIC_PATTERN = re.compile(r"\b\d+[\d,.]*\s*(?:tỷ|triệu|nghìn|năm|tháng|thợ|đơn|khách|%|m2|m²)?\b", re.IGNORECASE)
_BOAST_PHRASES = re.compile(
    r"(anh có|cửa hàng anh|anh đứng đầu|đứng đầu|số 1|hàng đầu|"
    r"top \d+|nhất khu|năm thứ|đào tạo|tự hào|gắn bó)",
    re.IGNORECASE,
)
_POSITIVE_EMOJI = re.compile(r"[💪✨🎉🏆🔥👍😊🌟]")

# Lo: defensive marker
_DEFENSIVE_PHRASES = re.compile(
    r"(lừa đảo|đa cấp|tổ chức gì|có phí|tốn tiền|miễn phí thật|"
    r"em là ai|bot à|có thật|công ty nào|lấy data|"
    r"an toàn|bảo mật|có share|share không|lộ số|lộ địa chỉ|"
    r"có an toàn|không tin|nghi|cẩn thận|cảnh giác)",
    re.IGNORECASE,
)

# Bận: message ngắn (count theo từ)
_MAX_SHORT_WORDS = 5


# ============================================================
# Score functions
# ============================================================


def _score_lua_lo(messages: list[str]) -> float:
    """Score Lửa Lò: caps + chửi bậy (cụt câu chỉ là signal phụ)."""
    score = 0.0
    for msg in messages:
        if not msg or not msg.strip():
            continue
        # Chửi bậy: weight cao
        has_profanity = bool(_PROFANITY_PATTERN.search(msg))
        if has_profanity:
            score += 2.5
        # Caps lock toàn câu: nếu ≥50% chữ là caps
        words = [w for w in msg.split() if len(w) >= 3 and w.isalpha()]
        has_caps = False
        if words:
            caps_ratio = sum(1 for w in words if w.isupper()) / len(words)
            if caps_ratio >= 0.5:
                score += 1.5
                has_caps = True
        # Cụt câu không dấu — CHỈ count nếu combo với caps hoặc chửi
        # (để tránh false positive cho câu trả lời bình thường)
        if (has_profanity or has_caps) and _NO_PUNCT_PATTERN.match(msg.strip()):
            if len(msg.split()) >= 3:
                score += 0.3
    return score


def _score_khoe(messages: list[str]) -> float:
    """Score Khoe: số liệu + boast phrase + emoji nhiệt + message dài."""
    score = 0.0
    for msg in messages:
        if not msg or not msg.strip():
            continue
        # Số liệu khoe (vd "8 thợ", "30 tỷ", "10 năm")
        numeric_matches = _NUMERIC_PATTERN.findall(msg)
        # Chỉ count nếu có context boast (tránh nhầm answer slot 3.1 "60%")
        if numeric_matches and _BOAST_PHRASES.search(msg):
            score += 2.0 * min(len(numeric_matches), 2)
        elif _BOAST_PHRASES.search(msg):
            score += 1.5
        # Emoji nhiệt
        emoji_count = len(_POSITIVE_EMOJI.findall(msg))
        if emoji_count:
            score += 0.5 * min(emoji_count, 3)
        # Message dài (Khoe hay kể dài)
        word_count = len(msg.split())
        if word_count >= 20:
            score += 1.0
        elif word_count >= 12:
            score += 0.5
    return score


def _score_lo(messages: list[str]) -> float:
    """Score Lo: defensive marker + hỏi ngược."""
    score = 0.0
    for msg in messages:
        if not msg or not msg.strip():
            continue
        # Defensive marker — weight rất cao (chỉ cần 1 lần)
        matches = _DEFENSIVE_PHRASES.findall(msg)
        if matches:
            score += 3.0 * min(len(matches), 2)
        # Hỏi ngược (có "?" + ngắn — chứng tỏ nghi)
        if "?" in msg and len(msg) <= 60:
            score += 0.8
    return score


def _score_ban(messages: list[str]) -> float:
    """Score Bận: message ngắn ≤5 từ + không follow-up."""
    score = 0.0
    short_count = 0
    for msg in messages:
        if not msg or not msg.strip():
            continue
        word_count = len(msg.split())
        if word_count <= _MAX_SHORT_WORDS:
            short_count += 1
            score += 1.0
    # Bonus: ≥2 message ngắn liên tục (pattern Bận rõ)
    if short_count >= 2:
        score += 0.5
    return score


# ============================================================
# Main detect function
# ============================================================


def detect_dealer_type(
    session: SessionState,
    user_messages: Optional[list[str]] = None,
) -> DealerType:
    """Detect dealer type tại turn 3/8/13.

    Args:
        session: SessionState (cần `turn_count`, `detected_dealer_type`,
                 `dealer_type_history`, `history`)
        user_messages: Override messages (test). Production: extract từ
                       session.history filter role="dealer".

    Returns:
        DealerType mới sau detect (có thể giống cũ).

    Side-effects:
        - Append entry vào `session.dealer_type_history` nếu detect chạy
        - Update `session.detected_dealer_type` nếu confidence cao

    Logic:
        - Nếu turn_count không trong DETECT_AT_TURNS → return type cũ
        - Tính 4 score, lấy argmax
        - top_score < MIN_CONFIDENCE_SCORE → BAN (default conservative)
        - Re-detect (đã có type cũ): chỉ dời nếu top_score >= HIGH_THRESH_SWITCH
    """
    if session.turn_count not in DETECT_AT_TURNS:
        return session.detected_dealer_type or DealerType.UNKNOWN

    # Gom messages
    if user_messages is None:
        user_messages = [
            m.content for m in session.history if m.role == "dealer"
        ]
    if not user_messages:
        return session.detected_dealer_type or DealerType.UNKNOWN

    # Score 4 dimension
    scores: dict[DealerType, float] = {
        DealerType.LUA_LO: _score_lua_lo(user_messages),
        DealerType.KHOE: _score_khoe(user_messages),
        DealerType.LO: _score_lo(user_messages),
        DealerType.BAN: _score_ban(user_messages),
    }

    # Tìm top
    top_type = max(scores.keys(), key=lambda k: scores[k])
    top_score = scores[top_type]

    # Confidence thấp → BAN (default conservative)
    if top_score < MIN_CONFIDENCE_SCORE:
        new_type = DealerType.BAN
    else:
        new_type = top_type

    # Re-detect rule: chỉ dời nếu confidence cao hơn HIGH_THRESH_SWITCH
    current_type = session.detected_dealer_type
    if current_type is not None and current_type != DealerType.UNKNOWN:
        if new_type != current_type and top_score < HIGH_THRESH_SWITCH:
            new_type = current_type  # giữ nguyên

    # Log history
    session.dealer_type_history.append(
        DealerTypeHistoryEntry(
            turn=session.turn_count,
            type=new_type,
            score=top_score,
            ts=datetime.now(timezone.utc),
        )
    )
    session.detected_dealer_type = new_type

    return new_type


def should_detect_now(turn_count: int) -> bool:
    """True nếu turn_count là 1 trong các turn detect (3/8/13)."""
    return turn_count in DETECT_AT_TURNS


def get_score_breakdown(messages: list[str]) -> dict[str, float]:
    """Trả 4 score chi tiết — dùng debug + test.

    Returns dict {"lua_lo": float, "khoe": float, "lo": float, "ban": float}
    """
    return {
        "lua_lo": _score_lua_lo(messages),
        "khoe": _score_khoe(messages),
        "lo": _score_lo(messages),
        "ban": _score_ban(messages),
    }
