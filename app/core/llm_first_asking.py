"""Quynh-style LLM-first ASKING engine for Em Linh MKT."""
from __future__ import annotations

import logging
import re

from app.core._conv_confirming import enter_confirming
from app.core._conv_helpers import get_slot_question_for_attempt, summarize_history
from app.core.bridge_rotation import get_avoid_hint
from app.core.edge_cases import record_tam_su, reset_tam_su
from app.core.intake_coverage import compute_intake_coverage
from app.core.intake_edge_cases import (
    is_benefit_question,
    is_boundary_flirt_message,
    render_benefit_reply,
    render_boundary_flirt_ack,
)
from app.core.intake_profile_merge import merge_intake_facts
from app.core.intent import detect_intent, detect_technical_inquiry
from app.llm.client import LLMClient
from app.llm.intake_fact_extractor import (
    FactExtractorError,
    IntakeFact,
    IntakeFacts,
    extract_intake_facts,
)
from app.llm.intake_finalize_judge import FinalizeJudgeError, judge_intake_finalize
from app.llm.linh_conversation_prompt import generate_linh_conversation_reply
from app.llm.tam_su_handler import handle_tam_su as handle_tam_su_llm
from app.llm.auto_derive import gen_initials_full
from app.llm.brand_correction import get_correction_candidates
from app.models.enums import DealerType, Intent, Stage
from app.models.schema import DealerProfileRaw, SessionState

logger = logging.getLogger(__name__)

LLM_FIRST_FALLBACK_REPLY = (
    "Dạ em đang bị lỗi kết nối một chút, anh nhắn lại giúp em sau ít phút nhé."
)


def handle_asking_llm_first(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
    *,
    raw_message: str | None = None,
) -> str:
    """Handle ASKING with an LLM as the primary conversation brain.

    This intentionally does not call the legacy slot/state-machine ASKING
    handler for the happy path.
    """
    # Quynh keeps the conversation buffer as the main context. Linh does the
    # same here, with a cap to keep long sessions bounded.
    history_text = summarize_history(session, max_turns=40)
    intent = detect_intent(message)
    if is_benefit_question(message):
        return render_benefit_reply(session)
    if is_boundary_flirt_message(message):
        coverage = compute_intake_coverage(profile, session=session)
        question = _deterministic_intake_reply(session, profile, coverage, message)
        ack = render_boundary_flirt_ack(session, profile.owner_name)
        return f"{ack}\n\n{question}"
    if _should_use_legacy_edge_case(session, message, intent):
        from app.core._conv_asking import handle_asking

        return handle_asking(session, profile, message, client)
    if intent == Intent.TAM_SU or _is_casual_chat(message):
        reply = _handle_smalltalk(session, message, client, history_text)
        return _ensure_owner_address_form(reply, session, profile)
    reset_tam_su(session)

    correction_confirmation = _supplier_brand_correction_confirmation(
        session,
        raw_message=raw_message or message,
    )
    if correction_confirmation:
        return correction_confirmation

    focus_before_merge = session.current_slot
    facts = _extract_facts_safely(
        session=session,
        profile=profile,
        message=message,
        history_text=history_text,
        client=client,
    )
    _apply_contextual_guardrail_facts(session, profile, message, facts)
    merge_summary = merge_intake_facts(profile, facts, client=client)
    _record_resolved_optional_slots(session, facts)
    coverage = compute_intake_coverage(profile, session=session)
    session.current_slot = coverage.recommended_slot

    logger.info(
        "LLM-first intake facts: session=%s applied=%s skipped=%s focus=%s",
        session.session_id,
        sorted(merge_summary.applied.keys()),
        merge_summary.skipped,
        session.current_slot,
    )

    if focus_before_merge == "1.2" and not profile.address:
        return _deterministic_intake_reply(session, profile, coverage, message)
    if (
        focus_before_merge == "1.3"
        and not profile.phone_or_zalo
        and _looks_like_phone_candidate(message)
    ):
        return _invalid_phone_reply(session, profile)

    if coverage.can_summarize and _should_finalize_safely(
        session=session,
        profile=profile,
        message=message,
        history_text=history_text,
        coverage=coverage,
        client=client,
    ):
        session.stage = Stage.CONFIRMING
        return enter_confirming(profile, session=session)

    try:
        reply = generate_linh_conversation_reply(
            session=session,
            profile=profile,
            coverage=coverage,
            history_text=history_text,
            user_message=message,
            client=client,
        )
    except Exception:
        logger.exception("LLM-first conversation reply failed")
        return _deterministic_intake_reply(session, profile, coverage, message)

    if not reply or not reply.strip():
        logger.warning("LLM-first conversation reply is empty: session=%s", session.session_id)
        return _deterministic_intake_reply(session, profile, coverage, message)
    reply = reply.strip()
    if _is_llm_error_reply(reply):
        logger.warning(
            "LLM-first chat returned adapter error fallback: session=%s reply=%r",
            session.session_id,
            reply[:120],
        )
        return _deterministic_intake_reply(session, profile, coverage, message)
    reply = _ensure_owner_address_form(reply, session, profile)
    if coverage.required_missing and not _reply_asks_for_required_focus(
        reply,
        coverage.recommended_focus,
    ):
        logger.warning(
            "LLM-first reply drifted away from required focus: session=%s focus=%s",
            session.session_id,
            coverage.recommended_focus,
        )
        return _deterministic_intake_reply(session, profile, coverage, message)
    return reply


