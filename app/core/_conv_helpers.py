"""Conversation orchestrator helpers — Phase 6 R2 refactor.

Refer:
- F2A.1 stage dispatcher orchestrator
- 1A § 1.5 PARTIAL fill field-specific questions
- KE_HOACH § action 20 — conversation orchestrator ≤ 300 dòng

Helpers tách khỏi `conversation.py` (979 → split package):
- _gen_ack_safe: gen ack qua LLM với safe fallback
- _gen_partial_question: hỏi field cụ thể còn thiếu (slot multi-field)
- _get_slot_question_for_attempt: variant rotate + retry tone
- _summarize_history: tóm tắt N turn gần nhất
- _phase_1_pause_fallback: safe template khi LLM defensive/tâm sự fail
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.bridge_rotation import get_avoid_hint
from app.llm.ack_generator import generate_unified_response
from app.llm.client import LLMClient
from app.llm.fallback import safe_ack
from app.models.enums import DealerType
from app.models.schema import DealerProfileRaw, SessionState
from app.slots.definitions import is_thong_bao
from app.slots.templates import get_question, get_retry_question

logger = logging.getLogger(__name__)


# ============================================================
# Business Whys for the 17 slots
# ============================================================
SLOT_BUSINESS_WHY: dict[str, str] = {
    "1.1": "Để biết cách xưng hô xưng em gọi anh/chị cho lịch sự và ghi nhận tên thương hiệu gốc của mình.",
    "1.2": "Để em biết khu vực địa lý của mình, hỗ trợ thiết kế bộ nhận diện phù hợp với đặc thù khách hàng vùng miền đó.",
    "1.3": "Để lưu thông tin liên lạc chính xác, giúp đội ngũ kỹ thuật có thể gửi link tải bộ thương hiệu và liên hệ hỗ trợ nâng cấp sau này.",
    "2.1": "Cực kỳ quan trọng để lấy cảm hứng thiết kế logo. Làm mảng nào thì logo cần có nét đặc trưng của mảng đó mới chuyên nghiệp.",
    "2.2": "Để biết logo nên thiết kế theo hướng vững chãi, quy mô (nếu có xưởng sản xuất) hay hướng dịch vụ, linh hoạt (nếu phân phối thương mại).",
    "2.3": "Để hiểu quy mô hoạt động thực tế của mình, từ đó em gợi ý slogan thể hiện được năng lực sản xuất hoặc tay nghề cao của đội ngũ.",
    "2.4": "Để khi lên video giới thiệu thương hiệu hoặc card, bên em có thể khéo léo lồng ghép nguồn hàng chất lượng cao của anh vào để tăng uy tín.",
    "2.5": "Để em biết thiết kế danh thiếp nên làm nổi bật kênh nào nhất (quét mã QR Zalo, số Hotline hay trang Facebook cá nhân) giúp khách dễ liên hệ.",
    "2.6": "Để kiểm tra xem cửa hàng mình đã có sự hiện diện trên mạng xã hội chưa, từ đó em tư vấn cách tối ưu ảnh bìa/ảnh đại diện theo bộ nhận diện mới.",
    "3.1": "Để đánh giá sức khỏe thương hiệu hiện tại. Tỉ lệ khách cũ cao chứng tỏ tay nghề anh cực tốt, slogan cần nhấn mạnh vào chữ 'Tín' và chất lượng.",
    "3.2": "Để em tư vấn cho anh giải pháp lưu trữ thông minh giúp chăm sóc lại khách cũ dễ dàng vào các dịp lễ tết mà không bị trôi số.",
    "3.3": "Để tìm ra điểm nghẽn lớn nhất trong dịch vụ chăm sóc khách hàng của mình, từ đó đưa ra giải pháp giải quyết triệt để.",
    "3.4": "Để tư vấn cho anh cách thiết kế hợp đồng mẫu và quy trình tạm ứng chuyên nghiệp hơn, hạn chế tối đa việc bị nợ đọng dòng tiền.",
    "3.5": "Để biết vị thế đàm phán của xưởng mình, giúp slogan/cam kết thương hiệu đưa ra đúng bản chất, tránh hứa suông gây mất lòng tin.",
    "4.0": "Xác nhận cuối cùng để em kích hoạt hệ thống thiết kế tự động bộ Logo, Danh thiếp và Video giới thiệu thương hiệu hoàn toàn miễn phí.",
    "4.1": "Chọn gu thẩm mỹ mà anh ưng mắt nhất để định hình nét vẽ của họa sĩ số thiết kế đúng ý anh ngay từ bản phác thảo đầu tiên.",
    "4.2": "Để phối màu logo chuẩn mệnh phong thủy của anh giúp kinh doanh thuận lợi, hoặc chọn màu hợp gu thẩm mỹ đặc trưng của ngành nhôm kính.",
}


# ============================================================
# PARTIAL fill field-specific questions (refer 1A § 1.5)
# Pattern: dealer cho 1 field trong slot multi-field → hỏi field còn thiếu.
# ============================================================
_PARTIAL_FIELD_QUESTIONS: dict[str, str] = {
    # Slot 1.1
    "owner_name": "Em chưa rõ anh xưng hô là gì để em gọi cho lịch sự ạ?",
    "dealer_name": "Còn tên cửa hàng mình là gì ạ?",
    # Slot 1.2
    "address": "Anh cho em xin địa chỉ cửa hàng nha — đủ tỉnh + quận là OK.",
    "local_dominance_signal": "Tiện đây khách thường ghé cửa hàng mình từ bao xa ạ?",
    # Slot 1.3
    "phone_or_zalo": "Anh cho em xin số Zalo / điện thoại để team em liên hệ khi cần ạ?",
    # Slot 2.1
    "main_product": "Bên mình mạnh nhất sản phẩm gì anh ạ?",
    "category_stack": "Ngoài ra cửa hàng mình còn làm những mảng nào nữa không anh?",
    # Slot 2.2
    "business_model_signal": "Bên mình theo mô hình phân phối thuần hay có xưởng + đội thi công luôn ạ?",
    # Slot 2.3
    "est_team_size": "Bên mình hiện có khoảng bao nhiêu thợ chính ạ?",
    "team_stability_signal": "Đội thợ mình gắn bó với anh lâu chưa ạ?",
    # Slot 2.4
    "supplier_brands": "Bên mình đang nhập hàng từ hãng nào là chính ạ?",
    "customer_segment_signal": "Khách bên mình chủ yếu nhà dân hay dự án thầu ạ?",
    "supplier_negotiation_signal": "Nếu lỡ đứt hàng từ hãng chính, anh có nguồn backup không ạ?",
    # Slot 2.5
    "primary_contact_channel": "Khách hay liên hệ anh qua kênh nào nhất ạ — Zalo, gọi điện hay Facebook?",
    "zalo": "Anh cho em xin Zalo cửa hàng (nếu khác số máy chính) ạ?",
    # Slot 2.6
    "facebook": "Cửa hàng mình có fanpage Facebook không anh?",
    "fb_marketing_status": "Page bên mình hiện đang chạy quảng cáo hay chỉ post tự nhiên ạ?",
    "community_network_signal": "Bên anh có thợ giới thiệu / chia sẻ khách qua lại với đồng nghiệp không ạ?",
    # Slot 3.3
    "customer_pain": "Anh có thể chia sẻ thêm vướng mắc lớn nhất bên khách cũ không ạ?",
    "motivation_signal": "Động lực lớn nhất giữ anh làm nghề này là gì ạ?",
    "usp_signal": "Bên mình có điểm khác biệt nào khách hay khen / nhắc lại không anh?",
    # Slot 4.2
    "color_accent": "Anh thích màu chủ đạo nào cho thương hiệu ạ?",
    "feng_shui_signal": "Anh có quan tâm phong thủy / màu hợp mệnh không ạ?",
    "logo_initials": "Anh muốn logo dùng viết tắt nào ạ? Nếu chưa rành, em tự rút gọn theo tên cửa hàng giúp anh.",
    "slogan_preference": "Cửa hàng mình đã có slogan chưa anh? Nếu chưa, em gợi ý vài câu ngắn để anh chọn.",
    "logo_style": "Anh thích logo tối giản hiện đại, hình học chắc chắn hay công nghiệp mạnh mẽ ạ? Nếu chưa rành, em chọn giúp anh.",
}

_LLM_FIRST_BRANDING_QUESTIONS: dict[str, str] = {
    "4.3": _PARTIAL_FIELD_QUESTIONS["logo_initials"],
    "4.4": _PARTIAL_FIELD_QUESTIONS["slogan_preference"],
    "4.5": _PARTIAL_FIELD_QUESTIONS["logo_style"],
}


def gen_unified_response_safe(
    slot_id: str,
    extracted_data: dict,
    next_slot_id: str,
    next_slot_question: str,
    client: LLMClient,
    session: SessionState,
) -> str:
    """Sinh câu thoại hợp nhất với fallback an toàn khi gọi LLM gặp sự cố."""
    if not slot_id or not extracted_data:
        return safe_ack()

    # Phase 6 R+ Fix C v2: DETERMINISTIC ack khi reference fill
    ref_fields = session.last_ref_filled_fields or []
    if ref_fields:
        ref_ack = _gen_reference_ack(slot_id, extracted_data, ref_fields)
        if ref_ack:
            # Track + clear flag
            new_name = extracted_data.get("owner_name") or extracted_data.get("dealer_name")
            if new_name:
                session.last_acked_name = str(new_name)
            session.last_ref_filled_fields = []
            return f"{ref_ack}\n\n{next_slot_question}" if next_slot_question else ref_ack

    # Bug 12: tránh lặp brand name đã ack
    acked_brands = [
        k.split("_brand_", 1)[1] for k in session.acked_direct_keys
        if "_brand_" in k
    ]
    brand_avoid_hint = ""
    if acked_brands:
        brand_avoid_hint = f"Đã ack brand {', '.join(acked_brands)} turn trước — KHÔNG nhắc lại."

    next_why = SLOT_BUSINESS_WHY.get(next_slot_id, "")

    # Gọi LLM sinh phản hồi hợp nhất mượt mà
    try:
        response = generate_unified_response(
            slot_id=slot_id,
            extracted_data=extracted_data,
            next_slot_id=next_slot_id,
            next_slot_question=next_slot_question,
            next_slot_why=next_why,
            client=client,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            history_summary=summarize_history(session),
            use_fallback_on_error=False,  # Ép throw để catch & fallback
            bridge_avoid_hint=get_avoid_hint(session) + (" " + brand_avoid_hint if brand_avoid_hint else ""),
            recently_acked_name=session.last_acked_name,
            ref_filled_fields=session.last_ref_filled_fields or None,
        )
        if response:
            new_name = extracted_data.get("owner_name") or extracted_data.get("dealer_name")
            if new_name:
                session.last_acked_name = str(new_name)
            session.last_ref_filled_fields = []
            return response
    except Exception as e:
        logger.exception("Unified response generation failed, falling back to deterministic template: %s", e)

    # ==========================================
    # FALLBACK AN TOÀN KHI LLM THẤT BẠI
    # ==========================================
    direct_ack = _gen_direct_ack(slot_id, extracted_data, address_form=session.address_form.value, session=session)
    if not direct_ack:
        direct_ack = safe_ack()

    new_name = extracted_data.get("owner_name") or extracted_data.get("dealer_name")
    if new_name:
        session.last_acked_name = str(new_name)
    session.last_ref_filled_fields = []

    # Ghép nối cơ học làm phương án dự phòng an toàn
    return f"{direct_ack}\n\n{next_slot_question}" if next_slot_question else direct_ack


def gen_ack_safe(
    slot_id: str,
    extracted_data: dict,
    client: LLMClient,
    session: SessionState,
) -> str:
    """Gen ack với fallback safe (legacy/compatibility)."""
    return gen_unified_response_safe(
        slot_id=slot_id,
        extracted_data=extracted_data,
        next_slot_id="",
        next_slot_question="",
        client=client,
        session=session,
    )


def _gen_direct_ack(slot_id: str, extracted_data: dict, address_form: str = "anh", session=None) -> Optional[str]:
    """Deterministic ack for fragile correction cases.

    Fix Lỗi 3: check session.last_acked_name để tránh lặp ack brand.
    """
    af = address_form
    if slot_id == "1.1":
        owner = str(extracted_data.get("owner_name") or "").strip()
        dealer = str(extracted_data.get("dealer_name") or "").strip()
        if owner and dealer:
            if owner.casefold() == dealer.casefold():
                return f"Tên cửa hàng cũng là {dealer} ạ."
            return None
        if owner:
            return f"Dạ vâng {af} {owner} 🌷! Em đổi xưng hô cho đúng nhé."
        if dealer:
            return f"Tên cửa hàng mình là {dealer} ạ."
    if slot_id == "1.2" and extracted_data.get("address"):
        address = str(extracted_data.get("address") or "").strip()
        if address:
            return f"Em ghi nhận cửa hàng mình ở {address} rồi ạ."
    if slot_id == "1.3" and extracted_data.get("phone_or_zalo"):
        return f"Số này dùng liên hệ là tiện rồi {af}."
    if slot_id == "2.1" and extracted_data.get("main_product"):
        product = str(extracted_data.get("main_product") or "").strip()
        product_fold = _fold_vn(product)
        if "tủ bếp" in product.lower():
            return "Tủ bếp là mảng khách rất kỹ tính — làm tốt dễ có khách giới thiệu."
        if "cua cuon" in product_fold:
            return "Cửa cuốn là mảng cần độ chính xác và an toàn khi lắp đặt; em ghi nhận đây là sản phẩm mạnh của bên mình."
    if slot_id == "2.2" and extracted_data.get("business_model_signal"):
        # FIX M4: ack dynamic theo value thực tế thay vì always assume trọn gói
        bms = str(extracted_data["business_model_signal"]).lower()
        bms_fold = _fold_vn(bms)
        if any(k in bms_fold for k in ("thi cong", "tron goi", "lam het", "lap dat", "xuong")):
            return f"Làm trọn từ tư vấn tới thi công thì {af} kiểm soát chất lượng tốt hơn nhiều."
        elif any(k in bms_fold for k in ("phan phoi", "dai ly", "ban le", "ban hang", "ban thoi", "chi ban")) or bms_fold.strip(" .,!?:;") == "ban":
            return f"Phân phối thuần thì {af} tập trung nguồn hàng tốt là có lợi thế lớn."
        return None  # fallback LLM ack
    if slot_id == "2.3" and extracted_data.get("est_team_size"):
        return "Lực lượng ổn định để xoay nhiều đơn cùng lúc."
    if slot_id == "2.4" and extracted_data.get("supplier_brands"):
        brands = extracted_data.get("supplier_brands") or []
        if isinstance(brands, str):
            brands = [brands]
        brand_text = ", ".join(str(b).strip() for b in brands if str(b).strip())
        if brand_text:
            # Fix Lỗi 3: không lặp ack brand — track qua acked_direct_keys
            ack_key = f"2.4:brand:{brand_text.lower()}"
            if session and ack_key in session.acked_direct_keys:
                return None  # đã ack brand này → skip
            # Track ack
            if session:
                session.acked_direct_keys.append(ack_key)
            return f"Em ghi lại hãng nhập là {brand_text} ạ."
    if slot_id == "3.2" and extracted_data.get("customer_storage_method"):
        method = str(extracted_data.get("customer_storage_method") or "").lower()
        if "không" in method or "chưa" in method:
            return "Vậy hiện tại khách cũ chưa được lưu thành danh sách riêng; điểm này sau này chăm lại sẽ hơi khó."
    if slot_id == "3.5" and extracted_data.get("warranty_responsibility_signal"):
        warranty = _fold_vn(str(extracted_data.get("warranty_responsibility_signal") or ""))
        if "hang" in warranty or "nha cung cap" in warranty:
            return "Em ghi nhận phần bảo hành bên mình báo hãng xử lý là chính."
        if any(p in warranty for p in ("tu lo", "tu xu ly", "anh xu ly", "ben anh xu ly", "lo het")):
            return "Em ghi nhận phần bảo hành bên mình tự đứng ra xử lý cho khách."
    if slot_id == "2.5" and extracted_data.get("primary_contact_channel"):
        channel = _fold_vn(str(extracted_data.get("primary_contact_channel") or ""))
        if any(p in channel for p in ("noi tieng", "tu tim", "khach tu den", "khach tim den")):
            return "Uy tín sẵn có giúp khách tự tìm đến là lợi thế rất đáng quý của cửa hàng."
        if "gioi thieu" in channel or "khach quen" in channel or "nguoi quen" in channel:
            return "Khách quen giới thiệu là nguồn rất đáng giá, vì nó đi kèm niềm tin sẵn."
    if slot_id == "2.6" and extracted_data.get("community_network_signal"):
        signal_fold = _fold_vn(str(extracted_data.get("community_network_signal") or ""))
        if any(p in signal_fold for p in ("noi tieng", "tu tim", "khach tu den", "khach tu tim")):
            return "Uy tín sẵn có giúp khách tự tìm đến là lợi thế rất đáng quý của cửa hàng."
        return "Mạng lưới thợ giới thiệu qua lại như vậy là tài sản thật của cửa hàng."
    if slot_id == "3.1" and extracted_data.get("customer_old_percentage"):
        return "Tỉ lệ khách cũ giới thiệu như vậy cho thấy cửa hàng đã có nền uy tín nhất định."
    if slot_id == "3.3" and extracted_data.get("customer_pain"):
        pain_fold = _fold_vn(str(extracted_data.get("customer_pain") or ""))
        if any(p in pain_fold for p in ("khong kho", "khong co vuong", "khong vuong", "khong co van de")):
            return "Vậy phần khách cũ hiện tại của mình đang khá ổn, em ghi nhận điểm này."
    if slot_id == "3.4" and extracted_data.get("payment_terms_signal"):
        payment_fold = _fold_vn(str(extracted_data.get("payment_terms_signal") or ""))
        if any(p in payment_fold for p in ("khong no", "khong bi no", "khong no dong")):
            return "Không bị nợ đọng là điểm rất tốt cho dòng tiền của cửa hàng."
    return None


def _strip_trailing_question(text: str) -> str:
    """Strip câu hỏi cuối ack — LLM hay tự bịa câu hỏi sau ack statement.

    Engine sẽ append slot question riêng. Để tránh 2 câu hỏi/lượt
    (anti-pattern CORE B.4 #4), strip câu cuối nếu kết bằng '?'.
    Giữ nếu ack chỉ có 1 câu duy nhất (đó là statement chính).

    Fix Lỗi 1: xử lý emoji sau dấu '?' (vd '...ạ? 🌷')
    FIX H2: strip câu cuối nếu chứa CTA pattern (hỏi thông tin) dù kết bằng '.'
    """
    if not text:
        return text
    import re as _re
    sentences = _re.split(r'(?<=[.!?\u2026])\s+', text.strip())
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return text
    # Fix Lỗi 1: strip trailing question (kết bằng ? + optional emoji)
    while len(sentences) > 1 and _re.search(r'\?\s*[\U0001F300-\U0001FAF8\u2600-\u27BF\s]*$', sentences[-1]):
        sentences.pop()
    # FIX H2: strip câu cuối nếu chứa CTA pattern (mời dealer cho thông tin)
    _CTA_PATTERNS = [
        r'cho em xin', r'anh cho em', r'chị cho em',
        r'em xin', r'em cần',
    ]
    if len(sentences) > 1 and any(
        _re.search(p, sentences[-1], _re.IGNORECASE)
        for p in _CTA_PATTERNS
    ):
        sentences.pop()
    if not sentences:
        return text
    return " ".join(sentences)


def _fold_vn(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _strip_storage_cliche(text: str) -> str:
    """Remove repetitive 'note/ghi nhận/lưu hồ sơ' boilerplate from LLM ack."""
    if not text:
        return text
    import re as _re

    patterns = [
        r"\s*[-—,]?\s*em\s+(đã\s+)?(ghi nhận|note|lưu)(\s+thông tin này)?(\s+vào\s+hồ\s+sơ)?\s*(rồi|ạ|nhé|luôn)?\.?",
        r"\s*[-—,]?\s*em\s+(đã\s+)?lưu\s+(lại\s+)?(vào\s+)?hồ\s+sơ(\s+nội\s+bộ)?\s*(rồi|ạ|nhé)?\.?",
        r"\s*[-—,]?\s*em\s+(đã\s+)?cập\s+nhật[^.?!]{0,40}(vào\s+)?danh\s+sách[^.?!]{0,20}\.?",
        r"\s*[-—,]?\s*em\s+(đã\s+)?cập\s+nhật[^.?!]{0,40}(vào\s+)?hệ\s+thống[^.?!]{0,20}\.?",
        r"\s*[-—,]?\s*vào\s+hệ\s+thống\s+hỗ\s+trợ\s+chiến\s+lược[^.?!]{0,20}\.?",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = _re.sub(pattern, "", cleaned, flags=_re.IGNORECASE)
    cleaned = _re.sub(r"\s{2,}", " ", cleaned).strip(" -—,")
    return cleaned or "Dạ vâng."


def _gen_reference_ack(
    slot_id: str,
    extracted_data: dict,
    ref_fields: list[str],
) -> Optional[str]:
    """Phase 6 R+ Fix C v2: gen ack DETERMINISTIC khi reference fill.

    Vd dealer "cùng tên anh luôn" → ref_fields=["dealer_name"] →
    ack "Dạ tên cửa hàng cũng là {value} — em note rồi."
    """
    if slot_id == "1.1":
        # Slot 1.1: owner_name ↔ dealer_name reference
        if "dealer_name" in ref_fields and extracted_data.get("dealer_name"):
            val = extracted_data["dealer_name"]
            return f"Dạ tên cửa hàng cũng là {val} ạ."
        if "owner_name" in ref_fields and extracted_data.get("owner_name"):
            val = extracted_data["owner_name"]
            return f"Dạ tên cũng là {val} ạ."
    return None


def gen_partial_question(
    slot_id: Optional[str],
    profile: DealerProfileRaw,
    session: Optional[SessionState] = None,
) -> str:
    """Hỏi field cụ thể còn thiếu trong slot multi-field (1A § 1.5).

    Phase 5 R3 Gap 11+12: ưu tiên REQUIRED field, fallback OPTIONAL/all_fields.
    Fix Lỗi 5: adapt address_form cho mọi partial question.
    """
    fallback = "Cho em thêm thông tin còn thiếu nha?"
    if not slot_id:
        return _adapt_address_form(fallback, session) if session else fallback
    from app.slots.definitions import SLOT_TO_ALL_FIELDS, SLOT_TO_REQUIRED_FIELDS

    required = SLOT_TO_REQUIRED_FIELDS.get(slot_id, [])
    for f in required:
        if getattr(profile, f, None) is None:
            q = _PARTIAL_FIELD_QUESTIONS.get(f)
            if q:
                return _adapt_address_form(q, session) if session else q
    all_fields = SLOT_TO_ALL_FIELDS.get(slot_id, [])
    for f in all_fields:
        if f in required:
            continue
        if getattr(profile, f, None) is None:
            q = _PARTIAL_FIELD_QUESTIONS.get(f)
            if q:
                return _adapt_address_form(q, session) if session else q
    return _adapt_address_form(fallback, session) if session else fallback


def _adapt_address_form(text: Optional[str], session: SessionState) -> Optional[str]:
    """Replace xưng hô 'anh' ↔ session.address_form trong MỌI output.

    Dùng \\banh\\b (word boundary) + negative lookahead để:
    - BẮT: 'anh Giang', 'gửi anh', 'đủ anh.', 'Anh có thể'
    - SKIP: 'anh chị' (compound), 'anh em' (compound), 'danh', 'nhanh'

    FIX H1: thêm guard ngược — khi address_form == ANH, replace 'chị' → 'anh'.
    """
    if not text:
        return text
    import re as _re
    af = session.address_form.value

    if af == "anh":
        # FIX H1: guard ngược — replace "chị" → "anh" khi template hard-code "chị"
        def _replace_chi(m):
            matched = m.group(0)
            if matched[0].isupper():
                return "Anh"
            return "anh"
        result = _re.sub(
            r'\bchị\b(?!\s+(?:anh|em\b))',
            _replace_chi,
            text,
            flags=_re.IGNORECASE,
        )
        return result

    # af == "chị" → replace "anh" → "chị"
    def _replace_anh(m):
        """Preserve capitalization: Anh → Chị, anh → chị."""
        matched = m.group(0)
        if matched[0].isupper():
            return af.capitalize()
        return af

    # Bắt standalone "anh" NHƯNG skip compound "anh chị", "anh em"
    result = _re.sub(
        r'\banh\b(?!\s+(?:chị|em\b))',
        _replace_anh,
        text,
        flags=_re.IGNORECASE,
    )
    return result


def get_slot_question_for_attempt(
    slot_id: Optional[str],
    session: SessionState,
) -> Optional[str]:
    """Lấy câu hỏi slot phù hợp attempt (retry tone giảm dần + variant rotate).

    Refer 1A § 1.2 + Phase 5 R1 Gap 7: nếu retry template empty → cycle variant
    qua `attempt_offset` để tránh lặp y hệt câu initial.
    """
    if not slot_id:
        return None
    sid = session.session_id
    if slot_id in _LLM_FIRST_BRANDING_QUESTIONS:
        return _adapt_address_form(_LLM_FIRST_BRANDING_QUESTIONS[slot_id], session)
    if is_thong_bao(slot_id):
        q = get_question(slot_id, session_id=sid)
        return _adapt_address_form(q, session)
    attempts = session.slot_attempts.get(slot_id)
    attempt_num = attempts.total + 1 if attempts else 1
    if attempt_num <= 1:
        q = get_question(slot_id, session_id=sid)
        return _adapt_address_form(q, session)
    q = (
        get_retry_question(slot_id, attempt=attempt_num)
        or get_question(
            slot_id,
            session_id=sid,
            attempt_offset=attempt_num - 1,
        )
    )
    return _adapt_address_form(q, session)


def summarize_history(session: SessionState, max_turns: int = 10) -> str:
    """Tóm tắt N turn gần nhất cho LLM context.

    Phase 6 R+ 2026-05-22: tăng default 3 → 10 turn (6 → 20 message).
    Cost tăng ~3x ($0.0014 → $0.0034/session Gemini Flash) nhưng quality
    cải thiện đáng kể — bot nhớ tên/địa chỉ/sản phẩm dealer nói từ đầu,
    less hallucinate.

    Format ngắn: "dealer: ... | bot: ... | dealer: ...".
    Truncate mỗi message ≤ 150 char (tăng từ 120) để giữ context giàu hơn.
    """
    if not session.history:
        return "(chưa có)"
    recent = session.history[-(2 * max_turns):]
    parts: list[str] = []
    for h in recent:
        content = (h.content or "").strip().replace("\n", " ")
        if len(content) > 150:
            content = content[:147] + "..."
        parts.append(f"{h.role}: {content}")
    return " | ".join(parts) if parts else "(chưa có)"


def phase_1_pause_fallback(paused_for: Optional[str], session: Optional[SessionState] = None) -> str:
    """Safe response cho PAUSE (defensive/tâm sự) khi LLM handler fail.

    Fix Lỗi 5: dùng text trung tính, adapt address_form.
    """
    if paused_for == "defensive":
        text = (
            "Dạ yên tâm — em không thu phí gì đâu ạ, em chỉ thu thập "
            "thông tin để team bên em hỗ trợ tốt hơn. Dữ liệu em lưu nội "
            "bộ, không share ra ngoài. Mình tiếp tục được không ạ?"
        )
    elif paused_for == "tam_su":
        text = "Dạ em hiểu mà ạ. Chia sẻ vậy em rất quý. À cho em hỏi tiếp xíu nhé?"
    else:
        text = "Dạ em hiểu ạ. Mình tiếp tục được không ạ?"
    return _adapt_address_form(text, session) if session else text
