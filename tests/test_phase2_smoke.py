"""Phase 2 smoke tests — API + Services.

Tests the full stack: main_v2 app → routes → services → store → DB.
Uses FastAPI TestClient (no network needed).
"""
from __future__ import annotations

import os
import sys

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"

from app.core.config_v2 import Settings, reset_settings

reset_settings()

from fastapi.testclient import TestClient
from app.main_v2 import create_app


def _app():
    reset_settings()
    settings = Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        session_token_secret="test-secret",
        admin_api_token="test-admin",
    )
    return create_app(settings)


def test_health():
    app = _app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["version"] == "2.0.0"
    print("  [OK] GET /health")


def test_api_health():
    app = _app()
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["db"] == "ok"
    print("  [OK] GET /api/v1/health")


def test_create_session():
    app = _app()
    client = TestClient(app)
    resp = client.post("/api/v1/sessions", json={"channel": "web_text"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["session_id"].startswith("ses_")
    assert len(data["session_token"]) > 20
    assert data["status"] == "ACTIVE"
    assert data["workflow_state"] == "SESSION_STARTED"
    print("  [OK] POST /api/v1/sessions")
    return data


def test_hydrate_session():
    app = _app()
    client = TestClient(app)

    # Create session
    create_resp = client.post("/api/v1/sessions", json={"channel": "web_text"})
    session = create_resp.json()["data"]

    # Hydrate without auth -> 401
    resp = client.get(f"/api/v1/sessions/{session['session_id']}")
    assert resp.status_code == 401

    # Hydrate with auth -> 200
    resp = client.get(
        f"/api/v1/sessions/{session['session_id']}",
        headers={"Authorization": f"Bearer {session['session_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["session_id"] == session["session_id"]
    assert data["status"] == "ACTIVE"
    assert data["recent_events"] == []
    assert data["profile_snapshot"]["profile_id"] is not None
    print("  [OK] GET /api/v1/sessions/{id} (auth)")


def test_send_message():
    app = _app()
    client = TestClient(app)

    # Create session
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    token = session["session_token"]
    sid = session["session_id"]

    # Send without idempotency key -> 400
    resp = client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400

    # Send with idempotency key -> 200
    resp = client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "Toi la Hung, xuong Hung Phat"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "key-001",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["turn_id"].startswith("turn_")
    assert data["session_id"] == sid
    assert len(data["events"]) >= 1
    assert data["events"][0]["source"] == "linh_mkt"
    assert data["events"][0]["text"]  # stub reply should be non-empty
    assert data["next_cursor"]
    print(f"  [OK] POST /api/v1/sessions/{{id}}/messages (reply: {data['events'][0]['text'][:50]}...)")

    # Idempotency replay -> same response
    resp2 = client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "Toi la Hung, xuong Hung Phat"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "key-001",
        },
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["data"]["turn_id"] == data["turn_id"]
    print("  [OK] Idempotency replay (same key, same payload)")

    # Idempotency conflict -> 409
    resp3 = client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "Different message"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "key-001",
        },
    )
    assert resp3.status_code == 409
    print("  [OK] Idempotency conflict (same key, different payload) -> 409")


def test_poll_events():
    app = _app()
    client = TestClient(app)

    session = client.post("/api/v1/sessions", json={}).json()["data"]
    token = session["session_token"]
    sid = session["session_id"]

    # Poll empty
    resp = client.get(
        f"/api/v1/sessions/{sid}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["events"] == []

    # Send a message
    client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "test"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "poll-key-1",
        },
    )

    # Poll again -> should have events
    resp = client.get(
        f"/api/v1/sessions/{sid}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    events = resp.json()["data"]["events"]
    # 1 user message + 1 bot message
    assert len(events) >= 1
    print(f"  [OK] GET /api/v1/sessions/{{id}}/events ({len(events)} events)")


def test_admin_review():
    app = _app()
    client = TestClient(app)

    # No admin token -> 401
    resp = client.get("/api/v1/admin/review-items")
    assert resp.status_code == 401

    # With admin token -> 200 (empty list)
    resp = client.get(
        "/api/v1/admin/review-items",
        headers={"X-Admin-Token": "test-admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []
    print("  [OK] GET /api/v1/admin/review-items (admin auth)")


def main():
    print("Phase 2 Smoke Tests")
    print("=" * 50)
    test_health()
    test_api_health()
    test_create_session()
    test_hydrate_session()
    test_send_message()
    test_poll_events()
    test_admin_review()
    print("=" * 50)
    print("ALL PHASE 2 TESTS PASSED [OK]")


if __name__ == "__main__":
    main()
