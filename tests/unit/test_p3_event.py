"""P3-EVENT — hardening cho sự kiện ~100 người cùng lúc (2026-06-10).

Cover:
- Gemini: 429 fail-nhanh (không sleep-retry), retry ngắn cho lỗi 5xx,
  semaphore in-flight → GeminiBusyError khi kín slot.
- Rate-limit per-session wire vào POST /messages (429 + Retry-After).
- read_transaction không giữ write-lock (writer khác ghi ngay được).
- History window: prompt LLM chỉ nhận ≤40 tin, turn_count vẫn từ full history.
- Threadpool limiter nâng được + Settings.threadpool_tokens.
"""
from __future__ import annotations

import inspect
import threading
import time
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

import app.llm.gemini as gemini_mod
from app.core.config_v2 import Settings
from app.db.connection import Database
from app.db.store import Store
from app.guards.rate_limit import reset_all as reset_rate_limits
from app.llm.gemini import GeminiBusyError, GeminiProvider
from app.services.chat_service import ChatService


# ============================================================
# Helpers
# ============================================================


def _fake_err(cls, code: int):
    """Tạo instance lỗi genai mà không gọi __init__ (test-only)."""
    err = cls.__new__(cls)
    err.code = code
    err.message = "fake"
    err.status = "FAKE"
    err.details = None
    err.response = None
    return err


def _ok_response():
    return SimpleNamespace(usage_metadata=None)


# ============================================================
# Gemini — chính sách retry/429/semaphore
# ============================================================


