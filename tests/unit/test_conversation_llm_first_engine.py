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


def _session():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "1.1"
    return session


def _client():
    client = MagicMock()
    client.extract_quality.return_value = {
        "facts": [
            {"field": "owner_name", "value": "Hùng", "evidence": "anh tên Hùng", "confidence": "high"},
            {"field": "dealer_name", "value": "Solar Hùng Phát", "evidence": "Solar Hùng Phát", "confidence": "high"},
            {"field": "main_product", "value": "cửa nhôm Xingfa", "evidence": "chuyên Xingfa", "confidence": "high"},
        ]
    }
    client.extract_fast.return_value = {}
    client.chat_quality.return_value = (
        "Dạ em ghi được thông tin anh Hùng và Solar Hùng Phát rồi. "
        "Anh cho em xin khu vực cửa hàng mình nhé?"
    )
    client.chat_fast.return_value = "legacy"
    return client


def test_llm_first_engine_bypasses_legacy_asking(monkeypatch):
    monkeypatch.setenv("CONVERSATION_ENGINE", "llm_first")
    reset_settings()
    legacy = MagicMock(side_effect=AssertionError("legacy ASKING should not run"))
    monkeypatch.setattr("app.core.conversation.handle_asking", legacy)
    session = _session()
    profile = DealerProfileRaw()
    client = _client()

    reply, session, profile = handle_message(
        session,
        profile,
        "Anh tên Hùng, cửa hàng Solar Hùng Phát, chuyên Xingfa",
        client,
    )

    legacy.assert_not_called()
    assert profile.owner_name == "Hùng"
    assert profile.dealer_name == "Solar Hùng Phát"
    assert profile.main_product == "cửa nhôm Xingfa"
    assert session.current_slot == "1.2"
    assert "khu vực" in reply
    client.chat_quality.assert_called_once()
