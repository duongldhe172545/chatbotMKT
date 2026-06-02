"""Test LLM defensive + tâm sự handler — F2B.4b (LUAT_2B_llm).

Refer:
- F2B.4b spec: 3-component defensive / engage CỤ THỂ tâm sự
- File 1C § 2 (defensive lặp), § 3 (tâm sự kéo dài)
- feedback_no_case_lock — không khoá case, test LUẬT.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.llm.defensive_handler import (
    DEFENSIVE_ESCALATE_AT,
    handle_defensive,
)
from app.llm.tam_su_handler import (
    TAM_SU_POLITE_CUT_AT,
    TAM_SU_TOPICS,
    detect_topic,
    handle_tam_su,
)
from app.models.enums import AddressForm, DealerType


def _make_client(chat_quality_return: str = "Default LLM reply", extract_return: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.chat_quality = MagicMock(return_value=chat_quality_return)
    client.extract_fast = MagicMock(return_value=extract_return or {"topic": "other", "severity": 1})
    return client


# ============================================================
# Defensive handler
# ============================================================


class TestDefensiveHandler:
    def test_returns_llm_response_when_success(self):
        custom = "Dạ anh yên tâm, em lưu nội bộ, mình tiếp tục nhé?"
        client = _make_client(chat_quality_return=custom)
        result = handle_defensive(
            dealer_message="bên nào làm vậy em?",
            defensive_count=1,
            dealer_type=DealerType.LO,
            address_form=AddressForm.ANH,
            client=client,
        )
        assert result == custom
        client.chat_quality.assert_called_once()

    def test_repairs_scam_reply_when_llm_omits_direct_answer_or_privacy(self):
        client = _make_client(
            chat_quality_return=(
                "Bộ thương hiệu gồm logo, danh thiếp và video hoàn toàn miễn "
                "phí. Mình tiếp tục nhé anh?"
            )
        )

        result = handle_defensive(
            dealer_message="có lừa đảo gì không em",
            defensive_count=1,
            dealer_type=DealerType.LO,
            address_form=AddressForm.ANH,
            client=client,
        )

        assert "KHÔNG lừa đảo" in result
        assert "KHÔNG mất phí" in result
        assert "chỉ dùng nội bộ" in result

    def test_empty_message_returns_none(self):
        client = _make_client()
        assert handle_defensive("", 1, DealerType.UNKNOWN, AddressForm.ANH, client) is None
        assert handle_defensive(None, 1, DealerType.UNKNOWN, AddressForm.ANH, client) is None
        client.chat_quality.assert_not_called()

    def test_llm_empty_returns_none(self):
        """LLM trả empty → return None (caller fallback template)."""
        client = _make_client(chat_quality_return="")
        result = handle_defensive(
            "phí gì không?",
            defensive_count=1,
            dealer_type=DealerType.LO,
            address_form=AddressForm.ANH,
            client=client,
        )
        assert result is None

    def test_llm_whitespace_returns_none(self):
        client = _make_client(chat_quality_return="   \n  ")
        assert handle_defensive(
            "lừa à",
            1,
            DealerType.LO,
            AddressForm.ANH,
            client,
        ) is None

    def test_llm_exception_returns_none(self):
        """LLM throw → return None gracefully."""
        client = MagicMock()
        client.chat_quality = MagicMock(side_effect=Exception("API timeout"))
        result = handle_defensive(
            "bot lừa đảo",
            1,
            DealerType.LO,
            AddressForm.ANH,
            client,
        )
        assert result is None

    def test_l3_escalation_hint_in_prompt(self):
        """ADVERSARIAL: count ≥ 3 → task prompt phải có offer dừng."""
        client = _make_client(chat_quality_return="reply")
        handle_defensive(
            "bot lừa đảo",
            defensive_count=DEFENSIVE_ESCALATE_AT,
            dealer_type=DealerType.LO,
            address_form=AddressForm.ANH,
            client=client,
        )
        call_args = client.chat_quality.call_args
        system_prompt = call_args.kwargs.get("system_prompt") or call_args.args[0]
        assert "dừng" in system_prompt or "OK ạ" in system_prompt or "ghi nhận tới đây" in system_prompt

    def test_uses_quality_tier(self):
        """ADVERSARIAL: defensive luôn dùng chat_quality, không chat_fast."""
        client = _make_client(chat_quality_return="ok")
        handle_defensive(
            "phí à?",
            1,
            DealerType.BAN,
            AddressForm.ANH,
            client,
        )
        client.chat_quality.assert_called_once()
        client.chat_fast.assert_not_called() if hasattr(client, "chat_fast") else None

    def test_context_includes_count_and_turn(self):
        client = _make_client(chat_quality_return="ok")
        handle_defensive(
            "lừa đảo à",
            defensive_count=2,
            dealer_type=DealerType.KHOE,
            address_form=AddressForm.ANH,
            client=client,
            turn_count=7,
        )
        call_args = client.chat_quality.call_args
        sp = call_args.kwargs.get("system_prompt") or call_args.args[0]
        assert "lần thứ 2" in sp.lower() or "2" in sp
        assert "7 turn" in sp or "7" in sp


# ============================================================
# Tâm sự handler
# ============================================================


class TestDetectTopic:
    def test_valid_topic(self):
        client = _make_client(extract_return={"topic": "family", "severity": 2})
        topic, severity = detect_topic("vợ tao mới sinh em bé", client)
        assert topic == "family"
        assert severity == 2

    def test_invalid_topic_falls_back_to_other(self):
        client = _make_client(extract_return={"topic": "BIA_topic_xyz", "severity": 1})
        topic, _ = detect_topic("hi", client)
        assert topic == "other"

    def test_severity_clamped(self):
        client = _make_client(extract_return={"topic": "health", "severity": 99})
        _, severity = detect_topic("ốm", client)
        assert 1 <= severity <= 3

    def test_severity_negative_clamped(self):
        client = _make_client(extract_return={"topic": "health", "severity": -5})
        _, severity = detect_topic("ốm", client)
        assert severity >= 1

    def test_severity_non_int_defaults_to_1(self):
        client = _make_client(extract_return={"topic": "health", "severity": "very high"})
        _, severity = detect_topic("ốm", client)
        assert severity == 1

    def test_llm_fail_returns_default(self):
        client = MagicMock()
        client.extract_fast = MagicMock(side_effect=Exception("API"))
        topic, severity = detect_topic("hi", client)
        assert topic == "other"
        assert severity == 1

    def test_non_dict_returns_default(self):
        client = MagicMock()
        client.extract_fast = MagicMock(return_value="not a dict")
        topic, severity = detect_topic("hi", client)
        assert topic == "other"

    def test_empty_message_returns_default(self):
        client = _make_client()
        topic, severity = detect_topic("", client)
        assert topic == "other"
        assert severity == 1
        client.extract_fast.assert_not_called()


class TestTamSuHandler:
    def test_returns_llm_response(self):
        custom = "Dạ chúc mừng anh có em bé. À hỏi tiếp..."
        client = _make_client(chat_quality_return=custom)
        result = handle_tam_su(
            dealer_message="vợ mới sinh",
            tam_su_count=1,
            dealer_type=DealerType.UNKNOWN,
            address_form=AddressForm.ANH,
            client=client,
            topic="family",
            severity=1,
        )
        assert result == custom

    def test_empty_message_returns_none(self):
        client = _make_client()
        assert handle_tam_su(
            "", 1, DealerType.UNKNOWN, AddressForm.ANH, client,
        ) is None

    def test_llm_empty_returns_none(self):
        client = _make_client(chat_quality_return="")
        result = handle_tam_su(
            "vợ ốm",
            1,
            DealerType.UNKNOWN,
            AddressForm.ANH,
            client,
            topic="family",
            severity=1,
        )
        assert result is None

    def test_llm_exception_returns_none(self):
        client = MagicMock()
        client.chat_quality = MagicMock(side_effect=Exception("API"))
        client.extract_fast = MagicMock(return_value={"topic": "other", "severity": 1})
        result = handle_tam_su(
            "vợ ốm",
            1,
            DealerType.UNKNOWN,
            AddressForm.ANH,
            client,
            topic="family",  # skip detect
            severity=1,
        )
        assert result is None

    def test_polite_cut_hint_in_prompt(self):
        """ADVERSARIAL: count ≥ 3 → task có polite cut hint."""
        client = _make_client(chat_quality_return="ok")
        handle_tam_su(
            "vợ ốm tiếp",
            tam_su_count=TAM_SU_POLITE_CUT_AT,
            dealer_type=DealerType.UNKNOWN,
            address_form=AddressForm.ANH,
            client=client,
            topic="family",
            severity=1,
        )
        sp = client.chat_quality.call_args.kwargs.get("system_prompt") or client.chat_quality.call_args.args[0]
        assert "polite cut" in sp.lower() or "team người thật" in sp.lower() or "quay lại" in sp.lower()

    def test_severity_3_includes_heavy_hint(self):
        """ADVERSARIAL: severity=3 (NẶNG) → task có hint cộng đồng kết nối."""
        client = _make_client(chat_quality_return="ok")
        handle_tam_su(
            "ly hôn rồi",
            tam_su_count=1,
            dealer_type=DealerType.UNKNOWN,
            address_form=AddressForm.ANH,
            client=client,
            topic="family",
            severity=3,
        )
        sp = client.chat_quality.call_args.kwargs.get("system_prompt") or client.chat_quality.call_args.args[0]
        assert "nhóm anh em" in sp.lower() or "cộng đồng" in sp.lower() or "nặng" in sp.lower()

    def test_auto_detect_topic_when_not_provided(self):
        """Caller không cung cấp topic → handler tự gọi detect_topic."""
        client = _make_client(
            chat_quality_return="ok",
            extract_return={"topic": "health", "severity": 2},
        )
        handle_tam_su(
            "ốm quá",
            tam_su_count=1,
            dealer_type=DealerType.UNKNOWN,
            address_form=AddressForm.ANH,
            client=client,
        )
        # Cả extract_fast (topic detect) và chat_quality (handler) được gọi
        client.extract_fast.assert_called_once()
        client.chat_quality.assert_called_once()

    def test_skip_topic_detect_when_provided(self):
        """Caller cung cấp topic + severity → KHÔNG gọi detect."""
        client = _make_client(chat_quality_return="ok")
        handle_tam_su(
            "ốm",
            tam_su_count=1,
            dealer_type=DealerType.UNKNOWN,
            address_form=AddressForm.ANH,
            client=client,
            topic="health",
            severity=2,
        )
        client.extract_fast.assert_not_called()

    def test_next_slot_hint_included_in_prompt(self):
        client = _make_client(chat_quality_return="ok")
        handle_tam_su(
            "ốm",
            tam_su_count=1,
            dealer_type=DealerType.UNKNOWN,
            address_form=AddressForm.ANH,
            client=client,
            topic="health",
            severity=1,
            next_slot_hint="Anh cho em xin số Zalo nhé?",
        )
        sp = client.chat_quality.call_args.kwargs.get("system_prompt") or client.chat_quality.call_args.args[0]
        assert "Zalo" in sp