class TestGeminiRetryPolicy:
    def test_429_fails_fast_no_sleep_no_retry(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(gemini_mod.time, "sleep", lambda s: sleeps.append(s))
        calls: list[int] = []

        def fn():
            calls.append(1)
            raise _fake_err(genai_errors.APIError, 429)

        provider = GeminiProvider(api_key="x", model="test-model")
        with pytest.raises(genai_errors.APIError):
            provider._call_with_retry(fn, method="test")
        assert len(calls) == 1, "429 KHÔNG được retry"
        assert sleeps == [], "429 KHÔNG được sleep giam thread"

    def test_server_error_retries_short(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(gemini_mod.time, "sleep", lambda s: sleeps.append(s))
        calls: list[int] = []

        def fn():
            calls.append(1)
            raise _fake_err(genai_errors.ServerError, 500)

        provider = GeminiProvider(api_key="x", model="test-model")
        with pytest.raises(genai_errors.ServerError):
            provider._call_with_retry(fn, method="test")
        assert len(calls) == 1 + len(gemini_mod.RETRY_DELAYS)
        assert len(sleeps) == len(gemini_mod.RETRY_DELAYS)
        # Retry ngắn: max 1.5s * jitter 1.3 < 2s (không còn 1+2+4=7s như cũ)
        assert all(s < 2.0 for s in sleeps), f"sleep quá dài: {sleeps}"

    def test_success_returns_response(self):
        provider = GeminiProvider(api_key="x", model="test-model")
        result = provider._call_with_retry(_ok_response, method="test")
        assert result is not None

    def test_busy_when_slots_full(self, monkeypatch):
        sem = threading.BoundedSemaphore(1)
        assert sem.acquire(timeout=0)  # chiếm hết slot
        monkeypatch.setattr(gemini_mod, "_gemini_slots", sem)
        monkeypatch.setattr(gemini_mod, "_SLOT_WAIT_S", 0.05)

        provider = GeminiProvider(api_key="x", model="test-model")
        start = time.monotonic()
        with pytest.raises(GeminiBusyError):
            provider._call_with_retry(_ok_response, method="test")
        assert time.monotonic() - start < 2.0, "phải fail nhanh, không chờ vô hạn"

    def test_slot_released_after_use(self, monkeypatch):
        sem = threading.BoundedSemaphore(1)
        monkeypatch.setattr(gemini_mod, "_gemini_slots", sem)
        provider = GeminiProvider(api_key="x", model="test-model")
        # 3 call tuần tự với CHỈ 1 slot → nếu rò slot thì call 2/3 kẹt
        for _ in range(3):
            provider._call_with_retry(_ok_response, method="test")
        # Slot phải còn trống sau cùng
        assert sem.acquire(timeout=0)
        sem.release()

    def test_defaults_sane(self):
        assert gemini_mod.GEMINI_MAX_CONCURRENCY > 0
        assert gemini_mod.HTTP_TIMEOUT_MS <= 30_000, "timeout phải ngắn hơn 60s cũ"
        assert sum(gemini_mod.RETRY_DELAYS) < 7.0, "tổng sleep retry phải ngắn hơn 7s cũ"


# ============================================================
# Rate-limit per-session trên POST /messages
# ============================================================


@pytest.fixture()
def api_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("APP_ENV", "test")
    from app.core.config_v2 import reset_settings
    from app.main_v2 import create_app
    from fastapi.testclient import TestClient

    reset_settings()
    reset_rate_limits()
    settings = Settings(
        database_url="sqlite:///:memory:",
        conversation_runtime="stub",
        gemini_api_key="",
        rate_limit_msg_per_minute=2,
        app_env="test",
    )
    app = create_app(settings)
    client = TestClient(app)
    yield client
    reset_rate_limits()
    reset_settings()


class TestRateLimitRoute:
    def _new_session(self, client):
        r = client.post("/api/v1/sessions", json={"channel": "web_text"})
        assert r.status_code == 200
        data = r.json()["data"]
        return data["session_id"], data["session_token"]

    def _send(self, client, sid, tok, i):
        return client.post(
            f"/api/v1/sessions/{sid}/messages",
            headers={"Authorization": f"Bearer {tok}", "Idempotency-Key": f"k{i}"},
            json={"message_type": "text", "text": f"tin {i}"},
        )

    def test_blocks_after_limit_with_retry_after(self, api_client):
        sid, tok = self._new_session(api_client)
        assert self._send(api_client, sid, tok, 1).status_code == 200
        assert self._send(api_client, sid, tok, 2).status_code == 200
        r3 = self._send(api_client, sid, tok, 3)
        assert r3.status_code == 429
        body = r3.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "rate_limited"
        assert "Retry-After" in r3.headers

    def test_limit_is_per_session_not_global(self, api_client):
        """ADVERSARIAL: session A bị limit KHÔNG được chặn session B (sự kiện
        cả trăm người chung 1 IP WiFi — tuyệt đối không limit chéo)."""
        sid_a, tok_a = self._new_session(api_client)
        self._send(api_client, sid_a, tok_a, 1)
        self._send(api_client, sid_a, tok_a, 2)
        assert self._send(api_client, sid_a, tok_a, 3).status_code == 429

        sid_b, tok_b = self._new_session(api_client)
        assert self._send(api_client, sid_b, tok_b, 1).status_code == 200


# ============================================================
# read_transaction — không giữ write-lock
# ============================================================


class TestReadTransaction:
    def test_reader_does_not_block_writer(self, tmp_path):
        db = Database(str(tmp_path / "rd.sqlite3"))
        db.initialize()
        with db.read_transaction() as rconn:
            rconn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            # Trong lúc "đang đọc": writer khác phải ghi được NGAY (WAL).
            # Nếu read_transaction lỡ lấy BEGIN IMMEDIATE thì câu dưới chờ 30s.
            start = time.monotonic()
            with db.transaction() as wconn:
                wconn.execute(
                    "INSERT INTO sessions (id, channel, status, workflow_state, "
                    "session_token_hash, started_at) "
                    "VALUES ('ses_rd', 'web', 'ACTIVE', 'X', 'h', '2026-01-01')"
                )
            assert time.monotonic() - start < 2.0, "reader đang chặn writer!"

        with db.read_transaction() as rconn:
            row = rconn.execute(
                "SELECT id FROM sessions WHERE id = 'ses_rd'"
            ).fetchone()
            assert row is not None


# ============================================================
# History window — prompt ≤40 tin, turn_count vẫn full
# ============================================================


def _make_service(tmp_path):
    db = Database(str(tmp_path / "win.sqlite3"))
    db.initialize()
    store = Store(db)
    settings = Settings(
        database_url="sqlite:///x", conversation_runtime="stub", gemini_api_key=""
    )
    svc = ChatService(store=store, settings=settings)
    return svc, store, db


class TestHistoryWindow:
    def test_prompt_window_capped_turn_count_full(self, tmp_path):
        svc, store, db = _make_service(tmp_path)
        with db.transaction() as conn:
            sid = store.create_session(
                conn, channel="web", token_hash="t", ip_hash=None,
                user_agent_hash=None, metadata={},
            )["id"]

        real = svc.turn_processor
        captured: dict = {}

        class Spy:
            def process(self, **kw):
                captured.clear()
                captured.update(kw)
                return real.process(**kw)

        svc._turn_processor = Spy()
        for i in range(25):  # 25 lượt = 50 messages trong DB
            svc.send_text_message(
                session_id=sid, text=f"tin {i}", client_message_id=str(i)
            )

        # Lượt cuối: DB có 49 msg trước reply → prompt cắt còn 40
        assert len(captured["recent_messages"]) == 40
        # turn_count vẫn tính từ FULL history (49//2=24), không phải từ window (40//2=20)
        assert captured["turn_count"] == 24


# ============================================================
# Threadpool + Settings
# ============================================================


async def test_apply_threadpool_sets_limiter():
    import anyio.to_thread
    from app.main_v2 import _apply_threadpool

    limiter = anyio.to_thread.current_default_thread_limiter()
    old = limiter.total_tokens
    try:
        await _apply_threadpool(150)
        assert (
            anyio.to_thread.current_default_thread_limiter().total_tokens == 150
        )
    finally:
        limiter.total_tokens = old


class TestThreadpoolSetting:
    def test_default_150(self):
        assert Settings().threadpool_tokens == 150

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("THREADPOOL_TOKENS", "64")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("APP_ENV", "test")
        assert Settings.from_env().threadpool_tokens == 64

    def test_web_workers_default_1(self):
        """Load test 2026-06-10: WEB_WORKERS>1 trên SQLite cho tail thảm hoạ
        (cross-process lock thrash, p95 59s). Default PHẢI là 1."""
        assert Settings().web_workers == 1

    def test_web_workers_env_override(self, monkeypatch):
        monkeypatch.setenv("WEB_WORKERS", "2")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("APP_ENV", "test")
        assert Settings.from_env().web_workers == 2


# ============================================================
# max_tokens cap (P3/M1)
# ============================================================


def test_agent_reply_max_tokens_capped():
    from app.parlant.agent import AgentReplyGenerator

    src = inspect.getsource(AgentReplyGenerator.generate)
    assert "max_tokens=512" in src
    assert "max_tokens=2048" not in src