def _should_use_legacy_edge_case(
    session: SessionState,
    message: str,
    intent: Intent,
) -> bool:
    """Reuse the mature Linh handlers for guardrail cases outside the happy path."""
    if detect_technical_inquiry(message, current_slot=session.current_slot):
        return True
    return intent in {
        Intent.DEFENSIVE,
        Intent.CONFUSION,
        Intent.REFUSAL,
    }


def _extract_facts_safely(
    *,
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    history_text: str,
    client: LLMClient,
) -> IntakeFacts:
    try:
        return extract_intake_facts(
            history_text=history_text,
            current_profile=profile,
            user_message=message,
            client=client,
            current_focus_slot=session.current_slot,
        )
    except FactExtractorError:
        logger.exception("LLM-first fact extractor returned invalid output")
    except Exception:
        logger.exception("LLM-first fact extractor failed")
    return IntakeFacts()


def _record_resolved_optional_slots(session: SessionState, facts: IntakeFacts) -> None:
    """Remember explicit optional skips so the LLM-first flow does not loop."""
    for slot_id in facts.resolved_optional_slots:
        if slot_id not in session.skipped_slots:
            session.skipped_slots.append(slot_id)


def _apply_contextual_guardrail_facts(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    facts: IntakeFacts,
) -> None:
    """Apply deterministic facts only where the current question is unambiguous."""
    if session.current_slot == "4.0" and detect_intent(message) == Intent.AFFIRMATIVE:
        if not any(fact.field == "brandkit_consent" for fact in facts.facts):
            facts.facts.append(
                IntakeFact(
                    field="brandkit_consent",
                    value="yes",
                    evidence=message,
                    confidence="high",
                )
            )

    auto_field = {
        "4.2": "color_accent",
        "4.3": "logo_initials",
        "4.4": "slogan_preference",
        "4.5": "logo_style",
    }.get(session.current_slot or "")
    
    is_delegated = _dealer_delegates_choice(message)
    if auto_field == "color_accent" and not is_delegated:
        # If the bot suggested colors and the dealer replies with a simple OK/Yes, auto-assign
        if detect_intent(message) == Intent.AFFIRMATIVE:
            is_delegated = True

    if not auto_field or not is_delegated:
        return
    existing = next((fact for fact in facts.facts if fact.field == auto_field), None)
    if existing is not None:
        if str(existing.value or "").strip().casefold() != "auto":
            return
        existing.value = _recommended_branding_value(auto_field, profile)
        existing.confidence = "high"
        return
    facts.facts.append(
        IntakeFact(
            field=auto_field,
            value=_recommended_branding_value(auto_field, profile),
            evidence=message,
            confidence="high",
        )
    )


