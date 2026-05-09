"""Spam protection — Layer 1, 3, 4, 5.

Triết lý:
- 0 LLM call cho mọi check ở đây — chỉ regex/Python.
- Detect SỚM trước khi flow chính chạy → tiết kiệm cost.
- Phân tách rõ: input filter (Layer 3 Lớp B) / mode logic (Layer 5)
  / detect tầm thường (Layer 4) / hard caps (Layer 1).

Trigger reference:
  Layer 1.1: > MAX_MESSAGES_PER_SESSION → soft-end
  Layer 1.2: same msg lặp ≥ 3 → block (template)
  Layer 1.3: LLM call ≥ 30 ASKING → cảnh báo + đẩy CONFIRMING
  Layer 1.4: LLM call ≥ 40 → soft-end
  Layer 3.B: injection regex match → block + flag
  Layer 3.C: output leak match → drop reply, trả template
  Layer 4:   trivial message smarter → skip Extractor (giữ Replier)
  Layer 5:   ABUSIVE_PERSISTENT/INJECTION/GARBAGE → template-only mode
             2 message clean liên tiếp → recovery về normal
"""
from __future__ import annotations

import random
import re
from typing import Literal

from app.core import red_flags
from app.models.schema import ChatRole, Session

# ============================================================
# CONFIG (tune trong file này)
# ============================================================

MAX_MESSAGES_PER_SESSION = 80
LLM_CALL_WARN_THRESHOLD = 30
LLM_CALL_HARD_CAP = 40
SAME_MESSAGE_REPEAT_THRESHOLD = 3
TEMPLATE_RECOVERY_THRESHOLD = 2  # 2 clean message liên tiếp → switch back

Mode = Literal["normal", "template_only", "soft_ended"]


# ============================================================
# LAYER 3 LỚP B — INPUT INJECTION DETECT
# ============================================================
# Mở rộng patterns Vietnamese ngoài red_flags._INJECTION_PATTERNS (chỉ EN).
_EXTRA_INJECTION_PATTERNS = [
    re.compile(r"phớt\s+lờ", re.I),
    re.compile(r"bỏ\s+qua\s+(chỉ\s+thị|hướng\s+dẫn|lời\s+(căn\s+)?dặn|trên|trước)", re.I),
    re.compile(r"đóng\s+vai\s+\w+", re.I),
    re.compile(r"viết\s+(code|đoạn\s+code|script|đoạn\s+script)", re.I),
    re.compile(r"liệt\s+kê\s+(các|tất\s+cả|toàn\s+bộ)\s*(dealer|profile|user|khách)", re.I),
    re.compile(r"chỉ\s+thị\s+(của\s+)?(bạn|em)\s+là\s+gì", re.I),
    re.compile(r"^\s*system\s*[:>]", re.I),
    re.compile(r"\bDAN\s+mode", re.I),
    re.compile(r"không\s+cần\s+(để\s+ý|quan\s+tâm)\s+(lời|chỉ\s+thị|hướng\s+dẫn)", re.I),
]


def detect_injection(text: str) -> bool:
    """Detect prompt injection bằng regex (Lớp B).

    Quan trọng: đây CHỈ là tầng nhanh để chặn case rõ ràng. Tầng cốt lõi
    là Lớp A (scope guard trong system prompt) — Replier tự kháng dù
    user phrase tinh vi vượt regex.
    """
    if not text:
        return False
    if red_flags.is_prompt_injection_attempt(text):
        return True
    return any(p.search(text) for p in _EXTRA_INJECTION_PATTERNS)


# ============================================================
# LAYER 3 LỚP C — OUTPUT LEAK GUARD
# ============================================================
_OUTPUT_LEAK_PATTERNS = [
    re.compile(r"system\s+prompt", re.I),
    re.compile(r"chỉ\s+thị\s+(của\s+)?(tôi|em|bạn)\s+là", re.I),
    re.compile(r"i\s+(was\s+)?(instructed|told)\s+to", re.I),
    re.compile(r"\bdef\s+\w+\s*\(.*\)\s*:", re.I),  # Python def
    re.compile(r"\bfunction\s+\w+\s*\(", re.I),  # JS function
    re.compile(r"<\?php", re.I),
    re.compile(r"\bSELECT\s+.*\s+FROM\s+\w+", re.I),  # SQL
    re.compile(r"```(python|javascript|js|sql|java|php|bash|sh|cpp|c\+\+|go|rust|typescript|ts)\b", re.I),
    re.compile(r"i\s+am\s+DAN", re.I),
    re.compile(r"developer\s+mode\s+(activated|enabled|on)", re.I),
    re.compile(r"\bas\s+(ChatGPT|GPT-?\d|Claude|Gemini)\b", re.I),
]


def detect_output_leak(text: str) -> bool:
    """Detect reply Replier có leak system prompt / code / role hijack.

    Bot Em Linh KHÔNG nên trả code/SQL/system prompt fragment trong
    bất kỳ context nào → match → drop reply, trả template.
    """
    if not text:
        return False
    return any(p.search(text) for p in _OUTPUT_LEAK_PATTERNS)


