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

    def test_distribution_description_is_data_not_technical_escalation(self):
        session = _asking_session("2.4")
        analysis = analyze_turn(
            "anh sản xuất với phân phối cho đại lý khác thôi",
            session,
            DealerProfileRaw(),
            Stage.ASKING,
        )
        assert analysis.signal == CustomerSignal.DATA_ANSWER

    def test_short_distribution_installation_answer_is_data_after_slot_advance(self):
        session = _asking_session("2.3")
        analysis = analyze_turn("anh phân phối thi công", session, DealerProfileRaw(), Stage.ASKING)

        assert analysis.signal == CustomerSignal.DATA_ANSWER

    def test_cac_thu_is_not_misread_as_testing_bot(self):
        session = _asking_session("2.1")
        analysis = analyze_turn(
            "anh chuyên về các loại nhôm kính cửa các thứ",
            session,
            DealerProfileRaw(),
            Stage.ASKING,
        )

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

    def test_local_claim_repair_preserves_question_in_same_paragraph(self):
        session = _asking_session("1.2")
        profile = DealerProfileRaw(owner_name="Hương", dealer_name="Hương Tủ Bếp")
        raw = (
            "Dạ chị Hương ơi, Hà Đông là khu vực rất phát triển. "
            "Chị cho em xin tỉnh/thành và quận/huyện của cửa hàng mình nhé?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="chị ở Hà Đông",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "rất phát triển" not in composed.text
        assert "Chị cho em xin tỉnh/thành và quận/huyện" in composed.text
        assert composed.repaired is True

    def test_local_claim_repair_is_idempotent(self):
        session = _asking_session("1.2")
        profile = DealerProfileRaw(owner_name="Hương", dealer_name="Hương Tủ Bếp")
        raw = (
            "Dạ chị Hương ơi, Hà Đông là khu vực rất phát triển. "
            "Chị cho em xin tỉnh/thành và quận/huyện của cửa hàng mình nhé?"
        )

        first = compose_and_validate_reply(
            raw,
            message="chị ở Hà Đông",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )
        second = compose_and_validate_reply(
            first.text,
            message="chị ở Hà Đông",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert second.text == first.text

    def test_unsupported_team_praise_is_removed_without_losing_question(self):
        session = _asking_session("2.3")
        profile = DealerProfileRaw(owner_name="Hùng")
        raw = (
            "Anh Hùng ơi, bên mình vừa sản xuất vừa thi công thì chắc hẳn "
            "đội thợ phải rất chuyên nghiệp ạ. "
            "Anh cho em hỏi đội thợ bên mình có bao nhiêu người ạ?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="anh vừa sản xuất vừa thi công",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "chắc hẳn" not in composed.text.lower()
        assert "rất chuyên nghiệp" not in composed.text.lower()
        assert "đội thợ bên mình có bao nhiêu người" in composed.text
        assert composed.repaired is True

    def test_generic_process_praise_is_removed_without_losing_question(self):
        session = _asking_session("3.5")
        profile = DealerProfileRaw()
        raw = (
            "Bên anh lưu Excel như vậy là rất khoa học và chuyên nghiệp ạ. "
            "Nếu có bảo hành thì bên nào đứng ra xử lý anh?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="anh lưu bằng excel",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "rất khoa học" not in composed.text.lower()
        assert "bên nào đứng ra xử lý" in composed.text

    def test_name_praise_with_inserted_word_is_removed_when_it_invents_quality(self):
        session = _asking_session("1.2")
        profile = DealerProfileRaw(owner_name="Tuấn", dealer_name="Điện Mặt Trời Tuấn Tú")
        raw = (
            "Em chào anh Tuấn và cửa hàng Điện Mặt Trời Tuấn Tú ạ! "
            "Nghe tên là thấy chuyên nghiệp về năng lượng sạch rồi anh ha.\n\n"
            "Anh Tuấn cho em xin địa chỉ cửa hàng mình được không ạ?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="điện mặt trời tuấn tú",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "thấy chuyên nghiệp" not in composed.text.lower()
        assert "xin địa chỉ" in composed.text.lower()
        assert composed.repaired is True

    def test_thuong_hieu_does_not_count_as_ack_for_playful_invitation(self):
        session = _asking_session("1.3")
        profile = DealerProfileRaw(owner_name="Tuấn")
        raw = (
            "Em rất sẵn lòng hỗ trợ anh làm bộ thương hiệu số miễn phí cho "
            "cửa hàng mình. Em cảm ơn anh nhiều nhé."
        )

        composed = compose_and_validate_reply(
            raw,
            message="đi chơi với anh đi rồi anh cho",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert composed.text.startswith("Em hiểu anh đang thử em một chút.")

    def test_polite_boundary_sentence_ending_nhe_is_not_counted_as_question(self):
        session = _asking_session("1.3")
        profile = DealerProfileRaw(owner_name="Tuấn")
        raw = (
            "Anh Tuấn vui tính quá ạ. Em chỉ xin phép hỗ trợ mình qua đây thôi, "
            "còn phần cửa hàng em vẫn chăm kỹ cho anh nhé.\n\n"
            "Anh Tuấn cho em xin số điện thoại hoặc Zalo tiện liên hệ nha."
        )

        composed = compose_and_validate_reply(
            raw,
            message="đi chơi với anh đi rồi anh cho",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "em vẫn chăm kỹ cho anh nhé" in composed.text.lower()
        assert "số điện thoại hoặc zalo" in composed.text.lower()

    def test_supplier_confirmation_is_not_rewritten_as_address_clarification(self):
        session = _asking_session("1.3")
        profile = DealerProfileRaw(owner_name="Long")
        raw = "Dạ anh, ý anh là hãng Koffman đúng không ạ?"

        composed = compose_and_validate_reply(
            raw,
            message="anh nhập của Koffman là chính",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert composed.text == raw

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

    def test_validator_flags_semantic_question_without_question_mark(self):
        session = _asking_session("2.1")
        profile = DealerProfileRaw()
        analysis = analyze_turn("nhôm kính", session, profile, Stage.ASKING)
        plan = ReplyPlan(analysis=analysis, raw_reply="")

        issues = validate_reply(
            "Anh ơi, cửa hàng mình chuyên về những sản phẩm nào ạ\n\n"
            "Mình có sản phẩm nào là thế mạnh nhất không anh?",
            plan,
            session,
            profile,
        )

        assert any(i.code == "too_many_questions" for i in issues)

    def test_false_human_claim_is_removed(self):
        session = _asking_session("1.3")
        profile = DealerProfileRaw(owner_name="Cường")
        raw = (
            "Dạ em xin lỗi anh Cường ạ, có gì chưa phải mong anh bỏ qua. "
            "Em là Linh thật, không phải robot đâu ạ. "
            "Anh Cường cho em xin số Zalo nhé?"
        )

        composed = compose_and_validate_reply(
            raw,
            message="trả lời thô vậy",
            session=session,
            profile=profile,
            stage_before=Stage.ASKING,
        )

        assert "không phải robot" not in composed.text.lower()
        assert "Linh thật" not in composed.text
        assert "số Zalo" in composed.text

    def test_validator_flags_asking_filled_current_slot(self):
        session = _asking_session("1.1")
        profile = DealerProfileRaw(owner_name="Tuấn", dealer_name="Tủ bếp Tuấn Cường")
        analysis = analyze_turn("anh tên Tuấn", session, profile, Stage.ASKING)
        plan = ReplyPlan(analysis=analysis, raw_reply="")

        repeated_current_question = get_slot_question_for_attempt("1.1", session)
        issues = validate_reply(repeated_current_question or "", plan, session, profile)

        assert any(i.code == "asks_filled_slot" for i in issues)
