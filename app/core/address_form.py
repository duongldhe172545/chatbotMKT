"""Detect xưng hô từ tên + lời dealer.

2 lớp detection:
1. `detect_explicit_address(text)` — bắt request CỤ THỂ ("gọi tao là đại ca",
   "xưng ngài", "kêu là sếp"...). LUÔN ưu tiên — dealer chủ động chỉ định.
2. `detect_address_form(text, owner_name)` — fallback default "anh"/"chị"
   từ tín hiệu chung (em là nữ, tên nữ phổ biến).

Một khi chốt → giữ nhất quán suốt phiên. Dealer thay đổi explicit → cập nhật.
"""
from __future__ import annotations

import re


# ============================================================
# LỚP 1 — EXPLICIT ADDRESS REQUEST
# ============================================================
# Capture bất kỳ word/cụm dealer yêu cầu xưng hô — không hardcode list.
# Chỉ chặn từ tục Việt Nam (offensive blacklist).

# Pattern: 3 cấu trúc thường gặp
_ADDRESS_REQUEST_PATTERNS = [
    # "gọi/kêu tao/mình/anh/chị/em là X"
    re.compile(
        r"(?:gọi|kêu)\s+(?:tao|mình|tôi|tớ|cậu|anh|chị|em)\s+(?:là|bằng)\s+"
        r"([^,.!?\n]{2,30})",
        re.I,
    ),
    # "xưng X"
    re.compile(r"\bxưng\s+([^,.!?\n]{2,30})", re.I),
    # "gọi/kêu là X" (không có chủ ngữ)
    re.compile(
        r"(?:gọi|kêu)\s+(?:là|bằng)\s+([^,.!?\n]{2,30})",
        re.I,
    ),
]

# Trailing modifiers thường gặp — strip để lấy core word
# vd: "ngài đi" → "ngài", "sếp ơi" → "sếp", "đại ca nhé" → "đại ca"
_TRAILING_TRIM = re.compile(
    r"\s+(?:đi|nhé|nha|nhá|ơi|đó|đấy|với|cho|tao|nào)\b.*$",
    re.I,
)

# Offensive blacklist — chỉ chặn từ tục thực sự, không chặn từ ngầu
# ("đại ca", "trùm", "sếp" OK; "lồn", "đĩ" REJECT).
_OFFENSIVE_WORDS = (
    "lồn", "lon ",
    "cặc", "cac ",
    "buồi", "buoi ",
    "đụ", "du me",
    "đm", "đmm",
    "đéo", "deo ",
    "địt", "dit ",
    "chó", "cho di",
    "đĩ", "di me",
    "súc vật", "suc vat",
    "khốn nạn", "khon nan",
    "ngu", "ngu ngốc",
)


def _is_offensive(candidate: str) -> bool:
    """True nếu candidate chứa từ tục."""
    low = f" {candidate.lower()} "
    return any(bad in low for bad in _OFFENSIVE_WORDS)


def detect_explicit_address(text: str) -> str | None:
    """Bắt request xưng hô CỤ THỂ từ dealer.

    Returns:
        str: address word ("đại ca", "ngài", "sếp", "Hùng"...) nếu detect được
        None: không có request explicit, hoặc request offensive (bị reject)
    """
    if not text:
        return None
    for pattern in _ADDRESS_REQUEST_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        candidate = m.group(1).strip()
        # Trim trailing modifiers ("đi"/"nhé"/"ơi"...)
        candidate = _TRAILING_TRIM.sub("", candidate).strip()
        # Normalize whitespace
        candidate = re.sub(r"\s+", " ", candidate)
        if len(candidate) < 2 or len(candidate) > 20:
            continue
        # Offensive filter
        if _is_offensive(candidate):
            return None
        return candidate.lower()
    return None


# ============================================================
# LỚP 2 — DEFAULT ANH/CHỊ
# ============================================================
# Tên nữ Việt Nam phổ biến — chỉ những tên KHÁ rõ là nữ.
# (không gồm Hà, Anh, Linh, Sơn, Thanh — ambiguous)
_FEMALE_NAMES = {
    "hương", "lan", "mai", "trang", "hoa", "hà", "nhung", "loan",
    "hằng", "vy", "phương", "thuỳ", "thùy", "diệu", "nga", "yến",
    "thảo", "vân", "quyên", "thuý", "thúy", "ngọc", "linh", "anh thư",
    "bảo châu", "bích", "hạnh", "tâm", "huyền",
}


def detect_address_form(text: str, owner_name: str | None) -> str:
    """Default detect "anh"/"chị" từ tín hiệu chung.

    KHÔNG override explicit request từ `detect_explicit_address()` —
    caller (ConversationService) phải gọi 2 hàm theo thứ tự ưu tiên.

    Returns:
        "anh" hoặc "chị"
    """
    if text:
        low = text.lower()
        # Tự xưng nữ rõ ràng
        if "em là nữ" in low or "tôi là nữ" in low or "tao là nữ" in low:
            return "chị"
        # Dealer tự xưng "chị" trong câu
        if low.startswith("chị ") or " chị " in low or low.startswith("chị,"):
            if "đừng gọi" not in low:
                return "chị"
        # Correct case sau khi bot gọi nhầm
        if "đừng gọi" in low and "anh" in low and ("chị" in low or "nữ" in low):
            return "chị"

    # Detect by name (last word usually is given name in VN)
    if owner_name:
        parts = owner_name.lower().strip().split()
        if parts:
            last_name = parts[-1]
            if last_name in _FEMALE_NAMES:
                return "chị"

    return "anh"