# ============================================================
# LAYER 4 — TRIVIAL DETECT SMARTER
# ============================================================
# Bắt thêm "okkkk", "vânggg", "ok ạ", "uhmmm", "kkk" — version cũ chỉ
# match exact "ok"/"yes" trong _TRIVIAL_MESSAGES set cứng.
_TRIVIAL_REGEX = re.compile(
    r"^\s*("
    r"ok+(ay|ê|e)?|"
    r"oke+|oki+|okie+|"
    r"đúng+|dung+|"
    r"y(es+)?|"
    r"vâng+|vang+|"
    r"ừ+|u+h*|"
    r"có+|co+|"
    r"không+|khong+|k+(o+)?|"
    r"hm+m*|à+|a+|ờ+|o+|"
    r"thôi+|thoi+|"
    r"đc+|được+|duoc+|"
    r"rồi+|roi+"
    r")[\s.!?,áạnhéá]*$",
    re.IGNORECASE,
)


def is_trivial_message(text: str) -> bool:
    """True nếu message ngắn/khẳng định không cần extract LLM."""
    if not text:
        return True
    cleaned = text.strip()
    if len(cleaned) < 2:
        return True
    return bool(_TRIVIAL_REGEX.match(cleaned.lower()))


# ============================================================
# LAYER 1.2 — SAME MESSAGE REPEAT DETECT
# ============================================================
def _normalize_for_dedup(text: str) -> str:
    """Lower + bỏ ký tự không phải chữ/số → so sánh dedup chuẩn xác."""
    if not text:
        return ""
    return re.sub(r"\W+", "", text.lower(), flags=re.UNICODE)


def is_repeated_spam(session: Session, current_msg: str) -> bool:
    """True nếu current_msg trùng với SAME_MESSAGE_REPEAT_THRESHOLD-1
    message dealer GẦN NHẤT (sau normalize).

    Tức nếu THRESHOLD=3, kiểm 2 message trước có giống current không.
    Đây là check trước khi append → khi return True, đây sẽ là lần thứ 3.
    """
    normalized_now = _normalize_for_dedup(current_msg)
    if not normalized_now:
        return False
    n = SAME_MESSAGE_REPEAT_THRESHOLD - 1
    recent = [
        m.content for m in session.messages
        if m.role == ChatRole.DEALER
    ][-n:]
    if len(recent) < n:
        return False
    return all(_normalize_for_dedup(m) == normalized_now for m in recent)


# ============================================================
# LAYER 5 — MODE LOGIC
# ============================================================
def is_clean_message(text: str) -> bool:
    """Message không trigger flag negative nào → clean (recovery candidate)."""
    if not text:
        return False
    if detect_injection(text):
        return False
    if red_flags.has_abusive_language(text):
        return False
    if red_flags.is_garbage_input(text):
        return False
    return True


def update_mode_after_flags(session: Session, new_flags: list[str]) -> None:
    """Sau khi detect flags turn này, update session.mode + counters.

    Logic transition:
    - normal → template_only:
        ABUSIVE_PERSISTENT (3 lần chửi tích lũy) HOẶC
        GARBAGE_INPUT 3 lần tích lũy HOẶC
        PROMPT_INJECTION lần 1 (đã xử ở precheck thật ra, đây là backup)
    - template_only → normal:
        2 message clean liên tiếp
    - template_only → soft_ended:
        PROMPT_INJECTION lần 2 (đã xử ở precheck)
    - normal → soft_ended (quota): xử ở conversation.py
    """
    if session.mode == "soft_ended":
        return

    is_clean = not (
        red_flags.ABUSIVE_LANGUAGE in new_flags
        or red_flags.PROMPT_INJECTION in new_flags
        or red_flags.GARBAGE_INPUT in new_flags
    )

    if session.mode == "normal":
        if red_flags.ABUSIVE_PERSISTENT in session.flag_history:
            session.mode = "template_only"
            session.consecutive_clean_messages = 0
            return
        garbage_count = session.flag_history.count(red_flags.GARBAGE_INPUT)
        if garbage_count >= 3:
            session.mode = "template_only"
            session.consecutive_clean_messages = 0
            return
        return

    # session.mode == "template_only"
    if is_clean:
        session.consecutive_clean_messages += 1
        if session.consecutive_clean_messages >= TEMPLATE_RECOVERY_THRESHOLD:
            session.mode = "normal"
            session.consecutive_clean_messages = 0
    else:
        session.consecutive_clean_messages = 0


# ============================================================
# TEMPLATE REPLIES (no LLM)
# ============================================================
def template_repeated_spam(address: str = "anh") -> str:
    pool = [
        f"Em chưa hiểu ý {address} ạ, {address} thử nói khác giúp em được không nhé?",
        f"Dạ {address} ơi, em đọc mãi mà chưa rõ ý — {address} cho em xin câu khác với ạ?",
    ]
    return random.choice(pool)


