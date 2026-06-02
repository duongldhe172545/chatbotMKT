"""Small deterministic edge cases shared by greeting and LLM-first intake."""
from __future__ import annotations

import re

from app.models.schema import SessionState


_BENEFIT_QUESTION_RE = re.compile(
    r"\b("
    r"(?:anh|chị|mình|tôi|tao)\s+(?:được|nhận|có)\s+(?:gì|quyền\s*lợi|lợi\s*ích)"
    r"|(?:nhắn\s*tin|nói\s*chuyện|trao\s*đổi|tham\s*gia).{0,30}"
    r"(?:được|nhận|có)\s+(?:gì|quyền\s*lợi|lợi\s*ích)"
    r"|(?:được|nhận|có)\s+(?:gì|quyền\s*lợi|lợi\s*ích).{0,30}"
    r"(?:nhắn\s*tin|nói\s*chuyện|trao\s*đổi|tham\s*gia)"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_PING_RE = re.compile(
    r"^\s*(?:(?:a\s*)?l[oô]+|hello|hi|ê|test|tét)"
    r"(?:[\s,!.?]*(?:(?:a\s*)?l[oô]+|hello|hi|ê|test|tét))*[\s,!.?]*$",
    re.IGNORECASE | re.UNICODE,
)

_BOUNDARY_FLIRT_RE = re.compile(
    r"\b(?:đi|di)\s+(?:chơi|choi|cà\s*phê|ca\s*phe|cafe|nhậu|nhau)"
    r"\s+(?:với|voi)\s+(?:anh|chị)\b|"
    r"\b(?:hẹn\s*hò|hen\s*ho)\b",
    re.IGNORECASE | re.UNICODE,
)


def is_benefit_question(message: str) -> bool:
    """True when the dealer asks what they receive from the conversation."""
    return bool(_BENEFIT_QUESTION_RE.search(message or ""))


def is_ping_message(message: str) -> bool:
    """True for a greeting/ping that must not be treated as consent."""
    return bool(_PING_RE.match(message or ""))


def is_boundary_flirt_message(message: str) -> bool:
    """True for a playful invitation that needs a polite work boundary."""
    return bool(_BOUNDARY_FLIRT_RE.search(message or ""))


def render_benefit_reply(session: SessionState) -> str:
    """Answer the benefit question first, then ask permission to continue."""
    address_form = session.address_form.value
    return (
        f"Dạ, sau cuộc trao đổi này bên em tặng {address_form} một bộ thương hiệu "
        "miễn phí gồm logo riêng, danh thiếp cá nhân hóa và video giới thiệu cửa "
        "hàng. Bộ này giúp cửa hàng mình có hình ảnh gọn gàng hơn khi giới thiệu "
        f"với khách. Mình tiếp tục được không {address_form}?"
    )


def render_ping_reply(session: SessionState) -> str:
    """Acknowledge a ping without pretending the dealer already consented."""
    address_form = session.address_form.value
    return (
        f"Dạ em nghe đây {address_form} ạ 🌷 Em đang ở đây để hỗ trợ mình "
        f"làm bộ thương hiệu miễn phí cho cửa hàng. Nếu {address_form} tiện, mình bắt "
        "đầu nhé?"
    )


def render_boundary_flirt_ack(session: SessionState, owner_name: str | None = None) -> str:
    """Decline a playful invitation warmly without losing the intake flow."""
    address_form = session.address_form.value
    call = f"{address_form.capitalize()} {owner_name}".strip() if owner_name else address_form.capitalize()
    return (
        f"{call} vui tính quá ạ. Em chỉ xin phép hỗ trợ mình qua đây thôi, "
        f"còn phần cửa hàng em vẫn chăm kỹ cho {address_form} nhé."
    )
