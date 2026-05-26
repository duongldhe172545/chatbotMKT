"""Unit test cho drift guard mở rộng: emoji guard + parrot guard.

Refer:
- CORE B.4 luật #2 (KHÔNG lặp y nguyên) + luật #5 (KHÔNG spam emoji)
- KICH_BAN_1B § 7 (anti-pattern 10 luật checklist)
- Code: app/guards/drift.py
"""
from __future__ import annotations

import pytest

from app.guards.drift import (
    auto_rewrite,
    check_parrot,
    count_emojis,
    trim_emojis,
)


# ============================================================
# count_emojis
# ============================================================


class TestCountEmojis:
    def test_no_emoji(self):
        assert count_emojis("Hello world") == 0

    def test_single_emoji(self):
        assert count_emojis("Dạ em chào anh 🌷") == 1

    def test_multiple_emoji(self):
        assert count_emojis("Dạ 🌷✨🎉 anh ơi 💪") == 4

    def test_emoji_at_start(self):
        assert count_emojis("🌷 Dạ em chào") == 1

    def test_only_emoji(self):
        assert count_emojis("🌷✨🎉") == 3

    def test_empty(self):
        assert count_emojis("") == 0

    def test_none(self):
        assert count_emojis(None) == 0  # type: ignore

    def test_misc_symbols(self):
        # ✨ ☀ ❤ thuộc Unicode Misc Symbols block
        assert count_emojis("Dạ ✨ và ❤") == 2

    def test_flag(self):
        # 🇻🇳 = 2 regional indicators (count = 2)
        assert count_emojis("Việt Nam 🇻🇳") == 2


# ============================================================
# trim_emojis
# ============================================================


class TestTrimEmojis:
    def test_no_change_when_under_limit(self):
        text = "Dạ em chào anh 🌷"
        assert trim_emojis(text, max_count=1) == text

    def test_trim_spam_to_one(self):
        text = "Dạ 🌷✨🎉 anh ơi 💪🔥"
        result = trim_emojis(text, max_count=1)
        assert count_emojis(result) == 1
        # First emoji kept (🌷)
        assert "🌷" in result
        assert "✨" not in result
        assert "💪" not in result

    def test_trim_to_zero(self):
        text = "Dạ 🌷 em ghi nhận ✨"
        result = trim_emojis(text, max_count=0)
        assert count_emojis(result) == 0

    def test_preserve_text(self):
        text = "Dạ anh Tuấn 🌷✨🎉 em đã ghi nhận"
        result = trim_emojis(text, max_count=1)
        assert "Dạ anh Tuấn" in result
        assert "em đã ghi nhận" in result

    def test_empty(self):
        assert trim_emojis("", max_count=1) == ""


# ============================================================
# auto_rewrite emoji integration
# ============================================================


class TestAutoRewriteEmoji:
    def test_auto_rewrite_trims_emoji_spam(self):
        text = "Dạ anh Tuấn 🌷✨🎉 em ghi nhận 💪🔥"
        result = auto_rewrite(text)
        # Auto-rewrite gọi trim_emojis(max=1)
        assert count_emojis(result) <= 1

    def test_auto_rewrite_single_emoji_ok(self):
        text = "Dạ em chào anh 🌷"
        result = auto_rewrite(text)
        assert "🌷" in result


# ============================================================
# check_parrot
# ============================================================


class TestCheckParrot:
    def test_no_overlap_ok(self):
        bot = "Dạ em đã ghi nhận thông tin"
        dealer = "Anh ở Hà Nội"
        assert check_parrot(bot, dealer) is False

    def test_short_ack_ok(self):
        bot = "Dạ Hà Nội — em ghi nhận"
        dealer = "Anh ở Hà Nội"
        # 2 từ trùng "hà nội" — KHÔNG parrot
        assert check_parrot(bot, dealer) is False

    def test_address_named_entity_ok(self):
        # Named entity (4 từ địa danh) KHÔNG parrot với default min_ngram=5
        bot = "Dạ Quận 1 TP HCM em note"
        dealer = "Anh ở Quận 1 TP HCM nha"
        assert check_parrot(bot, dealer) is False

    def test_parrot_5gram(self):
        bot = "Dạ anh ở Quận 1 TP HCM em ghi"
        dealer = "anh ở Quận 1 TP HCM, khách cách 5km"
        # 5-gram "anh ở quận 1 tp" lặp → PARROT
        assert check_parrot(bot, dealer) is True

    def test_parrot_long_repeat(self):
        bot = "Dạ anh ở Hà Nội em ghi nhận anh ở Hà Nội nên rất tiềm năng"
        dealer = "anh ở Hà Nội em là chủ cửa hàng"
        # CORE B.4 example: bot lặp "anh ở Hà Nội" nhiều lần
        # Bot có 5-gram "dạ anh ở hà nội" — dealer có "anh ở hà nội em"
        # Common 5-gram? Check
        # bot 5-grams: [dạ anh ở hà nội, anh ở hà nội em, ...]
        # dealer 5-grams: [anh ở hà nội em, ở hà nội em là, ...]
        # → match "anh ở hà nội em" → PARROT
        assert check_parrot(bot, dealer) is True

    def test_case_insensitive(self):
        bot = "DẠ ANH Ở QUẬN 1 TP HCM EM"
        dealer = "anh ở quận 1 tp hcm"
        assert check_parrot(bot, dealer) is True

    def test_punctuation_ignored(self):
        bot = "Dạ, anh ở Quận 1, TP HCM, em note!"
        dealer = "Anh ở Quận 1 TP HCM nha"
        assert check_parrot(bot, dealer) is True

    def test_short_messages_skip(self):
        # dealer < min_ngram từ → KHÔNG check
        bot = "Dạ vâng anh"
        dealer = "OK"
        assert check_parrot(bot, dealer) is False

    def test_custom_min_ngram(self):
        bot = "Dạ Quận 1 TP HCM em note"
        dealer = "Anh ở Quận 1 TP HCM"
        # min_ngram=4 → match "quận 1 tp hcm" → PARROT (relax mode)
        assert check_parrot(bot, dealer, min_ngram=4) is True
        # min_ngram=5 default → KHÔNG match
        assert check_parrot(bot, dealer, min_ngram=5) is False

    def test_empty_inputs(self):
        assert check_parrot("", "anh ở Hà Nội") is False
        assert check_parrot("Dạ vâng", "") is False