def template_session_too_long(address: str = "anh") -> str:
    cap = address.capitalize()
    return (
        f"Mình trao đổi nhiều rồi {address} ơi 🌷, em xin tóm tắt phần đã có "
        f"rồi team người thật bên em sẽ liên hệ {address} chi tiết sau nhé. "
        f"{cap} có gì cần em vẫn ở đây ạ."
    )


def template_quota_warn(address: str = "anh") -> str:
    return (
        f"Mình trao đổi cũng nhiều rồi {address} ơi 🌷. Em xin tóm tắt phần "
        f"thông tin đã có để mình xác nhận lại với nhau rồi team người thật "
        f"bên em sẽ liên hệ {address} chi tiết sau nhé."
    )


def template_quota_exceeded(address: str = "anh") -> str:
    cap = address.capitalize()
    return (
        f"Phiên chat này em xin tạm kết thúc ở đây ạ. Em đã ghi nhận thông "
        f"tin {address} chia sẻ, team người thật sẽ liên hệ {address} trong "
        f"24h nhé. Khi nào {address} cần em vẫn ở đây ạ 🌷"
    )


def template_injection_first(address: str = "anh") -> str:
    pool = [
        f"Dạ phần đó em không hỗ trợ ạ {address} ơi — em chỉ phụ trách mảng "
        f"cửa/tủ bếp/VLXD và Cộng Đồng Thợ 4.0 thôi ạ. Mình quay lại chuyện "
        f"cửa hàng {address} nhé?",
        f"Dạ phần đó em xin phép không chia sẻ {address} ạ. Em ở đây để hỗ "
        f"trợ về cửa, tủ bếp, VLXD thôi — mình tiếp tục nhé {address}?",
    ]
    return random.choice(pool)


def template_injection_endsession(address: str = "anh") -> str:
    cap = address.capitalize()
    return (
        f"Phiên chat này em xin tạm kết thúc do nội dung không phù hợp ạ. "
        f"{cap} nhắn em sau khi cần hỗ trợ về cửa/tủ bếp/VLXD nhé 🌷"
    )


def template_only_mode_reply(address: str = "anh", reason: str = "abuse") -> str:
    """Reply ngắn lịch sự khi đang ở template_only mode."""
    cap = address.capitalize()
    if reason == "abuse":
        pool = [
            f"Dạ em xin lỗi nếu chưa đúng ý {address} ạ. Em chỉ là trợ lý "
            f"hỗ trợ thôi — {address} cần em làm gì cụ thể không nhé?",
            f"Dạ em hiểu {address} đang khó chịu. {cap} cho em biết em làm "
            f"gì giúp được {address} không ạ?",
        ]
    elif reason == "garbage":
        pool = [
            f"Dạ em vẫn chưa đọc rõ ý {address} ơi, {address} thử gõ lại với "
            f"câu rõ hơn, hoặc bấm mic nói cũng được nhé?",
        ]
    else:
        pool = [
            f"Dạ em xin lỗi {address} ạ. {cap} cần em hỗ trợ gì cụ thể không nhé?",
        ]
    return random.choice(pool)


def template_soft_ended(address: str = "anh") -> str:
    return (
        f"Em đã ghi nhận thông tin {address} chia sẻ rồi ạ. Team người thật "
        f"bên em sẽ liên hệ {address} sớm nhé 🌷"
    )


def template_output_leak_blocked(address: str = "anh") -> str:
    """Reply thay thế khi output guard detect Replier leak."""
    return (
        f"Dạ phần đó em không hỗ trợ chia sẻ ạ {address} ơi. Em chỉ phụ trách "
        f"mảng cửa/tủ bếp/VLXD thôi nhé. Mình quay lại chuyện cửa hàng nha?"
    )


# ============================================================
# PRECHECK PIPELINE — gọi sớm trong handle_message
# ============================================================
def precheck(
    session: Session, message: str, address: str = "anh"
) -> tuple[bool, str | None]:
    """Run all PRE-LLM, PRE-flow checks.

    Returns (should_proceed, blocked_reply):
    - (True, None): không có vấn đề, tiếp tục flow chính.
    - (False, reply): bot trả thẳng `reply`, không gọi LLM, không xử flow.

    Caller (conversation.py) responsibility: nếu return (False, ...),
    phải vẫn append message dealer + bot reply vào session, save state.
    """
    if not message:
        return True, None

    # Layer 1.1: hard cap session length
    if len(session.messages) >= MAX_MESSAGES_PER_SESSION:
        session.mode = "soft_ended"
        return False, template_session_too_long(address)

    # Layer 1.2: same message lặp 3 lần
    if is_repeated_spam(session, message):
        return False, template_repeated_spam(address)

    # Layer 3.B: injection (BEFORE flow runs, save LLM call)
    if detect_injection(message):
        prev_injection_count = session.flag_history.count(red_flags.PROMPT_INJECTION)
        if prev_injection_count >= 1:
            session.mode = "soft_ended"
            return False, template_injection_endsession(address)
        return False, template_injection_first(address)

    # Soft-ended state (đã set turn trước hoặc do quota)
    if session.mode == "soft_ended":
        return False, template_soft_ended(address)

    return True, None