"""Safety net cho reply Replier — Layered defense post-LLM.

Chạy SAU khi Replier sinh reply để fix các vấn đề Replier đôi khi mắc:
- enforce_min_length: chống reply <30 từ; prepend compliment NẾU có field MỚI
  fill turn này nhưng Replier không khen (Q1 fix)
- enforce_defensive_answer: ép trả lời thẳng câu hỏi defensive nếu Replier
  bypass (vd dealer hỏi "miễn phí thật k" → bot phải khẳng định)

Triết lý: Replier có 70-80% case xử đúng, safety net cứu 20-30% còn lại.
Sẽ giảm dần khi prompt ổn hơn.
"""
from __future__ import annotations

import random
import re


def _word_count_vn(text: str) -> int:
    """Đếm số từ tiếng Việt — split theo whitespace, bỏ markdown/emoji."""
    if not text:
        return 0
    cleaned = re.sub(r"[*_`\[\]()•]", " ", text)
    return len([w for w in cleaned.split() if w.strip()])


# ============================================================
# COMPLIMENT BUILDER — pool template khen theo field
# ============================================================
def _build_compliment(extracted_data: dict, address: str) -> str:
    """Sinh câu compliment thật về data dealer vừa cho. Template-based.

    Random across all eligible fields → variety qua nhiều turn (không lặp).

    Quan trọng (Q1 fix): caller phải truyền `extracted_data` chỉ chứa field
    THỰC SỰ MỚI fill turn này (xem ConversationService._diff_new_fields).
    Nếu không, sẽ lạc quẻ khen field cũ.
    """
    data = extracted_data or {}

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
                "Wow nhôm kính là ngành đỉnh đó, tiềm năng lắm!",
                "Em phục, làm nhôm kính đòi tay nghề tinh tế lắm!",
            ],
            "cua_cuon": [
                f"Cửa cuốn — mảng truyền thống mà bền nhất luôn nhỉ {address}!",
                "Wow cửa cuốn là sản phẩm phổ biến nhất trong nhà ta đó!",
                "Em phục, cửa cuốn cần kinh nghiệm lắp đặt cao thật!",
            ],
            "tu_bep": [
                f"Tủ bếp là 'tâm hồn' của ngôi nhà, em phục {address} chăm gu thẩm mỹ!",
                "Wow tủ bếp giờ HOT lắm, ai chuyển nhà cũng cần!",
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
        # Tránh double "khách" nếu value đã chứa từ chỉ người ("khách", "ông",
        # "đứa", "người"). Vd "10 khách/tuần" → "Wow 10 khách/tuần — ..."
        # thay vì "Wow 10 khách/tuần khách —".
        n_low = str(n).lower()
        suffix = "" if any(w in n_low for w in ("khách", "ông", "đứa", "người", "anh")) else " khách"
        eligible.append(
            f"Wow {n}{suffix} — em phục {address} thật, chăm khách kỹ mới giữ được nhiều thế!"
        )

    if data.get("phone_or_zalo"):
        eligible.append(
            f"Em note số rồi {address} ơi, em chỉ nhắn khi có việc thật sự nhé."
        )

    if data.get("dealer_type"):
        dt = data["dealer_type"]
        dt_options = {
            "tho_doi": [
                f"Thợ trực tiếp tay nghề mới quý đó {address}!",
                f"Em phục thật, {address} đi thực địa suốt mới hiểu nghề!",
            ],
            "chu_xuong": [
                f"Chủ xưởng — {address} là gốc rễ ngành đó, em phục!",
            ],
            "dai_ly": [
                f"Đại lý là cầu nối chính rồi {address}, quan trọng lắm!",
            ],
            "nha_thau_nho": [
                f"Nhà thầu nhỏ — {address} quản nhiều mặt một lúc, vất vả thật!",
            ],
        }
        if dt in dt_options:
            eligible.extend(dt_options[dt])

    if data.get("dl0_priority"):
        eligible.extend([
            f"Lựa chọn chuẩn rồi {address}, cái đó em làm cho ổn nhất!",
            f"Hay đó {address}, đúng cái nhiều anh chọn!",
        ])

    if eligible:
        return random.choice(eligible)

    # Empty eligible — KHÔNG prepend gì (để Replier reply tự đứng, tránh
    # 2 prefix chồng "Dạ anh ơi... em ghi nhận..." kiểu loạn ngôn).
    return ""


# ============================================================
# ENFORCE MIN LENGTH — chống reply cộc lốc, prepend compliment nếu cần
# ============================================================
def _extract_new_values(extracted_data: dict) -> list[str]:
    """Lấy tất cả VALUE string của field mới (cả scalar lẫn item của list)."""
    out: list[str] = []
    for v in (extracted_data or {}).values():
        if isinstance(v, str) and v.strip():
            out.append(v.strip().lower())
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip().lower())
    return out


