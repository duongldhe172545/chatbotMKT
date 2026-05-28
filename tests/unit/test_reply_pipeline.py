"""Tests for the central reply pipeline adapter."""
from __future__ import annotations

from app.core.reply_pipeline import (
    CustomerSignal,
    ReplyPlan,
    analyze_turn,
    compose_and_validate_reply,
    validate_reply,
)
from app.core._conv_helpers import get_slot_question_for_attempt
from app.core.session import create_session
from app.models.enums import Stage
from app.models.schema import DealerProfileRaw


def _asking_session(slot: str = "1.2"):
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = slot
    return session


class TestTurnAnalyzer:
    def test_angry_message_is_not_data_answer(self):
        session = _asking_session("1.2")
        analysis = analyze_turn("mẹ mày", session, DealerProfileRaw(), Stage.ASKING)
        assert analysis.signal == CustomerSignal.ANGRY

    def test_wtf_is_joking_or_testing(self):
        session = _asking_session("1.2")
        analysis = analyze_turn("wtf??", session, DealerProfileRaw(), Stage.ASKING)
        assert analysis.signal in {CustomerSignal.JOKING_TESTING, CustomerSignal.ANGRY}

    def test_alo_is_joking_or_testing(self):
        session = _asking_session("1.1")
        analysis = analyze_turn("a lô a lô", session, DealerProfileRaw(), Stage.ASKING)
        assert analysis.signal == CustomerSignal.JOKING_TESTING

    def test_normal_slot_answer_defaults_to_data_answer(self):
        session = _asking_session("2.1")
        analysis = analyze_turn("bên anh mạnh nhất là nhôm kính", session, DealerProfileRaw(), Stage.ASKING)
        assert analysis.signal == CustomerSignal.DATA_ANSWER


class TestReplyComposerValidator:
    def test_bad_address_clarify_for_abuse_is_replaced(self):
        session = _asking_session("1.2")
        profile = DealerProfileRaw()
        raw = "Dạ mẹ mày thuộc tỉnh/thành nào anh nhỉ? Em cần ghi rõ để hỗ trợ đúng khu vực ạ."

        composed = compose_and_validate_reply(
            raw,
            message="mẹ mày",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "mẹ mày thuộc tỉnh" not in composed.text.lower()
        assert "khó chịu" in composed.text.lower()
        assert composed.repaired is True

    def test_question_only_retry_gets_customer_ack(self):
        session = _asking_session("2.1")
        profile = DealerProfileRaw()
        raw = "Anh chọn 1 cái mạnh nhất cho em là OK ạ — vd 'nhôm kính', 'cửa cuốn', 'tủ bếp'."

        composed = compose_and_validate_reply(
            raw,
            message="chịu đấy",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert composed.text.startswith("Em hiểu anh đang thử em")
        assert raw in composed.text

    def test_banned_name_praise_is_repaired(self):
        session = _asking_session("1.2")
        profile = DealerProfileRaw(owner_name="Dương", dealer_name="Nhôm kính Dương Đẹp Trai")
        raw = (
            'Chào anh Dương, cái tên "Nhôm kính Dương Đẹp Trai" nghe rất ấn tượng '
            "và dễ nhớ với khách hàng.\n\nCho em xin địa chỉ cửa hàng mình nha?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="anh tên Dương, cửa hàng Nhôm kính Dương Đẹp Trai",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "cái tên" not in composed.text.lower()
        assert "nghe rất" not in composed.text.lower()
        assert "Cho em xin địa chỉ" in composed.text
        assert composed.repaired is True

    def test_unsupported_local_claim_is_repaired(self):
        session = _asking_session("1.3")
        profile = DealerProfileRaw(address="Ecopark, Hưng Yên", province="Hưng Yên")
        raw = (
            "Vâng, Ecopark là khu vực có tốc độ phát triển hạ tầng rất nhanh, "
            "nhu cầu về cửa và nội thất tại đây luôn rất tiềm năng.\n\n"
            "Anh cho em xin số liên hệ chính ạ?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="cửa hàng ở Ecopark Hưng Yên",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "hạ tầng rất nhanh" not in composed.text
        assert composed.text.startswith("Em ghi nhận cửa hàng mình ở Ecopark, Hưng Yên rồi")
        assert "Anh cho em xin số liên hệ" in composed.text
        assert composed.repaired is True

    def test_validator_flags_more_than_one_user_question(self):
        session = _asking_session("1.1")
        profile = DealerProfileRaw()
        analysis = analyze_turn("anh tên Tuấn", session, profile, Stage.ASKING)
        plan = ReplyPlan(analysis=analysis, raw_reply="")

        issues = validate_reply(
            "Anh tên gì ạ? Cửa hàng mình tên gì ạ?",
            plan,
            session,
            profile,
        )

        assert any(i.code == "too_many_questions" for i in issues)

    def test_validator_flags_asking_filled_current_slot(self):
        session = _asking_session("1.1")
        profile = DealerProfileRaw(owner_name="Tuấn", dealer_name="Tủ bếp Tuấn Cường")
        analysis = analyze_turn("anh tên Tuấn", session, profile, Stage.ASKING)
        plan = ReplyPlan(analysis=analysis, raw_reply="")

        repeated_current_question = get_slot_question_for_attempt("1.1", session)
        issues = validate_reply(repeated_current_question or "", plan, session, profile)

        assert any(i.code == "asks_filled_slot" for i in issues)
