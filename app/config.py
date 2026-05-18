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

    # ----- LLM (full Gemini Phase 1, refer STRATEGY D8) -----
    GEMINI_API_KEY: str = ""
    LLM_FAST: str = "gemini-2.5-flash"
    LLM_QUALITY: str = "gemini-2.5-pro"
    # Phase 2+ fallback
    ANTHROPIC_API_KEY: Optional[str] = None

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
    SESSION_TIMEOUT_S: int = 3600
    RATE_LIMIT_IP_PER_HOUR: int = 5
    RATE_LIMIT_MSG_PER_MINUTE: int = 30


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton — cache config sau lần đọc đầu tiên."""
    return Settings()


def reset_settings() -> None:
    """Reset singleton (test helper)."""
    get_settings.cache_clear()