def _recommended_branding_value(field: str, profile: DealerProfileRaw) -> str:
    if field == "color_accent":
        category = (profile.main_category or "").lower()
        product = (profile.main_product or "").lower()
        if "bep" in product or "bep" in category:
            return "vàng hoàng kim phối đen"
        elif "dien" in product or "solar" in product or "dien_mat_troi" in category:
            return "xanh lục ngọc phối xám trắng"
        elif "cuon" in product or "cua_cuon" in category:
            return "ghi sáng phối xám đậm"
        return "xanh dương phối ghi bạc"
    if field == "logo_initials":
        return profile.initials_full or gen_initials_full(profile.dealer_name) or "CH"
    if field == "slogan_preference":
        return (
            str(profile.slogan_options[0])
            if profile.slogan_options
            else "Vững chất lượng, bền niềm tin"
        )
    if field == "logo_style":
        return "tối giản hiện đại"
    return "auto"


def _dealer_delegates_choice(message: str) -> bool:
    folded = _fold_vn(message)
    return any(
        phrase in folded
        for phrase in (
            "em chon",
            "chon ho",
            "tuy em",
            "sao cung duoc",
            "chon luon",
            "thich gi anh chon nay",
            "thich gi chon nay",
            "quynh chon",
            "linh chon",
        )
    )


_CASUAL_CHAT_RE = re.compile(
    r"\b("
    r"an com chua|uong ca phe chua|khoe khong|co met khong|"
    r"noi chuyen choi|chem gio|tam su ti|tam su chut|"
    r"em bao nhieu tuoi|em co nguoi yeu|em o dau|"
    r"troi nong|nong qua|troi lanh|lanh qua|mua qua|nang qua|"
    r"hom nay the nao"
    r")\b"
)


def _is_casual_chat(message: str) -> bool:
    folded = _fold_vn(message)
    if not folded:
        return False
    if any(token in folded for token in ("bao gia", "gia bao nhieu", "chiet khau", "hop dong")):
        return False
    return bool(_CASUAL_CHAT_RE.search(folded))


def _is_llm_error_reply(reply: str) -> bool:
    folded = _fold_vn(reply)
    return (
        ("truc trac" in folded or "ky thuat" in folded or "loi ket noi" in folded)
        and ("nhan lai" in folded or "thu lai" in folded or "sau it phut" in folded)
    )


def _supplier_brand_correction_confirmation(
    session: SessionState,
    *,
    raw_message: str,
) -> str | None:
    """Confirm a phonetic typed supplier brand before persisting a guess."""
    folded = _fold_vn(raw_message)
    supplier_context = session.current_slot == "2.4" or any(
        marker in folded
        for marker in ("hang ", "hang nao", "nhap ", "vat tu", "dung ", "xai ")
    )
    if not supplier_context:
        return None
    candidates = [
        canonical
        for typo, canonical in get_correction_candidates(raw_message, brands_only=True)
        if typo.casefold() != canonical.casefold()
    ]
    unique = list(dict.fromkeys(candidates))
    if not unique:
        return None
    joined = " và ".join(unique)
    af = session.address_form.value
    return f"Dạ {af}, ý {af} là hãng {joined} đúng không ạ?"


def _looks_like_phone_candidate(message: str) -> bool:
    digits = re.sub(r"\D+", "", message or "")
    return len(digits) >= 8


