"""Playbook loader — đọc các file .md để inject vào system prompt LLM."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PLAYBOOK_DIR = Path(__file__).parent


@lru_cache
def load_playbook() -> str:
    """Đọc tất cả .md trong thư mục này, ghép thứ tự alphabet.

    Cache một lần — nếu sửa .md cần restart server (để team biết).
    """
    parts: list[str] = []
    for fname in sorted(PLAYBOOK_DIR.glob("*.md")):
        content = fname.read_text(encoding="utf-8").strip()
        parts.append(content)
    return "\n\n---\n\n".join(parts)
