from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.core.llm_first_asking import handle_asking_llm_first
from app.core.session import create_session
from app.models.enums import Stage
from app.models.schema import DealerProfileRaw, HistoryMessage


def _session():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "1.1"
    return session


def _client(*, facts=None, reply="Dạ em ghi nhận rồi. Anh cho em xin số Zalo nhé?"):
    client = MagicMock()
    client.extract_quality.return_value = facts or {"facts": []}
    client.chat_quality.return_value = reply
    return client


def test_llm_first_extracts_facts_then_uses_conversation_brain_reply():
    client = _client(
        facts={
            "facts": [
                {"field": "owner_name", "value": "Hùng", "evidence": "anh tên Hùng", "confidence": "high"},
                {"field": "dealer_name", "value": "Solar Hùng Phát", "evidence": "Solar Hùng Phát", "confidence": "high"},
                {"field": "address", "value": "Gia Lâm, Hà Nội", "evidence": "ở Gia Lâm, Hà Nội", "confidence": "high"},
                {"field": "main_product", "value": "cửa nhôm Xingfa", "evidence": "chuyên Xingfa", "confidence": "high"},
            ]
        },
        reply="Dạ em ghi được thông tin anh Hùng rồi. Anh cho em xin số Zalo để gửi bộ thương hiệu nhé?",
    )
    session = _session()
    profile = DealerProfileRaw()

    reply = handle_asking_llm_first(
        session,
        profile,
        "Anh tên Hùng, cửa hàng Solar Hùng Phát ở Gia Lâm Hà Nội, chuyên Xingfa",
        client,
    )

    assert profile.owner_name == "Hùng"
    assert profile.dealer_name == "Solar Hùng Phát"
    assert profile.address == "Gia Lâm, Hà Nội"
    assert profile.main_product == "cửa nhôm Xingfa"
    assert session.current_slot == "1.3"
    assert "số Zalo" in reply
    client.chat_quality.assert_called_once()


def test_llm_first_passes_history_for_short_confirmation_context():
    session = _session()
    session.history.append(
        HistoryMessage(
            role="bot",
            content="Ý anh là khu Ocean Park, Gia Lâm đúng không ạ?",
            ts=datetime.now(timezone.utc),
        )
    )
    client = _client(reply="Dạ em hiểu là Ocean Park rồi ạ. Anh cho em xin số Zalo nhé?")

    handle_asking_llm_first(session, DealerProfileRaw(), "ờ em", client)

    prompt = client.chat_quality.call_args.kwargs["messages"][0]["content"]
    assert "Ocean Park" in prompt
    assert "ờ em" in prompt


def test_llm_first_empty_reply_uses_deterministic_next_question():
    client = _client(reply="")
    reply = handle_asking_llm_first(_session(), DealerProfileRaw(), "anh tên Hùng", client)

    assert "trục trặc" not in reply.lower()
    assert "tên anh" in reply.lower() or "tên cửa hàng" in reply.lower()


def test_llm_first_adapter_error_reply_is_not_shown_to_dealer():
    client = _client(
        reply="Dạ em xin lỗi, em đang gặp xíu trục trặc kỹ thuật. Anh thử nhắn lại em sau ít phút nhé ạ."
    )
    reply = handle_asking_llm_first(_session(), DealerProfileRaw(), "anh tên Hùng", client)

    assert "trục trặc" not in reply.lower()
    assert "kỹ thuật" not in reply.lower()
    assert "tên" in reply.lower()


def test_llm_first_repairs_bare_owner_vocative():
    client = _client(reply="Hưng ơi, em ghi nhận rồi. Anh cho em hỏi thêm về đội thợ nhé?")
    reply = handle_asking_llm_first(
        _session(),
        DealerProfileRaw(owner_name="Hưng"),
        "ok em",
        client,
    )

    assert reply.startswith("Anh Hưng ơi")


def test_llm_first_records_explicit_optional_skip_and_moves_on():
    session = _session()
    session.current_slot = "2.3"
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công và thương mại",
    )
    client = _client(
        facts={"facts": [], "resolved_optional_slots": ["2.3"]},
        reply="Không sao anh. Còn nguồn hàng chính bên mình thường lấy từ hãng nào ạ?",
    )

    handle_asking_llm_first(session, profile, "phần đội thợ anh chưa tiện chia sẻ", client)

    assert "2.3" in session.skipped_slots
    assert session.current_slot == "2.4"


