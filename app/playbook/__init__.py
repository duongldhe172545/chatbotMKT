"""Playbook loader — đọc các file .md để inject vào system prompt LLM.

Sau khi refactor: chỉ load 3 file domain knowledge essential (chính tả,
viết tắt slang, red flags). Các file persona/principles/scenarios/examples/
intake_flow được merge vào prompts.py body để giảm trùng lặp.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PLAYBOOK_DIR = Path(__file__).parent

# Chỉ load 3 file domain knowledge — không load file persona/rule
# (đã chuyển vào prompts.py để tránh duplicate, giảm size 50%).
_ESSENTIAL_FILES = (
    "04_vn_language.md",      # bẫy chính tả + cụm từ chuẩn
    "06_abbreviations_slang.md",  # giải mã viết tắt dealer
    "02_red_flags.md",        # xử mềm red flags
)


@lru_cache
def load_playbook() -> str:
    """Đọc 3 file domain knowledge. Persona/rule đã ở prompts.py body."""
    parts: list[str] = []
    for fname in _ESSENTIAL_FILES:
        path = PLAYBOOK_DIR / fname
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)
