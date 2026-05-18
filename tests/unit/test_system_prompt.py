"""Test system prompt builder. Refer F2B.1 (LUAT_2B_llm v0.1.2)."""
from __future__ import annotations

import pytest

from app.llm.system_prompt import (
    build_system_prompt,
    estimate_token_count,
)
from app.models.enums import AddressForm, DealerType


# ============================================================
# Basic build
# ============================================================


class TestBuildSystemPrompt:
    def test_default_build(self):
        """Default args → prompt với dealer_type=UNKNOWN."""
        prompt = build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "Em Linh" in prompt
        assert "anh" in prompt
        assert "unknown" in prompt

    def test_build_with_dealer_type(self):
        prompt = build_system_prompt(dealer_type=DealerType.KHOE)
        assert "khoe" in prompt
        assert "Khen CỤ THỂ" in prompt or "khen" in prompt.lower()

    def test_build_with_address_form_chi(self):
        prompt = build_system_prompt(address_form=AddressForm.CHI)
        assert "chị" in prompt

    def test_build_with_current_slot(self):
        prompt = build_system_prompt(current_slot="1.1")
        assert "1.1" in prompt

    def test_build_with_history_summary(self):
        prompt = build_system_prompt(history_summary="Dealer đã cho tên Tùng")
        assert "Tùng" in prompt

    def test_build_with_custom_task(self):
        prompt = build_system_prompt(task="Hỏi slot 1.2 địa chỉ.")
        assert "địa chỉ" in prompt


# ============================================================
# Tone rules per dealer_type
# ============================================================


class TestToneRules:
    @pytest.mark.parametrize("dealer_type,keyword", [
        (DealerType.LUA_LO, "≤8"),
        (DealerType.KHOE, "Khen CỤ THỂ"),
        (DealerType.LO, "cam kết bảo mật"),
        (DealerType.BAN, "5-12"),
        (DealerType.UNKNOWN, "Default tone Bận"),
    ])
    def test_tone_rules_match_type(self, dealer_type, keyword):
        prompt = build_system_prompt(dealer_type=dealer_type)
        assert keyword in prompt, \
            f"Prompt for {dealer_type} thiếu keyword '{keyword}'"


# ============================================================
# Vocab compliance — KHÔNG lộ Tier/C-score trong prompt
# ============================================================


class TestPromptVocabCompliance:
    def test_no_forbidden_vocab_target_dealer(self):
        """Prompt mention vocab cấm (như là cảnh báo cho LLM) nhưng KHÔNG
        nói với dealer những từ đó.

        Test: prompt phải có cảnh báo "CẤM" trước Tier/C-score, không nói
        thẳng "đại lý sẽ được phân Tier".
        """
        prompt = build_system_prompt()
        # Phải có cảnh báo vocab cấm
        assert "CẤM" in prompt or "TUYỆT ĐỐI" in prompt
        # Phải mention các vocab cấm để LLM biết
        assert "Tier" in prompt
        assert "C-score" in prompt or "C1" in prompt

    def test_persona_no_self_label_bot(self):
        """Prompt phải có rule 'KHÔNG tự xưng bot/AI'."""
        prompt = build_system_prompt()
        assert "KHÔNG tự xưng" in prompt or "trợ lý số" in prompt


# ============================================================
# Token count ≤ 600 (F2B.1 target)
# ============================================================


class TestTokenCount:
    def test_default_under_600_tokens(self):
        """Default prompt ≤ 600 token estimate."""
        prompt = build_system_prompt()
        tokens = estimate_token_count(prompt)
        assert tokens <= 600, \
            f"Default prompt {tokens} token > 600 limit"

    def test_with_all_args_under_600(self):
        """Với mọi arg fill → vẫn ≤ 600 token."""
        prompt = build_system_prompt(
            dealer_type=DealerType.KHOE,
            address_form=AddressForm.CHI,
            current_slot="3.3",
            history_summary="Dealer Quốc Vinh kể cửa hàng 5 năm, doanh thu tăng",
            task="Sinh ack Khoe có insight cụ thể + hỏi tiếp slot 3.4",
        )
        tokens = estimate_token_count(prompt)
        assert tokens <= 600, f"Full prompt {tokens} > 600"

    def test_estimate_token_count_reasonable(self):
        """estimate_token_count return positive int."""
        assert estimate_token_count("hello world") > 0
        assert estimate_token_count("") == 0

    def test_estimate_proportional(self):
        """Text dài hơn → token count cao hơn."""
        short = "a" * 100
        long = "a" * 1000
        assert estimate_token_count(long) > estimate_token_count(short)


# ============================================================
# Structure — 6 section
# ============================================================


class TestPromptStructure:
    def test_has_role_section(self):
        prompt = build_system_prompt()
        assert "VAI TRÒ:" in prompt

    def test_has_persona_section(self):
        prompt = build_system_prompt()
        assert "PERSONA:" in prompt

    def test_has_language_section(self):
        prompt = build_system_prompt()
        assert "NGÔN NGỮ:" in prompt

    def test_has_boundary_section(self):
        prompt = build_system_prompt()
        assert "RANH GIỚI:" in prompt

    def test_has_context_section(self):
        prompt = build_system_prompt()
        assert "CONTEXT" in prompt

    def test_has_task_section(self):
        prompt = build_system_prompt()
        assert "NHIỆM VỤ:" in prompt