def test_llm_first_records_contextual_consent_affirmative_without_asking_twice():
    session = _session()
    session.current_slot = "4.0"
    session.skipped_slots.extend([
        "2.3", "2.4", "2.5", "2.6",
        "3.1", "3.2", "3.3", "3.4", "3.5",
    ])
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công và thương mại",
    )
    client = _client(reply="Dạ, còn màu chủ đạo anh thích là màu gì ạ?")

    handle_asking_llm_first(session, profile, "ok em", client)

    assert profile.brandkit_consent == "yes"
    assert session.current_slot == "4.2"


def test_llm_first_smalltalk_does_not_extract_or_advance():
    session = _session()
    session.current_slot = "2.4"
    profile = DealerProfileRaw(owner_name="Hùng")
    client = _client(reply="unused")
    client.extract_fast.return_value = {"topic": "family", "severity": 1}
    client.chat_quality.return_value = "Em hiểu chuyện gia đình làm anh mệt. Khi tiện mình quay lại phần nguồn hàng nhé anh."

    reply = handle_asking_llm_first(
        session,
        profile,
        "vợ anh chán anh quá làm sao em",
        client,
    )

    client.extract_quality.assert_not_called()
    assert session.current_slot == "2.4"
    assert session.consecutive_tam_su == 1
    assert "gia đình" in reply


def test_llm_first_casual_chat_does_not_extract_or_advance():
    session = _session()
    session.current_slot = "2.4"
    profile = DealerProfileRaw(owner_name="HÃ¹ng")
    client = _client(reply="unused")
    client.extract_fast.return_value = {"topic": "other", "severity": 1}
    client.chat_quality.return_value = (
        "Em cÅ©ng váº«n á»•n anh HÃ¹ng áº¡. MÃ¬nh nÃ³i chuyá»‡n chÆ¡i tÃ­ cÅ©ng Ä‘Æ°á»£c, "
        "rá»“i lÃ¡t em xin phÃ©p quay láº¡i pháº§n nguá»“n hÃ ng nhÃ©."
    )

    reply = handle_asking_llm_first(
        session,
        profile,
        "em an com chua, noi chuyen choi ti",
        client,
    )

    client.extract_quality.assert_not_called()
    assert session.current_slot == "2.4"
    assert session.consecutive_tam_su == 1
    assert "anh HÃ¹ng" in reply


def test_llm_first_playful_invitation_keeps_boundary_and_returns_to_missing_field():
    session = _session()
    session.current_slot = "1.3"
    profile = DealerProfileRaw(
        owner_name="Tuấn",
        dealer_name="Điện Mặt Trời Tuấn Tú",
        address="Nam Đàn, Nghệ An",
    )
    client = _client(reply="unused")

    reply = handle_asking_llm_first(
        session,
        profile,
        "đi chơi với anh đi rồi anh cho",
        client,
    )

    client.extract_quality.assert_not_called()
    client.chat_quality.assert_not_called()
    assert session.current_slot == "1.3"
    assert "Anh Tuấn vui tính" in reply
    assert "số điện thoại hoặc Zalo" in reply


def test_llm_first_records_auto_logo_choices_without_reasking():
    session = _session()
    session.current_slot = "4.3"
    session.skipped_slots.extend([
        "2.3", "2.4", "2.5", "2.6",
        "3.1", "3.2", "3.3", "3.4", "3.5",
    ])
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm",
        business_model_signal="thi công",
        brandkit_consent="yes",
        color_accent="auto",
    )
    client = _client(reply="Dạ, em sẽ tự chọn viết tắt. Anh đã có slogan chưa ạ?")

    handle_asking_llm_first(session, profile, "em chọn cho anh đi", client)

    assert profile.logo_initials
    assert profile.logo_initials != "auto"
    assert session.current_slot == "4.4"


def test_llm_first_selects_concrete_color_when_dealer_is_unsure():
    session = _session()
    session.current_slot = "4.2"
    session.skipped_slots.extend([
        "2.3", "2.4", "2.5", "2.6",
        "3.1", "3.2", "3.3", "3.4", "3.5",
    ])
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm",
        business_model_signal="thi công",
        brandkit_consent="yes",
    )
    client = _client(reply="Em chốt xanh đậm phối ghi bạc nhé anh. Logo mình dùng viết tắt nào ạ?")

    handle_asking_llm_first(session, profile, "em chọn cho anh đi, anh không rành", client)

    assert profile.color_accent == "xanh đậm phối ghi bạc"
    assert session.current_slot == "4.3"


