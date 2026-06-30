"""Phase 5 smoke tests — Evidence, Trace, ProfileService, and Admin API integration.

Tests that profiles are persisted, facts are validated/upserted, turn traces
are fully populated with latency metrics, and the admin details endpoint returns trace logs.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from app.core.config_v2 import Settings
from app.db.connection import Database
from app.db.store import Store
from app.main_v2 import create_app
from app.services.chat_service import ChatService
from app.services.profile_service import ProfileService


def test_phase5_pipeline():
    print("\nPhase 5 Smoke Tests")
    print("==================================================")

    # 1. Initialize transient database
    settings = Settings(
        app_env="testing",
        database_url="sqlite:///:memory:",
        session_token_secret="test-secret-key-12345",
        admin_username="testadmin",
        admin_password="testpassword",
    )
    app = create_app(settings)
    client = TestClient(app)
    store = app.state.store

    # 2. Create session
    create_res = client.post("/api/v1/sessions", json={"channel": "web_text"})
    assert create_res.status_code == 200
    session_data = create_res.json()["data"]
    session_id = session_data["session_id"]
    token = session_data["session_token"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "idem-key-turn-1",
    }

    # 3. Send message that triggers regex extractor (Phone + Name)
    msg_res = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        headers=headers,
        json={
            "message_type": "text",
            "text": "Tôi tên Hùng, SĐT 0912345678, cửa hàng nhôm kính Hùng Phát",
            "client_message_id": "cmsg-1",
        },
    )
    assert msg_res.status_code == 200
    msg_data = msg_res.json()["data"]

    # 4. Verify DB profile persistence via ProfileService
    with store.database.transaction() as conn:
        profile_service = ProfileService(store, settings)
        snapshot = profile_service.get_profile_snapshot(conn, session_id)
        
        # Verify fields were successfully saved
        assert snapshot["profile_id"] is not None
        assert snapshot["required_fields"]["owner_name"] == "Hùng"
        assert snapshot["required_fields"]["phone_or_zalo"] == "0912345678"
        assert snapshot["required_fields"]["dealer_name"] == "nhôm kính Hùng Phát"
        
        # Verify auto-derives (hotline and contact_name)
        fields = store.get_profile_fields(conn, snapshot["profile_id"])
        field_map = {f["field_name"]: f["normalized_value"] for f in fields}
        assert field_map["contact_name"] == "Hùng"
        assert field_map["hotline"] == "0912345678"

        # Verify turn trace is logged with aggregation latencies and model ID
        turns = conn.execute("SELECT * FROM conversation_turns WHERE session_id = ?", (session_id,)).fetchall()
        assert len(turns) == 1
        turn = turns[0]
        assert turn["model_id"] in ("stub", "canned")
        assert turn["backend_latency_ms"] == 200
        assert turn["turn_aggregation_latency_ms"] >= 0  # stub turn có thể <1ms → 0
        assert turn["final_reply_hash"] is not None

    print("  ✓ ProfileService + persistence OK")
    print("  ✓ Auto-derivation OK")
    print("  ✓ Trace & latency metrics logging OK")

    # 5. Test Admin API /api/admin/sessions/{id} with HTTP Basic auth
    admin_auth = ("testadmin", "testpassword")
    
    # Detail session details endpoint
    detail_res = client.get(
        f"/api/admin/sessions/{session_id}",
        auth=admin_auth,
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["session_id"] == session_id
    assert detail["profile"]["owner_name"] == "Hùng"
    assert len(detail["turns"]) == 1
    assert detail["turns"][0]["backend_latency_ms"] == 200
    assert detail["turns"][0]["trace"]["extracted_fields"]["owner_name"] == "Hùng"
    
    print("  ✓ Admin detail endpoint + Basic Auth + Trace logs OK")

    # 6. Test Admin stats endpoint
    stats_res = client.get(
        "/api/admin/stats",
        auth=admin_auth,
    )
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_sessions"] == 1
    assert stats["by_stage"]["WAITING_REQUIRED_FIELD"] == 1
    
    print("  ✓ Admin stats endpoint OK")

    # 7. (Bỏ test Logo endpoint — cụm tự-gen-logo đã gỡ 2026-06-24)

    # 8. Test Export endpoints
    export_res = client.get(
        f"/api/admin/sessions/{session_id}/export",
        auth=admin_auth,
    )
    assert export_res.status_code == 200
    assert "text/markdown" in export_res.headers["content-type"]
    assert "Hùng" in export_res.text
    print("  ✓ Single session Markdown export OK")

    bulk_export_res = client.post(
        "/api/admin/sessions/export",
        json={"session_ids": [session_id]},
        auth=admin_auth,
    )
    assert bulk_export_res.status_code == 200
    assert "application/zip" in bulk_export_res.headers["content-type"]
    print("  ✓ Bulk session ZIP export OK")

    # 9. Test Optional Field Skip and Persistence flow
    # Pre-fill required fields for session_id in DB to trigger optional asks
    with store.database.transaction() as conn:
        profile_row = store.get_or_create_profile(conn, session_id)
        pid = profile_row["id"]
        required_fields = ["owner_name", "dealer_name", "address", "phone_or_zalo", "main_product", "business_model_signal"]
        for f in required_fields:
            store.upsert_profile_field(
                conn,
                profile_id=pid,
                field_name=f,
                raw_value="test",
                normalized_value="test",
                status="PROVIDED",
                source_type="test",
                confidence=1.0,
            )
        # FIX_GAP: 9 tiêu chí chạy SAU chốt → set consent + review_status=CONFIRMED
        store.upsert_profile_field(
            conn, profile_id=pid, field_name="brandkit_consent",
            raw_value="no", normalized_value="no", status="PROVIDED",
            source_type="test", confidence=1.0,
        )
        store.update_profile_status(
            conn, profile_id=pid, review_status="CONFIRMED",
            logo_issued_status=profile_row["logo_issued_status"],
        )

    # required + CONFIRMED → message bất kỳ → objective est_team_size (9 tiêu chí sau chốt)
    headers["Idempotency-Key"] = "idem-key-opt-ask-1"
    opt_res = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        headers=headers,
        json={
            "message_type": "text",
            "text": "Chào em",
            "client_message_id": "cmsg-opt-1",
        },
    )
    assert opt_res.status_code == 200

    # Verify via DB — sau khi từ chối brandkit, objective = est_team_size (C1-C9)
    with store.database.transaction() as conn:
        turns = conn.execute("SELECT suggested_objective_json FROM conversation_turns WHERE session_id = ? ORDER BY created_at DESC", (session_id,)).fetchall()
        assert len(turns) >= 2
        suggested_obj = json.loads(turns[0]["suggested_objective_json"])
        assert suggested_obj["type"] == "collect_optional_field"
        assert suggested_obj["target_field"] == "est_team_size"

    # User replies with refusal "không thích nói"
    headers["Idempotency-Key"] = "idem-key-opt-ask-2"
    refuse_res = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        headers=headers,
        json={
            "message_type": "text",
            "text": "không thích nói",
            "client_message_id": "cmsg-opt-2",
        },
    )
    assert refuse_res.status_code == 200

    # Verify that est_team_size and team_stability_signal are marked as SKIPPED in SQLite
    with store.database.transaction() as conn:
        fields = store.get_profile_fields(conn, pid)
        field_map = {f["field_name"]: f["status"] for f in fields}
        assert field_map["est_team_size"] == "SKIPPED"
        assert field_map["team_stability_signal"] == "SKIPPED"

    # Verify next suggested objective in DB is supplier_brands (next optional field)
    with store.database.transaction() as conn:
        turns = conn.execute("SELECT suggested_objective_json FROM conversation_turns WHERE session_id = ? ORDER BY created_at DESC", (session_id,)).fetchall()
        suggested_obj = json.loads(turns[0]["suggested_objective_json"])
        assert suggested_obj["type"] == "collect_optional_field"
        assert suggested_obj["target_field"] == "supplier_brands"
    print("  ✓ Optional Field Skip & Persistence OK")

    print("==================================================")
    print("ALL PHASE 5 TESTS PASSED [OK]\n")


if __name__ == "__main__":
    test_phase5_pipeline()
