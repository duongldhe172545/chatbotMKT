from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import reset_settings
from app.core.conversation import handle_message
from app.core.session import create_session
from app.models.enums import Stage
from app.models.schema import DealerProfileRaw


@pytest.fixture(autouse=True)
def reset_config_cache():
    reset_settings()
    yield
    reset_settings()


def _client(*, planner_raw=None, legacy_extract=None):
    client = MagicMock()
    client.extract_quality.return_value = planner_raw or {}
    client.extract_fast.return_value = legacy_extract or {}
    client.chat_fast.return_value = "Dạ em note."
    client.chat_quality.return_value = "Dạ em note."
    return client


def _asking_session(slot: str = "1.1"):
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = slot
    return session


def test_legacy_engine_keeps_existing_behavior(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "legacy")
    reset_settings()
    client = _client(
        planner_raw={"assistant_reply": "planner"},
        legacy_extract={"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"},
    )
    session = _asking_session("1.1")
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session, profile, "anh Tùng cửa hàng Nhôm Kính Thanh Tùng", client
    )

    assert profile.owner_name == "Tùng"
    assert session.current_slot == "1.2"
    client.extract_quality.assert_not_called()
    assert reply


def test_shadow_engine_returns_legacy_reply_and_runs_planner(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "planner_shadow")
    reset_settings()
    client = _client(
        planner_raw={
            "move": "continue_intake",
            "facts": [{"field": "owner_name", "value": "Tùng", "evidence": "Tùng", "confidence": "high"}],
            "assistant_reply": "planner reply",
        },
        legacy_extract={"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"},
    )
    session = _asking_session("1.1")
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session, profile, "anh Tùng cửa hàng Nhôm Kính Thanh Tùng", client
    )

    assert profile.dealer_name == "Nhôm Kính Thanh Tùng"
    assert session.current_slot == "1.2"
    client.extract_quality.assert_called_once()
    assert "planner reply" not in reply


def test_planner_engine_handles_multi_field_turn(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "planner")
    reset_settings()
    client = _client(
        planner_raw={
            "move": "continue_intake",
            "facts": [
                {"field": "owner_name", "value": "Hùng", "evidence": "Anh tên Hùng", "confidence": "high"},
                {"field": "dealer_name", "value": "Hùng Phát", "evidence": "Hùng Phát", "confidence": "high"},
                {"field": "address", "value": "Cầu Giấy", "evidence": "Cầu Giấy", "confidence": "high"},
                {
                    "field": "main_product",
                    "value": "cửa nhôm Xingfa và cửa cuốn Austdoor",
                    "evidence": "chuyên Xingfa với Austdoor",
                    "confidence": "high",
                },
            ],
            "next_focus_fields": ["phone_or_zalo"],
            "assistant_reply": "Dạ em ghi được tên, khu vực và sản phẩm chính rồi. Anh cho em xin số Zalo nhé?",
        },
    )
    session = _asking_session("1.1")
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session,
        profile,
        "Anh tên Hùng, cửa hàng Hùng Phát ở Cầu Giấy, chuyên Xingfa với Austdoor",
        client,
    )

    assert profile.owner_name == "Hùng"
    assert profile.dealer_name == "Hùng Phát"
    assert profile.address == "Cầu Giấy"
    assert profile.main_product == "cửa nhôm Xingfa và cửa cuốn Austdoor"
    assert session.current_slot == "1.3"
    assert "số Zalo" in reply
    client.extract_fast.assert_not_called()


def test_planner_invalid_output_falls_back_to_legacy(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "planner")
    reset_settings()
    client = _client(
        planner_raw={"move": "continue_intake", "facts": [], "assistant_reply": ""},
        legacy_extract={"owner_name": "Tùng", "dealer_name": "Nhôm Kính Thanh Tùng"},
    )
    session = _asking_session("1.1")
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(
        session, profile, "anh Tùng cửa hàng Nhôm Kính Thanh Tùng", client
    )

    assert profile.owner_name == "Tùng"
    assert session.current_slot == "1.2"
    assert reply


def test_planner_engine_keeps_consent_slot_on_legacy(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "planner")
    reset_settings()
    client = _client(
        planner_raw={"assistant_reply": "planner"},
        legacy_extract={"brandkit_consent": "yes"},
    )
    session = _asking_session("4.0")
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(session, profile, "ok em làm đi", client)

    assert profile.brandkit_consent == "yes"
    assert session.current_slot == "4.1"
    client.extract_quality.assert_not_called()
    assert reply


def test_planner_engine_confirms_pending_address(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "planner")
    reset_settings()
    client = _client(
        planner_raw={
            "move": "continue_intake",
            "facts": [],
            "next_focus_fields": ["phone_or_zalo"],
            "assistant_reply": "Dạ em ghi Gia Lâm, Hà Nội rồi ạ. Anh cho em xin số Zalo để gửi bộ thương hiệu nhé?",
        },
    )
    session = _asking_session("1.2")
    session.pending_address_text = "Gia Lâm"
    session.pending_address_canonical = "Gia Lâm, Hà Nội"
    profile = DealerProfileRaw()

    reply, session, profile = handle_message(session, profile, "ờ e", client)

    assert profile.address == "Gia Lâm, Hà Nội"
    assert profile.province == "Hà Nội"
    assert profile.district is None
    assert session.pending_address_text is None
    assert session.pending_address_canonical is None
    assert session.current_slot == "1.3"
    assert "số Zalo" in reply
    client.extract_fast.assert_not_called()
