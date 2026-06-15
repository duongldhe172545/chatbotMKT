"""P2/B5 — graceful exception handlers (2026-06-10).

Uncaught errors must return a `{ok: false}` JSON envelope, not a bare 500.
SQLite lock/busy under load → 503 + Retry-After so the client can retry.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from app.main_v2 import (
    _handle_sqlite_operational_error,
    _handle_unhandled_error,
    create_app,
)


def _fake_request(method: str = "POST", path: str = "/api/v1/sessions/x/messages"):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


async def test_sqlite_locked_returns_503_retryable():
    resp = await _handle_sqlite_operational_error(
        _fake_request(), sqlite3.OperationalError("database is locked")
    )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "2"


async def test_sqlite_busy_returns_503_retryable():
    resp = await _handle_sqlite_operational_error(
        _fake_request(), sqlite3.OperationalError("database is busy")
    )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "2"


async def test_sqlite_other_error_returns_503_no_retry_header():
    resp = await _handle_sqlite_operational_error(
        _fake_request(), sqlite3.OperationalError("disk I/O error")
    )
    assert resp.status_code == 503
    assert "Retry-After" not in resp.headers


async def test_unhandled_error_returns_500_envelope():
    resp = await _handle_unhandled_error(_fake_request(), RuntimeError("boom"))
    assert resp.status_code == 500


def test_handlers_registered_on_app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("APP_ENV", "test")
    from app.core.config_v2 import reset_settings

    reset_settings()
    try:
        app = create_app()
        assert sqlite3.OperationalError in app.exception_handlers
        assert Exception in app.exception_handlers
    finally:
        reset_settings()
