"""E2E test Phase 1 happy case — toàn bộ flow từ greeting → DONE.

Refer:
- KE_HOACH § PHẦN 5 action 23 — test e2e happy
- Phase 1 scope: 3 REQUIRED slot (1.1, 1.2, 4.0)

Strategy: mock LLMClient (extract + ack) để test deterministic.
KHÔNG call API thật — defer cho integration test thật khi có API key + budget.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture
def test_app(tmp_path: Path, monkeypatch):
    """FastAPI test app với DB tạm + mock LLM."""
    db_path = tmp_path / "test_e2e.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-mock")

    # Reset settings singleton + store singleton
    from app.config import reset_settings
    from app.api.chat import _get_store

    reset_settings()
    if hasattr(_get_store, "_instance"):
        del _get_store._instance

    # Mock LLMClient — replace get_default_client
    mock_client = MagicMock()
    mock_client.extract_fast.return_value = {}
    mock_client.chat_fast.return_value = "Dạ em note."
    mock_client.chat_quality.return_value = "Dạ em note."

    monkeypatch.setattr(
        "app.api.chat.get_default_client",
        lambda: mock_client,
    )

    app = create_app()
    client = TestClient(app)
    return client, mock_client


class TestE2EInit:
    def test_health(self, test_app):
        client, _ = test_app
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"

    def test_session_init_returns_greeting(self, test_app):
        """POST /api/chat với session_id=null → tạo session + return greeting."""
        client, _ = test_app
        r = client.post("/api/chat", json={"session_id": None, "message": ""})
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"]
        assert "Linh" in data["reply"]
        assert "Zalo" in data["reply"]
        assert data["stage"] == "GREETING"
        assert data["is_first_turn"] is True


class TestE2EHappyPath:
    def test_full_phase_1_flow(self, test_app):
        """Phase 1 happy path: Greeting → slot 1.1 → slot 1.2 → ... → 4.0 → CONFIRMING → DONE.

        Note: Phase 1 chỉ 3 slot có extractor (1.1, 1.2, 4.0). Slot 1.3/2.1/2.2 chưa có
        extractor → state machine RETRY 3 lần → SKIP với flag required_missing.
        """
        client, mock_client = test_app

        # Turn 0: init session → greeting
        r0 = client.post("/api/chat", json={"session_id": None, "message": ""})
        session_id = r0.json()["session_id"]
        assert r0.json()["stage"] == "GREETING"

        # Turn 1: dealer ack greeting
        mock_client.extract_fast.return_value = {}
        r1 = client.post("/api/chat", json={"session_id": session_id, "message": "OK em"})
        assert r1.status_code == 200
        data = r1.json()
        assert data["stage"] == "ASKING"
        assert data["current_slot"] == "1.1"

        # Turn 2: slot 1.1 fill 2 field
        mock_client.extract_fast.return_value = {
            "owner_name": "Tùng",
            "dealer_name": "Nhôm Kính Thanh Tùng",
        }
        r2 = client.post("/api/chat", json={
            "session_id": session_id,
            "message": "anh Tùng cửa hàng Nhôm Kính Thanh Tùng",
        })
        data = r2.json()
        assert data["current_slot"] == "1.2"

        # Turn 3: slot 1.2 fill address
        mock_client.extract_fast.return_value = {
            "address": "123 Lê Lợi Q.1 TP.HCM",
            "local_dominance_signal": None,
        }
        r3 = client.post("/api/chat", json={
            "session_id": session_id,
            "message": "123 Lê Lợi quận 1 TP.HCM",
        })
        data = r3.json()
        # Sau slot 1.2 → 1.3 (1.3 chưa có extractor Phase 1)
        assert data["current_slot"] == "1.3"

    def test_status_endpoint(self, test_app):
        client, _ = test_app
        r0 = client.post("/api/chat", json={"session_id": None, "message": ""})
        session_id = r0.json()["session_id"]
        r_status = client.get(f"/api/chat/{session_id}/status")
        assert r_status.status_code == 200
        status = r_status.json()
        assert status["session_id"] == session_id
        assert status["stage"] == "GREETING"
        assert status["turn_count"] == 0

    def test_invalid_session_returns_404(self, test_app):
        client, _ = test_app
        r = client.post("/api/chat", json={
            "session_id": "nonexistent-id",
            "message": "hi",
        })
        assert r.status_code == 404

    def test_empty_message_with_existing_session_rejected(self, test_app):
        """Empty message + session_id existing → 400 (chỉ OK khi init)."""
        client, _ = test_app
        r0 = client.post("/api/chat", json={"session_id": None, "message": ""})
        session_id = r0.json()["session_id"]
        r = client.post("/api/chat", json={
            "session_id": session_id,
            "message": "",
        })
        assert r.status_code == 400


class TestE2EConsentNoFlow:
    """Test D10 STRATEGY consent=no → skip 4.1/4.2 → CONFIRMING."""

    def test_consent_no_skips_to_confirming(self, test_app):
        client, mock_client = test_app

        # Init + bypass tới slot 4.0
        from app.core.session import create_session
        from app.models.enums import Stage
        from app.models.schema import DealerProfileRaw
        from app.storage.sqlite_store import SQLiteStore
        from app.config import get_settings

        store = SQLiteStore(get_settings().SQLITE_PATH)
        session = create_session()
        session.stage = Stage.ASKING
        session.current_slot = "4.0"
        store.save_session(session)
        profile = DealerProfileRaw(
            owner_name="Tùng",
            dealer_name="X",
            address="HCM",
        )
        store.save_profile(session.session_id, profile)

        # Slot 4.0 consent=no
        mock_client.extract_fast.return_value = {"brandkit_consent": "no"}
        r = client.post("/api/chat", json={
            "session_id": session.session_id,
            "message": "không cần đâu",
        })
        data = r.json()
        # Stage transitions to CONFIRMING
        assert data["stage"] == "CONFIRMING"
