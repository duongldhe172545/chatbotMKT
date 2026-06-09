"""Phase 1 smoke tests — verify core infrastructure modules work correctly."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_ids():
    from app.core.ids import new_id, new_session_token, utc_now_iso

    # new_id produces prefixed IDs
    sid = new_id("ses")
    assert sid.startswith("ses_"), f"Expected ses_ prefix, got {sid}"
    assert len(sid) > 10, f"ID too short: {sid}"

    mid = new_id("msg")
    assert mid.startswith("msg_"), f"Expected msg_ prefix, got {mid}"

    # Uniqueness
    assert new_id("x") != new_id("x"), "IDs should be unique"

    # Session token
    token = new_session_token()
    assert len(token) > 20, f"Token too short: {token}"

    # UTC ISO
    ts = utc_now_iso()
    assert ts.endswith("Z"), f"Expected Z suffix, got {ts}"
    assert "T" in ts, f"Expected ISO format, got {ts}"

    print("  ✓ ids.py OK")


def test_security():
    from app.core.security import extract_bearer_token, hash_client_signal, hash_token

    # Hash token
    h = hash_token("my-token", "my-secret")
    assert isinstance(h, str) and len(h) == 64, f"Expected 64-char hex, got {h}"

    # Same input → same hash
    h2 = hash_token("my-token", "my-secret")
    assert h == h2, "Same input should produce same hash"

    # Different input → different hash
    h3 = hash_token("other-token", "my-secret")
    assert h != h3, "Different input should produce different hash"

    # hash_client_signal
    assert hash_client_signal(None, "s") is None
    assert hash_client_signal("", "s") is None
    assert hash_client_signal("1.2.3.4", "s") is not None

    # extract_bearer_token
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("") is None
    assert extract_bearer_token("Basic abc") is None
    assert extract_bearer_token("Bearer") is None
    assert extract_bearer_token("Bearer my-token") == "my-token"
    assert extract_bearer_token("bearer MY-TOKEN") == "MY-TOKEN"

    print("  ✓ security.py OK")


def test_responses():
    from app.core.responses import error_response, success_envelope

    # Success envelope
    env = success_envelope({"foo": "bar"})
    assert env["ok"] is True
    assert env["data"]["foo"] == "bar"
    assert env["meta"]["request_id"].startswith("req_")
    assert env["meta"]["server_time"].endswith("Z")

    # Error response
    resp = error_response("not_found", "Not found", 404)
    assert resp.status_code == 404
    # Body is JSON
    import json
    body = json.loads(resp.body.decode())
    assert body["ok"] is False
    assert body["error"]["code"] == "not_found"
    assert body["meta"]["request_id"].startswith("req_")

    print("  ✓ responses.py OK")


def test_config():
    from app.core.config_v2 import Settings, reset_settings

    # Default settings
    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.conversation_runtime == "parlant_local"
    assert s.active_rules_version == "v2.0"

    # sqlite_path
    assert ":memory:" not in s.sqlite_path or s.database_url.endswith(":memory:")
    assert s.sqlite_path.endswith("chatbot_v2.sqlite3")

    # from_env with override
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    reset_settings()
    s2 = Settings.from_env()
    assert s2.app_env == "test"
    assert s2.sqlite_path == ":memory:"

    # Cleanup
    del os.environ["APP_ENV"]
    del os.environ["DATABASE_URL"]
    reset_settings()

    print("  ✓ config_v2.py OK")


def test_db_schema_and_connection():
    from app.db.connection import Database

    # In-memory DB
    db = Database(":memory:")
    db.initialize()

    # Health check
    assert db.health_check() is True

    # Verify tables exist
    conn = db.connect()
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        expected = [
            "admin_review_items",
            "conversation_turns",
            "dealer_identities",
            "dealer_profiles",
            "flags",
            "idempotency_records",
            "logo_briefs",
            "logo_issuances",
            "logo_jobs",
            "logo_outputs",
            "messages",
            "profile_corrections",
            "profile_field_events",
            "profile_fields",
            "session_access_tokens",
            "sessions",
        ]
        for t in expected:
            assert t in tables, f"Missing table: {t}"
        assert len(tables) >= len(expected), f"Expected ≥{len(expected)} tables, got {len(tables)}"
    finally:
        conn.close()

    print(f"  ✓ schema.py OK ({len(expected)} tables)")
    print("  ✓ connection.py OK")


def test_store_crud():
    from app.db.connection import Database
    from app.db.store import Store

    db = Database(":memory:")
    db.initialize()
    store = Store(db)

    with db.transaction() as conn:
        # Create session
        session = store.create_session(
            conn,
            channel="web",
            token_hash="hash123",
            ip_hash="ip_hash",
            user_agent_hash="ua_hash",
            metadata={"source": "test"},
        )
        assert session["id"].startswith("ses_")
        assert session["status"] == "ACTIVE"
        assert session["workflow_state"] == "SESSION_STARTED"
        assert session["channel"] == "web"

        # Token check
        assert store.token_is_active(conn, session_id=session["id"], token_hash="hash123")
        assert not store.token_is_active(conn, session_id=session["id"], token_hash="wrong")

        # Insert user message
        msg = store.insert_message(
            conn,
            session_id=session["id"],
            source="user",
            message_type="text",
            text="Tôi là Hùng, xưởng Hùng Phát",
        )
        assert msg["id"].startswith("msg_")
        assert msg["event_cursor"] == 1
        assert msg["source"] == "user"
        assert msg["text"] == "Tôi là Hùng, xưởng Hùng Phát"

        # Insert bot message
        bot_msg = store.insert_message(
            conn,
            session_id=session["id"],
            source="linh_mkt",
            message_type="text",
            text="Dạ chào anh Hùng!",
        )
        assert bot_msg["event_cursor"] == 2

        # Create turn
        turn = store.create_turn(
            conn,
            session_id=session["id"],
            user_message_id=msg["id"],
            active_rules_version="v2.0",
            backend_turn_trace={"phase": "test"},
            profile_snapshot={"profile_id": None},
            suggested_objective={"type": "collect_required_field", "target_field": "phone_or_zalo"},
            observations=["user_is_busy"],
            matched_guideline_ids=["tone_busy_user"],
        )
        assert turn["id"].startswith("turn_")
        assert turn["session_id"] == session["id"]

        # List messages
        messages = store.list_messages(conn, session_id=session["id"])
        assert len(messages) == 2

        # List after cursor
        messages_after = store.list_messages(conn, session_id=session["id"], after_cursor=1)
        assert len(messages_after) == 1
        assert messages_after[0]["event_cursor"] == 2

        # Latest cursor
        assert store.latest_cursor(conn, session_id=session["id"]) == 2

        # Touch session
        store.touch_session_after_message(conn, session_id=session["id"], workflow_state="COLLECTING_PROFILE")
        updated = store.get_session(conn, session["id"])
        assert updated["workflow_state"] == "COLLECTING_PROFILE"
        assert updated["last_message_at"] is not None

        # Idempotency
        assert store.get_idempotency_record(
            conn, session_id=session["id"], method="POST", path="/send", idempotency_key="key1"
        ) is None

        store.insert_idempotency_record(
            conn,
            session_id=session["id"],
            method="POST",
            path="/send",
            idempotency_key="key1",
            payload_hash="abc",
            response={"ok": True},
        )
        record = store.get_idempotency_record(
            conn, session_id=session["id"], method="POST", path="/send", idempotency_key="key1"
        )
        assert record is not None

    print("  ✓ store.py OK (session + message + turn + idempotency)")


def main():
    print("Phase 1 Smoke Tests")
    print("=" * 40)
    test_ids()
    test_security()
    test_responses()
    test_config()
    test_db_schema_and_connection()
    test_store_crud()
    print("=" * 40)
    print("ALL PHASE 1 TESTS PASSED ✓")


if __name__ == "__main__":
    main()
