"""Test Intent.CONFUSION + CONFUSION_PATTERNS.

Refer:
- CORE D.1 (bot chủ động giải thích "là sao/là gì")
- CORE B.4 #8 (KHÔNG bịa context "cao cấp")
"""
from __future__ import annotations

import pytest

from app.core.intent import detect_intent
from app.models.enums import Intent


class TestConfusionIntent:
    """Verify CONFUSION pattern matches dealer hỏi 'là sao/là gì'."""

    @pytest.mark.parametrize("msg", [
        "là sao?",
        "là sao em?",
        "là gì vậy",
        "là gì em?",
        "cái này là gì",
        "đây là gì vậy",
        "cái đó là gì",
        "ý em là sao?",
        "ý gì cơ?",
        "không hiểu em",
        "chưa hiểu",
        "nghĩa là sao",
        "nghĩa là gì",
        "thế nào cơ",
    ])
    def test_confusion_match(self, msg):
        assert detect_intent(msg) == Intent.CONFUSION, f"FAIL: {msg!r}"

    @pytest.mark.parametrize("msg", [
        "ok em",
        "anh tên Tuấn",
        "ở Hà Nội",
        "0912345678",
        "không biết",
        "đéo cho",
        "trời mưa quá",
        "tặng tiền không em?",  # defensive
    ])
    def test_no_confusion_match(self, msg):
        assert detect_intent(msg) != Intent.CONFUSION, f"FALSE POSITIVE: {msg!r}"


class TestColloquialNumberSchema:
    """Verify extractor schema slot 2.3 có hint colloquial number."""

    def test_schema_has_colloquial_hints(self):
        from app.llm.extractors.schemas import TOOL_SLOT_2_3
        desc = TOOL_SLOT_2_3["input_schema"]["properties"]["est_team_size"]["description"]
        # Phải mention các colloquial pattern
        assert "chục" in desc, "Schema must hint 'chục' colloquial"
        assert "vài chục" in desc or "đôi ba" in desc, "Must hint approximate"


class TestLocalHookVariant:
    """Verify local_hook có variant rotation + reject product hallucinate."""

    def test_variant_index_deterministic_per_session(self):
        """Same session_id → same variant_idx (cache hit)."""
        from app.llm.local_hook import gen_local_hook
        from unittest.mock import MagicMock

        client = MagicMock()
        client.chat_fast = MagicMock(return_value="Hà Nội đẹp lắm.")
        # 2 calls same session_id → cache hit
        r1 = gen_local_hook("Hà Nội", client=client, session_id="sid-1", use_cache=True)
        r2 = gen_local_hook("Hà Nội", client=client, session_id="sid-1", use_cache=True)
        assert r1 == r2
        # LLM called once
        assert client.chat_fast.call_count == 1

    def test_reject_product_hallucinate(self):
        """LLM gen 'nổi tiếng nhôm kính' → reject → empty."""
        from app.llm.local_hook import gen_local_hook
        from unittest.mock import MagicMock

        client = MagicMock()
        client.chat_fast = MagicMock(
            return_value="Gia Lộc nổi tiếng với xưởng sản xuất nhôm kính phát triển."
        )
        result = gen_local_hook(
            "Gia Lộc", client=client, session_id="sid-test", use_cache=False,
        )
        assert result == "", f"Should reject product hallucinate: {result!r}"

    def test_accept_clean_hook(self):
        """LLM gen hook clean (không bịa product) → accept."""
        from app.llm.local_hook import gen_local_hook
        from unittest.mock import MagicMock

        client = MagicMock()
        client.chat_fast = MagicMock(
            return_value="Cao Bằng là vùng biên cảnh đẹp, dân chân chất."
        )
        result = gen_local_hook(
            "Cao Bằng", client=client, session_id="sid-test", use_cache=False,
        )
        assert "Cao Bằng" in result or len(result) > 10
