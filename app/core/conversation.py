"""Conversation state machine.

Logic Python thuần — KHÔNG để LLM tự quyết bot nói gì,
LLM chỉ làm extractor. Đây là kỷ luật trong tài liệu MVP
(mục 7: "Schema để hệ thống hiểu đúng").
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from app.core import red_flags
from app.core.card_renderer import render_card
from app.core.chat_replier import ChatReplier
from app.core.edit_parser import parse_edit_command
from app.core.extractor import Extractor
from app.core.prompts import FIELD_LABEL, GREETING, QUESTIONS, REQUIRED_FIELDS
from app.core.replier import Goal, Replier
from app.models.schema import (
    ChatMessage,
    ChatRole,
    DealerProfileRaw,
    ExtractResult,
    Session,
    Stage,
)
from app.storage.base import StorageAdapter

# Số lần tối đa hỏi 1 field KHÔNG TIẾN TRIỂN. Sau đó skip để không loop vô tận.
# Chỉ count khi turn KHÔNG fill được field nào mới (xem _handle_asking).
MAX_FIELD_ATTEMPTS = 3

# Field "intent" — bắt buộc dealer trả lời TRỰC TIẾP câu hỏi của bot.
# LLM hay suy diễn từ context mơ hồ (vd: dealer nói "đưa kịch bản đây" →
# LLM đoán pain_point="khách cũ khó gọi"), nên ép HIGH confidence mới accept.
# MEDIUM/LOW → coi như chưa có, hỏi lại.
INTENT_FIELDS = {"pain_points", "dl0_priority"}

# Message ngắn/khẳng định không có info mới → skip LLM extractor để tiết kiệm cost.
# Backend sẽ dùng fallback question cho field weak hiện tại.
_TRIVIAL_MESSAGES = {
    "ok", "okay", "oke", "okeyy", "đúng", "dung", "yes", "y",
    "vâng", "vang", "ừ", "u", "uh", "có", "co", "không", "khong", "k",
    "hmm", "hm", "à", "a", "ờ", "o", "thôi", "thoi",
}


def _is_trivial_message(text: str) -> bool:
    """True nếu message ngắn/khẳng định không cần extract LLM."""
    if not text:
        return True
    cleaned = text.strip().lower().rstrip(".!?,")
    if len(cleaned) < 2:
        return True
    return cleaned in _TRIVIAL_MESSAGES


# Keyword classify nhóm cụm mở đầu của bot reply.
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


# Keywords báo hiệu dealer đang TÂM SỰ / nói chuyện đời thường — bot phải engage.
# Khi detect, KHÔNG inject target_field hint để LLM tự do xử persona.
_TAM_SU_KEYWORDS = (
    "vợ", "chồng", "bạn gái", "bạn trai", "ny", "gấu",
    "con", "gia đình", "ba mẹ", "bố mẹ", "bố", "mẹ",
    "nhậu", "say", "đau đầu", "mệt", "ốm", "bệnh", "viện", "đau",
    "golf", "bóng", "đá bóng", "tennis", "bida", "gym", "tập",
    "buồn", "chán", "stress", "căng thẳng", "đời", "tâm sự",
    "cãi nhau", "cãi cọ", "hết tiền", "kẹt tiền", "dịch bệnh",
    "công trình", "lắp đặt", "đi khách", "khách hàng khó",
)


def is_tam_su_message(text: str) -> bool:
    """Detect message của dealer có phải đang tâm sự / off-topic / đời thường.

    Dùng để KHÔNG inject target_field hint → để LLM theo persona engage tự nhiên.
    """
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in _TAM_SU_KEYWORDS)


# Keywords báo hiệu dealer ĐANG HỎI NGƯỢC / PHÒNG VỆ (Loại B trong 4 INTENT).
# Khi detect → KHÔNG inject target_field hint, inject directive "TRẢ LỜI TRƯỚC".
_DEFENSIVE_KEYWORDS = (
    # Benefit/lợi ích
    "được lợi", "được gì", "lợi gì", "có gì hay", "có ích gì", "có lợi gì",
    # Fraud/lừa đảo
    "lừa đảo", "lừa", "đa cấp", "scam", "tổ chức gì",
    # Cost/phí
    "miễn phí thật", "có phí", "tốn tiền", "thu phí", "trả phí", "miễn phí không",
    "tiền không", "đắt không", "rẻ không",
    # Privacy/data
    "spam", "lấy data", "lấy thông tin", "lấy số", "bán data", "bán thông tin",
    "lấy data ở đâu", "data ở đâu", "data từ đâu", "ai cấp", "ai cho",
    "có quyền xoá", "xoá dữ liệu", "xoá data", "gdpr", "bảo mật",
    "thông tin của tao có ai biết", "ai biết về tao",
    # Identity/legitimacy
    "ai làm", "em là ai", "mày là ai", "bot à", "có thật",
    "thật không", "có chuẩn", "uy tín",
    "tin được không", "tin tưởng được",
    "công ty nào", "ai chủ", "thuộc công ty", "của công ty nào",
    "có hợp pháp", "hợp pháp không", "có giấy phép",
    "chính chủ", "có chính chủ",
    # Time/availability
    "tao bận", "không có thời gian", "rảnh đâu",
)


# Keywords báo hiệu dealer TỪ CHỐI cung cấp 1 field cụ thể.
_REFUSAL_KEYWORDS = (
    "đéo cho", "deo cho", "không cho", "khong cho",
    "không tiện", "khong tien", "ko tiện", "ko cho",
    "không nói", "khong noi", "đéo nói", "deo noi",
    "miễn", "thôi không", "thoi khong", "không có",
    "bỏ qua", "bo qua", "skip",
)


def is_refusal_message(text: str) -> bool:
    """Detect dealer từ chối cung cấp field hiện tại.

    Khi detect → bot acknowledge + pivot:
    - Ack respect choice ("dạ em tôn trọng")
    - Persuade nhẹ về lý do cần info đó
    - Nếu user vẫn không cho → skip field, hỏi field khác
    """
    if not text:
        return False
    low = text.lower().strip()
    # Loại trừ false positive: "không có thời gian" thuộc busy không phải refusal
    if "thời gian" in low or "không có vốn" in low:
        return False
    return any(kw in low for kw in _REFUSAL_KEYWORDS)


def is_defensive_message(text: str) -> bool:
    """Detect dealer đang hỏi ngược / dò xét / nghi ngờ (Loại B).

    Khi detect:
    - KHÔNG inject target_field hint (LLM bị ép hỏi field, sẽ bơ câu hỏi).
    - Inject directive "PHẢI TRẢ LỜI câu hỏi của dealer TRƯỚC".
    """
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in _DEFENSIVE_KEYWORDS)


# Tên nữ Việt Nam phổ biến — dùng để detect xưng hô.
_FEMALE_NAMES = {
    "hương", "lan", "mai", "trang", "hoa", "hà", "nhung", "loan",
    "hằng", "vy", "phương", "thuỳ", "thùy", "diệu", "nga", "yến",
    "thảo", "vân", "quyên", "thuý", "thúy", "ngọc", "linh", "anh thư",
    "bảo châu", "bích", "hạnh", "tâm",
}


def detect_address_form(text: str, owner_name: str | None) -> str:
    """Detect xưng hô 'anh' hay 'chị' dựa vào 3 tín hiệu:
    1. Dealer tự xưng "chị" / "em là nữ"
    2. owner_name có dấu hiệu nữ rõ ràng
    3. Default "anh" nếu không có tín hiệu

    Trả: "anh" hoặc "chị"
    """
    if text:
        low = text.lower()
        if "em là nữ" in low or "tôi là nữ" in low or "tao là nữ" in low:
            return "chị"
        # Dealer tự xưng "chị" trong câu (vd "chị tên...", "chị bán...")
        if low.startswith("chị ") or " chị " in low or low.startswith("chị,"):
            # Check không phải "đừng gọi chị là anh" (correct case)
            if "đừng gọi" not in low:
                return "chị"
        # Correct case
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


def classify_opener_group(text: str) -> str:
    """Match prefix bot reply (80 ký tự đầu) → nhóm A/B/C/D. Trả 'X' nếu không khớp."""
    if not text:
        return "X"
    head = text.lower()[:80]
    for grp, kws in _OPENER_GROUPS:
        for kw in kws:
            if kw in head:
                return grp
    return "X"


# Pool cụm thay thế khi code force-replace opener — chỉ B/D (context-neutral).
# C (empathy) chỉ phù hợp với pain context → tránh dùng cho ack thông tin trung tính.
_REPLACEMENT_POOL: tuple[str, ...] = (
    "Wow", "Uầy", "Hay quá ạ,",
    "Tiện đây em hỏi anh,", "À mà anh ơi,", "Em tò mò xíu,",
)

# Regex match VERB OPENER nhóm A để strip — chỉ strip verb phrase,
# GIỮ NGUYÊN content theo sau. Tránh nuốt mất nội dung ack.
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


def _word_count_vn(text: str) -> int:
    """Đếm số từ tiếng Việt — split theo whitespace, bỏ markdown/emoji."""
    if not text:
        return 0
    # Strip markdown bullets/links/emojis
    cleaned = re.sub(r"[*_`\[\]()•]", " ", text)
    return len([w for w in cleaned.split() if w.strip()])


def _build_compliment(extracted_data: dict, address: str) -> str:
    """Sinh câu compliment thật về data dealer vừa cho. Template-based.

    Random across ALL eligible fields → variety qua nhiều turn (không lặp).
    """
    import random
    data = extracted_data or {}

    # Build list of all eligible compliments based on what's extracted
    eligible: list[str] = []

    if data.get("owner_name"):
        name = data["owner_name"]
        eligible.extend([
            f"Tên {name} nghe nhẹ nhàng dễ thương ghê {address} ơi!",
            f"{address.capitalize()} {name} ơi, tên đẹp em mê quá!",
            f"Wow tên {name} dễ nhớ lắm, em note rồi nhé!",
            f"Em phục {address} {name} đó, nghe có chí khí ghê!",
        ])

    if data.get("dealer_name"):
        shop = data["dealer_name"]
        eligible.extend([
            f"Tên cửa hàng '{shop}' nghe oách lắm {address} ơi!",
            f"'{shop}' — tên hay dễ nhớ, branding ổn rồi đó {address}!",
            f"Wow '{shop}' nghe uy tín lắm, em note rồi nhé!",
        ])

    if data.get("main_category"):
        cat = data["main_category"]
        cat_options = {
            "cua_nhom_kinh": [
                f"Cửa nhôm kính giờ là 'mảng vàng' đó {address} ơi, gu xịn rồi!",
                f"Wow nhôm kính là ngành đỉnh đó, tiềm năng lắm!",
                f"Em phục, làm nhôm kính đòi tay nghề tinh tế lắm!",
            ],
            "cua_cuon": [
                f"Cửa cuốn — mảng truyền thống mà bền nhất luôn nhỉ {address}!",
                f"Wow cửa cuốn là sản phẩm phổ biến nhất trong nhà ta đó!",
                f"Em phục, cửa cuốn cần kinh nghiệm lắp đặt cao thật!",
            ],
            "tu_bep": [
                f"Tủ bếp là 'tâm hồn' của ngôi nhà, em phục {address} chăm gu thẩm mỹ!",
                f"Wow tủ bếp giờ HOT lắm, ai chuyển nhà cũng cần!",
            ],
            "cua_thep": [
                f"Cửa thép — mảng kỹ thuật cao đó {address}, em phục thật!",
            ],
            "solar": [
                f"Solar là tương lai đó {address}, đầu tư đúng xu hướng quá!",
            ],
            "vlxd_tong_hop": [
                f"VLXD tổng hợp — đa dạng luôn, {address} quản kho khỏe nhỉ!",
            ],
            "bao_tri_sua_chua": [
                f"Bảo trì sửa chữa — mảng bền vững nhất đó {address}!",
            ],
        }
        if cat in cat_options:
            eligible.extend(cat_options[cat])

    if data.get("province"):
        prov = data["province"]
        eligible.append(f"{prov} thị trường to nhỉ {address}, tha hồ chốt đơn!")

    if data.get("customer_base_estimate"):
        n = data["customer_base_estimate"]
        eligible.append(
            f"Wow {n} khách — em phục {address} thật, chăm khách kỹ mới giữ được nhiều thế!"
        )

    if data.get("phone_or_zalo"):
        eligible.append(
            f"Em note số rồi {address} ơi, em chỉ nhắn khi có việc thật sự nhé."
        )

    if eligible:
        return random.choice(eligible)

    # Fallback
    return f"Dạ {address} ơi, em hỏi tiếp xíu nhé —"


def enforce_min_length(
    text: str,
    extracted_data: dict | None = None,
    address: str = "anh",
    min_words: int = 35,
) -> str:
    """Layer 1 — Pre-send safety net.

    Trigger condition (RỘNG hơn để đảm bảo compliment):
    - Reply < min_words (35 từ), HOẶC
    - Reply không có dấu hiệu compliment/cảm xúc (Wow/Tên/em phục/em hiểu mà...)
      MÀ có data mới extract turn này → prepend compliment

    Mục tiêu: 0% câu fallback template trần trụi không engagement.
    """
    if not text:
        return text

    # Detect compliment markers — nếu LLM đã có engagement, KHÔNG override
    low = text.lower()
    has_engagement = any(marker in low for marker in (
        "wow", "uầy", "tên ", "hay quá", "em phục", "em hiểu mà",
        "em đồng cảm", "đỉnh", "khủng", "nét", "em mê", "em thích",
        "em note", "em phục", "ngầu", "tuyệt", "đẹp ghê", "mê quá",
    ))

    word_count = _word_count_vn(text)
    has_new_data = bool(extracted_data and any(
        v not in (None, "", []) for v in extracted_data.values()
    ))

    # Skip nếu reply đã đủ engagement
    if word_count >= min_words and has_engagement:
        return text
    # Skip nếu reply dài và KHÔNG có data mới (LLM tự xử)
    if word_count >= min_words and not has_new_data:
        return text

    compliment = _build_compliment(extracted_data or {}, address)

    # Tránh double-Dạ
    if text.lower().startswith("dạ") and compliment.startswith("Dạ"):
        rest = text.split(maxsplit=1)
        text_body = rest[1] if len(rest) > 1 else ""
        return f"{compliment} {text_body}".strip()
    return f"{compliment} {text}"


def enforce_defensive_answer(text: str, latest_dealer: str, address: str) -> str:
    """Safety Layer 2 — nếu dealer hỏi defensive nhưng bot reply KHÔNG đề cập
    benefit/sự thật → ép prepend câu trả lời thẳng dựa trên loại defensive.

    Mục đích: GUARANTEE bot không bypass câu hỏi của dealer. Code đảm bảo,
    không phụ thuộc LLM tuân directive.
    """
    if not latest_dealer or not text:
        return text
    low_msg = latest_dealer.lower()
    low_text = text.lower()

    # Loại 1: hỏi benefit/lợi ích → check bot có liệt kê 4 công cụ không
    benefit_keywords = ("được lợi", "được gì", "lợi gì", "có gì hay", "có ích gì")
    if any(k in low_msg for k in benefit_keywords):
        # Bot reply có đề cập 4 công cụ chưa? Check ít nhất 2 trong số:
        tools_mentioned = sum(
            1 for tool in ("bộ mặt số", "qr khách", "bài đăng", "tư vấn", "miễn phí", "free")
            if tool in low_text
        )
        if tools_mentioned < 2:
            answer = (
                f"Dạ em không vòng vo — bên em hỗ trợ MIỄN PHÍ 4 thứ: "
                f"bộ mặt số (trang giới thiệu cửa hàng gửi khách), QR gọi lại "
                f"khách cũ tự động, bài đăng Zalo/Facebook, và trợ lý tư vấn. "
                f"Tất cả không mất đồng nào trong giai đoạn này ạ. "
            )
            return answer + text

    # Loại 2: nghi lừa đảo / spam
    fraud_keywords = ("lừa đảo", "đa cấp", "spam", "lấy data", "lấy thông tin")
    if any(k in low_msg for k in fraud_keywords):
        if "không lừa" not in low_text and "minh bạch" not in low_text and "miễn phí" not in low_text:
            answer = (
                f"Dạ em hiểu {address} dè chừng — bên em là Cộng Đồng Thợ 4.0, "
                f"hoàn toàn miễn phí, không bán hàng, không spam. "
                f"{address.capitalize()} có thể tra cứu tên cộng đồng để xác minh nhé. "
            )
            return answer + text

    # Loại 3: hỏi có phí/tốn tiền
    fee_keywords = ("có phí", "tốn tiền", "thu phí", "trả phí", "miễn phí thật")
    if any(k in low_msg for k in fee_keywords):
        if "miễn phí" not in low_text and "không thu" not in low_text:
            answer = (
                f"Dạ em khẳng định luôn — bên em hoàn toàn MIỄN PHÍ trong giai "
                f"đoạn này, không thu đồng nào. "
            )
            return answer + text

    # Loại 4: ai làm / em là ai / bot à
    identity_keywords = ("ai làm", "em là ai", "bot à", "bot không", "có thật",
                          "công ty nào", "ai chủ", "thuộc công ty")
    if any(k in low_msg for k in identity_keywords):
        if "cộng đồng" not in low_text:
            answer = (
                f"Dạ em là trợ lý số bên Cộng Đồng Thợ 4.0 ạ, hỗ trợ "
                f"các anh chị làm cửa/tủ/VLXD. Team người thật sẽ gọi lại "
                f"sau khi em ghi nhận hồ sơ {address} nhé. "
            )
            return answer + text

    # Loại 5: data privacy / GDPR / xoá data
    privacy_keywords = (
        "lấy data ở đâu", "data ở đâu", "data từ đâu", "ai cấp", "ai cho",
        "có quyền xoá", "xoá dữ liệu", "xoá data", "gdpr", "bán data",
        "bán thông tin", "ai biết về tao", "thông tin của tao có ai biết",
    )
    if any(k in low_msg for k in privacy_keywords):
        if "xoá" not in low_text and "minh bạch" not in low_text:
            answer = (
                f"Dạ về data, em xin cam kết: data {address} chia sẻ chỉ team "
                f"bên em xem để hỗ trợ — KHÔNG bán cho bên khác, KHÔNG spam. "
                f"{address.capitalize()} có quyền yêu cầu xoá data bất cứ lúc "
                f"nào, em sẽ xoá luôn trong 24h ạ. "
            )
            return answer + text

    # Loại 6: hợp pháp / giấy phép
    legitimacy_keywords = (
        "có hợp pháp", "hợp pháp không", "có giấy phép", "chính chủ",
        "có chính chủ", "đa cấp", "scam", "tổ chức gì",
    )
    if any(k in low_msg for k in legitimacy_keywords):
        if "hợp pháp" not in low_text and "cộng đồng" not in low_text:
            answer = (
                f"Dạ em khẳng định — Cộng Đồng Thợ 4.0 là cộng đồng nghề "
                f"chính thức, không đa cấp, không scam ạ. {address.capitalize()} "
                f"có thể search Google 'Cộng Đồng Thợ 4.0' để xác minh nhé. "
            )
            return answer + text

    # Loại 7: bận / không có thời gian
    busy_keywords = ("tao bận", "không có thời gian", "rảnh đâu", "lát nói")
    if any(k in low_msg for k in busy_keywords):
        if "bận" not in low_text:
            answer = (
                f"Dạ em hiểu {address} bận, em không làm phiền lâu đâu — "
                f"chỉ 2-3 thông tin nhanh thôi rồi team em chủ động liên hệ "
                f"khi {address} rảnh ạ. "
            )
            return answer + text

    return text


def enforce_opener_variety(
    text: str, forbidden_group: str | None
) -> tuple[str, str]:
    """Safety net: nếu opener trùng nhóm bị cấm → strip A-prefix + thay B/D.

    Chỉ enforce khi nhóm bị cấm là A (đa số case Haiku lặp). B/C/D giữ nguyên
    (LLM trách nhiệm) để tránh double-prefix.

    Trả (new_text, new_group).
    """
    import random
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


class ConversationService:
    def __init__(
        self,
        extractor: Extractor,
        storage: StorageAdapter,
        chat_replier: ChatReplier,
        replier: Replier | None = None,
    ):
        self.extractor = extractor
        self.storage = storage
        self.chat_replier = chat_replier
        # Replier mới (Bước 1 refactor). None = giữ flow cũ (Extractor sinh
        # cả field + reply). Set qua USE_REPLIER=true trong .env.
        self.replier = replier

    def handle_message(
        self, session_id: str | None, dealer_message: str
    ) -> tuple[Session, str]:
        session = self._load_or_create(session_id)
        msg_clean = dealer_message.strip()

        # Lần đầu kết nối (frontend gửi message rỗng) → trả greeting
        if session.stage == Stage.GREETING and not msg_clean:
            session.stage = Stage.ASKING
            bot_msg = GREETING
            session.messages.append(self._bot(bot_msg))
            self.storage.save_session(session)
            return session, bot_msg

        # Ping rỗng trên session đã có — chỉ trả lại state, KHÔNG append.
        # Dùng cho frontend khôi phục history khi reload trang.
        if not msg_clean:
            last_bot = next(
                (m.content for m in reversed(session.messages) if m.role == ChatRole.BOT),
                "Em đang ở đây ạ, anh nhắn em nhé!",
            )
            return session, last_bot

        # Ghi message của dealer
        session.messages.append(self._dealer(msg_clean))

        # Quét red flags trên message này, gộp vào lịch sử
        new_flags = red_flags.detect_message_flags(msg_clean)
        if new_flags:
            session.flag_history.extend(new_flags)
            session.flag_history = red_flags.upgrade_persistent_flags(
                session.flag_history
            )

        # Escalation request → defer to human, sang Confirmation Card với info hiện có
        if red_flags.ESCALATION_REQUESTED in new_flags:
            bot_msg = self._handle_escalation(session)
            session.messages.append(self._bot(bot_msg))
            self.storage.save_session(session)
            return session, bot_msg

        if session.stage == Stage.GREETING:
            session.stage = Stage.ASKING

        if session.stage == Stage.ASKING:
            bot_msg = self._handle_asking(session)
        elif session.stage == Stage.CONFIRMING:
            bot_msg = self._handle_confirming(session, msg_clean)
        elif session.stage == Stage.DONE:
            bot_msg = self._handle_done(session)
        else:
            bot_msg = "Em xin lỗi, em chưa nghe rõ ý anh, anh nói lại giúp em với ạ?"

        # B3: Post-process safety net — nếu Haiku vẫn lặp nhóm bị cấm dù
        # đã có directive trong prompt, code strip prefix + thay opener khác.
        # Chỉ apply cho ASKING (CONFIRMING+DONE đa phần dùng template hardcoded).
        if session.stage == Stage.ASKING:
            bot_msg, opener_group = enforce_opener_variety(
                bot_msg, session.last_opener_group
            )
        else:
            opener_group = classify_opener_group(bot_msg)

        # Layer 2 — Defensive answer guarantee: nếu dealer hỏi ngược mà bot
        # không trả lời thẳng, code prepend đáp trực tiếp.
        if session.stage in (Stage.ASKING, Stage.CONFIRMING):
            address = session.address_form or "anh"
            latest_dealer_msg = next(
                (m.content for m in reversed(session.messages) if m.role == ChatRole.DEALER),
                "",
            )
            bot_msg = enforce_defensive_answer(bot_msg, latest_dealer_msg, address)

        # Layer 1 — Pre-send validation: chống câu cộc lốc / quá ngắn.
        # Áp dụng cho ASKING + CONFIRMING (không áp dụng greeting/done).
        if session.stage in (Stage.ASKING, Stage.CONFIRMING):
            extracted_this_turn = getattr(self, "_last_extracted_this_turn", None) or {}
            bot_msg = enforce_min_length(
                bot_msg,
                extracted_data=extracted_this_turn,
                address=session.address_form or "anh",
                min_words=25,
            )

        # Track nhóm opener turn này → cấm nhóm này ở turn sau.
        if opener_group != "X":
            session.last_opener_group = opener_group

        session.messages.append(self._bot(bot_msg))
        self.storage.save_session(session)
        return session, bot_msg

    def _handle_escalation(self, session: Session) -> str:
        """Dealer xin gặp người thật — chuyển thẳng sang CONFIRMING với info hiện có."""
        if session.profile_raw.phone_or_zalo:
            session.stage = Stage.CONFIRMING
            return (
                "Dạ em hiểu rồi anh ạ. Em ghi nhận luôn để team người thật bên em "
                "liên hệ anh trong 24h nhé 🌷. Em xin tóm tắt info hiện có để xác "
                "nhận với anh trước nha:\n\n" + render_card(session.profile_raw)
            )
        # Chưa có SĐT → vẫn cần xin để team gọi lại
        return (
            "Dạ em hiểu rồi anh ạ. Em sẽ chuyển team người thật liên hệ anh nhé. "
            "Anh cho em xin số Zalo / SĐT cuối cùng để team gọi đúng số nha?"
        )

    # ---------- ASKING ----------
    def _handle_asking(self, session: Session) -> str:
        # Đếm số field đã fill TRƯỚC khi extract turn này (để biết có tiến triển không)
        weak_before_list = self._weak_required_fields(session)
        weak_before = set(weak_before_list)

        # C3: Skip LLM extractor khi dealer message tầm thường ("ok"/"yes"/"k"...)
        # → tiết kiệm 1 LLM call cho ~10-15% turn. Dùng fallback question.
        latest_dealer = next(
            (m.content for m in reversed(session.messages) if m.role == ChatRole.DEALER),
            "",
        )
        # Phân loại intent — dùng cho cả Extractor (cũ) và Replier (mới).
        defensive = is_defensive_message(latest_dealer) if latest_dealer else False
        tam_su = (
            is_tam_su_message(latest_dealer) and not defensive
            if latest_dealer else False
        )

        if _is_trivial_message(latest_dealer):
            result = ExtractResult()
        else:
            # KHÔNG inject target_field hint khi defensive/tâm sự — để LLM tự do
            # trả lời câu hỏi / engage theo persona, không bị ép hỏi field.
            target_for_extract = (
                weak_before_list[0]
                if weak_before_list and not (defensive or tam_su)
                else None
            )
            # Khi USE_REPLIER bật: Extractor chỉ trích field (confirm_questions
            # sẽ bị ignore phía dưới). Vẫn truyền is_tam_su/is_defensive cho
            # Extractor vì nó dùng cùng prompt — sẽ refactor ở Bước sau.
            result = self.extractor.extract(
                session.messages,
                forbidden_opener_group=session.last_opener_group,
                target_field=target_for_extract,
                is_tam_su=tam_su,
                is_defensive=defensive,
            )
        # Snapshot data NEW this turn (trước merge để biết turn này extract gì)
        self._last_extracted_this_turn = {
            k: v for k, v in (result.extracted_fields or {}).items()
            if v not in (None, "", [])
        }
        self._merge_extraction(session, result)
        # Detect xưng hô — sau khi đã có owner_name potentially mới
        detected = detect_address_form(latest_dealer, session.profile_raw.owner_name)
        if detected == "chị" and session.address_form != "chị":
            session.address_form = "chị"

        # Cross-session memory: nếu vừa cho phone và phone match dealer cũ,
        # auto-fill các field còn thiếu từ profile cũ.
        if not session.profile_raw.confirmation_status == "CONFIRMED":
            self._maybe_load_returning_dealer(session)

        weak_after = self._weak_required_fields(session)
        progress_made = len(weak_after) < len(weak_before)

        # REFUSAL handling — user nói "đéo cho" / "không cho" cho field hiện tại.
        # Acknowledge respect + skip field, không spam lại câu hỏi cũ.
        if (
            weak_after
            and is_refusal_message(latest_dealer)
            and not progress_made
        ):
            target_refused = weak_after[0]
            address = session.address_form or "anh"
            # Skip field này — ghi nhận count để re-ask logic biết khi nào
            # dealer đã hợp tác trở lại (sau ≥2 field mới fill).
            if target_refused not in session.skipped_fields:
                session.skipped_fields.append(target_refused)
                session.skipped_at_filled_count[target_refused] = (
                    self._count_filled_required(session)
                )
            weak_after = self._weak_required_fields(session)

            # Hết field weak → confirming ngay (vẫn cần ack ngắn trước card)
            if not weak_after:
                ack = (
                    f"Dạ em tôn trọng quyết định của {address} ạ — phần đó "
                    f"em tạm bỏ qua, không ép {address}. "
                )
                return ack + self._go_to_confirming(session)

            next_target = weak_after[0]

            # ===== PATH MỚI — Replier xử HANDLE_REFUSAL =====
            # Route qua Replier để tránh triple-prefix mess (template ack +
            # bridge + fallback question với prefix riêng).
            if self.replier is not None:
                goal = Goal(
                    kind="HANDLE_REFUSAL",
                    skipped_field=target_refused,
                    next_field=next_target,
                    forbidden_opener_group=session.last_opener_group,
                )
                try:
                    return self.replier.reply(
                        messages=session.messages,
                        goal=goal,
                        profile=session.profile_raw,
                        address=address,
                    )
                except Exception:
                    # Replier fail → fallback path cũ
                    pass

            # ===== PATH CŨ — template hardcoded =====
            ack = (
                f"Dạ em tôn trọng quyết định của {address} ạ — phần đó "
                f"em tạm bỏ qua, không ép {address}. "
            )
            return ack + "À tiện đây em hỏi xíu nhé — " + self._fallback_question_for(next_target)

        if weak_after:
            target = weak_after[0]

            # CHỈ tăng attempts khi turn này KHÔNG có tiến triển (no field newly filled).
            # Tránh bug: dealer defensive ("tao được gì") không trả lời nhưng attempts vẫn tăng
            # → field bị skip oan dù bot chưa thực sự hỏi nhiều lần.
            if not progress_made:
                session.field_attempts[target] = session.field_attempts.get(target, 0) + 1

            # Đã hỏi quá MAX_FIELD_ATTEMPTS không tiến triển → skip
            if session.field_attempts.get(target, 0) > MAX_FIELD_ATTEMPTS:
                if target not in session.skipped_fields:
                    session.skipped_fields.append(target)
                    session.skipped_at_filled_count[target] = (
                        self._count_filled_required(session)
                    )
                weak_after = self._weak_required_fields(session)
                if not weak_after:
                    return self._go_to_confirming(session)
                target = weak_after[0]

            # Re-ask logic: nếu target là field đã từng skip mà nay đủ điều
            # kiện hỏi lại → mark retried (chỉ retry 1 lần) + thêm hint cho
            # Replier để tone nhẹ ("nếu vẫn không tiện thì bỏ qua").
            is_reask = (
                target in session.skipped_fields
                and target not in session.skipped_retried
            )
            if is_reask:
                session.skipped_retried.append(target)

            # ===== PATH MỚI (Bước 1 refactor) — Replier sinh reply =====
            if self.replier is not None:
                # Re-ask hint chỉ áp dụng cho ASK_FIELD — defensive/tâm sự
                # ưu tiên trả lời/engage trước, re-ask vibe sẽ confuse.
                reask_hint = (
                    "Đây là lần hỏi lại nhẹ field dealer trước đó đã từ chối. "
                    "Tone NHẸ NHÀNG, KHÔNG ép. Chèn câu 'nếu anh vẫn không "
                    "tiện thì mình bỏ qua cũng được ạ'. Không hỏi lại lần "
                    "thứ hai nếu dealer tiếp tục từ chối."
                ) if is_reask else None

                if defensive:
                    goal = Goal(
                        kind="ANSWER_DEFENSIVE",
                        target_field=target,
                        forbidden_opener_group=session.last_opener_group,
                    )
                elif tam_su:
                    goal = Goal(
                        kind="ENGAGE_TAM_SU",
                        next_field=target,
                        forbidden_opener_group=session.last_opener_group,
                    )
                else:
                    goal = Goal(
                        kind="ASK_FIELD",
                        target_field=target,
                        forbidden_opener_group=session.last_opener_group,
                        extra_hint=reask_hint,
                    )
                try:
                    return self.replier.reply(
                        messages=session.messages,
                        goal=goal,
                        profile=session.profile_raw,
                        address=session.address_form or "anh",
                    )
                except Exception:
                    # Replier fail → fallback path cũ (template + chém gió)
                    pass

            # ===== PATH CŨ — dùng confirm_questions[0] từ Extractor =====
            # Field order guard — kiểm tra LLM có hỏi đúng target không.
            # LLM Sonnet đôi khi skip phone để hỏi ngành (vì ngành "thân thiện"
            # hơn). Force respect order priority.
            if result.confirm_questions:
                llm_q = result.confirm_questions[0]
                if self._llm_question_matches_target(llm_q, target):
                    return llm_q
                # LLM hỏi sai field → bỏ, dùng template + chém gió tâm sự nếu có
            tam_su_engage = self._tam_su_engagement(latest_dealer)
            base_question = self._fallback_question_for(target)
            if tam_su_engage:
                return f"{tam_su_engage} {base_question}"
            return base_question

        return self._go_to_confirming(session)

    @staticmethod
    def _llm_question_matches_target(question: str, target: str) -> bool:
        """Check LLM's confirm_question có thực sự hỏi về target field không.

        Match keyword cụ thể của field để tránh LLM skip target.
        """
        if not question or not target:
            return True  # no validation possible
        q = question.lower()
        # Map target field → keywords PHẢI có trong câu hỏi
        target_keywords = {
            "dealer_name": ("tên cửa hàng", "tên shop", "đặt tên"),
            "owner_name": ("tên anh", "tên chị", "tên gọi", "xưng hô", "anh tên", "chị tên"),
            "phone_or_zalo": ("zalo", "sđt", "số điện thoại", "điện thoại", "số liên hệ", "số khách"),
            "province": ("tỉnh", "thành phố"),
            "district": ("quận", "huyện"),
            "main_category": ("mảng", "ngành", "cửa cuốn", "nhôm kính", "tủ bếp", "solar", "vlxd"),
            "dealer_type": ("đại lý", "xưởng", "thợ", "bán lẻ", "phân phối", "lắp đặt"),
            "customer_base_estimate": ("khách cũ", "bao nhiêu khách", "tầm bao nhiêu", "khoảng bao nhiêu"),
            "pain_points": ("vướng", "đau", "khó khăn", "vấn đề"),
            "dl0_priority": ("ưu tiên", "muốn em làm", "bộ mặt số", "qr khách", "bài đăng", "trợ lý"),
        }
        keywords = target_keywords.get(target, ())
        if not keywords:
            return True
        return any(kw in q for kw in keywords)

    def _go_to_confirming(self, session: Session) -> str:
        session.stage = Stage.CONFIRMING
        prefix = ""
        if session.is_returning_dealer:
            prefix = (
                "Dạ em nhớ anh đã đăng ký bên em hôm trước rồi ạ 🌷. Em xin "
                "xác nhận lại thông tin để chắc chắn không có gì thay đổi nhé:\n\n"
            )
        elif session.skipped_fields:
            prefix = (
                "Em hiểu là có vài thông tin mình chưa tiện chia sẻ ngay, không sao ạ. "
                "Em xin tóm tắt phần đã có để mình xác nhận trước nhé:\n\n"
            )
        return prefix + render_card(session.profile_raw)

    def _merge_extraction(self, session: Session, result: ExtractResult) -> None:
        fields = result.extracted_fields or {}
        confidence = result.confidence or {}
        profile = session.profile_raw
        accepted_confidence: dict[str, str] = {}
        for key, val in fields.items():
            if val in (None, "", []):
                continue
            # INTENT fields (pain/priority): accept HIGH+MEDIUM — reject LOW.
            if key in INTENT_FIELDS and confidence.get(key) == "LOW":
                continue
            # Anti-overwrite: nếu field đã có value với confidence HIGH, KHÔNG cho
            # turn sau ghi đè bằng value khác trừ khi cũng HIGH. Tránh case LLM
            # extract sai (vd: dealer_name "Cuốn Phong" bị overwrite thành "Phong").
            if hasattr(profile, key):
                old_val = getattr(profile, key)
                old_conf = session.confidence.get(key)
                new_conf = confidence.get(key)
                if (
                    old_val not in (None, "", [])
                    and old_val != val
                    and old_conf == "HIGH"
                    and new_conf != "HIGH"
                ):
                    continue  # giữ value cũ HIGH, không đè bằng MEDIUM/LOW
                setattr(profile, key, val)
                if new_conf:
                    accepted_confidence[key] = new_conf
        # CHỈ merge confidence cho field thực sự được fill turn này. KHÔNG đè
        # confidence cũ HIGH với LOW của field không liên quan — fix bug
        # truncate history (C2) khiến extractor không thấy data cũ → trả LOW
        # cho field đã có HIGH → bot hỏi lại.
        session.confidence = {**session.confidence, **accepted_confidence}
        session.missing_fields = result.missing_fields or []
        # Rule-based regex bắt pain/priority từ message dealer cuối — bù khi LLM
        # đánh MEDIUM/LOW cho keyword rõ ràng.
        self._merge_rule_based_intent(session)

    def _maybe_load_returning_dealer(self, session: Session) -> None:
        """Cross-session memory v2 — SAFE LOAD.

        KHÔNG auto-fill profile từ dealer cũ (gây ô nhiễm data nếu trùng phone
        nhưng khác người). Chỉ:
        1. Mark `is_returning_dealer=True` (để bot greet đặc biệt)
        2. Verify owner_name nếu có — chỉ load nếu owner_name match

        Fix bug: phone trùng nhưng different dealer → KHÔNG load data sai.
        """
        if session.is_returning_dealer:
            return
        phone = (session.profile_raw.phone_or_zalo or "").strip()
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            return

        old_profile = self.storage.find_profile_by_phone(phone)
        if old_profile is None:
            return

        # SAFETY CHECK: nếu session HIỆN TẠI đã có owner_name, mà KHÁC owner_name
        # cũ → coi như là dealer khác dùng cùng số (hiếm), KHÔNG mark returning.
        current_owner = (session.profile_raw.owner_name or "").strip().lower()
        old_owner = (old_profile.owner_name or "").strip().lower()
        if current_owner and old_owner and current_owner != old_owner:
            # Tên khác hẳn → chắc chắn không phải cùng người. Bỏ qua.
            return

        # Phone match + tên ko mâu thuẫn → đánh dấu returning.
        # KHÔNG auto-fill profile data — để dealer tự xác nhận lại.
        # (Trước đây bug: auto-fill khiến confirm card hiển thị data người cũ.)
        session.is_returning_dealer = True

    def _merge_rule_based_intent(self, session: Session) -> None:
        """Regex bắt keyword phone/pain/priority từ message DEALER cuối cùng.

        Bot reply không tính. Chỉ áp khi field còn empty (không đè data LLM tốt).
        """
        latest_raw = ""
        for m in reversed(session.messages):
            if m.role == ChatRole.DEALER and (m.content or "").strip():
                latest_raw = m.content
                break
        if not latest_raw:
            return
        latest = latest_raw.lower()

        # PHONE regex: bắt số 9-11 chữ số bắt đầu bằng 0, có thể có dấu cách/dấu chấm/gạch
        if not session.profile_raw.phone_or_zalo:
            phone_match = re.search(r"(?<!\d)(0\d[\d\s.\-]{7,13}\d)(?!\d)", latest_raw)
            if phone_match:
                digits = re.sub(r"\D", "", phone_match.group(1))
                if 9 <= len(digits) <= 11:
                    session.profile_raw.phone_or_zalo = digits
                    session.confidence["phone_or_zalo"] = "HIGH"

        # PAIN keywords
        pain_keywords = [
            ("Khách cũ ít quay lại", ("khách cũ ít", "khach cu it", "khách cũ không quay",
                                       "khach cu khong quay")),
            ("Marketing yếu", ("marketing yếu", "marketing yeu", "quảng bá yếu",
                                "quang ba yeu", "không biết quảng bá", "khong biet quang ba")),
            ("Khó tìm khách", ("khó tìm khách", "kho tim khach", "thiếu khách",
                                "thieu khach", "ế ẩm", "e am", "vắng khách", "vang khach",
                                "ít khách", "it khach")),
            ("Đội thợ không ổn định", ("đội thợ", "doi tho", "thợ không ổn", "tho khong on",
                                         "thợ nghỉ", "tho nghi")),
            ("Thiếu vốn", ("thiếu tiền", "thieu tien", "hết tiền", "het tien",
                            "thiếu vốn", "thieu von", "không có vốn", "khong co von",
                            "kẹt tiền", "ket tien")),
            ("Dịch bệnh ảnh hưởng kinh doanh", ("dịch bệnh", "dich benh", "covid",
                                                  "dịch covid", "do dịch", "do dich")),
        ]
        # Bắt MULTIPLE pain trong 1 turn (max 3 mới mỗi turn để tránh nhiễu)
        # Dedupe: skip nếu existing pain đã cover keyword tương tự.
        new_pains_added = 0
        for label, kws in pain_keywords:
            if new_pains_added >= 3:
                break
            if any(kw in latest for kw in kws):
                pains = list(session.profile_raw.pain_points or [])
                # Check duplicate: existing pain text đã chứa keyword trong label?
                existing_text = " ".join(pains).lower()
                already_covered = any(kw in existing_text for kw in kws)
                if not already_covered and label not in pains:
                    pains.append(label)
                    new_pains_added += 1
                    session.profile_raw.pain_points = pains
                    session.confidence["pain_points"] = "HIGH"

        # PRIORITY keywords
        if any(neg in latest for neg in ("cái nào cũng được", "cai nao cung duoc",
                                          "gì cũng được", "gi cung duoc")):
            return  # mơ hồ → không suy ra priority
        priority_keywords = [
            ("qr_khach_cu", ("qr khách cũ", "qr khach cu", "qr gửi khách",
                              "qr gui khach", "qr khách", "qr khach")),
            ("bo_mat_so", ("bộ mặt số", "bo mat so", "mặt số", "mat so")),
            ("bai_dang", ("bài đăng", "bai dang", "đăng bài", "dang bai", "post bài")),
            ("tro_ly_tu_van", ("trợ lý tư vấn", "tro ly tu van", "trợ lý ai",
                                 "tro ly ai")),
        ]
        for value, kws in priority_keywords:
            if any(kw in latest for kw in kws):
                priorities = list(session.profile_raw.dl0_priority or [])
                if value not in priorities:
                    priorities.append(value)
                session.profile_raw.dl0_priority = priorities
                session.confidence["dl0_priority"] = "HIGH"
                break

    @staticmethod
    def _count_filled_required(session: Session) -> int:
        """Đếm số REQUIRED_FIELDS đã có giá trị thật (HIGH/MEDIUM, không LOW).

        Dùng làm thước đo "dealer đang hợp tác mức nào" cho re-ask logic.
        """
        profile_dict = session.profile_raw.model_dump()
        count = 0
        for field in REQUIRED_FIELDS:
            value = profile_dict.get(field)
            if value in (None, "", []):
                continue
            conf = session.confidence.get(field)
            if conf == "LOW":
                continue
            count += 1
        return count

    # Sau khi dealer fill thêm ≥ N field NEW so với lúc skip → field skip
    # được retry 1 lần. N=2 = "dealer trả lời 2 câu hỏi sau đó coi như cooperation".
    REASK_COOPERATION_THRESHOLD = 2

    def _weak_required_fields(self, session: Session) -> list[str]:
        """Field bắt buộc còn null hoặc confidence chưa đủ tin cậy.

        Logic skip:
        - Field trong skipped_fields → KHÔNG vào weak NẾU chưa đủ điều kiện re-ask.
        - Field đủ điều kiện re-ask (dealer đã fill thêm ≥2 field, chưa retry) →
          đẩy xuống CUỐI list (low priority — chỉ hỏi sau khi field ưu tiên hết).

        INTENT field accept MEDIUM nhờ rule-based regex bù.
        """
        weak: list[str] = []
        reaskable: list[str] = []  # field skip nhưng đủ điều kiện hỏi lại
        profile_dict = session.profile_raw.model_dump()
        filled_now = self._count_filled_required(session)

        for field in REQUIRED_FIELDS:
            if field in session.skipped_fields:
                # Đã retry rồi → bỏ luôn, không hỏi nữa
                if field in session.skipped_retried:
                    continue
                # Đủ điều kiện cooperation → đưa vào reaskable
                skipped_at = session.skipped_at_filled_count.get(field, filled_now)
                if filled_now - skipped_at >= self.REASK_COOPERATION_THRESHOLD:
                    reaskable.append(field)
                continue

            value = profile_dict.get(field)
            empty = value in (None, "", [])
            conf = session.confidence.get(field)
            if empty or conf == "LOW":
                weak.append(field)

        # Re-askable đẩy xuống cuối — ưu tiên field chưa từng hỏi trước
        return weak + reaskable

    @staticmethod
    def _tam_su_engagement(text: str) -> str:
        """Sinh 1 câu engagement đơn giản dựa trên keyword trong tâm sự message.

        Dùng khi LLM không sinh được confirm_questions cho turn tâm sự — bot
        không bị bơ hoàn toàn. Nếu không match keyword nào → trả "" (không prepend).
        """
        if not text:
            return ""
        low = text.lower()
        if any(k in low for k in ("vợ", "chồng", "cãi", "ny", "gấu", "gia đình")):
            return "Dạ chuyện vợ chồng cãi cọ thường thôi anh ơi 😊, em không tiện vào đâu. Cộng Đồng Thợ 4.0 bên em có nhiều anh em hay tụ cafe xả stress, anh thử join cho khuây khoả nhé."
        if any(k in low for k in ("nhậu", "say", "đau đầu rượu")):
            return "Hihi anh nhậu căng quá rồi 😂. Anh uống nước ép giải rượu cho khoẻ nhé."
        if any(k in low for k in ("bóng", "đá bóng", "tennis", "gym", "tập", "golf")):
            return "Wow anh khoẻ ghê, vận động xong nhìn vui lắm anh ạ 😊."
        if any(k in low for k in ("ốm", "bệnh", "viện", "đau ", "mệt")):
            return "Dạ em mong anh mau khoẻ lại ạ 🌷. Anh nhớ nghỉ ngơi nhé."
        if any(k in low for k in ("buồn", "chán", "stress", "căng thẳng", "khổ")):
            return "Dạ em hiểu mà anh, ai cũng có lúc thế thôi ạ 😔."
        if any(k in low for k in ("dịch bệnh", "ế ẩm", "khó khăn")):
            return "Dạ em đồng cảm với anh ạ, đợt này nhiều anh em làm nghề cũng kêu khó."
        if any(k in low for k in ("công trình", "lắp đặt", "đi khách")):
            return "Dạ anh đang trên công trình bận rộn em không làm phiền lâu đâu ạ 🌷."
        return ""

    @staticmethod
    def _fallback_question_for(field: str) -> str:
        # Fallback chỉ chạy khi LLM không sinh được confirm_questions —
        # vẫn cố gắng giữ tone acknowledge + ask, nhưng generic vì không có context.
        mapping = {
            "dealer_name": "Dạ em xin lỗi anh, em chưa rõ tên cửa hàng mình. Anh cho em biết bên mình đặt tên cửa hàng là gì với ạ?",
            "owner_name": "Dạ tiện đây để em biết xưng hô cho đúng, anh cho em xin tên gọi của anh với ạ?",
            "phone_or_zalo": "Dạ vâng em hiểu rồi ạ. Anh ơi cho em xin số Zalo hoặc số điện thoại khách hay liên hệ với cửa hàng mình luôn nhé?",
            "province": "Dạ em ghi nhận rồi ạ. Cho em hỏi cửa hàng mình hiện đang ở tỉnh/thành nào vậy anh?",
            "main_category": "Dạ em hiểu rồi ạ. Bên mình hiện làm mạnh nhất mảng gì nhỉ anh — cửa cuốn, cửa nhôm kính, tủ bếp, solar, bảo trì, hay VLXD tổng hợp ạ?",
            "customer_base_estimate": "Dạ vâng ạ. Anh ơi 2-3 năm gần đây bên mình tầm bao nhiêu khách cũ còn liên hệ lại được nhỉ? Anh ước chừng cho em cũng được ạ.",
            "pain_points": "Dạ em hiểu rồi anh. Em hỏi thật lòng nhé, hiện bên mình đang vướng nhất ở chỗ nào hả anh — khách cũ không quay lại, marketing yếu, hay khó quản lý đội thợ ạ? Anh có nhiều vướng cùng lúc cũng cứ kể em nghe nhé.",
            "dl0_priority": "Dạ vâng em ghi nhận hết rồi ạ. Vậy giữa các thứ em có thể hỗ trợ — bộ mặt số, QR gửi khách cũ, bài đăng, hay trợ lý tư vấn — anh muốn em ưu tiên cái nào trước hả anh?",
        }
        return mapping.get(field, QUESTIONS[0])

    # ---------- CONFIRMING ----------
    def _handle_confirming(self, session: Session, dealer_message: str) -> str:
        msg = dealer_message.strip().lower()

        if self._is_affirmative(msg):
            session.profile_raw.confirmation_status = "CONFIRMED"
            session.profile_raw.review_status = "RAW"
            session.profile_raw.flags = self._final_flags(session)
            self.storage.save_profile_raw(session.session_id, session.profile_raw)
            session.stage = Stage.DONE
            return (
                "Dạ em cảm ơn anh nhiều ạ! Em đã ghi nhận hồ sơ rồi nhé.\n"
                "Team bên em sẽ xem qua và liên hệ lại với anh trong 24h ạ. "
                "Có gì cần hỗ trợ thêm anh cứ nhắn em nhé! 🌷\n\n"
                "(MVP: phần Mini App + cộng đồng em sẽ làm tiếp ở giai đoạn sau ạ)"
            )

        # P1-7: thử parse "sửa X thành Y" bằng regex trước → tiết kiệm 1 LLM call
        regex_patch = parse_edit_command(dealer_message)
        if regex_patch:
            field, new_value = regex_patch
            setattr(session.profile_raw, field, new_value)
            session.profile_raw.confirmation_status = "EDITED"
            return (
                f"Dạ em đã cập nhật {FIELD_LABEL.get(field, field)} thành "
                f"{new_value} rồi ạ, anh xem lại giúp em nhé:\n\n"
                + render_card(session.profile_raw)
            )

        # Fallback: dealer nói tự do (không match regex) → gọi LLM extractor
        result = self.extractor.extract(session.messages)
        self._merge_extraction(session, result)
        session.profile_raw.confirmation_status = "EDITED"
        return "Dạ em đã cập nhật rồi ạ, anh xem lại giúp em nhé:\n\n" + render_card(session.profile_raw)

    # ---------- DONE — chat tiếp + cho phép sửa ----------
    EDIT_KEYWORDS = (
        "sửa", "sua", "đổi", "doi", "thay", "cập nhật", "cap nhat",
        "không phải", "khong phai", "nhầm", "nham", "lại", "đính chính",
        "dinh chinh", "update",
    )

    def _handle_done(self, session: Session) -> str:
        """Sau DONE: dealer chat thoải mái. Chỉ chạy edit detection khi
        dealer DÙNG keyword sửa/đổi — tránh LLM paraphrase nhẹ bị nhầm là edit."""
        latest_msg = ""
        for m in reversed(session.messages):
            if m.role == ChatRole.DEALER and (m.content or "").strip():
                latest_msg = m.content.lower()
                break

        wants_edit = any(kw in latest_msg for kw in self.EDIT_KEYWORDS)

        if wants_edit:
            result = self.extractor.extract(session.messages)
            changes = self._detect_field_changes(session.profile_raw, result)
            if changes:
                self._merge_extraction(session, result)
                session.profile_raw.confirmation_status = "EDITED"
                session.profile_raw.flags = self._final_flags(session)
                self.storage.save_profile_raw(
                    session.session_id, session.profile_raw
                )
                change_lines = "\n".join(
                    f"• {FIELD_LABEL.get(f, f)}: {self._fmt_value(v)}"
                    for f, v in changes
                )
                return (
                    f"Dạ em đã cập nhật hồ sơ rồi ạ:\n\n{change_lines}\n\n"
                    "Còn gì cần em chỉnh nữa không anh?"
                )
            # Có ý sửa nhưng chưa rõ field nào → để LLM hỏi rõ
            return (
                "Dạ anh nói rõ giúp em thông tin nào cần sửa và giá trị mới "
                "là gì với ạ? Ví dụ: \"sửa SĐT thành 0901234567\"."
            )

        # Không có ý sửa → casual chat
        return self.chat_replier.reply(session.messages)

    @staticmethod
    def _final_flags(session: Session) -> list[str]:
        """Gộp flag từ message history + flag suy ra từ profile data."""
        msg_flags = list(dict.fromkeys(session.flag_history))
        profile_flags = red_flags.detect_profile_flags(
            session.profile_raw.model_dump()
        )
        merged = list(dict.fromkeys(msg_flags + profile_flags))
        return red_flags.upgrade_persistent_flags(merged)

    @staticmethod
    def _detect_field_changes(
        current: DealerProfileRaw, result: ExtractResult
    ) -> list[tuple[str, object]]:
        """So sánh profile hiện tại với extracted_fields, trả list (field, new_value)."""
        changes = []
        current_dict = current.model_dump()
        for field, new_val in (result.extracted_fields or {}).items():
            if new_val in (None, "", []):
                continue
            old_val = current_dict.get(field)
            if old_val != new_val:
                changes.append((field, new_val))
        return changes

    @staticmethod
    def _fmt_value(v: object) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v) if v else "(trống)"
        return str(v) if v not in (None, "") else "(trống)"

    @staticmethod
    def _is_affirmative(msg: str) -> bool:
        if not msg:
            return False
        patterns = [
            r"^đúng\b", r"^dung\b", r"^ok\b", r"^okay\b",
            r"^chốt\b", r"^chot\b", r"^xác nhận\b", r"^xac nhan\b",
            r"^đồng ý\b", r"^dong y\b", r"^yes\b", r"^y\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    # ---------- helpers ----------
    def _load_or_create(self, session_id: str | None) -> Session:
        if session_id:
            existing = self.storage.load_session(session_id)
            if existing:
                return existing
        return Session(session_id=session_id or str(uuid.uuid4()))

    @staticmethod
    def _bot(content: str) -> ChatMessage:
        return ChatMessage(role=ChatRole.BOT, content=content, ts=datetime.utcnow())

    @staticmethod
    def _dealer(content: str) -> ChatMessage:
        return ChatMessage(role=ChatRole.DEALER, content=content, ts=datetime.utcnow())
