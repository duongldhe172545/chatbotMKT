"""G3 — Drift guard: forbidden vocab + auto-rewrite + emoji + parrot.

Refer LUAT_2B § F2B.8 G3 + CORE § C.1 + CORE § B.4 (anti-pattern luật
#2 KHÔNG lặp y nguyên + luật #5 KHÔNG spam emoji) + GLOSSARY § 6.

Mục đích:
- LLM hay slip vocab cấm vào bot response (Tier, BRANDKIT, Profile...)
- Hoặc dùng English thay vì Việt hóa
- LLM có thể spam emoji (>1/reply) hoặc parrot câu dealer
- Drift guard check + auto-rewrite trước khi gửi reply cho dealer

Data: data/forbidden_vocab.json (load qua data_loaders).
- scoring_internal[]: cấm tuyệt đối → REMOVE
- english_to_vietnamese{}: mapping → REWRITE

API:
- check_drift(text) → list[str] violations (vocab cấm tìm thấy)
- auto_rewrite(text) → cleaned text (REWRITE + REMOVE + emoji limit applied)
- has_forbidden_scoring_vocab(text) → bool (chỉ check scoring vocab —
  dùng cho admin queue trigger "drift" flag, không trigger cho english)
- count_emojis(text) → int (số emoji trong text)
- trim_emojis(text, max_count=1) → text với tối đa max_count emoji
- check_parrot(bot_reply, dealer_message, min_ngram=4) → bool (true nếu
  bot reply chứa đoạn ≥ min_ngram từ liên tiếp lặp y nguyên dealer)
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from app.cache.data_loaders import _load_json_file

logger = logging.getLogger(__name__)

# CORE B.4 luật #5: emoji ≤ 1/reply. Pattern bắt đầy đủ emoji Unicode
# (Misc Symbols / Pictographs / Transport / Flags / Supplemental).
# Refer Unicode 15.1 Emoji block: U+1F300-U+1F9FF + U+2600-U+27BF +
# U+1F000-U+1F02F + flags U+1F1E6-U+1F1FF.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F9FF"     # symbols/pictographs/emoticons/transport
    "\U0001FA00-\U0001FAFF"     # extended-A
    "\U00002600-\U000027BF"     # misc symbols + dingbats (☀ ✨ ✔ ❤)
    "\U0001F000-\U0001F02F"     # mahjong/dominoes/cards
    "\U0001F1E6-\U0001F1FF"     # regional indicators (flags)
    "\U0001F900-\U0001F9FF"     # supplemental symbols
    "\U00002700-\U000027BF"     # dingbats
    "]+",
    flags=re.UNICODE,
)


@lru_cache(maxsize=1)
def _load_vocab() -> dict:
    """Load forbidden_vocab.json (cache 1 lần)."""
    return _load_json_file("forbidden_vocab.json")


@lru_cache(maxsize=1)
def _get_scoring_vocab() -> list[str]:
    """Vocab Backend Scoring nội bộ — TUYỆT ĐỐI cấm."""
    data = _load_vocab()
    return data.get("scoring_internal", {}).get("keywords", [])


@lru_cache(maxsize=1)
def _get_rewrite_mapping() -> dict[str, str]:
    """English → Việt mapping."""
    data = _load_vocab()
    return data.get("english_to_vietnamese", {}).get("mapping", {})


def check_drift(text: str) -> list[str]:
    """Trả list vocab cấm tìm thấy trong text.

    Args:
        text: Bot response candidate

    Returns:
        List vocab vi phạm (có thể empty). Match case-insensitive
        substring.

    Note: dùng cho LOG + flag drift. Caller (conversation orchestrator)
    nên gọi auto_rewrite() để fix output trước khi gửi dealer.
    """
    if not text or not isinstance(text, str):
        return []
    violations: list[str] = []
    text_lower = text.lower()
    # Scoring vocab
    for vocab in _get_scoring_vocab():
        if vocab.lower() in text_lower:
            violations.append(vocab)
    # English vocab (cũng count vào drift để log)
    for english_vocab in _get_rewrite_mapping().keys():
        if english_vocab.lower() in text_lower:
            violations.append(english_vocab)
    return violations


def has_forbidden_scoring_vocab(text: str) -> bool:
    """True nếu text chứa scoring vocab (Tier/C-score/...).

    Đây là drift NGHIÊM TRỌNG — admin queue trigger.
    Khác với English vocab (chỉ là drift nhẹ, auto-rewrite xử được).
    """
    if not text:
        return False
    text_lower = text.lower()
    for vocab in _get_scoring_vocab():
        if vocab.lower() in text_lower:
            return True
    return False


def auto_rewrite(text: str) -> str:
    """Auto-rewrite vocab cấm:
    - English vocab → Việt thuần (vd "BRANDKIT" → "bộ thương hiệu")
    - Scoring vocab → REMOVE (xóa khỏi text)

    Args:
        text: Bot response

    Returns:
        Text đã rewrite. Multi-space sau REMOVE được collapse về 1.
    """
    if not text or not isinstance(text, str):
        return text

    result = text

    # 1. REWRITE English → Việt (case-sensitive replace để giữ
    # capitalization context — nhưng vocab dài hơn được thay trước)
    mapping = _get_rewrite_mapping()
    # Sort by length desc để "Mini App" thay trước "App" (nếu có)
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    for english in sorted_keys:
        if english.lower() in result.lower():
            # Case-insensitive replace, giữ Việt hóa form
            pattern = re.compile(re.escape(english), re.IGNORECASE)
            result = pattern.sub(mapping[english], result)

    # 2. REMOVE scoring vocab
    for vocab in _get_scoring_vocab():
        pattern = re.compile(r"\b" + re.escape(vocab) + r"\b", re.IGNORECASE)
        if pattern.search(result):
            logger.warning(
                "Drift REMOVE scoring vocab: %r trong text: %r",
                vocab, text[:200],
            )
            result = pattern.sub("", result)

    # 3. Trim emoji (CORE B.4 luật #5: max 1 emoji/reply)
    result = trim_emojis(result, max_count=1)

    # 4. Collapse multi-space + strip stray punctuation
    result = re.sub(r"\s+", " ", result).strip()
    # Bỏ space trước dấu câu
    result = re.sub(r"\s+([,.!?;:])", r"\1", result)
    return result


def count_emojis(text: str) -> int:
    """Đếm số ký tự emoji trong text (Phase 6 R+ fix — CORE B.4 luật #5).

    1 cụm emoji liên tiếp (vd "🌷✨") count = 2 (mỗi ký tự là 1 emoji).
    Skin tone modifier + ZWJ KHÔNG count riêng (1 family emoji = 1).
    """
    if not text or not isinstance(text, str):
        return 0
    matches = _EMOJI_PATTERN.findall(text)
    # Mỗi match có thể chứa nhiều emoji liên tiếp — count từng char
    total = sum(len(m) for m in matches)
    return total


def trim_emojis(text: str, max_count: int = 1) -> str:
    """Giảm số emoji xuống tối đa max_count (giữ emoji ĐẦU TIÊN, drop sau).

    CORE B.4 luật #5: tối đa 1 emoji/reply.

    Args:
        text: Bot reply candidate
        max_count: Số emoji tối đa cho phép (default 1 theo CORE)

    Returns:
        Text với ≤ max_count emoji. Emoji thừa bị xóa, whitespace cleanup.
    """
    if not text or count_emojis(text) <= max_count:
        return text

    # Iterate qua emoji, giữ max_count đầu, drop rest
    kept = 0
    result_chars: list[str] = []
    for char in text:
        if _EMOJI_PATTERN.match(char):
            if kept < max_count:
                result_chars.append(char)
                kept += 1
            # else drop
        else:
            result_chars.append(char)
    result = "".join(result_chars)
    # Cleanup: collapse multi-space + strip space trước dấu câu
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"\s+([,.!?;:])", r"\1", result)
    logger.info(
        "Drift trim emoji: %d → %d (text head=%r)",
        count_emojis(text), kept, text[:60],
    )
    return result


def check_parrot(
    bot_reply: str,
    dealer_message: str,
    min_ngram: int = 5,
) -> bool:
    """True nếu bot_reply lặp y nguyên đoạn ≥ min_ngram từ liên tiếp từ
    dealer_message (CORE B.4 luật #2 — KHÔNG lặp y nguyên).

    Args:
        bot_reply: Reply candidate của bot
        dealer_message: Message vừa nhận từ dealer
        min_ngram: Số từ liên tiếp tối thiểu để coi là parrot. Default 5
            (4 từ thường là tên riêng địa danh: "Quận 1 TP HCM", "Khu CN
            Sóng Thần"). 5+ từ liên tiếp lặp là parrot cấu trúc câu rõ.

    Returns:
        True nếu phát hiện parrot. False nếu OK.

    Example:
        dealer: "anh ở Hà Nội"
        bot 1: "Dạ Hà Nội — em ghi nhận" (2 từ trùng → OK)
        bot 2: "Dạ anh ở Hà Nội em ghi nhận anh ở Hà Nội." (5+ từ lặp → PARROT)
    """
    if not bot_reply or not dealer_message:
        return False

    def _normalize(s: str) -> list[str]:
        s = re.sub(r"[,.!?;:\"'\(\)\[\]]", " ", s.lower())
        return [w for w in s.split() if w]

    bot_words = _normalize(bot_reply)
    dealer_words = _normalize(dealer_message)

    if len(dealer_words) < min_ngram or len(bot_words) < min_ngram:
        return False

    # Build set of n-gram từ dealer
    dealer_ngrams = set()
    for i in range(len(dealer_words) - min_ngram + 1):
        ngram = tuple(dealer_words[i : i + min_ngram])
        dealer_ngrams.add(ngram)

    # Check bot có ngram nào match dealer không
    for i in range(len(bot_words) - min_ngram + 1):
        ngram = tuple(bot_words[i : i + min_ngram])
        if ngram in dealer_ngrams:
            logger.warning(
                "Drift parrot: bot lặp %d-gram từ dealer: %r",
                min_ngram, " ".join(ngram),
            )
            return True
    return False


def clear_cache() -> None:
    """Clear lru_cache — dùng cho test."""
    _load_vocab.cache_clear()
    _get_scoring_vocab.cache_clear()
    _get_rewrite_mapping.cache_clear()
