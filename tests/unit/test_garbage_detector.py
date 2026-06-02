"""Test garbage detector — refer 1C § 7."""
from __future__ import annotations

import pytest

from app.core.garbage_detector import is_garbage, is_meaningful_short


class TestIsGarbage:
    @pytest.mark.parametrize("msg", [
        "",
        "   ",
        "\n\t",
        "a",                 # 1 ký tự ngẫu
        ".",
        ",,,",
        "!?",
        "xxxxx",             # repeat
        "aaaa",
        "asdf",              # random keyboard
        "qwerty",
        "qwe asdf",
        "😀😀😀",            # toàn emoji
        "🌷🎉",
        "...",
    ])
    def test_garbage_detected(self, msg):
        assert is_garbage(msg) is True, f"Should be garbage: {msg!r}"

    @pytest.mark.parametrize("msg", [
        "ok",
        "OK",
        "ờ",
        "ò",
        "ừa",
        "có",
        "không",
        "anh tên Tùng",
        "0912345678",
        "123 Lê Lợi Hoàn Kiếm",
        "nhôm kính là chính",
        "ok em làm đi",
        "đúng rồi em chốt",
        "60-70%",
        "anh có 5 thợ",
    ])
    def test_valid_messages(self, msg):
        assert is_garbage(msg) is False, f"Should NOT be garbage: {msg!r}"

    def test_none_input(self):
        assert is_garbage(None) is True

    def test_emoji_with_content_not_garbage(self):
        """Emoji + text có nghĩa → KHÔNG garbage."""
        assert is_garbage("ok em 🎉") is False
        assert is_garbage("anh tên Tùng 🌷") is False


class TestIsMeaningfulShort:
    @pytest.mark.parametrize("msg", ["ok", "có", "ờ", "ò", "ừa", "vâng", "dạ", "đúng"])
    def test_valid_short_words(self, msg):
        assert is_meaningful_short(msg) is True

    @pytest.mark.parametrize("msg", ["a", "xx", "asdf", ""])
    def test_invalid_short_words(self, msg):
        assert is_meaningful_short(msg) is False
