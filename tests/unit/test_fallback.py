"""Test fallback safe ack templates. Refer F2C.4."""
from __future__ import annotations

import pytest

from app.llm.fallback import (
    SAFE_ACK_TEMPLATES,
    SAFE_ERROR_MESSAGES,
    SAFE_RETRY_MESSAGES,
    safe_ack,
    safe_error_message,
    safe_retry_message,
)


# ============================================================
# Template lists
# ============================================================


class TestTemplateLists:
    def test_safe_ack_has_at_least_3(self):
        assert len(SAFE_ACK_TEMPLATES) >= 3

    def test_safe_retry_has_at_least_2(self):
        assert len(SAFE_RETRY_MESSAGES) >= 2

    def test_safe_error_has_at_least_2(self):
        assert len(SAFE_ERROR_MESSAGES) >= 2


# ============================================================
# Vocab compliance — refer GLOSSARY § 6 + F2B.8
# ============================================================


class TestVocabCompliance:
    @pytest.mark.parametrize("template", SAFE_ACK_TEMPLATES + SAFE_RETRY_MESSAGES + SAFE_ERROR_MESSAGES)
    def test_no_forbidden_vocab(self, template):
        """Templates KHÔNG được chứa vocab cấm (Tier/C-score/BRANDKIT/etc.)."""
        forbidden = [
            "Tier", "C-score", "Scoring", "chấm điểm",
            "BRANDKIT", "Profile", "Namecard", "Slogan",
            "Mini App", "Marketing", "evaluation", "ranking",
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9",
        ]
        for word in forbidden:
            assert word not in template, \
                f"Template '{template}' chứa vocab cấm '{word}'"

    @pytest.mark.parametrize("template", SAFE_ACK_TEMPLATES + SAFE_RETRY_MESSAGES + SAFE_ERROR_MESSAGES)
    def test_no_english_no_viet_hoa(self, template):
        """Templates phải Việt thuần (trừ tên brand)."""
        # KHÔNG dùng "AI", "bot", "model" tự xưng (refer CORE § E)
        english_self_label = ["AI", "bot này", "model", "machine"]
        for word in english_self_label:
            assert word not in template, \
                f"Template '{template}' tự xưng '{word}'"

    @pytest.mark.parametrize("template", SAFE_ACK_TEMPLATES + SAFE_RETRY_MESSAGES + SAFE_ERROR_MESSAGES)
    def test_starts_with_polite_prefix(self, template):
        """Templates polite — bắt đầu 'Dạ' / 'Em'."""
        starts_polite = template.startswith("Dạ") or template.startswith("Em")
        assert starts_polite, f"Template '{template}' không bắt đầu polite"


# ============================================================
# safe_ack / safe_retry_message / safe_error_message
# ============================================================


class TestSafeAck:
    def test_returns_non_empty(self):
        for _ in range(5):
            result = safe_ack()
            assert result
            assert isinstance(result, str)

    def test_returns_from_template_list(self):
        """Always return 1 trong SAFE_ACK_TEMPLATES."""
        for _ in range(10):
            assert safe_ack() in SAFE_ACK_TEMPLATES

    def test_deterministic_with_seed(self):
        """Same seed → same template."""
        a = safe_ack(seed=42)
        b = safe_ack(seed=42)
        assert a == b


class TestSafeRetryMessage:
    def test_returns_non_empty(self):
        result = safe_retry_message()
        assert result in SAFE_RETRY_MESSAGES

    def test_deterministic_with_seed(self):
        a = safe_retry_message(seed=1)
        b = safe_retry_message(seed=1)
        assert a == b


class TestSafeErrorMessage:
    def test_returns_non_empty(self):
        result = safe_error_message()
        assert result in SAFE_ERROR_MESSAGES

    def test_deterministic_with_seed(self):
        a = safe_error_message(seed=99)
        b = safe_error_message(seed=99)
        assert a == b
