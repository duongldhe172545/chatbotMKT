"""App config — Pydantic Settings load từ .env.

Refer:
- .env.example v8 — mọi env var
- STRATEGY D8 — LLM_FAST/LLM_QUALITY tier abstraction
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Em Linh MKT v8 settings.

    Load từ .env file. Refer .env.example cho default values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- LLM (Gemini runtime, refer STRATEGY D8) -----
    GEMINI_API_KEY: str = ""
    LLM_FAST: str = "gemini-2.5-flash"
    LLM_QUALITY: str = "gemini-2.5-pro"

    # ----- Conversation engine rollout -----
    # legacy: existing slot/state-machine flow.
    # planner_shadow: run legacy response, call planner only for logs/tests.
    # planner: intermediate planner-first ASKING engine.
    # llm_first: Quynh-style full-context conversation brain for ASKING.
    CONVERSATION_ENGINE: str = "legacy"

    # ----- Storage -----
    SQLITE_PATH: str = "data/chatbot.db"

    # ----- Server -----
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # ----- Admin (HTTP Basic) -----
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "changeme"

    # ----- CORS -----
    CORS_ALLOWED_ORIGINS: str = "*"

    # ----- Session / rate limit (F2C.1, F2C.2) -----
    # Phase 6 R+ 2026-05-22 (user feedback): set timeout = 999 ngày
    # (effectively vĩnh viễn) — dealer có thể quay lại session bất kỳ lúc.
    # Session chỉ DONE qua: (1) confirm card → CONFIRMING/DONE, (2) escalate L3.
    SESSION_TIMEOUT_S: int = 999 * 24 * 3600  # 999 ngày ≈ vĩnh viễn
    RATE_LIMIT_IP_PER_HOUR: int = 5
    RATE_LIMIT_MSG_PER_MINUTE: int = 30

    # ----- Background scheduler (Phase 4 R1 + Phase 5 R5) -----
    # 2026-05-22: tắt sweep auto-close session (timeout = vĩnh viễn).
    # Giữ scheduler chạy cho NUDGE_PENDING (3 phút sau Card render) — đó
    # là behavior khác (nhắc dealer xác nhận card, KHÔNG close session).
    SCHEDULER_ENABLED: bool = True            # False để tắt khi test
    SCHEDULER_SWEEP_INTERVAL_S: int = 300     # 5 phút sweep nudge (không close session)
    SESSION_TIMEOUT_NUDGE_CARD_S: int = 180   # 3 phút sau Card render → mark NUDGE_PENDING (1C § 9)
    SESSION_TIMEOUT_CONFIRMING_S: int = 600   # 10 phút CONFIRMING im → soft-close (1C § 9 — vẫn close stage CONFIRMING)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton — cache config sau lần đọc đầu tiên."""
    return Settings()


def reset_settings() -> None:
    """Reset singleton (test helper)."""
    get_settings.cache_clear()
