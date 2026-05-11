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

# Lãnh tụ / lãnh đạo CỤ THỂ — cấm xưng hô (rủi ro crisis PR + Luật An ninh
# mạng Điều 8 + xúc phạm danh dự lãnh tụ). CHỈ block khi tên gắn duy nhất 1
# người, KHÔNG block chức danh chung (Thủ tướng/CTN/TBT… anh em trêu nhau OK).
_SENSITIVE_FIGURES = (
    # Lãnh tụ lịch sử
    "bác hồ", "bac ho",
    "hồ chí minh", "ho chi minh",
    "lê duẩn", "le duan",
    "võ nguyên giáp", "vo nguyen giap",
    "trường chinh", "truong chinh",
    "tôn đức thắng", "ton duc thang",
    "phạm văn đồng", "pham van dong",
    "trần phú", "tran phu",
    "lê hồng phong", "le hong phong",
    "nguyễn ái quốc", "nguyen ai quoc",
    # Lãnh đạo đương nhiệm
    "tô lâm", "to lam",
    "lương cường", "luong cuong",
    "phạm minh chính", "pham minh chinh",
    "trần thanh mẫn", "tran thanh man",
    # Lãnh đạo gần đây (vừa miễn nhiệm / từ trần — vẫn nhạy cảm)
    "nguyễn phú trọng", "nguyen phu trong",
    "nguyễn xuân phúc", "nguyen xuan phuc",
    "võ văn thưởng", "vo van thuong",
    "vương đình huệ", "vuong dinh hue",
    "nguyễn tấn dũng", "nguyen tan dung",
)

# Tôn giáo CỤ THỂ — cấm xưng hô (xúc phạm tín ngưỡng).
# CHỈ block các danh xưng GẮN 1 vị duy nhất; KHÔNG block "phật"/"chúa"/"thánh"
# alone (chung chung).
_RELIGIOUS_TITLES = (
    "đức phật", "duc phat",
    "phật tổ", "phat to",
    "bồ tát", "bo tat",
    "đức chúa", "duc chua",
    "chúa giê", "chua gie", "chúa jesus", "chua jesus",
    "đức mẹ", "duc me",
    "đức thánh cha", "duc thanh cha",
    "thượng đế", "thuong de",
    "allah",
    "đạt lai lạt ma", "dat lai lat ma",
    "thánh ala", "thanh ala",
)

# Phân biệt vùng miền — cấm xưng.
_REGIONAL_SLURS = (
    "bắc kỳ", "bac ky",
    "nam kỳ", "nam ky",
    "ba que", "ba quẻ",
    "phản động", "phan dong",
)

# Gộp tất cả blacklist để check 1 lần.
# CHÚ Ý: KHÔNG có _POLITICAL_TITLES — chức danh chính trị generic (Thủ tướng,
# CTN, Bộ trưởng, TBT…) được PHÉP xưng hô vì anh em trêu nhau bình thường.
_ADDRESS_BLACKLIST = (
    _OFFENSIVE_WORDS
    + _SENSITIVE_FIGURES
    + _RELIGIOUS_TITLES
    + _REGIONAL_SLURS
)


def _is_offensive(candidate: str) -> bool:
    """True nếu candidate chứa từ tục / lãnh tụ / chức danh chính trị / tôn
    giáo / phân biệt vùng miền — KHÔNG cho phép xưng hô."""
    low = f" {candidate.lower()} "
    return any(bad in low for bad in _ADDRESS_BLACKLIST)


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