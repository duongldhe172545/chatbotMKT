"""Test admin endpoints. Refer F2C.8."""
from __future__ import annotations

from base64 import b64encode
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings, reset_settings


def _basic_auth_header(user: str, pwd: str) -> dict:
    token = b64encode(f"{user}:{pwd}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _seed_session(store, sid: str, **profile_kwargs):
    """Seed 1 session + profile cho test."""
    from app.core.session import create_session
    from app.models.enums import ConfirmationStatus, Stage
    from app.models.schema import DealerProfileRaw
    s = create_session()
    s.session_id = sid
    s.stage = Stage.DONE
    s.confirmation_status = ConfirmationStatus.CONFIRMED
    store.save_session(s)
    p = DealerProfileRaw(**profile_kwargs)
    store.save_profile(sid, p)
    return s, p


@pytest.fixture
def admin_client(tmp_path: Path, monkeypatch):
    """TestClient với DB tạm + admin auth header."""
    db_path = tmp_path / "test_admin.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    reset_settings()
    from app.api.chat import _get_store
    if hasattr(_get_store, "_instance"):
        del _get_store._instance

    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    auth = _basic_auth_header("admin", "testpass")
    return client, auth


@pytest.fixture
def admin_client_with_data(admin_client):
    """Client + 2 sessions sẵn cho test list."""
    client, auth = admin_client
    from app.api.chat import _get_store
    from app.core.session import create_session
    from app.models.enums import Stage, ConfirmationStatus, Flag
    from app.models.schema import DealerProfileRaw

    store = _get_store()

    s1 = create_session()
    s1.stage = Stage.ASKING
    s1.current_slot = "1.2"
    s1.turn_count = 2
    store.save_session(s1)
    p1 = DealerProfileRaw(owner_name="Tùng", dealer_name="Cửa Hàng A",
                         phone_or_zalo="0912345678")
    store.save_profile(s1.session_id, p1)

    s2 = create_session()
    s2.stage = Stage.DONE
    s2.confirmation_status = ConfirmationStatus.CONFIRMED
    s2.flags = [Flag.REQUIRED_MISSING]
    s2.turn_count = 6
    store.save_session(s2)
    p2 = DealerProfileRaw(owner_name="Lan", dealer_name="Cửa Hàng B")
    store.save_profile(s2.session_id, p2)

    return client, auth, s1.session_id, s2.session_id


# ============================================================
# Auth
# ============================================================


class TestAuth:
    def test_no_auth_returns_401(self, admin_client):
        client, _ = admin_client
        r = client.get("/api/admin/stats")
        assert r.status_code == 401

    def test_wrong_password_401(self, admin_client):
        client, _ = admin_client
        r = client.get(
            "/api/admin/stats",
            headers=_basic_auth_header("admin", "wrong"),
        )
        assert r.status_code == 401

    def test_correct_auth_200(self, admin_client):
        client, auth = admin_client
        r = client.get("/api/admin/stats", headers=auth)
        assert r.status_code == 200


# ============================================================
# Stats
# ============================================================


class TestStats:
    def test_empty_stats(self, admin_client):
        client, auth = admin_client
        r = client.get("/api/admin/stats", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["total_sessions"] == 0
        assert data["queue_pending"] == 0

    def test_stats_with_sessions(self, admin_client_with_data):
        client, auth, _, _ = admin_client_with_data
        r = client.get("/api/admin/stats", headers=auth)
        data = r.json()
        assert data["total_sessions"] == 2
        assert data["by_stage"].get("ASKING") == 1
        assert data["by_stage"].get("DONE") == 1
        assert data["by_confirmation"].get("CONFIRMED") == 1


# ============================================================
# Sessions list + detail + delete
# ============================================================


class TestSessions:
    def test_list_sessions(self, admin_client_with_data):
        client, auth, _, _ = admin_client_with_data
        r = client.get("/api/admin/sessions", headers=auth)
        assert r.status_code == 200
        sessions = r.json()
        assert len(sessions) == 2

    def test_filter_by_stage(self, admin_client_with_data):
        client, auth, _, _ = admin_client_with_data
        r = client.get("/api/admin/sessions?stage=ASKING", headers=auth)
        sessions = r.json()
        assert len(sessions) == 1
        assert sessions[0]["stage"] == "ASKING"
        assert sessions[0]["owner_name"] == "Tùng"

    def test_filter_by_confirmation(self, admin_client_with_data):
        client, auth, _, _ = admin_client_with_data
        r = client.get("/api/admin/sessions?confirmation_status=CONFIRMED", headers=auth)
        sessions = r.json()
        assert len(sessions) == 1
        assert sessions[0]["confirmation_status"] == "CONFIRMED"

    def test_filter_by_flag(self, admin_client_with_data):
        """Filter session có flag X."""
        client, auth, _, _ = admin_client_with_data
        r = client.get("/api/admin/sessions?has_flag=required_missing", headers=auth)
        sessions = r.json()
        assert len(sessions) == 1
        assert "required_missing" in sessions[0]["flags"]

    def test_get_session_detail(self, admin_client_with_data):
        client, auth, s1_id, _ = admin_client_with_data
        r = client.get(f"/api/admin/sessions/{s1_id}", headers=auth)
        assert r.status_code == 200
        detail = r.json()
        assert detail["session_id"] == s1_id
        assert detail["profile"]["owner_name"] == "Tùng"

    def test_get_session_not_found(self, admin_client):
        client, auth = admin_client
        r = client.get("/api/admin/sessions/nonexistent", headers=auth)
        assert r.status_code == 404

    def test_delete_session(self, admin_client_with_data):
        client, auth, s1_id, _ = admin_client_with_data
        r = client.delete(f"/api/admin/sessions/{s1_id}", headers=auth)
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        # Verify gone
        r2 = client.get(f"/api/admin/sessions/{s1_id}", headers=auth)
        assert r2.status_code == 404


# ============================================================
# Admin queue
# ============================================================


@pytest.fixture
def queue_data(admin_client_with_data):
    """Add queue entries."""
    client, auth, s1_id, s2_id = admin_client_with_data
    from app.api.chat import _get_store
    from app.models.enums import Flag, Priority
    from app.models.schema import AdminQueueEntry

    store = _get_store()
    entry1 = AdminQueueEntry(
        queue_id="q-test-1",
        session_id=s1_id,
        trigger=Flag.HALLUCINATE,
        priority=Priority.HIGH,
    )
    store.push_admin_queue(entry1)

    entry2 = AdminQueueEntry(
        queue_id="q-test-2",
        session_id=s2_id,
        trigger=Flag.SANITY_CHECK_FAILED,
        priority=Priority.MEDIUM,
    )
    store.push_admin_queue(entry2)

    return client, auth, s1_id, s2_id


class TestQueue:
    def test_list_queue_pending(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.get("/api/admin/queue", headers=auth)
        items = r.json()
        assert len(items) == 2

    def test_list_queue_priority_sort(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.get("/api/admin/queue", headers=auth)
        items = r.json()
        # HIGH trước MEDIUM
        assert items[0]["priority"] == "HIGH"
        assert items[1]["priority"] == "MEDIUM"

    def test_filter_priority(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.get("/api/admin/queue?priority=HIGH", headers=auth)
        items = r.json()
        assert len(items) == 1
        assert items[0]["trigger"] == "hallucinate"

    def test_get_queue_detail(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.get("/api/admin/queue/q-test-1", headers=auth)
        assert r.status_code == 200
        assert r.json()["queue_id"] == "q-test-1"

    def test_claim_queue(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.post("/api/admin/queue/q-test-1/claim", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "IN_REVIEW"
        assert data["assigned_to"] == "admin"

    def test_claim_already_in_review_409(self, queue_data):
        client, auth, _, _ = queue_data
        client.post("/api/admin/queue/q-test-1/claim", headers=auth)
        # Re-claim → fail
        r = client.post("/api/admin/queue/q-test-1/claim", headers=auth)
        assert r.status_code == 409

    def test_approve_queue(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.post("/api/admin/queue/q-test-1/approve", headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "APPROVED"

    def test_reject_queue(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.post("/api/admin/queue/q-test-1/reject", headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "REJECTED"

    def test_approve_with_notes(self, queue_data):
        client, auth, _, _ = queue_data
        r = client.post(
            "/api/admin/queue/q-test-1/approve?notes=OK%20duyet",
            headers=auth,
        )
        assert r.status_code == 200
        # Verify notes saved
        r2 = client.get("/api/admin/queue/q-test-1", headers=auth)
        assert "OK" in r2.json()["notes"]



# ============================================================
# Phase 5 R4 Gap 13 — Markdown export endpoint
# ============================================================


class TestMarkdownExport:
    def test_export_session_md_returns_markdown(self, admin_client):
        client, auth = admin_client
        from app.api.chat import _get_store
        store = _get_store()
        _seed_session(
            store, "exp-sess-1",
            owner_name="Tùng", dealer_name="Nhôm Kính Thanh Tùng",
            address="123 Lê Lợi, Hoàn Kiếm, Hà Nội", phone_or_zalo="0912345678",
            main_product="cửa nhôm Xingfa", brandkit_consent="yes",
        )
        r = client.get("/api/admin/sessions/exp-sess-1/export", headers=auth)
        assert r.status_code == 200
        assert "text/markdown" in r.headers["content-type"]
        # Filename header
        assert "attachment" in r.headers.get("content-disposition", "")
        # Markdown content
        body = r.text
        assert "Nhôm Kính Thanh Tùng" in body
        assert "Tùng" in body
        assert "Hà Nội" in body or "Hoàn Kiếm" in body

    def test_export_404_for_missing_session(self, admin_client):
        client, auth = admin_client
        r = client.get("/api/admin/sessions/no-such-sess/export", headers=auth)
        assert r.status_code == 404

    def test_export_no_history_flag(self, admin_client):
        client, auth = admin_client
        from app.api.chat import _get_store
        store = _get_store()
        _seed_session(store, "exp-sess-2", owner_name="Vinh")
        r = client.get(
            "/api/admin/sessions/exp-sess-2/export?include_history=false",
            headers=auth,
        )
        assert r.status_code == 200

    def test_export_requires_auth(self, admin_client):
        client, _ = admin_client
        r = client.get("/api/admin/sessions/any/export")
        assert r.status_code == 401
