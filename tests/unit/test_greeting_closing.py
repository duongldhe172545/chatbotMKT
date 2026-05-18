"""Test greeting + closing render. Refer F2A.8 + CORE § A.3 + § H.3 + 1A § 3/7."""
from __future__ import annotations

import pytest

from app.core.closing import (
    render_closing,
    render_soft_end_closing,
)
from app.core.greeting import (
    get_num_variants,
    render_greeting,
)


# ============================================================
# Greeting
# ============================================================


class TestGreeting:
    def test_has_3_variants(self):
        """3 biến thể greeting — refer 1A § 3.2."""
        assert get_num_variants() == 3

    def test_render_returns_text(self):
        text = render_greeting("test-session-id-1")
        assert isinstance(text, str)
        assert len(text) > 100

    def test_deterministic_per_session(self):
        """Same session_id → cùng variant (refer 1A § 1.2)."""
        a = render_greeting("session-abc")
        b = render_greeting("session-abc")
        assert a == b

    def test_different_session_potentially_different(self):
        """Different session_id → may have different variant."""
        variants = {render_greeting(f"sess-{i}") for i in range(20)}
        # Probabilistic — 20 sessions thường cover cả 3 variants
        assert len(variants) >= 2

    def test_mentions_em_linh(self):
        text = render_greeting("session-1")
        assert "Em là Linh" in text or "Linh" in text

    def test_mentions_zalo(self):
        """Greeting clarify quà gửi qua Zalo (CORE § A.3 batch 3)."""
        text = render_greeting("session-1")
        assert "Zalo" in text

    def test_no_forbidden_vocab(self):
        """Greeting KHÔNG vocab cấm Tier/C-score/BRANDKIT."""
        forbidden = ["Tier", "C-score", "Scoring", "BRANDKIT",
                     "Profile", "Namecard", "Mini App", "Marketing"]
        for sid in [f"sess-{i}" for i in range(20)]:
            text = render_greeting(sid)
            for word in forbidden:
                assert word not in text, \
                    f"Greeting variant chứa vocab cấm '{word}': {text[:100]}"

    def test_mentions_3_quà(self):
        """Greeting mention 3 quà: logo, danh thiếp, video."""
        text = render_greeting("session-1")
        assert "Logo" in text or "logo" in text.lower()
        assert "danh thiếp" in text.lower() or "Danh thiếp" in text
        assert "Video" in text or "video" in text.lower()

    def test_empty_session_id_uses_first_variant(self):
        text = render_greeting("")
        assert "Em là Linh" in text or "em là Linh" in text


# ============================================================
# Closing — consent=yes path
# ============================================================


class TestClosingConsentYes:
    def test_basic_closing(self):
        text = render_closing(province="Hà Nội", consent="yes")
        assert "cảm ơn" in text.lower()
        assert "Zalo" in text

    def test_closing_with_specialty_hook(self):
        """Province có specialty → hook đặc sản."""
        text = render_closing(province="Cao Bằng", consent="yes")
        assert "vịt quay" in text.lower() or "Cao Bằng" in text

    def test_closing_no_specialty_fallback(self):
        """Province không có specialty → no hook (refer F2A.8)."""
        text = render_closing(province="Province xa xôi không có", consent="yes")
        # Không crash, không có hook
        assert "cảm ơn" in text.lower()

    def test_closing_none_province(self):
        text = render_closing(province=None, consent="yes")
        assert "cảm ơn" in text.lower()

    def test_closing_mentions_bộ_thương_hiệu(self):
        text = render_closing(province="Hà Nội", consent="yes")
        assert "bộ thương hiệu" in text.lower()


# ============================================================
# Closing — consent=no path (D10 STRATEGY)
# ============================================================


class TestClosingConsentNo:
    def test_consent_no_different_template(self):
        yes_text = render_closing(province="Hà Nội", consent="yes")
        no_text = render_closing(province="Hà Nội", consent="no")
        assert yes_text != no_text

    def test_consent_no_acknowledges_refusal(self):
        text = render_closing(province="Hà Nội", consent="no")
        # Phải có ý "không ép" hoặc "đổi ý"
        assert "không ép" in text or "đổi ý" in text or "không cần" in text

    def test_consent_no_still_mention_zalo(self):
        """Vẫn dẫn dealer sang Zalo (cho nhóm + plan 3 ngày)."""
        text = render_closing(province="Hà Nội", consent="no")
        assert "Zalo" in text


# ============================================================
# Soft-end closing — escalation L3 / timeout
# ============================================================


class TestSoftEndClosing:
    def test_returns_polite_text(self):
        text = render_soft_end_closing()
        assert "cảm ơn" in text.lower() or "ngừng" in text.lower()

    def test_does_not_promise_brandkit(self):
        """Soft-end KHÔNG promise quà (vì L3 escalation)."""
        text = render_soft_end_closing()
        assert "logo" not in text.lower() or "ngừng" in text.lower()

    def test_no_forbidden_vocab(self):
        text = render_soft_end_closing()
        for word in ["Tier", "C-score", "Scoring", "BRANDKIT"]:
            assert word not in text


# ============================================================
# Vocab compliance — all closing variants
# ============================================================


class TestClosingVocab:
    @pytest.mark.parametrize("consent", ["yes", "no", None])
    def test_no_forbidden_vocab_in_closing(self, consent):
        text = render_closing(province="Hà Nội", consent=consent)
        forbidden = ["Tier", "C-score", "Scoring", "BRANDKIT",
                     "Profile", "Namecard", "Mini App", "Marketing"]
        for word in forbidden:
            assert word not in text
