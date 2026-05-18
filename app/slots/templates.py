"""Slot Q&A templates.

Phase 1 scope: 3 slot REQUIRED đầy đủ (1.1, 1.2, 4.0) — D9 STRATEGY.
14 slot còn lại: stub đơn giản, Phase 2 mở rộng full 3 biến thể + retry tone.

Refer:
- File 1A § 4 (KICH_BAN_1A_core v0.2.2) — 17 slot template chi tiết
- F2A.5 (LUAT_2A_core v0.2.4) — retry tone giảm dần REQUIRED

> DISCLAIMER: ack template per dealer type là LLM gen (ack_generator.py),
> không paste cứng từ template. Template chỉ là HINT cho câu hỏi gốc.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SlotTemplate(BaseModel):
    """Template 1 slot — refer 1A § 4."""
    slot_id: str
    questions: list[str] = Field(default_factory=list)              # 3 biến thể câu hỏi gốc
    retry_questions: list[str] = Field(default_factory=list)        # Lượt 2-3 (REQUIRED only)
    is_phase_1: bool = False                                        # True nếu có content đầy đủ


# ============================================================
# 17 slot templates — Phase 1 đầy đủ 3 slot, 14 slot stub
# ============================================================


_SLOT_TEMPLATES: dict[str, SlotTemplate] = {
    # ============================================================
    # PHASE 1 — 3 slot REQUIRED (D9 STRATEGY)
    # ============================================================

    "1.1": SlotTemplate(
        slot_id="1.1",
        questions=[
            "Dạ em cảm ơn anh đã sẵn sàng. Đầu tiên cho em xin tên anh và "
            "tên cửa hàng mình ạ — để em xưng hô đúng và lưu hồ sơ cho "
            "chuẩn từ đầu nhé.",
            "Dạ anh ơi, bắt đầu nhé. Em xin tên anh và tên cửa hàng mình "
            "trước để em xưng hô cho đúng ạ.",
            "Em cảm ơn anh nhận lời. Anh cho em xin tên + tên cửa hàng "
            "để em ghi hồ sơ chuẩn nha.",
        ],
        retry_questions=[
            # Lượt 2: nhẹ + giải thích
            "Dạ em xin tên để em biết xưng hô anh cho đúng ạ — em chỉ lưu "
            "trong hồ sơ nội bộ thôi. Anh cho em tên + cửa hàng mình nhé?",
            # Lượt 3 (sau DEFER, re-check): tha thiết + offer dễ hơn
            "Anh không muốn đưa tên thật cũng OK ạ — em ghi tên anh muốn "
            "em gọi là gì cũng được, miễn để em xưng hô cho lịch sự. Anh "
            "cho em chữ gọi mình thôi cũng được ạ.",
        ],
        is_phase_1=True,
    ),

    "1.2": SlotTemplate(
        slot_id="1.2",
        questions=[
            "Dạ em note. Anh cho em xin địa chỉ cửa hàng mình ạ — em ghi "
            "đầy đủ vào hồ sơ. Tiện đây, khách thường đến cửa hàng anh từ "
            "bao xa nhỉ?",
            "Anh ơi, em xin địa chỉ cửa hàng mình. Khách hay đến từ trong "
            "bán kính bao xa anh?",
            "Cho em xin địa chỉ cửa hàng + khách thường đến từ bao xa "
            "nha anh?",
        ],
        retry_questions=[
            "Anh cho em xin địa chỉ cửa hàng — em lưu hồ sơ nội bộ thôi, "
            "không share ra ngoài đâu ạ.",
            "Địa chỉ cửa hàng mình ở đâu vậy anh? Anh ghi quận/huyện cũng "
            "được, không cần chi tiết quá.",
        ],
        is_phase_1=True,
    ),

    "4.0": SlotTemplate(
        slot_id="4.0",
        questions=[
            "Em chuẩn bị bộ thương hiệu (logo + danh thiếp + video giới "
            "thiệu) gửi anh qua Zalo nhé. Anh đồng ý nhận quà này không ạ?",
            "Để em gửi anh bộ thương hiệu riêng cho cửa hàng qua Zalo — "
            "anh OK chứ ạ?",
            "Em làm bộ thương hiệu (logo + danh thiếp + video) gửi qua "
            "Zalo cho anh nhé, anh đồng ý không ạ?",
        ],
        retry_questions=[
            "Bộ thương hiệu này hoàn toàn miễn phí — em gửi qua Zalo cho "
            "anh xem trước. Anh OK chứ ạ?",
            "Anh không cần cũng OK ạ, nhưng em chuẩn bị sẵn cho cửa hàng "
            "mình rồi. Anh có muốn em gửi qua Zalo xem qua không?",
        ],
        is_phase_1=True,
    ),

    # ============================================================
    # PHASE 2+ — 14 slot stub (sẽ fill chi tiết Phase 2)
    # ============================================================

    "1.3": SlotTemplate(
        slot_id="1.3",
        questions=["[Phase 2] Anh cho em xin SĐT / Zalo liên hệ chính ạ?"],
    ),
    "2.1": SlotTemplate(
        slot_id="2.1",
        questions=["[Phase 2] Bên mình mạnh nhất sản phẩm gì anh?"],
    ),
    "2.2": SlotTemplate(
        slot_id="2.2",
        questions=["[Phase 2] Đang phân phối hay sản xuất ạ?"],
    ),
    "2.3": SlotTemplate(
        slot_id="2.3",
        questions=["[Phase 2] Có bao nhiêu thợ, gắn bó lâu chưa anh?"],
    ),
    "2.4": SlotTemplate(
        slot_id="2.4",
        questions=["[Phase 2] Nhập hãng nào? Nếu đứt hàng có backup không?"],
    ),
    "2.5": SlotTemplate(
        slot_id="2.5",
        questions=["[Phase 2] Khách thường liên hệ qua kênh nào?"],
    ),
    "2.6": SlotTemplate(
        slot_id="2.6",
        questions=["[Phase 2] Có Facebook không? Có thợ/đối tác giới thiệu khách không?"],
    ),
    "3.1": SlotTemplate(
        slot_id="3.1",
        questions=["[Phase 2] Khách cũ giới thiệu chiếm bao nhiêu %?"],
    ),
    "3.2": SlotTemplate(
        slot_id="3.2",
        questions=["[Phase 2] Lưu danh sách khách trên Zalo/sổ/Excel ạ?"],
    ),
    "3.3": SlotTemplate(
        slot_id="3.3",
        questions=["[Phase 2] Vướng nhất ở khách cũ là gì anh?"],
    ),
    "3.4": SlotTemplate(
        slot_id="3.4",
        questions=["[Phase 2] Quy trình cọc + công nợ thế nào?"],
    ),
    "3.5": SlotTemplate(
        slot_id="3.5",
        questions=["[Phase 2] Khi lỗi sau bán, anh hay nhà cung cấp đứng ra xử ạ?"],
    ),
    "4.1": SlotTemplate(
        slot_id="4.1",
        questions=[
            "Đầu tiên về LOGO — em đã có sẵn bộ phong cách thiết kế chuẩn "
            "cho ngành mình. Để em chọn 1 cái phù hợp nhất với anh nha, "
            "anh cần chỉnh thì bên em sẽ chỉnh sửa cho anh sau ạ."
        ],
    ),
    "4.2": SlotTemplate(
        slot_id="4.2",
        questions=["[Phase 2] Anh thích màu nào? Có hợp mệnh không?"],
    ),
}


# ============================================================
# Helpers
# ============================================================


def get_template(slot_id: str) -> Optional[SlotTemplate]:
    """Lấy template cho slot_id. None nếu chưa define."""
    return _SLOT_TEMPLATES.get(slot_id)


def get_question(slot_id: str, variant: int = 0) -> Optional[str]:
    """Lấy câu hỏi biến thể `variant` (0/1/2) cho slot.

    Args:
        slot_id: vd "1.1"
        variant: 0/1/2 (engine chọn theo hash(session_id + slot_id) mod 3)
                 — refer 1A § 1.2 rotation

    Returns:
        Câu hỏi tiếng Việt, hoặc None nếu slot không có template.
    """
    tpl = _SLOT_TEMPLATES.get(slot_id)
    if not tpl or not tpl.questions:
        return None
    return tpl.questions[variant % len(tpl.questions)]


def get_retry_question(slot_id: str, attempt: int) -> Optional[str]:
    """Lấy câu retry theo attempt. Refer 1A § 4 retry tone bảng + D11 STRATEGY.

    Args:
        slot_id: vd "1.1"
        attempt: 1/2/3
            - 1: câu hỏi gốc (biến thể 0)
            - 2: retry_questions[0] — nhẹ + giải thích lý do
            - 3: retry_questions[1] — tha thiết + offer fallback (sau DEFER re-check)

    Returns:
        Câu retry, hoặc None.
    """
    tpl = _SLOT_TEMPLATES.get(slot_id)
    if not tpl:
        return None
    if attempt == 1:
        return tpl.questions[0] if tpl.questions else None
    idx = attempt - 2
    if 0 <= idx < len(tpl.retry_questions):
        return tpl.retry_questions[idx]
    return None


def is_phase_1_ready(slot_id: str) -> bool:
    """True nếu slot có template Phase 1 đầy đủ (3 biến thể + retry tone)."""
    tpl = _SLOT_TEMPLATES.get(slot_id)
    return tpl is not None and tpl.is_phase_1
