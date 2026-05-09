"""Enforce variety opener — chống bot lặp 'Dạ em ghi nhận' nhiều turn liền.

Logic:
- 4 nhóm cụm mở đầu: A (acknowledge) / B (cảm xúc) / C (đồng cảm) / D (bắc cầu)
- Mỗi turn, classify nhóm opener bot dùng → cấm nhóm đó ở turn sau
- Nếu LLM vẫn lặp (Haiku đặc biệt hay lặp nhóm A) → strip A-prefix + thay
  bằng B/D từ replacement pool
- C (đồng cảm) chỉ thay khi context phù hợp → tránh dùng cho neutral ack
"""
from __future__ import annotations

import random
import re

# ============================================================
# CLASSIFY — match prefix bot reply (80 ký tự đầu) vào nhóm A/B/C/D
# ============================================================
# Order quan trọng: B/C/D check TRƯỚC A vì A có cụm phổ biến dễ nhầm.
_OPENER_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("B", ("wow", "uầy", "uây", "hay quá", "tên hay", "đẹp ghê",
           "đa dạng ghê", "em phục", "tuyệt", "đỉnh thật", "ngầu")),
    ("C", ("em hiểu mà", "em nghe mà thương", "vất vả thật", "khó thật",
           "thương ghê", "cực thật", "em đồng cảm")),
    ("D", ("tiện đây em hỏi", "tiện đây", "à mà anh", "à anh ơi",
           "em tò mò", "còn 1 cái", "còn một cái", "còn 1 ý",
           "nhân tiện", "à còn")),
    ("A", ("dạ em ghi nhận", "em ghi nhận", "dạ em đã ghi nhận",
           "em đã ghi nhận", "dạ em hiểu rồi", "em hiểu rồi",
           "em note", "oke anh", "dạ vâng", "ok anh", "rõ rồi ạ",
           "em rõ rồi", "dạ em rất vui", "rất vui được làm quen")),
]


def classify_opener_group(text: str) -> str:
    """Match prefix bot reply (80 ký tự đầu) → nhóm A/B/C/D.

    Returns 'X' nếu không khớp nhóm nào — KHÔNG track nhóm này ở turn sau.
    """
    if not text:
        return "X"
    head = text.lower()[:80]
    for grp, kws in _OPENER_GROUPS:
        for kw in kws:
            if kw in head:
                return grp
    return "X"


# ============================================================
# ENFORCE VARIETY — strip A-prefix + thay opener khác nếu LLM lặp
# ============================================================
# Pool cụm thay thế khi force-replace opener. Chỉ dùng B/D (context-neutral).
# C (empathy) chỉ phù hợp với pain context → KHÔNG vào pool generic.
_REPLACEMENT_POOL: tuple[str, ...] = (
    "Wow", "Uầy", "Hay quá ạ,",
    "Tiện đây em hỏi anh,", "À mà anh ơi,", "Em tò mò xíu,",
)

# Regex strip VERB OPENER nhóm A — chỉ strip verb phrase, GIỮ NGUYÊN content
# theo sau. Tránh nuốt mất nội dung ack.
_A_PREFIX_RE = re.compile(
    r"^(?:"
    r"dạ\s+em\s+(?:đã\s+)?ghi\s+nhận|em\s+(?:đã\s+)?ghi\s+nhận|"
    r"dạ\s+vâng\s+em\s+hiểu\s+rồi|"  # cụ thể trước
    r"dạ\s+em\s+hiểu\s+rồi|em\s+hiểu\s+rồi|em\s+note(?:\s+rồi)?|"
    r"oke\s+anh|dạ\s+vâng|ok\s+anh|dạ\s+em\s+rất\s+vui|em\s+rõ\s+rồi"
    r")"
    # Strip trailing "ạ"/"nhé"/"nha"/"ơi" + dấu câu để tránh orphan
    r"(?:\s+(?:ạ|nhé|nha|ơi|rồi|nhá))*"
    r"[\s,.!?]*",
    re.IGNORECASE,
)


def enforce_opener_variety(
    text: str, forbidden_group: str | None
) -> tuple[str, str]:
    """Safety net: nếu opener trùng nhóm bị cấm → strip A-prefix + thay B/D.

    Chỉ enforce khi nhóm bị cấm là A (đa số case Haiku lặp). B/C/D giữ nguyên
    (LLM trách nhiệm) để tránh double-prefix.

    Returns (new_text, new_group_after_replace).
    """
    current = classify_opener_group(text)
    if not forbidden_group or current != forbidden_group:
        return text, current
    if current != "A":
        return text, current

    stripped = _A_PREFIX_RE.sub("", text, count=1).strip()
    if not stripped or len(stripped) < 5:
        return text, current

    if stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]

    new_opener = random.choice(_REPLACEMENT_POOL)
    new_text = f"{new_opener} {stripped}"
    return new_text, classify_opener_group(new_text)