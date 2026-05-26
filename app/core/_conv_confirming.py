"""CONFIRMING + DONE stage handlers — Phase 6 R2 refactor.

Refer:
- F2A.1 stage CONFIRMING/DONE
- F2A.7 sanity check 5-point
- 1A § 6 — confirmation card + edit handler
- 1A § 7 — closing template + local hook

Fix Lỗi 5: adapt address_form cho mọi output.
Fix Lỗi 8: edit parser LLM Layer 2 (không khoá keyword).
Fix Lỗi 9: handle_done dynamic (nhận session + message).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.brandkit_exporter import export_brandkit_pack_json
from app.core.card_renderer import render_card
from app.core.closing import render_closing, render_soft_end_closing
from app.core.edit_parser import parse_edit_command
from app.core.intent import detect_intent
from app.core.sanity import check_sanity
from app.core.session import mark_session_closed
from app.llm.client import LLMClient
from app.models.enums import ConfirmationStatus, DealerType, Flag, Intent, Stage
from app.models.schema import DealerProfileRaw, SessionState

logger = logging.getLogger(__name__)


def _af(session: SessionState) -> str:
    """Shorthand lấy address_form value."""
    return session.address_form.value if session else "anh"


def handle_confirming(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> str:
    """Stage CONFIRMING: dealer xác nhận card."""
    intent = detect_intent(message)
    af = _af(session)

    # Bug 10: de-escalate profanity at CONFIRMING
    if intent == Intent.DEFENSIVE:
        return (
            f"Dạ em hiểu {af} đang bực, em xin lỗi nếu làm phiền. "
            f"{af.capitalize()} duyệt OK hay cần sửa chỗ nào ạ?"
        )

    if intent == Intent.AFFIRMATIVE:
        # Sanity check 5-point trước khi CONFIRMED (F2A.7)
        passed, failed = check_sanity(session, profile)
        if not passed:
            logger.warning("Sanity check fail: %s", failed)
            if Flag.SANITY_CHECK_FAILED not in session.flags:
                session.flags.append(Flag.SANITY_CHECK_FAILED)
            # Vẫn cho confirm — admin queue sẽ review

        session.confirmation_status = ConfirmationStatus.CONFIRMED
        session.stage = Stage.DONE
        mark_session_closed(session)

        # CORE H.4 bản #2: export brandkit pack cho designer team nếu
        # consent=yes. Log only — không gửi dealer (designer team đọc
        # từ admin queue/DB sau). Phase 5+ có thể push qua webhook.
        if profile.brandkit_consent == "yes":
            try:
                pack_json = export_brandkit_pack_json(
                    profile,
                    session_id=session.session_id,
                    indent=0,
                )
                logger.info(
                    "Brandkit pack exported (designer team): session=%s "
                    "len=%d bytes",
                    session.session_id, len(pack_json),
                )
            except Exception as e:
                logger.exception(
                    "Brandkit pack export fail: session=%s err=%s",
                    session.session_id, e,
                )

        return render_closing(
            province=profile.province,
            consent=profile.brandkit_consent,
            client=client,
            dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
            address_form=session.address_form,
            session_id=session.session_id,
            dealer_name=profile.dealer_name,
        )

    if intent == Intent.EDIT:
        return _handle_edit(session, profile, message, client)

    if intent == Intent.REFUSAL:
        session.confirmation_status = ConfirmationStatus.PENDING
        session.stage = Stage.DONE
        mark_session_closed(session)
        return render_soft_end_closing()

    # Layer 1 = NORMAL → LLM Layer 2 intent detect
    # Dealer có thể nói "hãng nhập là ốt đo" mà regex không bắt EDIT
    if intent == Intent.NORMAL and client:
        l2_intent = _detect_confirming_intent_llm(message, client)
        if l2_intent == "edit":
            return _handle_edit(session, profile, message, client)
        if l2_intent == "confirm":
            # Treat as affirmative
            session.confirmation_status = ConfirmationStatus.CONFIRMED
            session.stage = Stage.DONE
            mark_session_closed(session)
            if profile.brandkit_consent == "yes":
                try:
                    pack_json = export_brandkit_pack_json(
                        profile, session.session_id,
                    )
                    logger.info(
                        "Brandkit pack exported: session=%s size=%d",
                        session.session_id, len(pack_json),
                    )
                except Exception as e:
                    logger.warning(
                        "Brandkit export fail: session=%s err=%s",
                        session.session_id, e,
                    )
            return render_closing(
                province=profile.province,
                consent=profile.brandkit_consent,
                client=client,
                dealer_type=session.detected_dealer_type or DealerType.UNKNOWN,
                address_form=session.address_form,
                session_id=session.session_id,
                dealer_name=profile.dealer_name,
            )

    # Re-prompt — Fix Lỗi 5: dùng address_form
    return f"{af.capitalize()} duyệt OK / sửa gì giúp em ạ?"


def handle_done(
    session: Optional[SessionState] = None,
    message: Optional[str] = None,
    client: Optional[LLMClient] = None,
) -> str:
    """Stage DONE: session đóng — Fix Lỗi 9: dynamic reply.

    Nếu dealer nói thêm sau DONE, trả lời linh hoạt thay vì 1 câu tĩnh.
    """
    af = _af(session) if session else "anh"

    # Nếu không có message (first call) → default closing
    if not message:
        return (
            f"Em đã chốt thông tin rồi ạ. Em hẹn {af} trên Zalo nhé — "
            f"bộ thương hiệu + kế hoạch nền tảng số em gửi trong ít giờ tới."
        )

    # Dealer nói thêm sau DONE — phân loại ý
    msg_lower = message.strip().lower()

    # Cảm ơn / chào
    thank_words = {"cảm ơn", "cam on", "thanks", "thank", "cám ơn"}
    bye_words = {"tạm biệt", "bye", "chào", "hẹn gặp"}
    if any(w in msg_lower for w in thank_words):
        return f"Dạ em cảm ơn {af} nhiều ạ 🌷! Hẹn gặp lại {af} trên Zalo nhé!"

    if any(w in msg_lower for w in bye_words):
        return f"Dạ vâng, hẹn gặp lại {af} ạ 🌷!"

    # Nếu có LLM client → gen reply ngắn
    if client:
        try:
            from app.llm.system_prompt import build_system_prompt
            system = build_system_prompt(
                address_form=session.address_form if session else None,
                task=(
                    "Session ĐÃ ĐÓNG. Dealer tâm sự thêm sau khi đã chốt xong. "
                    f"Reply TỰ NHIÊN như bạn bè, ≤25 từ. "
                    "CẤM TUYỆT ĐỐI nhắc lại 'đã chốt thông tin', 'gửi qua Zalo', "
                    "'em sẽ tổng hợp' — dealer BIẾT RỒI, nhắc lại = spam. "
                    "Ví dụ: dealer hỏi thời tiết → trả lời thời tiết thực tế "
                    "(VN tháng 5-6 mùa hè nắng nóng 35-40°C). "
                    "Dealer tâm sự gia đình → đồng cảm nhẹ nhàng. "
                    "KHÔNG kéo về business. Trò chuyện bình thường."
                ),
            )
            reply = client.chat_fast(
                system_prompt=system,
                messages=[{"role": "user", "content": message}],
                max_tokens=128,
            )
            if reply and reply.strip():
                return reply.strip()
        except Exception:
            pass

    # Fallback tĩnh
    return (
        f"Dạ em đã chốt thông tin rồi ạ. Nếu {af} cần gì thêm, "
        f"{af} nhắn em trên Zalo nhé!"
    )


def _detect_confirming_intent_llm(message: str, client: LLMClient) -> str:
    """LLM Layer 2: detect intent at CONFIRMING stage.

    Returns: "edit" | "confirm" | "other"
    """
    import json

    prompt = (
        f"Dealer đang xem card xác nhận thông tin. Dealer nói:\n"
        f"\"{message}\"\n\n"
        f"Dealer có ý gì?\n"
        f"- \"edit\": muốn SỬA/ĐỔI/CẬP NHẬT 1 trường thông tin nào đó\n"
        f"- \"confirm\": xác nhận OK, đồng ý, duyệt\n"
        f"- \"other\": không rõ / chửi / tâm sự / hỏi\n\n"
        f"CHỈ trả JSON: {{\"intent\": \"edit/confirm/other\"}}"
    )
    try:
        response = client.chat_fast(
            system_prompt="Bạn là intent classifier. Chỉ trả JSON.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=64,
        )
        if not response:
            return "other"
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(text)
        intent_val = data.get("intent", "other")
        if intent_val in ("edit", "confirm"):
            logger.info("Confirming L2 intent: %r → %s", message[:60], intent_val)
            return intent_val
    except Exception as e:
        logger.debug("Confirming L2 intent fail: %s", e)
    return "other"


def enter_confirming(
    profile: DealerProfileRaw,
    session: Optional[SessionState] = None,
) -> str:
    """Render card khi vào CONFIRMING. Fix Lỗi 5: adapt address_form."""
    af = _af(session) if session else "anh"
    return (
        f"Em đã ghi nhận đủ thông tin rồi ạ. {af.capitalize()} xem giúp em "
        f"qua card này nhé:\n\n"
        + render_card(profile, address_form=af)
    )


def _handle_edit(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: Optional[LLMClient] = None,
) -> str:
    """Fix Lỗi 8: edit parser dùng regex L1 + LLM L2 (không khoá keyword).

    Layer 1: regex parse_edit_command() — fast, free
    Layer 2: LLM parse_edit_llm() — hiểu ngữ cảnh tự nhiên
    """
    af = _af(session)

    # Layer 1: regex (instant, miễn phí)
    parsed = parse_edit_command(message)

    # Layer 2: LLM nếu L1 fail — Fix Lỗi 8: bot PHẢI tự hiểu ý dealer
    if parsed is None and client is not None:
        parsed = _parse_edit_llm(message, profile, client)

    if parsed:
        field, new_value = parsed
        if hasattr(profile, field):
            setattr(profile, field, new_value)
            logger.info(
                "Edit applied: session=%s field=%s value=%r",
                session.session_id, field, new_value,
            )
            # Hiển thị tên field đẹp thay vì code name
            field_display = _FIELD_DISPLAY_NAMES.get(field, field)
            # Re-render card với data mới
            return (
                f"Dạ em đã cập nhật {field_display} rồi ạ. "
                f"Em hiển thị lại card mình cùng check nhé:\n\n"
                + render_card(profile, address_form=af)
            )
        else:
            logger.warning("Edit parsed field không có trong profile: %s", field)

    # Parse fail cả L1 + L2 → ask dealer rõ hơn
    return (
        f"Dạ {af} ghi rõ giúp em — sửa phần nào, thành gì ạ? "
        f"(Vd: 'sửa SĐT thành 0901234567', 'tên là Vinh', "
        f"'đổi địa chỉ thành Quận 5')"
    )


# ============================================================
# LLM-based edit parser — Layer 2 (Fix Lỗi 8)
# ============================================================


_FIELD_DISPLAY_NAMES: dict[str, str] = {
    "owner_name": "tên",
    "dealer_name": "tên cửa hàng",
    "address": "địa chỉ",
    "phone_or_zalo": "số điện thoại",
    "main_product": "sản phẩm chính",
    "est_team_size": "số thợ",
    "color_accent": "màu chủ đạo",
    "brandkit_consent": "đồng ý nhận bộ thương hiệu",
    "facebook": "Facebook",
    "business_model_signal": "mô hình kinh doanh",
    "supplier_brands": "hãng nhập",
}


def _parse_edit_llm(
    message: str,
    profile: DealerProfileRaw,
    client: LLMClient,
) -> Optional[tuple[str, object]]:
    """LLM Layer 2: hiểu ý dealer muốn sửa gì từ ngữ cảnh tự nhiên.

    Không khoá keyword — bot tự hiểu câu dealer có ý đổi hay chốt.
    """
    import json

    # Build profile summary cho LLM context
    profile_fields = {
        "owner_name": profile.owner_name,
        "dealer_name": profile.dealer_name,
        "address": profile.address,
        "phone_or_zalo": profile.phone_or_zalo,
        "main_product": profile.main_product,
        "est_team_size": profile.est_team_size,
        "supplier_brands": ", ".join(profile.supplier_brands) if profile.supplier_brands else None,
        "color_accent": profile.color_accent,
        "facebook": profile.facebook,
    }
    profile_summary = ", ".join(
        f"{k}={v!r}" for k, v in profile_fields.items() if v is not None
    )

    prompt = (
        f"Dealer đang xem card xác nhận thông tin cá nhân.\n"
        f"Profile hiện tại: {profile_summary}\n\n"
        f"Dealer nói: \"{message}\"\n\n"
        f"Dealer có đang muốn SỬA/ĐỔI thông tin nào không?\n"
        f"- Nếu CÓ: trả JSON duy nhất {{\"field\": \"<tên field>\", \"value\": \"<giá trị mới>\"}}\n"
        f"  Field phải là 1 trong: owner_name, dealer_name, address, phone_or_zalo, "
        f"main_product, est_team_size, color_accent, facebook\n"
        f"- Nếu KHÔNG phải sửa: trả {{\"field\": null}}\n\n"
        f"CHỈ trả JSON, KHÔNG giải thích."
    )

    try:
        response = client.chat_fast(
            system_prompt="Bạn là parser. Chỉ trả JSON.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=128,
        )
        if not response:
            return None

        # Extract JSON from response
        text = response.strip()
        # Handle markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        field = data.get("field")
        value = data.get("value")

        if field and value and isinstance(field, str):
            # Validate field name
            valid_fields = {
                "owner_name", "dealer_name", "address", "phone_or_zalo",
                "main_product", "est_team_size", "color_accent", "facebook",
                "business_model_signal", "brandkit_consent", "supplier_brands",
            }
            if field in valid_fields:
                return (field, str(value).strip())

    except (json.JSONDecodeError, Exception) as e:
        logger.debug("LLM edit parse fail: %s", e)

    return None

