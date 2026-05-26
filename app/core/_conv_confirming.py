"""CONFIRMING + DONE stage handlers — Phase 6 R2 refactor.

Refer:
- F2A.1 stage CONFIRMING/DONE
- F2A.7 sanity check 5-point
- 1A § 6 — confirmation card + edit handler
- 1A § 7 — closing template + local hook
"""
from __future__ import annotations

import logging

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


def handle_confirming(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> str:
    """Stage CONFIRMING: dealer xác nhận card."""
    intent = detect_intent(message)

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
        return _handle_edit(session, profile, message)

    if intent == Intent.REFUSAL:
        session.confirmation_status = ConfirmationStatus.PENDING
        session.stage = Stage.DONE
        mark_session_closed(session)
        return render_soft_end_closing()

    # Re-prompt
    return "Anh duyệt OK / sửa gì giúp em ạ?"


def handle_done() -> str:
    """Stage DONE: session đóng, chỉ trả message thông báo."""
    return (
        "Em đã chốt thông tin của anh rồi ạ. Em hẹn anh trên Zalo nhé — "
        "bộ thương hiệu + kế hoạch nền tảng số em gửi trong ít giờ tới."
    )


def enter_confirming(profile: DealerProfileRaw) -> str:
    """Render card khi vào CONFIRMING."""
    return (
        "Em đã ghi nhận đủ thông tin rồi ạ. Anh xem giúp em qua card này nhé:\n\n"
        + render_card(profile)
    )


def _handle_edit(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
) -> str:
    """Phase 3 R9: parse edit command qua regex."""
    parsed = parse_edit_command(message)
    if parsed:
        field, new_value = parsed
        if hasattr(profile, field):
            setattr(profile, field, new_value)
            logger.info(
                "Edit applied: session=%s field=%s value=%r",
                session.session_id, field, new_value,
            )
            # Re-render card với data mới
            return (
                f"Dạ em đã cập nhật {field} thành {new_value!r} rồi ạ. "
                f"Em hiển thị lại card mình cùng check nhé:\n\n"
                + render_card(profile)
            )
        else:
            logger.warning("Edit parsed field không có trong profile: %s", field)
    # Parse fail / field không tồn tại → ask dealer ghi rõ
    return (
        "Dạ anh ghi rõ giúp em — sửa phần nào, thành gì ạ? "
        "(Vd: 'sửa SĐT thành 0901234567', 'tên là Vinh', "
        "'đổi địa chỉ thành Quận 5')"
    )