def test_llm_first_routes_defensive_question_to_mature_handler(monkeypatch):
    session = _session()
    profile = DealerProfileRaw()
    client = _client(reply="unused")
    legacy = MagicMock(
        return_value=(
            "Dạ KHÔNG lừa đảo, KHÔNG mất phí gì cả ạ. "
            "Mình tiếp tục được không anh?"
        )
    )
    monkeypatch.setattr("app.core._conv_asking.handle_asking", legacy)

    reply = handle_asking_llm_first(session, profile, "có lừa đảo không?", client)

    legacy.assert_called_once_with(session, profile, "có lừa đảo không?", client)
    client.extract_quality.assert_not_called()
    assert "KHÔNG lừa đảo" in reply


def test_llm_first_answers_benefit_question_without_extracting_or_advancing():
    session = _session()
    profile = DealerProfileRaw()
    client = _client(reply="unused")

    reply = handle_asking_llm_first(
        session,
        profile,
        "anh được gì khi nhắn tin",
        client,
    )

    client.extract_quality.assert_not_called()
    client.chat_quality.assert_not_called()
    assert session.current_slot == "1.1"
    assert "logo riêng" in reply.lower()
    assert "tiếp tục được không anh" in reply.lower()


def test_llm_first_asks_for_address_confirmation_when_location_is_incomplete():
    session = _session()
    session.current_slot = "1.2"
    profile = DealerProfileRaw(owner_name="Hương", dealer_name="Hương Tủ Bếp")
    client = _client(facts={"facts": []}, reply="unused")

    reply = handle_asking_llm_first(session, profile, "chị ở Hà Đông", client)

    assert profile.address is None
    assert "tỉnh/thành" in reply.lower()
    assert "quận/huyện" in reply.lower()
    assert "trục trặc" not in reply.lower()
    client.chat_quality.assert_not_called()


def test_llm_first_chat_exception_uses_intake_fallback_not_technical_error():
    session = _session()
    profile = DealerProfileRaw()
    client = _client(facts={"facts": []}, reply="unused")
    client.chat_quality.side_effect = RuntimeError("provider unavailable")

    reply = handle_asking_llm_first(session, profile, "anh tên Hùng", client)

    assert "trục trặc" not in reply.lower()
    assert "lỗi kết nối" not in reply.lower()
    assert "tên" in reply.lower()


def test_llm_first_does_not_ack_invalid_phone_as_saved():
    session = _session()
    session.current_slot = "1.3"
    profile = DealerProfileRaw(
        owner_name="Long",
        dealer_name="Cửa gỗ Long Trọc",
        address="Đô Lương, Nghệ An",
    )
    client = _client(
        facts={
            "facts": [
                {
                    "field": "phone_or_zalo",
                    "value": "0123811291",
                    "evidence": "0123811291",
                    "confidence": "high",
                }
            ]
        },
        reply="Dạ em cảm ơn anh Long đã cho em xin số điện thoại ạ!",
    )

    reply = handle_asking_llm_first(session, profile, "0123811291", client)

    assert profile.phone_or_zalo is None
    assert "chưa đúng định dạng" in reply
    assert "chưa dám lưu" in reply
    client.chat_quality.assert_not_called()


def test_llm_first_confirms_phonetic_supplier_brand_before_persisting():
    session = _session()
    session.current_slot = "1.3"
    profile = DealerProfileRaw(owner_name="Long")
    client = _client(reply="unused")

    reply = handle_asking_llm_first(
        session,
        profile,
        "anh nhập của Koffman là chính",
        client,
        raw_message="anh nhập của cốp men là chính",
    )

    assert profile.supplier_brands == []
    assert "Koffman đúng không" in reply
    client.extract_quality.assert_not_called()
    client.chat_quality.assert_not_called()


def test_llm_first_keeps_next_question_on_missing_required_field():
    session = _session()
    session.current_slot = "1.3"
    profile = DealerProfileRaw(
        owner_name="Long",
        dealer_name="Cửa gỗ Long Trọc",
        address="Đô Lương, Nghệ An",
    )
    client = _client(
        facts={
            "facts": [
                {
                    "field": "supplier_brands",
                    "value": "Koffman",
                    "evidence": "anh nhập Koffman là chính",
                    "confidence": "high",
                }
            ]
        },
        reply="Anh Long cho em hỏi khách bên mình chủ yếu là nhà dân hay công trình ạ?",
    )

    reply = handle_asking_llm_first(session, profile, "anh nhập Koffman là chính", client)

    assert profile.supplier_brands == ["Koffman"]
    assert "số điện thoại hoặc Zalo" in reply
