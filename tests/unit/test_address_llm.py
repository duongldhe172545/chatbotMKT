"""Test Address parser Layer 2 LLM fuzzy — F2B.6.

Refer:
- F2B.6 — algorithm 3 layer (regex → LLM → district)
- feedback_no_case_lock — LLM province PHẢI match whitelist, reject bịa.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.address_parser import parse_address
from app.llm.address_llm import _match_whitelist, llm_parse_address


def _client(extract_return: dict | None = None) -> MagicMock:
    c = MagicMock()
    c.extract_fast = MagicMock(return_value=extract_return or {})
    return c


class TestLLMParseAddress:
    def test_empty_returns_none(self):
        client = _client()
        assert llm_parse_address("", client) == (None, None, None)
        assert llm_parse_address(None, client) == (None, None, None)
        client.extract_fast.assert_not_called()

    def test_valid_province_whitelist(self):
        client = _client({"province": "Hà Nội", "district": "Cầu Giấy"})
        prov, dist, ward = llm_parse_address("vùng nào đó Hà Nôi", client)
        assert prov == "Hà Nội"
        assert dist == "Cầu Giấy"

    def test_llm_bia_province_rejected(self):
        """ADVERSARIAL: LLM bịa "Thái Lan" → reject (không trong whitelist)."""
        client = _client({"province": "Thái Lan", "district": "Bangkok"})
        prov, _, _ = llm_parse_address("ở Thái Lan ạ", client)
        assert prov is None

    def test_fuzzy_substring_match_canonical(self):
        """LLM trả "TP.HCM" / "Hồ Chí Minh" → match canonical từ whitelist."""
        client = _client({"province": "Hồ Chí Minh"})
        prov, _, _ = llm_parse_address("Sài Gòn quận 1", client)
        # Whitelist có "TP.HCM" — fuzzy substring match
        assert prov is not None
        assert "HCM" in prov or "Hồ Chí Minh" in prov

    def test_llm_fail_returns_none(self):
        client = MagicMock()
        client.extract_fast = MagicMock(side_effect=Exception("API timeout"))
        assert llm_parse_address("Hà Nội", client) == (None, None, None)

    def test_non_dict_response(self):
        client = MagicMock()
        client.extract_fast = MagicMock(return_value="not a dict")
        assert llm_parse_address("HN", client) == (None, None, None)

    def test_null_province_returned(self):
        client = _client({"province": None})
        prov, dist, ward = llm_parse_address("vùng xa lắm em ơi", client)
        assert prov is None

    def test_district_empty_string_returned_none(self):
        client = _client({"province": "Hà Nội", "district": ""})
        _, dist, _ = llm_parse_address("Hà Nội", client)
        assert dist is None


class TestMatchWhitelist:
    def test_exact_match(self):
        provinces = ["Hà Nội", "Đà Nẵng", "TP.HCM"]
        assert _match_whitelist("Hà Nội", provinces) == "Hà Nội"
        assert _match_whitelist("hà nội", provinces) == "Hà Nội"

    def test_substring_match(self):
        provinces = ["TP.HCM"]
        # LLM trả "TP. Hồ Chí Minh" → fuzzy match
        assert _match_whitelist("TP. HCM", provinces) == "TP.HCM"

    def test_not_in_whitelist(self):
        provinces = ["Hà Nội"]
        assert _match_whitelist("Thái Lan", provinces) is None

    def test_empty_input(self):
        assert _match_whitelist("", ["Hà Nội"]) is None
        assert _match_whitelist(None, ["Hà Nội"]) is None


class TestParseAddress3Layer:
    def test_layer_1_only_no_client(self):
        """Không có client → chỉ Layer 1 regex."""
        prov, dist = parse_address("123 Lê Lợi, Quận 1, TP.HCM")
        assert prov == "TP.HCM"
        assert dist == "Quận 1"

    def test_layer_2_triggers_when_layer_1_fails(self):
        """Layer 1 fail (text lạ) → Layer 2 LLM được gọi."""
        client = _client({"province": "Hà Nội"})
        # Text không có province name standard → Layer 1 miss
        prov, _ = parse_address("vùng ngoại thành phía bắc thủ đô", client=client)
        # Layer 2 LLM được gọi và trả Hà Nội
        client.extract_fast.assert_called_once()
        assert prov == "Hà Nội"

    def test_layer_2_skipped_when_layer_1_matches(self):
        """Layer 1 match → KHÔNG gọi Layer 2 (perf)."""
        client = _client({"province": "Hà Nội"})
        prov, _ = parse_address("Cầu Giấy Hà Nội", client=client)
        assert prov == "Hà Nội"
        client.extract_fast.assert_not_called()

    def test_layer_2_fail_keeps_none(self):
        """Layer 2 LLM throw → giữ Layer 1 result (None)."""
        client = MagicMock()
        client.extract_fast = MagicMock(side_effect=Exception("fail"))
        prov, _ = parse_address("vùng xa em ơi", client=client)
        assert prov is None
