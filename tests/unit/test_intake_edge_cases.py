from __future__ import annotations

from unittest.mock import MagicMock

from app.core._conv_greeting import handle_greeting
from app.core.intake_edge_cases import (
    is_benefit_question,
    is_boundary_flirt_message,
    is_ping_message,
)
from app.core.session import create_session
from app.models.enums import Stage


def test_detects_benefit_question_without_treating_duoc_as_consent():
    assert is_benefit_question("anh được gì khi nhắn tin")
    assert is_benefit_question("nói chuyện với em thì anh nhận được gì")


def test_detects_ping_message():
    assert is_ping_message("alo alo")
    assert is_ping_message("a lô a lô")


def test_detects_playful_invitation_that_needs_work_boundary():
    assert is_boundary_flirt_message("đi chơi với anh đi rồi anh cho")
    assert is_boundary_flirt_message("đi cafe với anh không em")
    assert not is_boundary_flirt_message("hôm nay anh đi chơi với bạn")


def test_greeting_ping_does_not_advance_or_claim_dealer_is_ready():
    session = create_session()

    reply = handle_greeting(session, "alo alo", MagicMock())

    assert session.stage == Stage.GREETING
    assert "em nghe đây" in reply.lower()
    assert "bộ thương hiệu miễn phí" in reply.lower()
    assert "đã sẵn sàng" not in reply.lower()
    assert "tên cửa hàng" not in reply.lower()


def test_greeting_benefit_question_answers_then_asks_permission():
    session = create_session()

    reply = handle_greeting(session, "anh được gì khi nhắn tin", MagicMock())

    assert session.stage == Stage.GREETING
    assert "logo riêng" in reply.lower()
    assert "danh thiếp" in reply.lower()
    assert "video" in reply.lower()
    assert "miễn phí" in reply.lower()
    assert "tiếp tục được không anh" in reply.lower()
    assert "xin tên" not in reply.lower()
