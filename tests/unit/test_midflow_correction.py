"""Tests for anytime correction while the bot is asking another slot."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.core.conversation import handle_message
from app.core.session import create_session
from datetime import datetime, timezone

from app.models.enums import Flag, Stage
import pytest
from app.models.schema import DealerProfileRaw


@pytest.fixture(autouse=True)
def force_legacy_engine(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "legacy")
    from app.config import reset_settings
    reset_settings()
    yield
    reset_settings()


def _mock_client():
    client = MagicMock()
    client.extract_fast.return_value = {}

    def extract_quality_side_effect(*args, **kwargs):
        fast_res = client.extract_fast() or {}
        if isinstance(fast_res, dict) and "facts" in fast_res:
            return fast_res
        facts_list = []
        if isinstance(fast_res, dict):
            for k, v in fast_res.items():
                facts_list.append({
                    "field": k,
                    "value": v,
                    "evidence": f"extracted {k}",
                    "confidence": "high",
                    "is_correction": False
                })
        return {"facts": facts_list}

    client.extract_quality.side_effect = extract_quality_side_effect
    client.chat_fast.side_effect = Exception("force fallback")
    client.chat_quality.side_effect = Exception("force fallback")
    return client


def test_address_correction_updates_previous_address_while_asking_phone():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "1.3"
    profile = DealerProfileRaw(address="Ecopark Hưng Yên", province="Hưng Yên")

    reply, session, profile = handle_message(
        session,
        profile,
        "à nhầm, ở âu sừn pắc chứ",
        _mock_client(),
    )

    assert profile.address == "Ocean Park, Gia Lâm, Hà Nội"
    assert profile.province == "Hà Nội"
    assert profile.district == "Gia Lâm"
    assert "Ocean Park" in reply
    assert session.current_slot == "1.3"
    assert "sửa lại địa chỉ" in reply.lower()
    assert "số" in reply.lower() or "zalo" in reply.lower()


def test_business_model_answer_derives_business_dealer_type():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.2"
    profile = DealerProfileRaw(main_product="cửa thép")

    reply, session, profile = handle_message(
        session,
        profile,
        "anh bán thôi em",
        _mock_client(),
    )

    assert profile.business_model_signal == "bán thôi"
    assert profile.dealer_type == "dai_ly"
    assert session.current_slot == "2.3"
    assert "bảo hành" not in reply.lower()


def test_business_model_data_suppresses_tam_su_misclassification():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.2"
    profile = DealerProfileRaw(main_product="cửa thép")
    client = _mock_client()
    client.extract_fast.return_value = {"business_model_signal": "ban thoi"}

    from app.models.enums import Intent
    import app.core._conv_asking as asking

    original_classifier = asking.classify_intent_layer2
    asking.classify_intent_layer2 = lambda *args, **kwargs: (Intent.TAM_SU, "HIGH")
    try:
        reply, session, profile = handle_message(
            session,
            profile,
            "anh ban thoi em",
            client,
        )
    finally:
        asking.classify_intent_layer2 = original_classifier

    assert profile.business_model_signal == "bán thôi"
    assert profile.dealer_type == "dai_ly"
    assert session.current_slot == "2.3"
    assert "Phân phối thuần" in reply


def test_business_model_short_llm_value_is_normalized_from_message():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.2"
    profile = DealerProfileRaw(main_product="cửa thép")
    client = _mock_client()
    client.extract_fast.return_value = {"business_model_signal": "ban"}

    reply, session, profile = handle_message(
        session,
        profile,
        "anh ban thoi em",
        client,
    )

    assert profile.business_model_signal == "bán thôi"
    assert profile.dealer_type == "dai_ly"
    assert "Phân phối thuần" in reply


def test_supplier_brand_correction_replaces_old_brand_mid_flow():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.5"
    profile = DealerProfileRaw(supplier_brands=["Koffman", "Alumac"])

    reply, session, profile = handle_message(
        session,
        profile,
        "alumax em oi",
        _mock_client(),
    )

    assert profile.supplier_brands == ["Koffman", "Alumax"]
    assert session.current_slot == "2.5"
    assert "sửa lại hãng nhập" in reply.lower()
    assert "Alumac" not in reply


def test_supplier_brand_correction_replaces_explicit_wrong_brand():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.6"
    profile = DealerProfileRaw(supplier_brands=["Koffman", "Alumac"])

    reply, session, profile = handle_message(
        session,
        profile,
        "ý là alumax chứ không phải alumac",
        _mock_client(),
    )

    assert profile.supplier_brands == ["Koffman", "Alumax"]
    assert session.current_slot == "2.6"
    assert "sửa lại hãng nhập" in reply.lower()
    assert "Alumac" not in reply


def test_supplier_brand_append_keeps_existing_brands_while_asking_next_slot():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.5"
    profile = DealerProfileRaw(supplier_brands=["Titadoor", "Mitadoor"])

    reply, session, profile = handle_message(
        session,
        profile,
        "có austdoor nữa",
        _mock_client(),
    )

    assert profile.supplier_brands == ["Titadoor", "Mitadoor", "Austdoor"]
    assert session.current_slot == "2.5"
    assert "sửa lại hãng nhập" in reply.lower()


def test_supplier_brand_correction_in_slot_2_4_keeps_customer_segment_question():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.4"
    profile = DealerProfileRaw(supplier_brands=["Austdoor", "TitaDo", "MitaDo"])

    reply, session, profile = handle_message(
        session,
        profile,
        "titadoor với mitadoor em ơi",
        _mock_client(),
    )

    assert profile.supplier_brands == ["Austdoor", "Titadoor", "Mitadoor"]
    assert session.current_slot == "2.4"
    assert "khách" in reply.lower()
    assert "nhà dân" in reply.lower() or "dự án" in reply.lower()


def test_negative_customer_storage_is_acknowledged_as_data():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "3.2"
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session,
        profile,
        "anh khong luu luon",
        _mock_client(),
    )

    assert profile.customer_storage_method == "không lưu"
    assert session.current_slot == "3.3"
    assert "khách cũ chưa được lưu" in reply.lower()
    assert "mình tiếp tục nhé" not in reply.lower()


def test_color_suggestion_request_gets_suggested_color_without_skipping():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "4.2"
    profile = DealerProfileRaw(main_product="cửa thép", main_category="cua_thep")

    reply, session, profile = handle_message(
        session,
        profile,
        "em gợi ý cho anh đi",
        _mock_client(),
    )

    assert profile.color_accent == "xanh đen phối ghi bạc"
    assert session.current_slot == "4.2"
    assert "xanh đen phối ghi bạc" in reply
    assert reply.count("?") <= 1


def test_brandkit_soft_no_then_affirmative_updates_to_yes():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "4.0"
    profile = DealerProfileRaw()
    client = _mock_client()
    client.extract_fast.return_value = {"brandkit_consent": "no"}

    reply, session, profile = handle_message(
        session,
        profile,
        "anh không thèm",
        client,
    )

    assert session.current_slot == "4.0"
    assert profile.brandkit_consent is None
    assert "không ép" in reply.lower() or "làm thử" in reply.lower()

    client.extract_fast.return_value = {}
    reply, session, profile = handle_message(
        session,
        profile,
        "ừ rồi",
        client,
    )

    assert profile.brandkit_consent == "yes"
    assert session.stage == Stage.ASKING
    assert session.current_slot == "4.1"
    assert "logo" in reply.lower()


def test_no_customer_pain_and_self_warranty_get_direct_acks():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "3.3"
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session,
        profile,
        "không khó tí nào",
        _mock_client(),
    )

    assert profile.customer_pain == "không có vướng mắc lớn"
    assert session.current_slot == "3.4"
    assert "khá ổn" in reply.lower()
    assert reply.strip() != "."

    session.current_slot = "3.5"
    reply, session, profile = handle_message(
        session,
        profile,
        "anh tự lo hết",
        _mock_client(),
    )

    assert profile.warranty_responsibility_signal == "anh tự lo hết"
    assert "tự đứng ra xử lý" in reply.lower()


def test_customer_self_source_is_not_treated_as_worker_network():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "2.5"
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session,
        profile,
        "anh nổi tiếng nên khách tự tìm đến đông lắm",
        _mock_client(),
    )

    assert profile.primary_contact_channel == "anh nổi tiếng nên khách tự tìm đến đông lắm"
    assert "tự tìm đến" in reply.lower()
    assert "thợ giới thiệu" not in reply.lower()


def test_brandkit_consent_correction_after_done_reopens_card():
    session = create_session()
    session.stage = Stage.DONE
    session.closed_at = datetime.now(timezone.utc)
    session.flags.append(Flag.DEALER_DECLINED)
    session.skipped_slots.extend(["4.1", "4.2"])
    profile = DealerProfileRaw(
        owner_name="Phong",
        dealer_name="Cửa thép Phong Linh",
        brandkit_consent="no",
    )

    reply, session, profile = handle_message(
        session,
        profile,
        "anh có đồng ý nhận bộ thương hiệu mà",
        _mock_client(),
    )

    assert profile.brandkit_consent == "yes"
    assert session.stage == Stage.CONFIRMING
    assert session.closed_at is None
    assert Flag.DEALER_DECLINED not in session.flags
    assert "4.1" not in session.skipped_slots
    assert "nhận bộ thương hiệu thành Có" in reply
