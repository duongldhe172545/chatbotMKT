"""Em Linh MKT v7 — định nghĩa 16 micro-turn của flow chính.

Cấu trúc: 4 chủ đề × micro-turn:
- Chủ đề 1 (Danh thiếp):       1.1, 1.2, 1.3       (3 turn)
- Chủ đề 2 (Công việc + Kênh): 2.1 .. 2.6          (6 turn)
- Chủ đề 3 (Mỏ vàng khách cũ): 3.1, 3.2, 3.3, 3.4  (4 turn)
- Chủ đề 4 (Quà BRANDKIT):     4.0, 4.1, 4.2       (3 turn)

Mỗi turn có `instruction` — prompt template inject runtime cho Replier
để Replier sinh câu hỏi tự nhiên, có hồn, không cộc lốc.

Source: EM_LINH_MKT_v7.md (PHẦN 2 — happy case Anh Tùng/Cao Bằng).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class V7Turn:
    turn_id: str           # "1.1", "1.2", "2.1", ..., "4.2"
    theme: str             # "danh_thiep" | "cong_viec" | "mo_vang" | "brandkit"
    description: str       # mô tả ngắn (cho log/debug)
    expected_fields: tuple[str, ...]  # field cần extract turn này
    is_required: bool      # True = không cho skip (1.1, 4.0); False = retry 2 lần rồi skip
    instruction: str       # template inject vào Replier — bao gồm CONTEXT + question style
    next_turn: str | None  # turn kế tiếp; None = đi confirming


# ============================================================
# CHỦ ĐỀ 1 — DANH THIẾP (3 turn)
# ============================================================
TURN_1_1 = V7Turn(
    turn_id="1.1",
    theme="danh_thiep",
    description="Tên anh + tên cửa hàng",
    expected_fields=("owner_name", "dealer_name"),
    is_required=True,  # KHÔNG cho skip — bắt buộc để xưng hô + lưu hồ sơ
    instruction=(
        "TURN 1.1 — Xin tên người + tên cửa hàng (BẮT BUỘC, không cho skip).\n"
        "Mở đầu bằng cảm ơn dealer đã đồng ý chat. Sau đó hỏi tên CỦA NGƯỜI và "
        "tên CỬA HÀNG — gộp 2 ý vào 1 câu hỏi tự nhiên (đây là cặp tự nhiên).\n"
        "Mục đích: để xưng hô đúng + lưu hồ sơ cho chuẩn.\n"
        "Tone: ngắn gọn, chuyên gia, không sến.\n"
        "Mẫu: 'Dạ em cảm ơn anh. Đầu tiên cho em xin tên anh và tên cửa hàng "
        "mình ạ — để em xưng hô đúng và lưu hồ sơ cho chuẩn.'"
    ),
    next_turn="1.2",
)

TURN_1_2 = V7Turn(
    turn_id="1.2",
    theme="danh_thiep",
    description="Địa chỉ đầy đủ",
    expected_fields=("address",),
    is_required=False,
    instruction=(
        "TURN 1.2 — Xin địa chỉ ĐẦY ĐỦ (tổ/phường/quận/TP/tỉnh).\n"
        "Ack tên dealer + tên cửa hàng vừa nhận (anchor latest). Sau đó hỏi địa "
        "chỉ FULL — không chỉ tỉnh.\n"
        "Mẫu: 'Dạ anh Tùng, cửa hàng Thanh Tùng — em note rồi ạ. Cho em xin "
        "địa chỉ đầy đủ của cửa hàng mình được không anh?'"
    ),
    next_turn="1.3",
)

TURN_1_3 = V7Turn(
    turn_id="1.3",
    theme="danh_thiep",
    description="SĐT + đặc sản hook (province_specialty)",
    expected_fields=("phone_or_zalo",),
    is_required=False,
    instruction=(
        "TURN 1.3 — Xin SĐT, KÈM hook đặc sản tỉnh (PROVINCE_SPECIALTY).\n"
        "Nếu PROFILE SO FAR có 'province_specialty' (vd 'vịt quay 7 vị Cao "
        "Bằng'), CHÈN câu khen đặc sản đó TRƯỚC khi xin số — để tạo "
        "cảm giác địa phương, không phải bot generic. Vd: 'Cao Bằng — em "
        "mê vịt quay 7 vị với phở chua Cao Bằng từ lâu mà chưa được ăn "
        "thật anh ơi 🤤'.\n"
        "Sau đó hỏi SĐT nhẹ nhàng kèm cớ 'để hẹn anh trên đó' hoặc 'liên hệ "
        "công việc'.\n"
        "Nếu KHÔNG có province_specialty trong PROFILE → vào thẳng hỏi SĐT, "
        "không bịa đặc sản."
    ),
    next_turn="2.1",
)


# ============================================================
# CHỦ ĐỀ 2 — CÔNG VIỆC + KÊNH (6 turn)
# ============================================================
TURN_2_1 = V7Turn(
    turn_id="2.1",
    theme="cong_viec",
    description="Danh mục chủ lực + sản phẩm chính",
    expected_fields=("category_stack", "main_product"),
    is_required=False,
    instruction=(
        "TURN 2.1 — Hỏi DANH MỤC SẢN PHẨM chủ lực + sản phẩm MẠNH NHẤT.\n"
        "Cảm ơn dealer cho số. Sau đó MỞ ĐẦU bằng câu show kiến thức ngành: "
        "'em nắm được anh em trong ngành [nhôm kính/cửa cuốn/...] bên mình "
        "thường phân phối hoặc sản xuất rất nhiều mặt hàng — cửa cuốn, "
        "NHÔM HỆ, cửa nhôm, vách kính, tủ bếp...' (chèn 'nhôm hệ' để show "
        "biết từ chuyên môn).\n"
        "Sau đó hỏi: 'anh cho em xin các danh mục sản phẩm chủ lực của bên "
        "[dealer_name] được không ạ?'\n"
        "Mục đích: lấy category_stack (list) + main_product (1 cái MẠNH NHẤT, "
        "dealer thường tự nói 'mạnh nhất là X')."
    ),
    next_turn="2.2",
)

TURN_2_2 = V7Turn(
    turn_id="2.2",
    theme="cong_viec",
    description="Mô hình phân phối/sản xuất/cả 2",
    expected_fields=("business_model_signal", "dealer_type"),
    is_required=False,
    instruction=(
        "TURN 2.2 — Hỏi MÔ HÌNH KD: phân phối / sản xuất / cả 2.\n"
        "Ack ngắn product chủ lực dealer vừa nói (vd 'em thấy rất nhiều dự "
        "án lớn đều ưa chuộng sản phẩm này').\n"
        "Sau đó hỏi: 'Hiện tại [dealer_name] đang tập trung mô hình nào ạ — "
        "phân phối thương mại, sản xuất, hay cả hai vậy anh?'\n"
        "Tone: chuyên gia khiêm tốn, không show off."
    ),
    next_turn="2.3",
)

TURN_2_3 = V7Turn(
    turn_id="2.3",
    theme="cong_viec",
    description="Đội thợ — số lượng + ổn định",
    expected_fields=("est_team_size", "team_stability_signal"),
    is_required=False,
    instruction=(
        "TURN 2.3 — Hỏi ĐỘI THỢ (số người + ổn định).\n"
        "MỞ ĐẦU bằng LÝ DO CHUYÊN MÔN: 'Lắp đặt [main_product] thường yêu "
        "cầu chính xác tỉ mỉ về kỹ thuật và độ thẩm mỹ anh nhỉ. Để cân "
        "bằng được 2 yếu tố này, bên mình đang có tổng bao nhiêu thợ ạ?'\n"
        "Đây là CẶP TỰ NHIÊN — có đội + bao nhiêu thợ gộp 1 câu hỏi.\n"
        "Mục đích: lấy est_team_size (số) + signal stability (cơ hữu hay vụ)."
    ),
    next_turn="2.4",
)

TURN_2_4 = V7Turn(
    turn_id="2.4",
    theme="cong_viec",
    description="Hãng nhập + phân khúc khách",
    expected_fields=("supplier_brands", "customer_segment_signal"),
    is_required=False,
    instruction=(
        "TURN 2.4 — Hỏi HÃNG NHẬP + cớ lấy phân khúc khách.\n"
        "Khen team thợ vừa nghe ('4 thợ cơ hữu mà gắn bó lâu — đây là tài sản "
        "thật của cửa hàng mình anh ơi').\n"
        "Hỏi hãng nhập KÈM lý do tại sao hỏi: 'hiện tại [dealer_name] đang "
        "phát triển mặt hàng của những hãng nào ạ? Em hỏi cái này vì khi nắm "
        "được anh đang chạy hãng nào, em cũng hình dung được phân khúc khách "
        "hàng anh đang nhắm tới — cao cấp, trung cấp hay phổ thông — để hỗ "
        "trợ chiến lược cho chuẩn ạ.'\n"
        "Mục đích: lấy supplier_brands (list) + signal phân khúc."
    ),
    next_turn="2.5",
)

TURN_2_5 = V7Turn(
    turn_id="2.5",
    theme="cong_viec",
    description="Kênh khách liên hệ chính",
    expected_fields=("primary_contact_channel", "zalo"),
    is_required=False,
    instruction=(
        "TURN 2.5 — Hỏi KÊNH KHÁCH LIÊN HỆ chính.\n"
        "Ack hãng + phân khúc dealer vừa nói (vd 'em thấy nhiều nhà trên "
        "[province] đều sử dụng combo [supplier_brands] chắc bên mình bán "
        "chạy lắm anh ha 😊').\n"
        "Sau đó: 'Hiện tại khách thường liên hệ anh qua kênh nào nhất ạ, "
        "để tiện sau này em hỗ trợ anh trên các nền tảng số này?'"
    ),
    next_turn="2.6",
)

TURN_2_6 = V7Turn(
    turn_id="2.6",
    theme="cong_viec",
    description="Facebook quảng bá",
    expected_fields=("facebook", "fb_marketing_status"),
    is_required=False,
    instruction=(
        "TURN 2.6 — Hỏi FACEBOOK quảng bá ('tương tác tốt' — show quan sát).\n"
        "Mở đầu: 'Em có lượn lờ Facebook thì thấy các anh hay up ảnh công "
        "trình trên đó, em thấy tương tác cũng tốt lắm 💚.'\n"
        "Sau đó: 'Không biết anh [owner_name] có quảng bá sản phẩm trên kênh "
        "online nào không, cho em xem với ạ?'\n"
        "Nếu dealer trả lời 'chưa có' / 'lười' → ack nhẹ 'vậy em lại có thêm "
        "việc hỗ trợ anh — em rất tự tin về phần này 😉'."
    ),
    next_turn="3.1",
)


# ============================================================
# CHỦ ĐỀ 3 — MỎ VÀNG KHÁCH CŨ (4 turn)
# ============================================================
TURN_3_1 = V7Turn(
    turn_id="3.1",
    theme="mo_vang",
    description="60-80% truyền miệng — xác nhận",
    expected_fields=("customer_old_percentage",),
    is_required=False,
    instruction=(
        "TURN 3.1 — Mồi 60-80% khách truyền miệng, xác nhận.\n"
        "Insight chính xác: 'Thường em thấy trong ngành mình bây giờ tới 60-"
        "80% khách hàng [main_category] là do khách cũ giới thiệu. Không biết "
        "bên mình thì thế nào anh nhỉ?'\n"
        "Mục đích: lấy customer_old_percentage (vd '60-80%', 'gần như hết', "
        "'không nhiều')."
    ),
    next_turn="3.2",
)

TURN_3_2 = V7Turn(
    turn_id="3.2",
    theme="mo_vang",
    description="Cách lưu khách (Zalo/Sổ/Excel/khác)",
    expected_fields=("customer_storage_method",),
    is_required=False,
    instruction=(
        "TURN 3.2 — Hỏi CÁCH LƯU khách + framing 'chốt đơn trong tầm tay'.\n"
        "Khen tỷ lệ khách cũ dealer vừa nói (vd 'Ui được vậy là tốt nhất rồi "
        "anh nhỉ. Vì đây là nhóm khách tin tưởng vào uy tín của mình, họ tìm "
        "đến là khả năng chốt đơn trong tầm tay 💪.').\n"
        "Sau đó hỏi: 'Vậy còn khách hàng cũ mình có lưu lại danh sách để liên "
        "hệ chăm sóc không anh? Nếu có thì anh lưu trên:\n"
        "📱 Zalo\n"
        "📓 Sổ tay\n"
        "💻 Excel\n"
        "Hay có phần mềm nào khác không anh?'"
    ),
    next_turn="3.3",
)

TURN_3_3 = V7Turn(
    turn_id="3.3",
    theme="mo_vang",
    description="Vướng mắc — open question ('đang chờ kể')",
    expected_fields=("customer_pain", "usp_signal"),
    is_required=False,
    instruction=(
        "TURN 3.3 — Open question về VƯỚNG MẮC khách cũ (turn quan trọng nhất).\n"
        "Framing MỎ VÀNG: 'Em thấy đây là MỎ VÀNG đấy anh ạ ✨. Khách hàng đã "
        "tin tưởng mình rồi, khả năng mua thêm sản phẩm là rất cao. Nếu mình "
        "đang bỏ quên mỏ vàng này thì tiếc lắm anh.'\n"
        "Mở mời chia sẻ THẬT: 'Anh có thể chia sẻ cho em những phần mình "
        "đang vướng mắc đối với khách hàng cũ. Chăm sóc khách hàng là nghề "
        "của em rồi, em đang chờ để được anh kể cho nghe đây ạ 🌷.'\n"
        "Mục đích: lấy customer_pain (TEXT DÀI raw — toàn bộ câu chuyện "
        "dealer kể) + usp_signal (lợi thế ngầm trong câu kể). Đây là turn MỞ "
        "— dealer kể tự do, KHÔNG enum, KHÔNG cắt ngắn."
    ),
    next_turn="3.4",
)

TURN_3_4 = V7Turn(
    turn_id="3.4",
    theme="mo_vang",
    description="Cọc + công nợ (cặp tự nhiên)",
    expected_fields=("payment_terms_signal",),
    is_required=False,
    instruction=(
        "TURN 3.4 — Hỏi CỌC + CÔNG NỢ (cặp tự nhiên).\n"
        "Empathy: 'Đây hình như là bệnh chung của ngành mình đó anh. Em nghĩ "
        "là em sẽ hỗ trợ được anh phần nào, bằng những cách bài bản hơn.'\n"
        "Hỏi câu cuối: 'Anh cho em hỏi thêm một câu cuối cùng — phần này nhiều "
        "anh em hay tâm sự với em nhất — thường khi bắt đầu một công trình "
        "bên mình, quy trình thanh toán cọc sẽ ra sao ạ, và sau khi bàn giao "
        "có hay bị nợ kéo dài không anh?'"
    ),
    next_turn="4.0",
)


# ============================================================
# CHỦ ĐỀ 4 — QUÀ BRANDKIT (3 turn)
# ============================================================
TURN_4_0 = V7Turn(
    turn_id="4.0",
    theme="brandkit",
    description="Xin consent nhận quà brandkit",
    expected_fields=("brandkit_consent",),
    is_required=True,  # BẮT BUỘC consent
    instruction=(
        "TURN 4.0 — Cảm ơn + xin CONSENT nhận quà BRANDKIT (BẮT BUỘC).\n"
        "Cảm ơn chia sẻ: 'Em xin chân thành cảm ơn anh đã chia sẻ rất thật "
        "cùng em Linh ạ 🌷.'\n"
        "CALLBACK GREETING: 'Như đã nói ở phần đầu, em xin phép gửi tặng anh "
        "món quà nhỏ — một bộ BRANDKIT bao gồm:\n"
        "🎨 Logo riêng cho [dealer_name]\n"
        "📇 Namecard cá nhân hóa\n"
        "🎬 Video giới thiệu thương hiệu (gen từ logo)\n\n"
        "Anh có đồng ý nhận quà của em không ạ?'\n"
        "Chờ dealer trả lời yes/no — chỉ tiếp 4.1+4.2 nếu yes."
    ),
    next_turn="4.1",
)

TURN_4_1 = V7Turn(
    turn_id="4.1",
    theme="brandkit",
    description="Logo (Em chọn, sửa sau)",
    expected_fields=(),  # No extract — logic flow
    is_required=False,
    instruction=(
        "TURN 4.1 — LOGO: thông báo 'em chọn, sửa sau'. KHÔNG hỏi gì.\n"
        "Cảm ơn ngắn: 'Em cảm ơn anh ạ 🎉. Em xin phép hỏi thêm 2 ý nhỏ để bộ "
        "brandkit được cá nhân hóa đúng ý anh nhất nhé.'\n"
        "Thông báo logo: 'Đầu tiên về LOGO — em đã có sẵn bộ phong cách thiết "
        "kế chuẩn cho ngành [main_category]. Để em chọn 1 cái phù hợp nhất "
        "với anh nha, anh cần chỉnh thì bên em sẽ chỉnh sửa toàn phần cho "
        "anh sau ạ — anh yên tâm điểm này nhé.'\n"
        "Dealer reply 'ok' → qua 4.2. Không cần extract field."
    ),
    next_turn="4.2",
)

TURN_4_2 = V7Turn(
    turn_id="4.2",
    theme="brandkit",
    description="Màu + phong thủy",
    expected_fields=("color_accent", "feng_shui_signal"),
    is_required=False,
    instruction=(
        "TURN 4.2 — Hỏi MÀU SẮC thương hiệu + có hợp mệnh phong thủy không.\n"
        "Hỏi gọn: 'Dạ. Còn về MÀU SẮC thương hiệu — không biết anh có đặc "
        "biệt thích màu nào không, hoặc có màu nào hợp mệnh phong thủy của "
        "anh không ạ?'\n"
        "Khi dealer trả lời (vd 'Mậu Thân, hợp xanh đậm + bạc'), ack với "
        "lời khen tổng hợp: 'Xanh đậm + bạc kim loại — vừa hợp mệnh, vừa "
        "hợp ngành, vừa hợp gu anh — đẹp đúng kiểu chuẩn rồi ạ ✨. Em ghi "
        "nhận đầy đủ. Em xin tóm tắt toàn bộ hồ sơ để anh xem có gì cần "
        "chỉnh không nhé.'\n"
        "Sau turn này → CONFIRMING (render card)."
    ),
    next_turn=None,  # → confirming
)


# ============================================================
# DICT lookup turn_id → V7Turn
# ============================================================
V7_TURNS: dict[str, V7Turn] = {
    t.turn_id: t for t in [
        TURN_1_1, TURN_1_2, TURN_1_3,
        TURN_2_1, TURN_2_2, TURN_2_3, TURN_2_4, TURN_2_5, TURN_2_6,
        TURN_3_1, TURN_3_2, TURN_3_3, TURN_3_4,
        TURN_4_0, TURN_4_1, TURN_4_2,
    ]
}

# Turn đầu tiên (sau greeting)
FIRST_TURN_ID = "1.1"

# Số lần retry tối đa cho turn KHÔNG required khi dealer refuse/skip.
# Sau MAX_TURN_RETRIES → skip turn, qua next_turn.
MAX_TURN_RETRIES = 2


def get_turn(turn_id: str) -> V7Turn | None:
    """Lookup turn by id."""
    return V7_TURNS.get(turn_id)


def next_turn_id(current_turn_id: str) -> str | None:
    """Trả turn_id kế tiếp; None nếu đã hết flow (→ confirming)."""
    t = V7_TURNS.get(current_turn_id)
    return t.next_turn if t else None


def is_turn_complete(turn: V7Turn, profile_dict: dict) -> bool:
    """True nếu MỌI expected_field đã có giá trị (không None/empty)."""
    if not turn.expected_fields:
        return True  # turn không cần extract (vd 4.1)
    for field in turn.expected_fields:
        val = profile_dict.get(field)
        if val is None or val == "" or val == []:
            return False
    return True


# ============================================================
# HARDCODED REPLY TEMPLATES — đảm bảo bot hỏi ĐÚNG câu mỗi turn
# (LLM Replier drift quá nhiều — không follow strict instruction)
# ============================================================
def render_turn_question(turn_id: str, profile, address_form: str = "anh") -> str:
    """Render câu hỏi của turn từ template hardcoded + interpolate dealer data.

    Trả "" nếu turn_id không có template.
    """
    from app.labels import CATEGORY_LABEL

    owner = profile.owner_name or "anh/chị"
    dealer = profile.dealer_name or "bên mình"
    addr = address_form or "anh"
    main_prod = profile.main_product or (
        profile.category_stack[0] if profile.category_stack else "sản phẩm chủ lực"
    )
    # main_cat: ưu tiên dùng category_stack đầu tiên (raw), fallback label
    # của main_category enum, fallback chữ generic "nhôm kính".
    if profile.category_stack:
        main_cat = profile.category_stack[0]
    elif profile.main_category:
        main_cat = CATEGORY_LABEL.get(profile.main_category, profile.main_category)
    else:
        main_cat = "nhôm kính"
    specialty = profile.province_specialty

    templates: dict[str, str] = {
        "1.1": (
            f"Dạ em cảm ơn {addr} đã sẵn sàng nhé. Đầu tiên cho em xin tên "
            f"{addr} và tên cửa hàng mình ạ — để em xưng hô đúng và lưu hồ "
            f"sơ cho chuẩn từ đầu nhé."
        ),
        "1.2": (
            f"Dạ {addr} {owner}, cửa hàng {dealer} — em note rồi ạ! Cho em "
            f"xin địa chỉ đầy đủ của cửa hàng mình được không {addr}? "
            f"(số nhà / tổ / phường, quận-huyện, tỉnh-thành ạ)"
        ),
        "1.3": (
            (
                f"{(specialty.split(',')[0].split(' với ')[0].capitalize())} — em "
                f"mê {specialty} từ lâu mà chưa được ăn thật {addr} ơi 🤤. "
                f"Nếu có dịp em được ăn cùng {addr} {owner} thì còn gì bằng. "
                f"Mà tiện đây {addr} cho em xin số điện thoại để em hẹn {addr} "
                f"trên đó luôn được không ạ?"
            )
            if specialty
            else (
                f"Dạ em ghi nhận địa chỉ rồi ạ. Tiện đây {addr} cho em xin "
                f"số điện thoại hoặc Zalo mình hay dùng nhất với ạ — để em "
                f"liên hệ {addr} khi cần."
            )
        ),
        "2.1": (
            f"Dạ em cảm ơn, em lưu số rồi. Em nắm được anh em trong ngành "
            f"{main_cat} bên mình thường phân phối hoặc sản xuất rất nhiều "
            f"mặt hàng — cửa cuốn, nhôm hệ, cửa nhôm, vách kính, tủ bếp... "
            f"{addr.capitalize()} cho em xin các danh mục sản phẩm chủ lực "
            f"của bên {dealer} được không ạ, đặc biệt là mảng mạnh nhất?"
        ),
        "2.2": (
            f"Dạ em thấy rất nhiều dự án lớn đều ưa chuộng sản phẩm này. "
            f"Hiện tại {dealer} đang tập trung mô hình nào ạ — phân phối "
            f"thương mại, sản xuất, hay cả hai vậy {addr}?"
        ),
        "2.3": (
            f"Lắp đặt {main_prod} thường yêu cầu chính xác tỉ mỉ về kỹ "
            f"thuật và độ thẩm mỹ {addr} nhỉ. Để cân bằng được 2 yếu tố "
            f"này, bên mình đang có tổng bao nhiêu thợ ạ?"
        ),
        "2.4": (
            f"Đội thợ ổn định lâu — đây là tài sản thật của cửa hàng mình "
            f"{addr} ơi. {addr.capitalize()} chia sẻ thêm với em — hiện tại "
            f"{dealer} đang phát triển mặt hàng của những hãng nào ạ?\n\n"
            f"Em hỏi cái này vì khi nắm được {addr} đang chạy hãng nào, em "
            f"cũng hình dung được phân khúc khách hàng {addr} đang nhắm tới "
            f"— cao cấp, trung cấp hay phổ thông — để hỗ trợ chiến lược cho "
            f"chuẩn ạ."
        ),
        "2.5": (
            f"Em ghi nhận hãng nhập + phân khúc bên mình rồi ạ. Hiện tại "
            f"khách thường liên hệ {addr} qua kênh nào nhất ạ, để tiện sau "
            f"này em hỗ trợ {addr} trên các nền tảng số này?"
        ),
        "2.6": (
            f"Em có 'lượn lờ' Facebook thì thấy các anh hay up ảnh công "
            f"trình trên đó, em thấy tương tác cũng tốt lắm 💚. Không biết "
            f"{addr} {owner} có quảng bá sản phẩm trên kênh online nào "
            f"không, cho em xem với ạ?"
        ),
        "3.1": (
            f"Thường em thấy trong ngành mình bây giờ tới 60-80% khách hàng "
            f"{main_cat} là do khách cũ giới thiệu. Không biết bên mình thì "
            f"thế nào {addr} nhỉ?"
        ),
        "3.2": (
            f"Ui được vậy là tốt nhất rồi {addr} nhỉ. Vì đây là nhóm khách "
            f"tin tưởng vào uy tín của mình, họ tìm đến là khả năng 'chốt "
            f"đơn' trong tầm tay 💪.\n\n"
            f"Vậy còn khách hàng cũ mình có lưu lại danh sách để liên hệ "
            f"chăm sóc không {addr}? Nếu có thì {addr} lưu trên:\n"
            f"📱 Zalo\n"
            f"📓 Sổ tay\n"
            f"💻 Excel\n"
            f"Hay có phần mềm nào khác không {addr}?"
        ),
        "3.3": (
            f"Em thấy đây là MỎ VÀNG đấy {addr} ạ ✨. Khách hàng đã tin "
            f"tưởng mình rồi, khả năng mua thêm sản phẩm là rất cao. Nếu "
            f"mình đang 'bỏ quên' mỏ vàng này thì tiếc lắm {addr}.\n\n"
            f"{addr.capitalize()} có thể chia sẻ cho em những phần mình đang "
            f"vướng mắc đối với khách hàng cũ. Chăm sóc khách hàng là nghề "
            f"của em rồi, em đang chờ để được {addr} kể cho nghe đây ạ 🌷."
        ),
        "3.4": (
            f"Đây hình như là bệnh chung của ngành mình đó {addr}. Em nghĩ "
            f"là em sẽ hỗ trợ được {addr} phần nào, bằng những cách bài bản "
            f"hơn.\n\n"
            f"{addr.capitalize()} cho em hỏi thêm một câu cuối cùng — phần "
            f"này nhiều anh em hay tâm sự với em nhất — thường khi bắt đầu "
            f"một công trình bên mình, quy trình thanh toán cọc sẽ ra sao ạ, "
            f"và sau khi bàn giao có hay bị nợ kéo dài không {addr}?"
        ),
        "4.0": (
            f"Em xin chân thành cảm ơn {addr} đã chia sẻ rất thật cùng em "
            f"Linh ạ 🌷.\n\n"
            f"Như đã nói ở phần đầu, em xin phép gửi tặng {addr} món quà "
            f"nhỏ — một bộ BRANDKIT bao gồm:\n\n"
            f"🎨 Logo riêng cho {dealer}\n"
            f"📇 Namecard cá nhân hóa\n"
            f"🎬 Video giới thiệu thương hiệu (gen từ logo)\n\n"
            f"{addr.capitalize()} có đồng ý nhận quà của em không ạ?"
        ),
        "4.1": (
            f"Em cảm ơn {addr} ạ 🎉. Em xin phép hỏi thêm 2 ý nhỏ để bộ "
            f"brandkit được cá nhân hóa đúng ý {addr} nhất nhé.\n\n"
            f"Đầu tiên về LOGO — em đã có sẵn bộ phong cách thiết kế chuẩn "
            f"cho ngành {main_cat}. Để em chọn 1 cái phù hợp nhất với "
            f"{addr} nha, {addr} cần chỉnh thì bên em sẽ chỉnh sửa toàn "
            f"phần cho {addr} sau ạ — {addr} yên tâm điểm này nhé."
        ),
        "4.2": (
            f"Dạ. Còn về MÀU SẮC thương hiệu — không biết {addr} có đặc "
            f"biệt thích màu nào không, hoặc có màu nào hợp mệnh phong thủy "
            f"của {addr} không ạ?"
        ),
    }
    return templates.get(turn_id, "")
