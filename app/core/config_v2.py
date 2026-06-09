"""App config — LINHMKT dataclass pattern.

Replaces the old Pydantic BaseSettings config with a plain dataclass
that reads from environment variables via os.getenv().

The old config at app/config.py is renamed to app/config_legacy.py
for backward compatibility during migration. New code should import
from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Em Linh MKT v2 — Parlant-style settings."""

    app_env: str = "local"
    app_base_url: str = "http://127.0.0.1:8000"

    # Database
    database_url: str = "sqlite:///./data/chatbot_v2.sqlite3"

    # Security
    session_token_secret: str = "local-dev-change-me"
    admin_api_token: str = "local-admin-token"

    # LLM
    gemini_api_key: str = ""
    llm_fast: str = "gemini-3.1-flash-lite"
    llm_quality: str = "gemini-3.1-flash-lite"

    # Conversation
    active_rules_version: str = "v2.0"
    conversation_runtime: str = "parlant_local"  # parlant_local | stub

    # Logo
    logo_provider: str = "local"
    logo_image_model: str = "imagen-4.0-ultra-generate-001"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Admin
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # CORS
    cors_allowed_origins: str = "*"

    # Session
    session_timeout_s: int = 999 * 24 * 3600  # ~infinite

    # Rate limits
    rate_limit_ip_per_hour: int = 5
    rate_limit_msg_per_minute: int = 30

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_sweep_interval_s: int = 300

    # Feature flags
    feature_voice_input: bool = True
    feature_long_poll_events: bool = True

    # Zalo
    zalo_cta_enabled: bool = True
    zalo_group_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables with validation."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            sqlite_path = os.getenv("SQLITE_PATH")
            if sqlite_path:
                if sqlite_path.startswith("sqlite:///"):
                    db_url = sqlite_path
                else:
                    db_url = f"sqlite:///{sqlite_path}"
            else:
                db_url = cls.database_url

        settings = cls(
            app_env=os.getenv("APP_ENV", cls.app_env),
            app_base_url=os.getenv("APP_BASE_URL", cls.app_base_url),
            database_url=db_url,
            session_token_secret=os.getenv("SESSION_TOKEN_SECRET", cls.session_token_secret),
            admin_api_token=os.getenv("ADMIN_API_TOKEN", cls.admin_api_token),
            gemini_api_key=os.getenv("GEMINI_API_KEY", cls.gemini_api_key),
            llm_fast=os.getenv("LLM_FAST", cls.llm_fast),
            llm_quality=os.getenv("LLM_QUALITY", cls.llm_quality),
            active_rules_version=os.getenv("ACTIVE_RULES_VERSION", cls.active_rules_version),
            conversation_runtime=os.getenv("CONVERSATION_RUNTIME", cls.conversation_runtime),
            logo_provider=os.getenv("LOGO_PROVIDER", cls.logo_provider),
            logo_image_model=os.getenv("LOGO_IMAGE_MODEL", cls.logo_image_model),
            host=os.getenv("HOST", cls.host),
            port=int(os.getenv("PORT", str(cls.port))),
            admin_username=os.getenv("ADMIN_USERNAME", cls.admin_username),
            admin_password=os.getenv("ADMIN_PASSWORD", cls.admin_password),
            cors_allowed_origins=os.getenv("CORS_ALLOWED_ORIGINS", cls.cors_allowed_origins),
            session_timeout_s=int(os.getenv("SESSION_TIMEOUT_S", str(cls.session_timeout_s))),
            rate_limit_ip_per_hour=int(os.getenv("RATE_LIMIT_IP_PER_HOUR", str(cls.rate_limit_ip_per_hour))),
            rate_limit_msg_per_minute=int(os.getenv("RATE_LIMIT_MSG_PER_MINUTE", str(cls.rate_limit_msg_per_minute))),
            scheduler_enabled=_env_bool("SCHEDULER_ENABLED", cls.scheduler_enabled),
            scheduler_sweep_interval_s=int(os.getenv("SCHEDULER_SWEEP_INTERVAL_S", str(cls.scheduler_sweep_interval_s))),
            feature_voice_input=_env_bool("FEATURE_VOICE_INPUT", cls.feature_voice_input),
            feature_long_poll_events=_env_bool("FEATURE_LONG_POLL_EVENTS", cls.feature_long_poll_events),
            zalo_cta_enabled=_env_bool("ZALO_CTA_ENABLED", cls.zalo_cta_enabled),
            zalo_group_url=os.getenv("ZALO_GROUP_URL"),
        )
        settings.validate()
        return settings

    @property
    def sqlite_path(self) -> str:
        """Extract the file path from the DATABASE_URL.

        Supports:
            sqlite:///./data/chatbot.db  → PROJECT_ROOT/data/chatbot.db
            sqlite:///:memory:           → :memory:
        """
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError(f"Only sqlite:/// DATABASE_URL is supported. Got: {self.database_url}")

        raw_path = self.database_url[len(prefix):]
        if raw_path == ":memory:":
            return raw_path

        path = Path(raw_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)

    def validate(self) -> None:
        """Validate settings for production readiness."""
        if self.app_env == "production" and self.session_token_secret == "local-dev-change-me":
            raise ValueError("SESSION_TOKEN_SECRET must be set in production.")
        if self.app_env == "production" and self.admin_api_token == "local-admin-token":
            raise ValueError("ADMIN_API_TOKEN must be set in production.")
        if self.app_env == "production" and not self.zalo_group_url:
            raise ValueError("ZALO_GROUP_URL must be set before production launch.")


def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean from environment variable."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


# Module-level singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the settings singleton.

    For new code, prefer dependency injection over this global accessor.
    """
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """Reset singleton — for tests."""
    global _settings
    _settings = None
