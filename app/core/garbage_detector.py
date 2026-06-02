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
    "ok", "okay", "oke", "okê", "ờ", "ò", "ừ", "ừa", "ừm", "uh", "uhm", "ạ", "à",
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
    - Phase 6 R+ Fix A: Random alpha sequence không có VN phonotactic
      structure (vd "ekgrerhger", "sdfhjklmn") — single token ≥ 5 char
      không có vowel cluster tiếng Việt.
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
    # Phase 6 R+ Fix A: random alpha không có VN phonotactic structure
    if _is_random_alpha_no_vn(cleaned):
        return True
    return False


# Phase 6 R+ Fix A: VN phonotactic check
# Tiếng Việt: âm tiết = phụ âm đầu + nguyên âm (BẮT BUỘC) + phụ âm cuối.
# Nguyên âm: a/e/i/o/u/y + tổ hợp ai/ao/au/eo/ia/iê/oi/ua/ưa/ươ/yê...
# Token KHÔNG có nguyên âm → không phải tiếng Việt → garbage.
_VOWEL_PATTERN = re.compile(
    r"[aeiouyàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵAEIOUY]",
    re.UNICODE,
)


# VN syllable onset cluster hợp lệ (3 phụ âm liên tiếp chỉ chấp nhận khi
# bắt đầu bằng "ngh"). 2 phụ âm onset: ng/nh/kh/ph/th/tr/ch/gh/gi/qu.
_VALID_VN_ONSET_3 = ("ngh",)
_CONSONANT_CLUSTER_3PLUS = re.compile(
    r"[bcdfghjklmnpqrstvwxzđBCDFGHJKLMNPQRSTVWXZĐ]{3,}",
    re.UNICODE,
)


def _is_random_alpha_no_vn(text: str) -> bool:
    """True nếu text là chuỗi alpha không có cấu trúc tiếng Việt.

    Phase 6 R+ Fix A — bắt "ekgrerhger" / "sdfhjklmn":
    1. Vowel ratio < 0.2 → garbage (vd "ngmbnhg")
    2. ≥ 4 phụ âm liên tiếp → garbage (vd "asdfgh")
    3. ≥ 3 phụ âm liên tiếp KHÔNG bắt đầu bằng VN cluster "ngh" → garbage
       (vd "kgr", "rhg" in "ekgrerhger")
    """
    if not text:
        return False
    if any(c.isdigit() for c in text):
        return False
    tokens = [t for t in re.split(r"\s+", text) if t.strip()]
    if not tokens:
        return False
    long_tokens = [t for t in tokens if len(t) >= 4]
    if not long_tokens:
        return False
    for tok in long_tokens:
        tok_alpha = "".join(c for c in tok if c.isalpha())
        if not tok_alpha or len(tok_alpha) < 4:
            continue
        vowels = _VOWEL_PATTERN.findall(tok_alpha)
        vowel_ratio = len(vowels) / len(tok_alpha)
        if vowel_ratio < 0.2:
            return True
        # Tìm cluster ≥ 3 phụ âm liên tiếp; nếu KHÔNG match VN onset hợp lệ
        # ("ngh") thì garbage
        for cluster in _CONSONANT_CLUSTER_3PLUS.findall(tok_alpha):
            cluster_lower = cluster.lower()
            # Cluster ≥ 4 phụ âm: gần chắc chắn không VN
            if len(cluster) >= 4:
                return True
            # Cluster 3 phụ âm: chấp nhận chỉ khi là VN onset hợp lệ
            if not any(cluster_lower.startswith(c) for c in _VALID_VN_ONSET_3):
                return True
    return False


def is_meaningful_short(message: str) -> bool:
    """Check message ngắn có nghĩa (vd 'ok', 'ờ', 'có') — KHÔNG garbage."""
    if not message:
        return False
    return message.strip().lower() in _VALID_SHORT_WORDS
