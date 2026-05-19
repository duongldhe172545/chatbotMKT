"""Garbage input detector — refer KICH_BAN_1C § 7.

Detect khi dealer nhập text random / chỉ emoji / chỉ 1-2 ký tự vô nghĩa.
Bot ack confused polite + flag GARBAGE_INPUT nếu lặp ≥ 2 lần cùng slot.

Marker:
- Toàn emoji / dấu chấm
- Chỉ 1-2 ký tự
- Chỉ ký tự lặp ("xxxxx", "aaa")
- Chỉ số mà không có context phone/giá trị (vd "123" ở slot tên)
- Random ký tự (vd "asdf", "qwer")

Wire: conversation gọi is_garbage(message, slot_id) TRƯỚC khi extract.
Nếu True → bot ack "chưa rõ ý" + flag (nếu lặp 2 lần) + RETRY slot.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# Pattern garbage
_ONLY_EMOJI = re.compile(
    r"^[\W\s☀-⟿\U0001F000-\U0001FFFF.,!?─-◿]+$",
    re.UNICODE,
)
_ONLY_PUNCT = re.compile(r"^[.,!?;:\-\s]+$")
_REPEAT_CHAR = re.compile(r"^(.)\1{3,}$")  # "xxxx", "aaaaa"
_RANDOM_KEYBOARD = re.compile(
    r"^(asd|qwe|qaz|wsx|xcv|zxc|asdf|qwer|qwerty|yuio|"
    r"asdfgh|zxcvbn|hjkl)+\s*$",
    re.IGNORECASE,
)
# Random gồm nhiều keyboard segment cách bằng space: "qwe asd zxc"
_MULTI_KEYBOARD_SEGMENT = re.compile(
    r"^((asd|qwe|qaz|wsx|xcv|zxc|asdf|qwer|yuio|hjkl)\s+)+"
    r"(asd|qwe|qaz|wsx|xcv|zxc|asdf|qwer|yuio|hjkl)\s*$",
    re.IGNORECASE,
)

# Common short answers — KHÔNG phải garbage (whitelist)
_VALID_SHORT_WORDS: set[str] = {
    "ok", "okay", "oke", "okê", "ờ", "ừ", "uh", "uhm", "ạ", "à",
    "có", "k", "ko", "không", "vâng", "dạ", "đúng", "rồi",
    "chuẩn", "phải", "yes", "no", "y", "n",
}


def is_garbage(message: str, slot_id: str | None = None) -> bool:
    """True nếu message là garbage input.

    Args:
        message: Raw user message
        slot_id: Slot đang hỏi (để context-aware — vd "123" OK ở slot phone,
                 garbage ở slot tên). Phase 3: chỉ check pattern chung.

    Returns:
        True nếu garbage, False nếu nội dung có nghĩa.

    Pattern:
    - Empty / whitespace → True
    - Chỉ emoji / dấu chấm → True
    - Lặp 1 ký tự ≥ 4 lần → True
    - Ngắn ≤ 1 ký tự (và không trong whitelist) → True
    - Random keyboard pattern → True
    """
    if not message or not isinstance(message, str):
        return True
    cleaned = message.strip()
    if not cleaned:
        return True
    if len(cleaned) == 1 and cleaned.lower() not in _VALID_SHORT_WORDS:
        return True
    if _ONLY_PUNCT.match(cleaned):
        return True
    if _REPEAT_CHAR.match(cleaned):
        return True
    if _RANDOM_KEYBOARD.match(cleaned):
        return True
    if _MULTI_KEYBOARD_SEGMENT.match(cleaned):
        return True
    # Emoji-only: check sau khi strip emoji còn gì
    stripped_emoji = re.sub(
        r"[☀-⟿\U0001F000-\U0001FFFF─-◿✀-➿]",
        "",
        cleaned,
    ).strip()
    if not stripped_emoji:
        # Toàn emoji → garbage
        return True
    return False


def is_meaningful_short(message: str) -> bool:
    """Check message ngắn có nghĩa (vd 'ok', 'ờ', 'có') — KHÔNG garbage."""
    if not message:
        return False
    return message.strip().lower() in _VALID_SHORT_WORDS