def _reply_asks_for_required_focus(reply: str, focus: str | None) -> bool:
    """Reject an LLM question that wanders past a still-missing required field."""
    if not focus:
        return True
    folded = _fold_vn(reply[-420:])
    markers = {
        "owner_name": ("ten anh", "ten chi", "xung ho", "ten that", "ten de"),
        "dealer_name": ("ten cua hang", "cua hang minh ten", "ten thuong hieu"),
        "address": ("dia chi", "o dau", "tinh", "thanh", "quan", "huyen", "khu vuc"),
        "phone_or_zalo": ("so dien thoai", "zalo", "lien he", "so dt", "sdt"),
        "main_product": (
            "san pham", "chuyen ve", "manh nhat", "mang nao",
            "cua", "nhom", "kinh", "bep", "thep", "sat", "go",
            "chong chay", "van go", "nhap hang", "dien mat troi", "vat tu",
        ),
        "business_model_signal": (
            "san xuat", "phan phoi", "thi cong", "mo hinh",
            "dai ly", "xuong", "ban le", "ban lai", "tu lam",
            "ca ba", "ba luon", "ca 3", "ba nhom",
        ),
        "brandkit_consent": (
            "dong y", "dung thong tin", "dung bo thuong hieu",
            "nhan qua", "nhan bo", "nhan logo", "nhan card",
            "lam logo", "mien phi", "tang anh",
        ),
        "est_team_size": ("doi tho", "bao nhieu nguoi", "co tho", "bao nhieu tho", "so luong tho"),
        "supplier_brands": ("nhap", "hang nao", "thuong hieu", "nhap cua", "nhap tu", "xingfa", "pma", "viet phap"),
        "primary_contact_channel": ("lien he", "qua dau", "zalo", "dien thoai", "facebook", "lien lac"),
        "facebook": ("facebook", "fanpage", "kenh online", "trang cua hang"),
        "customer_old_percentage": ("khach cu", "khach quen", "gioi thieu", "quay lai", "ti le", "phan tram"),
        "customer_storage_method": ("luu danh sach", "luu khach", "ghi so", "excel", "so sach", "luu thong tin"),
        "customer_pain": ("vuong mac", "kho khan", "dau dau", "lo lang", "ngai nhat", "khong thich nhat"),
        "payment_terms_signal": ("thanh toan", "coc", "dat coc", "cong no", "no"),
        "warranty_responsibility_signal": ("bao hanh", "sua chua", "loi", "trach nhiem"),
        "color_accent": ("mau", "phong thuy", "hop menh", "mau sac", "chu dao"),
        "logo_initials": ("viet tat", "chu tren logo", "chu viet tat", "ten viet tat"),
        "slogan_preference": ("slogan", "cau chot", "khau hieu", "cau ngon"),
        "logo_style": ("phong cach", "gu logo", "toi gian", "hien dai", "hinh hoc", "chac chan", "cong nghiep"),
    }.get(focus)
    return True if not markers else any(marker in folded for marker in markers)


def _extract_clean_location(message: str) -> str:
    cleaned = message.strip(" .,!?:;\"'")
    import re as _re
    cleaned = _re.sub(
        r"^(?:dạ\s+)?(?:anh\s+|chị\s+|em\s+)?(?:ở|o|khu vực|tại|tai)\s+",
        "",
        cleaned,
        flags=_re.IGNORECASE | _re.UNICODE,
    )
    cleaned = _re.sub(
        r"\s+(?:ấy\s+em|ay\s+em|em\s+ơi|em\s+oi|nhé|nhe|nha|ạ|a|nhen|đấy|day)$",
        "",
        cleaned,
        flags=_re.IGNORECASE | _re.UNICODE,
    )
    return cleaned.strip()


def _invalid_phone_reply(session: SessionState, profile: DealerProfileRaw) -> str:
    af = session.address_form.value
    owner = (profile.owner_name or "").strip()
    call = f"{af} {owner}".strip() if owner else af
    return (
        f"Dạ em thấy số vừa rồi chưa đúng định dạng nên chưa dám lưu, sợ team "
        f"gửi nhầm mất. {_cap_first(call)} kiểm tra và nhắn lại giúp em số điện "
        "thoại hoặc Zalo nhé."
    )


