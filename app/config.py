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
# 2 LLM client riêng cho Extractor + Replier để dùng model khác nhau:
# Extractor (trích field) — có thể Haiku (rẻ, nhanh).
# Replier (sinh reply) — nên Sonnet (quality persona).
_llm_extractor: LLMProvider | None = None
_llm_replier: LLMProvider | None = None
_storage: StorageAdapter | None = None
_conversation: ConversationService | None = None


def _build_llm(model: str) -> LLMProvider:
    provider = _env("LLM_PROVIDER", "claude").lower()
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


# LLM_MODEL = backward-compat fallback nếu EXTRACTOR_MODEL/REPLIER_MODEL
# không set. Khuyến nghị set 2 biến riêng để optimize cost/speed.
_DEFAULT_MODEL = "claude-sonnet-4-6"


def _extractor_model() -> str:
    return _env("EXTRACTOR_MODEL") or _env("LLM_MODEL") or _DEFAULT_MODEL


def _replier_model() -> str:
    return _env("REPLIER_MODEL") or _env("LLM_MODEL") or _DEFAULT_MODEL


def get_llm_extractor() -> LLMProvider:
    global _llm_extractor
    if _llm_extractor is None:
        _llm_extractor = _build_llm(_extractor_model())
    return _llm_extractor


def get_llm_replier() -> LLMProvider:
    global _llm_replier
    if _llm_replier is None:
        _llm_replier = _build_llm(_replier_model())
    return _llm_replier


def get_llm() -> LLMProvider:
    """Backward compat — trả LLM Replier (mặc định cho chat_replier)."""
    return get_llm_replier()


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
        llm_ex = get_llm_extractor()
        llm_re = get_llm_replier()
        replier = Replier(llm=llm_re) if use_replier() else None
        _conversation = ConversationService(
            extractor=Extractor(llm=llm_ex),
            storage=get_storage(),
            chat_replier=ChatReplier(llm=llm_re),
            replier=replier,
        )
    return _conversation


def reset_singletons() -> None:
    """Reset cache khi cần reload (vd: test, hot config). Production cứ restart server."""
    global _llm_extractor, _llm_replier, _storage, _conversation
    _llm_extractor = None
    _llm_replier = None
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
