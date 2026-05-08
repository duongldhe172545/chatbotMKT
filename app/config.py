"""Đọc .env và factory ra adapter đúng provider — đổi backend chỉ bằng env.

Singleton tường minh thay vì @lru_cache để dễ reset trong test/maintenance.
Khi đổi env, gọi reset_singletons() (hoặc đơn giản restart server).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from app.core.chat_replier import ChatReplier
from app.core.conversation import ConversationService
from app.core.extractor import Extractor
from app.core.replier import Replier
from app.llm.base import LLMProvider
from app.llm.claude import ClaudeProvider
from app.storage.base import StorageAdapter
from app.storage.sqlite_store import SQLiteStore

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ---------- Singletons (lazy init) ----------
_llm: LLMProvider | None = None
_storage: StorageAdapter | None = None
_conversation: ConversationService | None = None


def _build_llm() -> LLMProvider:
    provider = _env("LLM_PROVIDER", "claude").lower()
    model = _env("LLM_MODEL", "claude-sonnet-4-6")

    if provider == "claude":
        api_key = _env("ANTHROPIC_API_KEY")
        return ClaudeProvider(api_key=api_key, model=model)

    raise ValueError(f"LLM provider chưa hỗ trợ: {provider}")


def _build_storage() -> StorageAdapter:
    adapter = _env("STORAGE_ADAPTER", "sqlite").lower()
    if adapter == "sqlite":
        path = _env("SQLITE_PATH", "data/dealers.db")
        return SQLiteStore(db_path=path)
    raise ValueError(f"Storage adapter chưa hỗ trợ: {adapter}")


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm


def get_storage() -> StorageAdapter:
    global _storage
    if _storage is None:
        _storage = _build_storage()
    return _storage


def use_replier() -> bool:
    """Bước 1 refactor flag — bật để dùng Replier mới (tách khỏi Extractor).

    Mặc định FALSE (giữ nguyên flow cũ) để A/B test an toàn. Đặt
    USE_REPLIER=true trong .env để bật path mới.
    """
    return _env("USE_REPLIER", "false").lower() in ("1", "true", "yes", "on")


def get_conversation_service() -> ConversationService:
    global _conversation
    if _conversation is None:
        llm = get_llm()
        replier = Replier(llm=llm) if use_replier() else None
        _conversation = ConversationService(
            extractor=Extractor(llm=llm),
            storage=get_storage(),
            chat_replier=ChatReplier(llm=llm),
            replier=replier,
        )
    return _conversation


def reset_singletons() -> None:
    """Reset cache khi cần reload (vd: test, hot config). Production cứ restart server."""
    global _llm, _storage, _conversation
    _llm = None
    _storage = None
    _conversation = None


# ---------- Server config ----------
def get_server_config() -> tuple[str, int]:
    host = _env("HOST", "127.0.0.1")
    try:
        port = int(_env("PORT", "8000"))
    except ValueError:
        port = 8000  # fallback nếu env có giá trị bậy
    return host, port
