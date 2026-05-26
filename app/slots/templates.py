"""Slot Q&A templates — 17 slot × 3 biến thể câu hỏi.

Refer:
- File 1A § 4 (KICH_BAN_1A_core v0.3.0) — 17 slot template chi tiết
- F2A.5 (LUAT_2A_core v0.2.5) — retry tone giảm dần REQUIRED
- D9 STRATEGY — Phase 1 = 3 REQUIRED slot, Phase 2 = đủ 17

> DISCLAIMER:
> Template = câu hỏi mặc định / fallback khi LLM gen fail. Production
> dùng `ack_generator.py` LLM gen kết hợp ack + bridge + question theo
> dealer_type (refer F2B.4). Template chỉ là HINT cho LLM + safety net.
>
> Nguyên tắc "lí do ẩn" (refer memory feedback_ack_and_why): câu hỏi
> KHÔNG được kết bằng "Em hỏi để X" hay "(Em muốn biết Y để Z)". Lí do
> phải nén trong cảm thán mở, scenario invite, hoặc cụm danh từ.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SlotTemplate(BaseModel):
    """Template 1 slot — refer 1A § 4."""
    slot_id: str
    questions: list[str] = Field(default_factory=list)              # 3 biến thể câu hỏi gốc
    retry_questions: list[str] = Field(default_factory=list)        # Lượt 2-3 (REQUIRED only)
    is_phase_1: bool = False                                        # True nếu Phase 1 đã có extractor
    has_full_question_set: bool = False                             # True nếu có đủ 3 biến thể (Phase 2+)


# ============================================================
# 17 slot templates — Phase 2 đầy đủ 3 biến thể / slot
# Lấy chính xác từ File 1A § 4 (KICH_BAN_1A_core v0.3.0)
# ============================================================


_SLOT_TEMPLATES: dict[str, SlotTemplate] = {
    # ----------------------------------------------------------------
    # CHỦ ĐỀ 1 — DANH THIẾP (slot 1.1 + 1.2 + 1.3)
    # ----------------------------------------------------------------

    "1.1": SlotTemplate(
        slot_id="1.1",
        questions=[
            "Em cảm ơn anh đã sẵn sàng. Đầu tiên cho em xin tên anh "
            "và tên cửa hàng mình ạ — để em xưng hô cho đúng nhé.",
            "Dạ anh ơi, bắt đầu nhé. Em xin tên anh và tên cửa hàng "
            "mình trước để em xưng hô cho đúng ạ.",
            "Em cảm ơn anh nhận lời. Anh cho em xin tên + tên cửa hàng "
            "để em gọi đúng từ đầu nha.",
        ],
        retry_questions=[
            "Dạ em xin tên để em biết xưng hô anh cho đúng ạ — em chỉ "
            "dùng trong cuộc trao đổi này thôi. Anh cho em tên + cửa hàng "
            "mình nhé?",
            "Anh không muốn đưa tên thật cũng OK ạ — em ghi tên anh "
            "muốn em gọi là gì cũng được, miễn để em xưng hô cho lịch "
            "sự. Anh cho em chữ gọi mình thôi cũng được ạ.",
        ],
        is_phase_1=True,
        has_full_question_set=True,
    ),

    "1.2": SlotTemplate(
        slot_id="1.2",
        questions=[
            "Cho em xin địa chỉ cửa hàng mình nha — tỉnh/thành và quận/huyện là đủ anh.",
            "Anh cho em xin khu vực cửa hàng mình đang ở tỉnh/thành nào, quận/huyện nào nhé.",
            "Em xin địa chỉ khu vực của cửa hàng mình trước nha anh.",
        ],
        retry_questions=[
            "Anh cho em xin tỉnh/thành + quận/huyện của cửa hàng là được ạ.",
            "Anh ngại địa chỉ cụ thể thì cho em tỉnh + quận thôi cũng "
            "được ạ. Vd 'Hà Nội, Cầu Giấy' là đủ.",
        ],
        is_phase_1=True,
        has_full_question_set=True,
    ),

    "1.3": SlotTemplate(
        slot_id="1.3",
        questions=[
            "Tiện đây anh cho em xin số Zalo / điện thoại mình hay dùng "
            "nhất với ạ — em chỉ dùng để hỗ trợ khi cần, không spam đâu nhé.",
            "Anh cho em xin số liên hệ chính ạ (Zalo hoặc điện thoại). "
            "Em chỉ dùng để hỗ trợ anh, không spam đâu nhé.",
            "Còn một thứ nhỏ ạ — em xin số Zalo của anh để khách dễ tìm "
            "+ team em tiện liên hệ. Anh cho em được không?",
        ],
        retry_questions=[
            # Phase 6 R+ Fix F+G: retry tone trung tính + hint format 10-11 số.
            # KHÔNG dùng số ví dụ thực (trùng PII session khác) — dạng generic.
            "Anh cho em xin lại số liên hệ ạ — đủ 10-11 chữ số bắt đầu "
            "bằng 0 (vd 09xx xxx xxx). Em chỉ dùng nội bộ thôi, không spam.",
            "Số liên hệ em chưa nhận đủ ạ. Anh check lại số đầy đủ giúp "
            "em — 10-11 chữ số bắt đầu bằng 0 nhé. Zalo phụ cũng OK ạ.",
        ],
        has_full_question_set=True,
    ),

    # ----------------------------------------------------------------
    # CHỦ ĐỀ 2 — CÔNG VIỆC & KÊNH (slot 2.1 → 2.6)
    # ----------------------------------------------------------------

    "2.1": SlotTemplate(
        slot_id="2.1",
        questions=[
            "Anh em trong ngành mình thường làm nhiều mảng — cửa cuốn, "
            "nhôm hệ, vách kính, tủ bếp... bên anh đang chủ lực mảng "
            "gì, và cái nào anh tự tin mạnh nhất ạ?",
            "Anh ơi, bên cửa hàng mình đang phát triển những mảng sản "
            "phẩm nào ạ, và mảng nào là mạnh nhất?",
            "Em hỏi tiếp ạ — danh mục sản phẩm chủ lực của cửa hàng "
            "mình là gì, và cái nào anh tự tin nhất?",
        ],
        retry_questions=[
            "Anh chọn 1 cái mạnh nhất cho em là OK ạ — vd 'nhôm kính', "
            "'cửa cuốn', 'tủ bếp'. Em cần để hiểu cửa hàng mình rõ hơn.",
            "Anh nói chung chung kiểu 'ngành cửa' / 'nhôm kính' cũng "
            "được ạ — em cần để chọn phong cách thiết kế phù hợp cho "
            "bộ thương hiệu.",
        ],
        has_full_question_set=True,
    ),

    "2.2": SlotTemplate(
        slot_id="2.2",
        questions=[
            "À — hiện bên mình theo mô hình nào: phân phối thuần, hay "
            "có xưởng + đội thi công luôn ạ?",
            "Anh ơi, bên cửa hàng mình là đại lý phân phối thuần, hay "
            "có xưởng sản xuất / thi công luôn ạ?",
            "Em hỏi xíu — bên mình chỉ bán lẻ, hay nhập về gia công + "
            "lắp đặt trực tiếp luôn?",
        ],
        retry_questions=[
            "Đơn giản thôi anh — bên mình là đại lý bán lại hàng nhà "
            "sản xuất, hay anh có xưởng/đội thi công riêng ạ?",
            "Anh nói qua thôi cũng được — bán lẻ hay tự làm? Một trong hai.",
        ],
        has_full_question_set=True,
    ),

    "2.3": SlotTemplate(
        slot_id="2.3",
        questions=[
            "Đội thợ là tài sản số 1 trong ngành mình — bên mình "
            "hiện có tổng bao nhiêu thợ, và mọi người gắn bó với anh "
            "lâu chưa ạ?",
            "Em hỏi thêm — bên anh có đội thợ riêng không, bao nhiêu "
            "người, và ổn định lâu chưa?",
            "Anh cho em xíu thông tin về đội thợ — có bao nhiêu người, "
            "thợ cơ hữu hay vụ?",
        ],
        has_full_question_set=True,
    ),

    "2.4": SlotTemplate(
        slot_id="2.4",
        questions=[
            # Phase 6 R+ Fix B.4 #4: 1 câu hỏi/lượt (combined supplier + backup
            # vào 1 câu duy nhất). Backup question hỏi turn sau qua PARTIAL.
            "Hiện anh đang nhập hàng từ những hãng nào là chính ạ?",
            "Bên cửa hàng mình đang nhập từ hãng nào là chủ lực anh nhỉ?",
            "Em hỏi xíu về nguồn cung — anh nhập từ những hãng nào là chính ạ?",
        ],
        has_full_question_set=True,
    ),

    "2.5": SlotTemplate(
        slot_id="2.5",
        questions=[
            "Còn khách hàng — họ thường tìm đến anh qua kênh nào là "
            "chính ạ, Zalo, điện thoại, hay Facebook?",
            "Anh ơi, khách hàng tìm đến bên mình qua đâu là chính ạ?",
            "À cho em hỏi — khách quen liên hệ anh qua kênh nào hay nhất?",
        ],
        has_full_question_set=True,
    ),

    "2.6": SlotTemplate(
        slot_id="2.6",
        questions=[
            "Cửa hàng mình có fanpage Facebook chưa anh?",
            "Anh có dùng Facebook riêng cho cửa hàng không ạ?",
            "Facebook bên mình hiện có trang cửa hàng chưa anh?",
        ],
        has_full_question_set=True,
    ),

    # ----------------------------------------------------------------
    # CHỦ ĐỀ 3 — KHÁCH CŨ & VƯỚNG MẮC (slot 3.1 → 3.5)
    # ----------------------------------------------------------------

    "3.1": SlotTemplate(
        slot_id="3.1",
        questions=[
            "Chuyển sang chuyện khách cũ xíu — như anh vừa nói khách cũ "
            "giới thiệu là kênh chính. Trong tổng đơn, anh ước chừng "
            "khách cũ + khách giới thiệu lại chiếm khoảng bao nhiêu "
            "phần trăm ạ? Em đoán cao đấy nha.",
            "Anh ơi, khách của mình chủ yếu đến từ giới thiệu của khách "
            "cũ, hay khách mới qua quảng cáo / đi ngang?",
            "Em tò mò xíu — tỉ lệ khách cũ giới thiệu khách mới bên "
            "mình tầm bao nhiêu % vậy anh?",
        ],
        has_full_question_set=True,
    ),

    "3.2": SlotTemplate(
        slot_id="3.2",
        questions=[
            "Cái danh sách khách quý vậy anh đang lưu ở đâu — sổ tay, "
            "Zalo, hay file Excel ạ?",
            "Anh có giữ danh sách khách cũ không? Lưu trên Zalo, sổ tay, "
            "hay Excel ạ?",
            "Em hỏi xíu — danh sách khách cũ mình có lưu lại không, và "
            "nếu có thì ở đâu?",
        ],
        has_full_question_set=True,
    ),

    "3.3": SlotTemplate(
        slot_id="3.3",
        questions=[
            "À cái này em tò mò — khi làm việc với khách cũ, anh thấy "
            "vướng mắc lớn nhất hay gặp là gì ạ? (Quên lịch bảo trì, "
            "không nhớ đã làm gì cho khách sau 1-2 năm, hay khách quay "
            "lại kỳ kèo giá...)",
            "Anh kể em nghe — bên cửa hàng mình đang vướng nhất ở chỗ "
            "nào với khách cũ ạ? (chăm sóc, liên hệ lại, hay gì khác?)",
            "Em tò mò xíu — với khách cũ bên mình, anh đang thấy khó "
            "nhất ở khâu nào ạ?",
        ],
        has_full_question_set=True,
    ),

    "3.4": SlotTemplate(
        slot_id="3.4",
        questions=[
            "Đây hình như là bệnh chung của ngành mình đó anh. Em hỏi "
            "thêm một câu — quy trình thanh toán cọc bên mình thường "
            "thế nào, và sau bàn giao có hay bị nợ kéo dài không ạ?",
            "Anh chia sẻ xíu về tài chính — bên mình thường cọc bao "
            "nhiêu %, và khách thanh toán đầy đủ trong bao lâu sau bàn "
            "giao ạ?",
            "Em hỏi 2 ý nhỏ về dòng tiền — cọc bao nhiêu khi ký, và có "
            "hay bị nợ đọng không?",
        ],
        has_full_question_set=True,
    ),

    "3.5": SlotTemplate(
        slot_id="3.5",
        questions=[
            "Em hỏi thêm 1 ý nhỏ về trách nhiệm sau bán — khi khách "
            "phản ánh lỗi sau lắp đặt, bên mình đứng ra xử trước, hay "
            "là nhà cung cấp ạ?",
            "Anh ơi, nếu sản phẩm bị lỗi sau khi giao, chi phí bảo "
            "hành / sửa thường ai chịu — bên cửa hàng mình, hay nhà "
            "sản xuất ạ?",
            "Em tò mò — bảo hành cho khách, anh ký dưới danh nghĩa cửa "
            "hàng, hay đẩy về nhà cung cấp xử?",
        ],
        has_full_question_set=True,
    ),

    # ----------------------------------------------------------------
    # CHỦ ĐỀ 4 — BỘ THƯƠNG HIỆU (slot 4.0 + 4.1 + 4.2)
    # ----------------------------------------------------------------

    "4.0": SlotTemplate(
        slot_id="4.0",
        questions=[
            "Em xin chân thành cảm ơn anh đã chia sẻ rất thật cùng em "
            "ạ 🌷. Như đã nói ở phần đầu, em xin phép gửi tặng anh món "
            "quà nhỏ — một bộ thương hiệu bao gồm:\n"
            "  🎨 Logo riêng cho cửa hàng mình\n"
            "  📇 Danh thiếp cá nhân hoá\n"
            "  🎬 Video giới thiệu thương hiệu (gen từ logo)\n\n"
            "Anh có đồng ý nhận quà của em không ạ?",
            "Em rất cảm ơn anh đã chia sẻ. Theo đúng lời hứa lúc đầu, "
            "em xin phép tặng anh bộ thương hiệu nhỏ gồm logo riêng + "
            "danh thiếp + video giới thiệu cho cửa hàng mình. Anh đồng "
            "ý nhận chứ ạ?",
            "Dạ phần thu thập thông tin xong rồi anh ơi. Em xin phép "
            "tặng anh bộ thương hiệu (logo + danh thiếp + video giới "
            "thiệu thương hiệu) cho cửa hàng mình — đây là quà miễn phí "
            "em tặng để cảm ơn anh dành thời gian. Anh nhận không ạ?",
        ],
        retry_questions=[
            "Dạ em hỏi lại — bộ thương hiệu này em tặng miễn phí, gồm "
            "logo, danh thiếp, video giới thiệu, đều là quà anh giữ lại "
            "dùng. Anh có muốn em làm cho không ạ?",
            "Nếu anh ngại phiền em làm, em vẫn cứ làm rồi gửi link anh "
            "xem sau cũng OK ạ. Anh cứ nói có hay không thôi, em ghi nhận.",
        ],
        is_phase_1=True,
        has_full_question_set=True,
    ),

    "4.1": SlotTemplate(
        slot_id="4.1",
        questions=[
            "Đầu tiên về LOGO — em đã có sẵn bộ phong cách thiết kế "
            "chuẩn cho ngành mình. Để em chọn 1 cái phù hợp nhất với "
            "anh nha, anh cần chỉnh thì bên em sẽ chỉnh sửa cho anh sau "
            "ạ — anh yên tâm điểm này nhé.",
            "Em làm bộ thương hiệu cho anh nhé. Phần logo, em đã có "
            "sẵn nhiều phong cách phù hợp ngành mình — em chọn cho anh "
            "trước, sau đó anh duyệt và chỉnh nếu cần ạ.",
            "Em làm bộ thương hiệu cho anh. Logo em chọn theo phong "
            "cách phổ biến ngành mình rồi gửi anh xem, OK chứ ạ?",
        ],
        has_full_question_set=True,
    ),

    "4.2": SlotTemplate(
        slot_id="4.2",
        questions=[
            "Dạ. Còn về MÀU SẮC thương hiệu — không biết anh có đặc "
            "biệt thích màu nào không, hoặc có màu nào hợp mệnh phong "
            "thủy của anh không ạ?",
            "Anh có thích màu nào cho thương hiệu của mình không, hoặc "
            "có quan tâm đến phong thủy / mệnh hợp màu không ạ?",
            "Em hỏi xíu — màu chủ đạo cho bộ thương hiệu mình, anh "
            "muốn màu gì, hay để em chọn theo gu ngành + phong thủy?",
        ],
        has_full_question_set=True,
    ),
}


# ============================================================
# Helpers
# ============================================================


def get_template(slot_id: str) -> Optional[SlotTemplate]:
    """Lấy template cho slot_id. None nếu chưa define."""
    return _SLOT_TEMPLATES.get(slot_id)


def get_question(
    slot_id: str,
    variant: Optional[int] = None,
    session_id: Optional[str] = None,
    attempt_offset: int = 0,
) -> Optional[str]:
    """Lấy câu hỏi biến thể `variant` cho slot (refer 1A § 1.2 rotation).

    Args:
        slot_id: vd "1.1"
        variant: 0/1/2 chỉ định trực tiếp (test). None → tự pick theo session.
        session_id: Khi variant=None + có session_id → hash(session_id+slot_id)
            mod len(questions) để giữ variant cố định CẢ SESSION (consistent).
            Default 0 nếu cả 2 đều None.
        attempt_offset: Offset cộng vào variant khi retry không có retry template
            (Phase 5 R1 Gap 7) — ép đổi variant để KHÔNG lặp câu y hệt.
            Default 0 (giữ behavior cũ).

    Returns:
        Câu hỏi tiếng Việt, hoặc None nếu slot không có template.
    """
    tpl = _SLOT_TEMPLATES.get(slot_id)
    if not tpl or not tpl.questions:
        return None
    if variant is not None:
        return tpl.questions[(variant + attempt_offset) % len(tpl.questions)]
    if session_id:
        import hashlib
        h = hashlib.md5(f"{session_id}|{slot_id}".encode("utf-8")).hexdigest()
        idx = (int(h, 16) + attempt_offset) % len(tpl.questions)
        return tpl.questions[idx]
    return tpl.questions[attempt_offset % len(tpl.questions)]


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
    """True nếu slot có Phase 1 extractor (3 slot: 1.1, 1.2, 4.0)."""
    tpl = _SLOT_TEMPLATES.get(slot_id)
    return tpl is not None and tpl.is_phase_1


def has_full_question_set(slot_id: str) -> bool:
    """True nếu slot có đủ 3 biến thể câu hỏi (Phase 2+)."""
    tpl = _SLOT_TEMPLATES.get(slot_id)
    return tpl is not None and tpl.has_full_question_set