def _deterministic_intake_reply(
    session: SessionState,
    profile: DealerProfileRaw,
    coverage,
    message: str,
) -> str:
    """Non-error fallback when the LLM chat adapter fails.

    Keep the dealer moving instead of surfacing a technical apology.
    """
    af = session.address_form.value
    owner = (profile.owner_name or "").strip()
    call = f"{af} {owner}".strip() if owner else af
    focus = coverage.recommended_focus or ""
    latest = (message or "").strip()

    if focus in {"owner_name", "dealer_name"}:
        return f"Dạ để em làm hồ sơ thương hiệu cho đúng người đúng cửa hàng, {call} cho em xin tên anh và tên cửa hàng mình nha."
    if focus == "address":
        if latest:
            clean_loc = _extract_clean_location(latest)
            if clean_loc and len(clean_loc) >= 3:
                return f"Dạ em nghe phần địa chỉ ở \"{clean_loc}\" rồi ạ nhưng chưa muốn chốt nhầm khu vực. {_cap_first(call)} xác nhận giúp em tỉnh/thành và quận/huyện của cửa hàng mình nha."
            return f"Dạ em nghe phần địa chỉ rồi nhưng chưa muốn chốt nhầm khu vực. {_cap_first(call)} xác nhận giúp em tỉnh/thành và quận/huyện của cửa hàng mình nha."
        return f"Dạ phần địa chỉ giúp em ghi đúng khu vực trên hồ sơ thương hiệu. {_cap_first(call)} cho em xin tỉnh/thành và quận/huyện cửa hàng mình nha."
    if focus == "phone_or_zalo":
        return f"Dạ thông tin này để team em gửi bộ thương hiệu sau khi chốt. {_cap_first(call)} cho em xin số điện thoại hoặc Zalo tiện liên hệ nha."
    if focus == "main_product":
        return f"Dạ phần sản phẩm chính rất quan trọng để logo không bị chung chung. {_cap_first(call)} cho em biết cửa hàng mình mạnh nhất mảng nào nha."
    if focus == "business_model_signal":
        return f"Dạ để em chọn hướng thương hiệu sát hơn, {call} cho em biết bên mình thiên về sản xuất, phân phối hay thi công lắp đặt ạ?"
    if focus in {"est_team_size", "team_stability_signal"}:
        return f"Dạ phần đội thợ giúp em kể năng lực triển khai của cửa hàng cho đúng. Bên mình có đội thợ riêng khoảng bao nhiêu người anh?"
    if focus == "supplier_brands":
        return f"Dạ tên hãng vật tư giúp logo và hồ sơ thương hiệu đúng chất nghề hơn. Bên mình thường dùng hãng nhôm/kính nào là chính anh?"
    if focus == "customer_segment_signal":
        return f"Dạ biết nhóm khách chính sẽ giúp em chọn phong cách logo hợp hơn. Khách bên mình chủ yếu là nhà dân, thầu hay công trình dự án anh?"
    if focus == "supplier_negotiation_signal":
        return f"Dạ nguồn backup cũng là điểm mạnh khi kể về độ chủ động của cửa hàng. Nếu hãng chính đứt hàng, bên anh có nguồn thay thế không ạ?"
    if focus == "primary_contact_channel":
        return f"Dạ để sau này đặt thông tin liên hệ cho gọn trên danh thiếp, khách thường liên hệ anh qua Zalo, gọi điện hay Facebook là chính ạ?"
    if focus in {"facebook", "fb_marketing_status", "community_network_signal"}:
        return f"Dạ phần kênh online giúp bộ thương hiệu nối đúng chỗ khách đang thấy mình. Cửa hàng mình hiện có Facebook/fanpage chưa anh?"
    if focus == "customer_old_percentage":
        return f"Dạ khách cũ giới thiệu là tín hiệu uy tín rất đáng đưa vào cách kể thương hiệu. Khoảng bao nhiêu phần khách bên mình là khách quen hoặc được giới thiệu lại anh?"
    if focus == "customer_storage_method":
        return f"Dạ cách lưu khách cũ giúp em hiểu mình chăm lại khách thế nào. Hiện anh lưu khách bằng Zalo, sổ, Excel hay chưa lưu riêng ạ?"
    if focus == "customer_pain":
        return f"Dạ để em hiểu đúng bài toán kinh doanh chứ không chỉ làm logo đẹp, vướng mắc lớn nhất của bên anh với khách cũ hiện là gì ạ?"
    if focus == "payment_terms_signal":
        return f"Dạ quy trình cọc và thanh toán là phần tạo niềm tin khi kể về cửa hàng. Bên mình thường nhận cọc/thanh toán theo cách nào anh?"
    if focus == "warranty_responsibility_signal":
        return f"Dạ phần bảo hành giúp thương hiệu nghe rõ trách nhiệm sau lắp đặt. Khi có bảo hành thì bên anh xử lý hay hãng/nhà cung cấp xử lý ạ?"
    if focus == "brandkit_consent":
        return f"Dạ em đã có khung thông tin chính rồi. {_cap_first(call)} đồng ý để em dùng thông tin này dựng bộ thương hiệu miễn phí cho cửa hàng mình nha?"
    if focus == "color_accent":
        return f"Dạ màu chủ đạo sẽ quyết định cảm giác đầu tiên của logo. {_cap_first(call)} thích màu nào, hay để em chọn phương án hợp ngành cho mình ạ?"
    if focus == "logo_initials":
        return f"Dạ để logo nhìn gọn và dễ nhớ, {call} muốn dùng viết tắt nào trên logo, hay để em tự rút gọn từ tên cửa hàng ạ?"
    if focus == "slogan_preference":
        return f"Dạ slogan giúp logo có câu chốt thương hiệu rõ hơn. Bên mình đã có slogan chưa, hay để em gợi ý vài câu ngắn cho anh chọn?"
    if focus == "logo_style":
        return f"Dạ bước cuối là gu logo để em dựng mẫu đúng ý hơn. {_cap_first(call)} thích tối giản hiện đại, hình học chắc chắn hay công nghiệp mạnh mẽ ạ?"
    return f"Dạ em ghi nhận rồi. {_cap_first(call)} cho em thêm một chút thông tin về cửa hàng mình để em làm bộ thương hiệu sát hơn nha."


