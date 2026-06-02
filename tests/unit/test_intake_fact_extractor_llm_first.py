from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.llm.intake_fact_extractor import FactExtractorError, extract_intake_facts
from app.models.schema import DealerProfileRaw


def _client(raw):
    client = MagicMock()
    client.extract_quality.return_value = raw
    return client


def test_extract_intake_facts_validates_structured_output():
    client = _client(
        {
            "facts": [
                {
                    "field": "owner_name",
                    "value": "Hùng",
                    "evidence": "anh tên Hùng",
                    "confidence": "high",
                    "is_correction": False,
                },
                {
                    "field": "dealer_name",
                    "value": "Solar Hùng Phát",
                    "evidence": "cửa hàng Solar Hùng Phát",
                    "confidence": "high",
                    "is_correction": False,
                },
            ],
            "uncertainty_notes": [],
        }
    )

    facts = extract_intake_facts(
        history_text="dealer: anh tên Hùng, cửa hàng Solar Hùng Phát",
        current_profile=DealerProfileRaw(),
        user_message="anh tên Hùng, cửa hàng Solar Hùng Phát",
        client=client,
    )

    assert [fact.field for fact in facts.facts] == ["owner_name", "dealer_name"]
    call = client.extract_quality.call_args.kwargs
    assert call["tool_name"] == "extract_linh_intake_facts"
    assert "không hard-code địa danh" in call["system_prompt"].lower()
    assert "confidence=\"low\"" in call["system_prompt"]
    assert "hỏi xác nhận" in call["system_prompt"].lower()


def test_extract_intake_facts_invalid_field_raises():
    client = _client(
        {
            "facts": [
                {
                    "field": "province",
                    "value": "Hà Nội",
                    "evidence": "Hà Nội",
                    "confidence": "high",
                    "is_correction": False,
                }
            ]
        }
    )

    with pytest.raises(FactExtractorError):
        extract_intake_facts(
            history_text="dealer: Hà Nội",
            current_profile=DealerProfileRaw(),
            user_message="Hà Nội",
            client=client,
        )


def test_extract_intake_facts_prompt_resolves_context_references_and_optional_skips():
    client = _client(
        {
            "facts": [
                {
                    "field": "supplier_brands",
                    "value": "Hòa Phát, Việt Nhật",
                    "evidence": "bot vừa gợi ý Hòa Phát, Việt Nhật; dealer nói 2 hãng đó",
                    "confidence": "high",
                    "is_correction": False,
                }
            ],
            "resolved_optional_slots": ["3.2"],
        }
    )

    facts = extract_intake_facts(
        history_text="bot: Anh dùng Hòa Phát hay Việt Nhật? | dealer: anh xài 2 hãng đó",
        current_profile=DealerProfileRaw(),
        user_message="anh xài 2 hãng đó",
        current_focus_slot="2.4",
        client=client,
    )

    assert facts.facts[0].value == "Hòa Phát, Việt Nhật"
    assert facts.resolved_optional_slots == ["3.2"]
    call = client.extract_quality.call_args.kwargs
    assert '"2 hãng đó"' in call["system_prompt"]
    assert "Slot đang được ưu tiên hỏi:\n2.4" in call["conversation_text"]
