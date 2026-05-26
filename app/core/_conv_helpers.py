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
from app.llm.ack_generator import generate_ack
from app.llm.client import LLMClient
from app.llm.fallback import safe_ack
from app.models.enums import DealerType
from app.models.schema import DealerProfileRaw, SessionState
from app.slots.definitions import is_thong_bao
from app.slots.templates import get_question, get_retry_question

logger = logging.getLogger(__name__)


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
}


def gen_ack_safe(
    slot_id: str,
    extracted_data: dict,
    client: LLMClient,
    session: SessionState,
) -> str:
    """Gen ack với fallback safe (refer F2B.4 + memory feedback_ack_and_why)."""
    if not slot_id or not extracted_data:
        return safe_ack()

    # Phase 6 R+ Fix C v2: DETERMINISTIC ack khi reference fill —
    # LLM_FAST không reliably follow "ack explicit cũng là X" hint.
    # Code-gen template trực tiếp + clear flag.
    ref_fields = session.last_ref_filled_fields or []
    if ref_fields:
        ack = _gen_reference_ack(slot_id, extracted_data, ref_fields)
        if ack:
            # Track + clear flag
            new_name = extracted_data.get("owner_name") or extracted_data.get("dealer_name")
            if new_name:
                session.last_acked_name = str(new_name)
            session.last_ref_filled_fields = []
            return ack

    direct_ack = _gen_direct_ack(slot_id, extracted_data, address_form=session.address_form.value, session=session)
    if direct_ack:
        return direct_ack

    # Bug 12: extract already-acked brand names to hint LLM
    acked_brands = [
        k.split("_brand_", 1)[1] for k in session.acked_direct_keys
        if "_brand_" in k
    ]
    brand_avoid_hint = ""
    if acked_brands:
        brand_avoid_hint = f"Đã ack brand {', '.join(acked_brands)} turn trước — KHÔNG nhắc lại."

    try:
        ack = generate_ack(
            slot_id=slot_id,
            extracted_data=extracted_data,
            client=client,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            use_fallback_on_error=True,
            bridge_avoid_hint=get_avoid_hint(session) + (" " + brand_avoid_hint if brand_avoid_hint else ""),
            recently_acked_name=session.last_acked_name,
            ref_filled_fields=session.last_ref_filled_fields or None,
        )
    except Exception as e:
        logger.exception("Ack gen fail: %s", e)
        return safe_ack()
    new_name = extracted_data.get("owner_name") or extracted_data.get("dealer_name")
    if new_name:
        session.last_acked_name = str(new_name)
    session.last_ref_filled_fields = []
    # Phase 6 R+ Fix question-leak: strip câu hỏi cuối ack (LLM hay bịa
    # hỏi lại slot đã fill — engine append slot question riêng).
    ack = _strip_storage_cliche(_strip_trailing_question(ack))
    return ack


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
    if slot_id == "1.3" and extracted_data.get("phone_or_zalo"):
        return f"Số này dùng liên hệ là tiện rồi {af}."
    if slot_id == "2.1" and extracted_data.get("main_product"):
        product = str(extracted_data.get("main_product") or "").strip()
        if "tủ bếp" in product.lower():
            return "Tủ bếp là mảng khách rất kỹ tính — làm tốt dễ có khách giới thiệu."
    if slot_id == "2.2" and extracted_data.get("business_model_signal"):
        return f"Làm trọn từ tư vấn tới thi công thì {af} kiểm soát chất lượng tốt hơn nhiều."
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
            return f"{brand_text}, em hiểu đúng tên hãng rồi."
    if slot_id == "2.5" and extracted_data.get("primary_contact_channel"):
        channel = str(extracted_data.get("primary_contact_channel") or "").lower()
        if "giới thiệu" in channel or "khách quen" in channel or "người quen" in channel:
            return "Khách quen giới thiệu là nguồn rất đáng giá, vì nó đi kèm niềm tin sẵn."
    if slot_id == "2.6" and extracted_data.get("community_network_signal"):
        return "Mạng lưới thợ giới thiệu qua lại như vậy là tài sản thật của cửa hàng."
    return None


def _strip_trailing_question(text: str) -> str:
    """Strip câu hỏi cuối ack — LLM hay tự bịa câu hỏi sau ack statement.

    Engine sẽ append slot question riêng. Để tránh 2 câu hỏi/lượt
    (anti-pattern CORE B.4 #4), strip câu cuối nếu kết bằng '?'.
    Giữ nếu ack chỉ có 1 câu duy nhất (đó là statement chính).

    Fix Lỗi 1: xử lý emoji sau dấu '?' (vd '...ạ? 🌷')
    """
    if not text or "?" not in text:
        return text
    import re as _re
    sentences = _re.split(r"(?<=[.!?…])\s+", text.strip())
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return text
    # Fix Lỗi 1: strip emoji/whitespace sau ? trước khi check endswith
    while sentences and _re.search(r'\?\s*[\U0001F300-\U0001FAF8\u2600-\u27BF\s]*$', sentences[-1]):
        sentences.pop()
    if not sentences:
        return text
    return " ".join(sentences)


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
    """Replace xưng hô 'anh' → session.address_form trong MỌI output.

    Dùng \\banh\\b (word boundary) + negative lookahead để:
    - BẮT: 'anh Giang', 'gửi anh', 'đủ anh.', 'Anh có thể'
    - SKIP: 'anh chị' (compound), 'anh em' (compound), 'danh', 'nhanh'
    """
    if not text or session.address_form.value == "anh":
        return text
    import re as _re
    af = session.address_form.value  # "chị"

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
