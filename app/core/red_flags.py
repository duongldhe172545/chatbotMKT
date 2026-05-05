"""Red flag detection — rule-based, không dùng LLM.

Phát hiện các pattern nguy hiểm/bất thường trong tin nhắn dealer.
Profile có flag → reviewer ADG chú ý trước khi cấp Dealer_ID (mục 26 .md).
"""
from __future__ import annotations

import re
from collections import Counter

# ---------- Flag constants ----------
PHONE_SUSPICIOUS = "phone_suspicious"
NAME_SUSPICIOUS = "name_suspicious"
ABUSIVE_LANGUAGE = "abusive_language"
ABUSIVE_PERSISTENT = "abusive_persistent"
PROMPT_INJECTION = "prompt_injection_attempt"
ESCALATION_REQUESTED = "escalation_requested"
GARBAGE_INPUT = "garbage_input"
SPAM_SUSPECT = "spam_suspect"
DEALER_PAUSED = "dealer_paused"


# ---------- Phone ----------
_PHONE_OBVIOUS_FAKE = {
    "0123456789", "1234567890", "9876543210", "0987654321",
    "0000000000", "1111111111",
}


def is_suspicious_phone(phone: str | None) -> bool:
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return False
    # Quá ngắn (SĐT VN ≥10 chữ số)
    if len(digits) < 9:
        return True
    # Mẫu hiển nhiên giả
    if digits in _PHONE_OBVIOUS_FAKE:
        return True
    # Toàn 1 chữ số (0000000000)
    if len(set(digits)) <= 1:
        return True
    # Tăng/giảm dần liên tục
    if digits[1:] == "".join(str(int(digits[0]) + i) for i in range(len(digits) - 1)):
        return True
    return False


# ---------- Name ----------
def is_suspicious_name(name: str | None) -> bool:
    if not name:
        return False
    cleaned = name.strip()
    if len(cleaned) < 2:
        return True
    # Toàn ký tự lặp ("xxx", "aaaa")
    if len(set(cleaned.lower())) == 1:
        return True
    # Test placeholder
    if cleaned.lower() in {"abc", "xxx", "test", "haha", "asdf", "noname", "abcd"}:
        return True
    # Toàn số
    if cleaned.isdigit():
        return True
    return False


# ---------- Abuse ----------
# Blacklist tiếng Việt — không cần đầy đủ, chỉ những từ phổ biến
_ABUSE_KEYWORDS = (
    "địt", "dit", "đụ", "du me", "đm", "dm",
    "cặc", "cac", "buồi", "buoi", "lồn", "lon",
    "vcl", "vl", "vleu", "đjt", "djt",
    "mẹ mày", "me may", "con cặc", "con cac",
    "ngu", "óc chó", "oc cho", "súc vật", "suc vat",
)


def has_abusive_language(text: str) -> bool:
    if not text:
        return False
    t = f" {text.lower()} "
    return any(f" {kw} " in t or kw in t.split() for kw in _ABUSE_KEYWORDS)


# ---------- Prompt injection ----------
_INJECTION_PATTERNS = (
    "ignore previous", "ignore all previous", "ignore the above",
    "disregard previous", "forget everything", "forget all",
    "system prompt", "system message", "your instructions",
    "you are now", "you must now", "pretend to be",
    "act as ", "act like ", "roleplay",
    "repeat the words above", "show me your prompt",
    "reveal your", "what are your instructions",
    "developer mode", "jailbreak", "dan mode",
)


def is_prompt_injection_attempt(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(p in t for p in _INJECTION_PATTERNS)


# ---------- Escalation request ----------
_ESCALATION_KEYWORDS = (
    "người thật", "nguoi that", "nguoi that su", "ngươi thật",
    "gặp người", "gap nguoi", "gặp ai", "gap ai",
    "nói với người", "noi voi nguoi",
    "không nói với bot", "khong noi voi bot",
    "không muốn chat bot", "khong muon chat bot",
    "gọi cho tôi", "goi cho toi", "gọi anh", "goi anh",
    "cho gặp", "cho gap",
    "ai phụ trách", "ai quản lý", "quan ly",
    "cho gặp sếp", "cho gap sep",
)


def is_escalation_request(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in _ESCALATION_KEYWORDS)


# ---------- Garbage / spam ----------
def is_garbage_input(text: str) -> bool:
    """Toàn ký tự ngẫu nhiên / lặp nhiều / không có nguyên âm tiếng Việt."""
    if not text:
        return False
    cleaned = re.sub(r"\s+", "", text.lower())
    if len(cleaned) < 3:
        return False  # Câu ngắn không tính garbage
    # Toàn 1-2 ký tự
    if len(set(cleaned)) <= 2:
        return True
    # Lặp 1 cụm 3 lần liên tiếp ("hahaha hahaha hahaha")
    if re.search(r"(.{2,5})\1{2,}", cleaned):
        return True
    # Không có nguyên âm và độ dài >5 (gần như không phải tiếng Việt)
    vowels = set("aeiouăâêôơưyàáạảãèéẹẻẽìíịỉĩòóọỏõùúụủũ")
    if len(cleaned) > 5 and not (set(cleaned) & vowels):
        return True
    return False


# ---------- Pause / từ chối ----------
_PAUSE_KEYWORDS = (
    "không quan tâm", "khong quan tam",
    "đang bận", "dang ban", "bận lắm", "ban lam",
    "để sau", "de sau", "sau nói", "sau noi",
    "không cần", "khong can",
    "không tham gia", "khong tham gia",
    "thôi nhé", "thoi nhe",
)


def is_pause_signal(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in _PAUSE_KEYWORDS)


# ---------- Aggregator ----------
def detect_message_flags(dealer_message: str) -> list[str]:
    """Quét 1 tin nhắn dealer, trả list flag được trigger."""
    flags = []
    if has_abusive_language(dealer_message):
        flags.append(ABUSIVE_LANGUAGE)
    if is_prompt_injection_attempt(dealer_message):
        flags.append(PROMPT_INJECTION)
    if is_escalation_request(dealer_message):
        flags.append(ESCALATION_REQUESTED)
    if is_garbage_input(dealer_message):
        flags.append(GARBAGE_INPUT)
    if is_pause_signal(dealer_message):
        flags.append(DEALER_PAUSED)
    return flags


def detect_profile_flags(profile_dict: dict) -> list[str]:
    """Quét profile snapshot, trả flag dạng phone/name suspicious."""
    flags = []
    if is_suspicious_phone(profile_dict.get("phone_or_zalo")):
        flags.append(PHONE_SUSPICIOUS)
    if is_suspicious_name(profile_dict.get("dealer_name")):
        flags.append(NAME_SUSPICIOUS)
    return flags


def upgrade_persistent_flags(flags: list[str]) -> list[str]:
    """Chuyển flag tích luỹ thành 'persistent' nếu xuất hiện ≥3 lần."""
    counter = Counter(flags)
    out = list(dict.fromkeys(flags))  # dedupe giữ thứ tự
    if counter[ABUSIVE_LANGUAGE] >= 3 and ABUSIVE_PERSISTENT not in out:
        out.append(ABUSIVE_PERSISTENT)
    if counter[GARBAGE_INPUT] >= 3 and SPAM_SUSPECT not in out:
        out.append(SPAM_SUSPECT)
    return out
