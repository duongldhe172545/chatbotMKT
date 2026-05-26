"""Bridge phrase rotation engine — refer 1A § 2.2.

Pool 11 bridge + 1 no-bridge mode. Engine track 3 bridge gần nhất, KHÔNG lặp
trong 3 turn liên tiếp. LLM được hint via system_prompt task.

Refer:
- File 1A § 2.2 — pool 11 + no-bridge xác suất ~1/12
- feedback_test_form — test multi-turn 10-15 để verify rotation
- LUAT_2B_llm § F2B.1 NGUYÊN TẮC ACK + ASK rule 3 (bridge rotate)
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from app.models.schema import SessionState

logger = logging.getLogger(__name__)


# 11 bridge — refer 1A § 2.2
BRIDGE_POOL: list[str] = [
    "À mà anh ơi",
    "Em hỏi thêm xíu",
    "Tiện đây em hỏi",
    "Em tò mò xíu",
    "Còn 1 ý em hỏi anh nhé",
    "Nhân tiện em hỏi luôn",
    "À hỏi anh xíu",
    "Em xin phép hỏi tiếp",
    "Quay lại chuyện cửa hàng xíu",
    "À cho em hỏi",
    "Em hỏi thêm cái này",
]

# Organic bridge prefixes — LLM thường tự sinh, không nằm pool.
# Track theo prefix (lowercase) để rotate dù LLM không dùng pool chuẩn.
# Lưu ý: "Anh ơi" KHÔNG nằm trong organic — đây là no-bridge mode marker
# (spec § 2.2 — "Hoặc CHẲNG có bridge — vào thẳng câu hỏi với 'Anh ơi, ...'")
_ORGANIC_BRIDGE_PREFIXES: list[str] = [
    "tiện đây",
    "nhân tiện",
    "à hỏi",
    "à mà",
    "à cho em",
    "à —",
    "em hỏi thêm",
    "em tò mò",
    "em hỏi tiếp",
    "em xin phép",
    "còn 1",
    "còn một",
    "quay lại",
]

# No-bridge mode marker — engine có thể chọn KHÔNG bridge (đi thẳng "Anh ơi, ...")
NO_BRIDGE_MARKER = "(no-bridge)"

# Track top 3 bridge gần nhất (LRU)
MAX_RECENT_BRIDGES = 3

# Xác suất chọn no-bridge mode (~1/12 theo spec)
NO_BRIDGE_PROBABILITY = 1.0 / 12.0


def detect_bridge_in_reply(reply: str) -> Optional[str]:
    """Scan reply, tìm bridge phrase đầu tiên match từ pool.

    Match case-insensitive + longest first (tránh prefix overlap).
    Fallback organic prefix nếu LLM sinh bridge ngoài pool (track để rotate).

    Returns:
        Bridge string từ pool (original case), hoặc "(organic: prefix)" nếu
        chỉ match organic. None nếu không match.
    """
    if not reply or not isinstance(reply, str):
        return None
    lower_reply = reply.lower()
    # Longest first để "Em hỏi thêm cái này" match trước "Em hỏi thêm xíu"
    for bridge in sorted(BRIDGE_POOL, key=len, reverse=True):
        if bridge.lower() in lower_reply:
            return bridge
    # Fallback: organic prefix (LLM tự sinh, ngoài pool)
    for prefix in sorted(_ORGANIC_BRIDGE_PREFIXES, key=len, reverse=True):
        if prefix in lower_reply:
            return f"(organic:{prefix})"
    return None


def record_bridge(session: SessionState, reply: str) -> Optional[str]:
    """Detect bridge trong reply + push vào session.recent_bridges (LRU, max 3).

    Args:
        session: SessionState (mutated in-place)
        reply: Bot reply text vừa gen

    Returns:
        Bridge detected, hoặc None nếu reply không chứa bridge nào.
    """
    bridge = detect_bridge_in_reply(reply)
    if not bridge:
        return None
    # LRU: nếu đã có thì remove + insert head
    if session.recent_bridges is None:
        session.recent_bridges = []
    bridges = [b for b in session.recent_bridges if b != bridge]
    bridges.insert(0, bridge)
    session.recent_bridges = bridges[:MAX_RECENT_BRIDGES]
    return bridge


def get_avoid_hint(session: SessionState) -> str:
    """Build hint cho LLM: bridge nào tránh dùng turn này.

    Refer F2B.1 NGUYÊN TẮC ACK + ASK rule 3 — bridge rotate không lặp.

    Returns:
        Empty string nếu chưa có bridge nào (turn đầu).
        Otherwise: format với pool + recent để LLM hiểu cần dùng cụm khác.
    """
    recent = list(session.recent_bridges or [])
    if not recent:
        return ""
    # Normalize organic markers: "(organic:tiện đây)" → "tiện đây"
    def _clean(b: str) -> str:
        if b.startswith("(organic:") and b.endswith(")"):
            return b[len("(organic:"):-1]
        return b
    bridges_quoted = ", ".join(f'"{_clean(b)}"' for b in recent)
    return (
        f"BRIDGE PHRASE — TRÁNH lặp {len(recent)} cụm bridge gần nhất: {bridges_quoted}. "
        f"Dùng cụm khác (vd: 'À mà anh ơi', 'Em tò mò xíu', 'Còn 1 ý em hỏi', "
        f"'Em xin phép hỏi tiếp', 'Quay lại chuyện cửa hàng xíu') hoặc đi thẳng "
        f"vào câu hỏi không bridge."
    )


def pick_unused_bridge(
    session: SessionState,
    rng: Optional[random.Random] = None,
) -> Optional[str]:
    """Pick 1 bridge từ pool KHÔNG có trong recent. None = no-bridge mode.

    Engine có thể chọn no-bridge với xác suất ~1/12 (refer 1A § 2.2).

    Args:
        session: SessionState
        rng: Random instance (cho deterministic test). None = random thật.

    Returns:
        Bridge string, hoặc None nếu engine quyết định no-bridge / pool cạn.
    """
    rng = rng or random
    # No-bridge probability check
    if rng.random() < NO_BRIDGE_PROBABILITY:
        return None
    recent_set = set(session.recent_bridges or [])
    available = [b for b in BRIDGE_POOL if b not in recent_set]
    if not available:
        # Pool cạn (recent ≥ 11) — fallback no-bridge
        logger.warning(
            "Bridge pool exhausted (recent=%d/%d) — fallback no-bridge",
            len(recent_set), len(BRIDGE_POOL),
        )
        return None
    return rng.choice(available)


def reset_bridges(session: SessionState) -> None:
    """Clear recent_bridges (vd khi đổi stage)."""
    session.recent_bridges = []