def enforce_min_length(
    text: str,
    extracted_data: dict | None = None,
    address: str = "anh",
    min_words: int = 35,
    confidence: dict | None = None,
) -> str:
    """Pre-send safety net — prepend compliment cho field MỚI nếu Replier
    chưa engage value field đó.

    Logic mới (đơn giản, tổng quát cho mọi field):
    1. Không có field mới → return text (Replier tự xử).
    2. Có field mới + Replier reply đã ĐỀ CẬP value field đó → return text
       (đã engage rồi, không cần prepend).
    3. Có field mới + Replier chưa đề cập → prepend compliment template.

    A1 fix: CHỈ prepend cho field có confidence HIGH. Field MEDIUM/LOW là
    Haiku INFER từ context (vd suy main_category từ shop name) — dealer
    chưa nói rõ → prepend compliment sẽ "lạc quẻ".

    `min_words` giữ làm parameter backward compat nhưng không dùng nữa.
    """
    if not text:
        return text

    # A1 fix: filter extracted_data chỉ giữ field HIGH confidence.
    # Field MEDIUM/LOW thường là Haiku infer/đoán → dealer chưa nói rõ →
    # không nên khen tránh "Tủ bếp là tâm hồn..." khi dealer chưa nói tủ bếp.
    if confidence:
        extracted_data = {
            k: v for k, v in (extracted_data or {}).items()
            if confidence.get(k) == "HIGH"
        }

    # Lấy danh sách value string của field mới
    new_values = _extract_new_values(extracted_data or {})

    # Rule 1: không có field mới → skip (Replier không cần khen ai)
    if not new_values:
        return text

    # Rule 2: Replier reply đã đề cập value field mới ở đầu reply → skip
    # (check 200 ký tự đầu — đủ cover compliment opening + intro)
    head_low = text.lower()[:200]
    already_engaged = any(v in head_low for v in new_values)
    if already_engaged:
        return text

    # Rule 3: Replier chưa engage value field mới → prepend compliment
    compliment = _build_compliment(extracted_data or {}, address)
    if not compliment:
        # _build_compliment không có template cho field mới này → skip
        # (KHÔNG prepend fallback generic — chống loạn ngôn)
        return text

    # Tránh double-Dạ
    if text.lower().startswith("dạ") and compliment.startswith("Dạ"):
        rest = text.split(maxsplit=1)
        text_body = rest[1] if len(rest) > 1 else ""
        return f"{compliment} {text_body}".strip()
    return f"{compliment} {text}"


# ============================================================
# ENFORCE DEFENSIVE ANSWER — ép trả lời thẳng câu hỏi defensive
# ============================================================
def enforce_defensive_answer(text: str, latest_dealer: str, address: str) -> str:
    """Safety Layer 2 — nếu dealer hỏi defensive nhưng bot reply KHÔNG đề cập
    benefit/sự thật → prepend câu trả lời thẳng dựa trên loại defensive.

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