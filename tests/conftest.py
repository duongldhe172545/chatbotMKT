"""Global test safety: standard pytest runs must never call paid providers."""
from __future__ import annotations

import os

import pytest


_LIVE_API_ENABLED = os.getenv("RUN_LIVE_API_TESTS") == "1"

# Set these before test modules import application settings. Environment values
# override the developer's local .env file.
if not _LIVE_API_ENABLED:
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["LOGO_GENERATION_MODE"] = "local"
os.environ["SCHEDULER_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def block_paid_api_calls(request, monkeypatch):
    """Fail a normal test if it reaches Gemini or Imagen, even if app code catches it."""
    is_live_test = request.node.get_closest_marker("live_api") is not None
    if is_live_test and _LIVE_API_ENABLED:
        yield
        return

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("LOGO_GENERATION_MODE", "local")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    from app.core.config_v2 import reset_settings
    from app.llm.client import reset_default_client
    from app.llm.gemini import GeminiProvider

    paid_calls: list[str] = []

    def _blocked_gemini_client(self):
        paid_calls.append(f"GeminiProvider:{getattr(self, 'model', 'unknown')}")
        raise AssertionError("Paid Gemini API call attempted during a standard test")

    def _blocked_image_client(*args, **kwargs):
        paid_calls.append("ImagenClient")
        raise AssertionError("Paid Imagen API call attempted during a standard test")

    monkeypatch.setattr(GeminiProvider, "_get_client", _blocked_gemini_client)
    try:
        from google import genai

        monkeypatch.setattr(genai, "Client", _blocked_image_client)
    except ImportError:
        pass

    reset_settings()
    reset_default_client()
    yield
    reset_settings()
    reset_default_client()

    assert not paid_calls, f"Paid API calls are forbidden in standard tests: {paid_calls}"
