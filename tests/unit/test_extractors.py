"""Test extractor runner + tool schemas. Refer F2B.2."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.llm.extractors import (
    SLOT_TOOL_SCHEMAS,
    extract_slot,
)
from app.llm.extractors.schemas import (
    TOOL_SLOT_1_1,
    TOOL_SLOT_1_2,
    TOOL_SLOT_4_0,
    get_tool_schema,
    list_phase_1_slot_ids,
)
from app.models.enums import AddressForm, DealerType


# ============================================================
# Schema definitions integrity
# ============================================================


class TestSchemas:
    def test_phase_2_has_16_schemas(self):
        """Phase 2: 16 slot có extractor (slot 4.1 THÔNG BÁO không có)."""
        assert len(SLOT_TOOL_SCHEMAS) == 16
        expected = {
            "1.1", "1.2", "1.3",
            "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",
            "3.1", "3.2", "3.3", "3.4", "3.5",
            "4.0", "4.2",
        }
        assert set(SLOT_TOOL_SCHEMAS.keys()) == expected

    def test_slot_4_1_is_thong_bao_no_extractor(self):
        """Slot 4.1 = THÔNG BÁO, không có extractor (refer GLOSSARY)."""
        assert "4.1" not in SLOT_TOOL_SCHEMAS

    @pytest.mark.parametrize("tool", [TOOL_SLOT_1_1, TOOL_SLOT_1_2, TOOL_SLOT_4_0])
    def test_tool_has_required_keys(self, tool):
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]

    def test_slot_1_1_has_2_fields(self):
        """Slot 1.1 multi-field: owner_name + dealer_name."""
        props = TOOL_SLOT_1_1["input_schema"]["properties"]
        assert "owner_name" in props
        assert "dealer_name" in props
        assert len(props) == 2

    def test_slot_1_2_has_address_and_signal(self):
        props = TOOL_SLOT_1_2["input_schema"]["properties"]
        assert "address" in props
        assert "local_dominance_signal" in props

    def test_slot_4_0_consent_enum(self):
        """brandkit_consent phải có enum yes/no."""
        prop = TOOL_SLOT_4_0["input_schema"]["properties"]["brandkit_consent"]
        # Enum chứa "yes", "no", có thể có None (cho Gemini nullable)
        assert "yes" in prop["enum"]
        assert "no" in prop["enum"]

    def test_all_schemas_have_maxlength(self):
        """Chống prompt injection bằng input dài — maxLength bắt buộc cho string field."""
        for slot_id, tool in SLOT_TOOL_SCHEMAS.items():
            for field_name, prop in tool["input_schema"]["properties"].items():
                # Field type string nên có maxLength
                if "string" in str(prop.get("type", [])):
                    # enum field không cần maxLength (enum đã cố định values)
                    if "enum" in prop:
                        continue
                    assert "maxLength" in prop, \
                        f"Slot {slot_id} field {field_name} thiếu maxLength"

    def test_no_required_at_top_level(self):
        """Field optional (required=[]) — LLM trả null nếu dealer chưa cho."""
        for tool in SLOT_TOOL_SCHEMAS.values():
            assert tool["input_schema"].get("required") == []


# ============================================================
# Helper functions
# ============================================================


class TestHelpers:
    def test_get_tool_schema_valid(self):
        schema = get_tool_schema("1.1")
        assert schema is not None
        assert schema["name"] == "extract_slot_1_1"

    def test_get_tool_schema_unknown(self):
        """Slot 4.1 THÔNG BÁO không có extractor → None."""
        assert get_tool_schema("4.1") is None
        assert get_tool_schema("99.99") is None

    def test_list_phase_1_slot_ids(self):
        """Phase 2: 16 slot có extractor."""
        ids = list_phase_1_slot_ids()
        assert len(ids) == 16
        assert "1.1" in ids
        assert "4.0" in ids
        assert "3.3" in ids
        assert "4.1" not in ids  # THÔNG BÁO, không có extractor


# ============================================================
# extract_slot runner — mock LLMClient
# ============================================================


def _make_mock_client(extract_return: dict | None = None):
    """Tạo mock LLMClient với extract_fast return mock dict."""
    client = MagicMock()
    client.extract_fast.return_value = extract_return or {}
    return client


class TestExtractSlot:
    def test_unknown_slot_returns_empty(self):
        """Slot không có schema (vd 4.1 THÔNG BÁO) → return {}."""
        client = _make_mock_client()
        result = extract_slot("4.1", "ok", client)
        assert result == {}
        # KHÔNG gọi LLM
        client.extract_fast.assert_not_called()

    def test_empty_message_returns_empty(self):
        client = _make_mock_client()
        assert extract_slot("1.1", "", client) == {}
        assert extract_slot("1.1", "   ", client) == {}
        client.extract_fast.assert_not_called()

    def test_extract_slot_1_1_full_fill(self):
        """Slot 1.1 đầy đủ 2 field → both validated."""
        client = _make_mock_client({
            "owner_name": "Tùng",
            "dealer_name": "Nhôm Kính Thanh Tùng",
        })
        result = extract_slot("1.1", "anh Tùng cửa hàng Nhôm Kính Thanh Tùng", client)
        assert result == {
            "owner_name": "Tùng",
            "dealer_name": "Nhôm Kính Thanh Tùng",
        }
        client.extract_fast.assert_called_once()

    def test_extract_slot_1_1_partial(self):
        """Slot 1.1 dealer chỉ cho owner_name → dealer_name = null."""
        client = _make_mock_client({
            "owner_name": "Tùng",
            "dealer_name": None,
        })
        result = extract_slot("1.1", "anh Tùng", client)
        assert result["owner_name"] == "Tùng"
        assert result["dealer_name"] is None

    def test_extract_slot_1_2_address_validate(self):
        """Slot 1.2 LLM trả address → validator strip + check ≥ 3 char."""
        client = _make_mock_client({
            "address": "  123 Lê Lợi, Q.1, TP.HCM  ",
            "local_dominance_signal": "khách đến từ 5km",
        })
        result = extract_slot("1.2", "123 Lê Lợi quận 1, khách 5km", client)
        # validate_address strips whitespace
        assert result["address"] == "123 Lê Lợi, Q.1, TP.HCM"
        assert result["local_dominance_signal"] == "khách đến từ 5km"

    def test_extract_slot_1_2_blacklist_address_rejected(self):
        """Address blacklist (1C § 10) → validate fail → null."""
        client = _make_mock_client({
            "address": "Gần Lăng Bác, Hà Nội",
            "local_dominance_signal": None,
        })
        result = extract_slot("1.2", "ở gần Lăng Bác", client)
        assert result["address"] is None  # blacklist → reject

    def test_extract_slot_4_0_yes(self):
        client = _make_mock_client({"brandkit_consent": "yes"})
        result = extract_slot("4.0", "ok em làm đi", client)
        assert result["brandkit_consent"] == "yes"

    def test_extract_slot_4_0_no(self):
        client = _make_mock_client({"brandkit_consent": "no"})
        result = extract_slot("4.0", "không cần", client)
        assert result["brandkit_consent"] == "no"

    def test_extract_slot_4_0_invalid_enum(self):
        """LLM trả enum lạ → validator reject → null."""
        client = _make_mock_client({"brandkit_consent": "maybe"})
        result = extract_slot("4.0", "chưa quyết", client)
        assert result["brandkit_consent"] is None

    def test_extract_llm_exception_returns_empty(self):
        """LLM raise exception → log warning + return {}."""
        client = MagicMock()
        client.extract_fast.side_effect = ConnectionError("API down")
        result = extract_slot("1.1", "anh Tùng", client)
        assert result == {}

    def test_extract_llm_returns_non_dict(self):
        """LLM trả về không phải dict → return {}."""
        client = _make_mock_client()
        client.extract_fast.return_value = "not a dict"  # broken
        result = extract_slot("1.1", "test", client)
        assert result == {}

    def test_extract_passes_dealer_type_to_prompt(self):
        """Verify extract_slot tạo prompt với dealer_type."""
        client = _make_mock_client({"owner_name": "X", "dealer_name": "Y"})
        extract_slot(
            "1.1", "X cửa hàng Y", client,
            dealer_type=DealerType.KHOE,
            address_form=AddressForm.CHI,
        )
        # Verify call_args
        call_kwargs = client.extract_fast.call_args.kwargs
        system_prompt = call_kwargs["system_prompt"]
        assert "khoe" in system_prompt
        assert "chị" in system_prompt
