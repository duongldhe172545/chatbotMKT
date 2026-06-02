from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.intake_planner import (
    PlannerError,
    handle_asking_with_planner,
    is_planner_eligible,
    plan_intake_turn,
)
from app.core.session import create_session
from app.models.enums import Stage
from app.models.schema import DealerProfileRaw


def _session():
    session = create_session()
    session.stage = Stage.ASKING
    session.current_slot = "1.1"
    return session


def _client(raw):
    client = MagicMock()
    client.extract_quality.return_value = raw
    return client


def test_plan_intake_turn_validates_llm_output():
    client = _client(
        {
            "move": "continue_intake",
            "facts": [
                {
                    "field": "owner_name",
                    "value": "Hùng",
                    "evidence": "Anh tên Hùng",
                    "confidence": "high",
                }
            ],
            "next_focus_fields": ["dealer_name"],
            "assistant_reply": "Dạ em ghi tên anh Hùng rồi ạ. Cửa hàng mình tên gì anh?",
        }
    )

    result = plan_intake_turn(_session(), DealerProfileRaw(), "Anh tên Hùng", client)

    assert result.facts[0].field == "owner_name"
    assert result.next_focus_fields == ["dealer_name"]
    client.extract_quality.assert_called_once()
    assert client.extract_quality.call_args.kwargs["tool_name"] == "plan_intake_turn"


def test_plan_intake_turn_empty_reply_raises():
    client = _client({"move": "continue_intake", "facts": [], "assistant_reply": ""})

    with pytest.raises(PlannerError):
        plan_intake_turn(_session(), DealerProfileRaw(), "Anh tên Hùng", client)


def test_handle_asking_with_planner_merges_facts_and_updates_focus():
    client = _client(
        {
            "move": "continue_intake",
            "facts": [
                {"field": "owner_name", "value": "Hùng", "evidence": "Hùng", "confidence": "high"},
                {"field": "dealer_name", "value": "Hùng Phát", "evidence": "Hùng Phát", "confidence": "high"},
                {"field": "address", "value": "Cầu Giấy", "evidence": "Cầu Giấy", "confidence": "high"},
            ],
            "next_focus_fields": ["phone_or_zalo"],
            "assistant_reply": "Dạ em ghi đủ tên và khu vực rồi. Anh cho em xin số Zalo nhé?",
        }
    )
    session = _session()
    profile = DealerProfileRaw()

    reply = handle_asking_with_planner(session, profile, "Anh Hùng, Hùng Phát, Cầu Giấy", client)

    assert profile.owner_name == "Hùng"
    assert profile.dealer_name == "Hùng Phát"
    assert profile.address == "Cầu Giấy"
    assert session.current_slot == "1.3"
    assert "số Zalo" in reply


def test_planner_accepts_pending_address_confirmation_before_llm_call():
    client = _client(
        {
            "move": "continue_intake",
            "facts": [],
            "next_focus_fields": ["phone_or_zalo"],
            "assistant_reply": "Dạ em ghi khu vực Gia Lâm, Hà Nội rồi ạ. Anh cho em xin số Zalo để gửi bộ thương hiệu nhé?",
        }
    )
    session = _session()
    session.current_slot = "1.2"
    session.pending_address_text = "Gia Lâm"
    session.pending_address_canonical = "Gia Lâm, Hà Nội"
    profile = DealerProfileRaw()

    reply = handle_asking_with_planner(session, profile, "ờ e", client)

    assert profile.address == "Gia Lâm, Hà Nội"
    assert profile.province == "Hà Nội"
    assert profile.district is None
    assert session.pending_address_text is None
    assert session.pending_address_canonical is None
    assert session.current_slot == "1.3"
    assert "số Zalo" in reply


def test_planner_eligible_allows_confusion_for_llm_first_chat():
    session = _session()

    assert is_planner_eligible(session, "là sao em")