def _cap_first(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _handle_smalltalk(
    session: SessionState,
    message: str,
    client: LLMClient,
    history_text: str,
) -> str:
    """Engage with smalltalk without consuming profile fields or advancing focus."""
    count = record_tam_su(session)
    next_slot_hint = get_slot_question_for_attempt(session.current_slot, session)
    reply = handle_tam_su_llm(
        dealer_message=message,
        tam_su_count=count,
        dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
        address_form=session.address_form,
        client=client,
        history_summary=history_text,
        current_slot=session.current_slot,
        next_slot_hint=next_slot_hint,
        bridge_avoid_hint=get_avoid_hint(session),
    )
    if reply and reply.strip():
        return reply.strip()
    af = session.address_form.value
    if next_slot_hint:
        return f"Em nghe {af} chia sẻ rồi ạ. Khi tiện mình quay lại phần này nhé:\n\n{next_slot_hint}"
    return f"Em nghe {af} chia sẻ rồi ạ."


def _fold_vn(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _ensure_owner_address_form(
    reply: str,
    session: SessionState,
    profile: DealerProfileRaw,
) -> str:
    """Repair a bare vocative such as "Hưng ơi" to "Anh Hưng ơi"."""
    owner_name = (profile.owner_name or "").strip()
    if not reply or not owner_name:
        return reply

    names = sorted({owner_name, owner_name.split()[-1]}, key=len, reverse=True)
    alternatives = "|".join(re.escape(name) for name in names)
    pattern = re.compile(
        rf"(?P<prefix>^|[.!?\n]\s*)(?P<name>{alternatives})\s+ơi\b",
        re.IGNORECASE | re.UNICODE,
    )
    address_form = session.address_form.value.capitalize()

    def _replace(match: re.Match) -> str:
        return f"{match.group('prefix')}{address_form} {match.group('name')} ơi"

    return pattern.sub(_replace, reply)


def _should_finalize_safely(
    *,
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    history_text: str,
    coverage,
    client: LLMClient,
) -> bool:
    try:
        decision = judge_intake_finalize(
            history_text=history_text,
            user_message=message,
            profile=profile,
            coverage=coverage,
            client=client,
        )
    except FinalizeJudgeError:
        logger.exception("LLM-first finalize judge returned invalid output")
        return False
    except Exception:
        logger.exception("LLM-first finalize judge failed")
        return False

    logger.info(
        "LLM-first finalize judge: session=%s should=%s reason=%s blockers=%s",
        session.session_id,
        decision.should_finalize,
        decision.reason,
        decision.missing_blockers,
    )
    return decision.should_finalize
