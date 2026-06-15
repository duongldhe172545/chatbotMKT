"""FastAPI entry point v2 — Parlant-style architecture.

Coexists with app/main.py (legacy). Run via:
    python -m app.main_v2
    uvicorn app.main_v2:app --port 8001
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_v2 import router
from app.api.admin_v2 import router as admin_router
from app.core.config_v2 import Settings, get_settings
from app.core.responses import error_response, success_envelope
from app.db.connection import Database
from app.db.store import Store


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

logger = logging.getLogger(__name__)


async def _handle_sqlite_operational_error(
    request: Request, exc: sqlite3.OperationalError
):
    """Turn a SQLite lock/busy into a graceful 503 (+Retry-After), not a bare 500.

    After P2 the write lock is held only ~ms, so 'database is locked' should be
    rare — but if it happens under load, the client gets a retryable envelope
    instead of a dead 'Internal Server Error'.
    """
    detail = str(exc).lower()
    if "locked" in detail or "busy" in detail:
        logger.warning("DB busy on %s %s: %s", request.method, request.url.path, exc)
        resp = error_response(
            "db_busy",
            "Hệ thống đang bận một chút, anh/chị thử gửi lại giúp em nhé.",
            status_code=503,
        )
        resp.headers["Retry-After"] = "2"
        return resp
    logger.exception("SQLite error on %s %s", request.method, request.url.path)
    return error_response(
        "db_error",
        "Cơ sở dữ liệu trục trặc tạm thời, anh/chị thử lại giúp em nhé.",
        status_code=503,
    )


async def _apply_threadpool(tokens: int) -> None:
    """Raise the AnyIO threadpool limit (default 40) for sync endpoints.

    Each chat turn parks a thread for the full Gemini wait (~3-8s); 40 threads
    means a 100-person burst queues 60 of them. Must run inside the event loop
    (the limiter is loop-local) — hence called from lifespan. (P3.1)
    """
    import anyio.to_thread

    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = tokens
    logger.info("AnyIO threadpool tokens = %d", tokens)


def _make_lifespan(settings: Settings):
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        try:
            await _apply_threadpool(settings.threadpool_tokens)
        except Exception:
            logger.exception("Không nâng được threadpool limiter — giữ default 40")
        yield

    return _lifespan


async def _handle_unhandled_error(request: Request, exc: Exception):
    """Last-resort handler: any uncaught error returns a JSON envelope, not a bare 500."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(
        "internal_error",
        "Có lỗi nội bộ rồi, anh/chị thử lại sau giây lát giúp em nhé.",
        status_code=500,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory — creates FastAPI app with DB and routes."""
    resolved_settings = settings or get_settings()
    database = Database(resolved_settings.sqlite_path)
    database.initialize()

    app = FastAPI(
        title="Em Linh MKT — Parlant-style Chatbot v2",
        version="2.0.0",
        description="Parlant-style turn pipeline: extract → objective → agent → guards → trace",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_make_lifespan(resolved_settings),
    )

    # Store settings and DB on app state (accessible in routes via request.app.state)
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.store = Store(database)

    # CORS
    origins = (
        ["*"]
        if resolved_settings.cors_allowed_origins == "*"
        else [
            o.strip()
            for o in resolved_settings.cors_allowed_origins.split(",")
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Graceful error envelopes (P2/B5) — uncaught errors return {ok:false} JSON.
    # HTTPException/validation errors keep FastAPI's own handlers (more specific).
    app.add_exception_handler(
        sqlite3.OperationalError, _handle_sqlite_operational_error
    )
    app.add_exception_handler(Exception, _handle_unhandled_error)

    # Root health check (outside /api/v1)
    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        db_ok = request.app.state.database.health_check()
        return success_envelope(
            {
                "status": "ok" if db_ok else "degraded",
                "version": "2.0.0",
                "app_env": request.app.state.settings.app_env,
                "db": "ok" if db_ok else "failed",
            }
        )

    # Static files
    if STATIC_DIR.exists():
        app.mount(
            "/static", StaticFiles(directory=str(STATIC_DIR)), name="static"
        )

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/admin")
        @app.get("/admin/{path:path}")
        def admin_page(path: str = None):
            return FileResponse(STATIC_DIR / "admin.html")

    # API v1 routes
    app.include_router(router)
    app.include_router(admin_router)

    return app


app = create_app()


def main() -> None:
    import logging
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)
    settings = get_settings()
    logger.info(
        "Em Linh MKT v2 (Parlant) starting — %s:%d", settings.host, settings.port
    )
    # WEB_WORKERS>1: nhiều process chia CPU floor (GIL) cho burst đông người.
    # SQLite WAL + write-lock ~ms (P2) → nhiều worker cùng 1 file DB an toàn;
    # initialize() idempotent + additive nên mỗi worker tự chạy không phá nhau.
    uvicorn.run(
        "app.main_v2:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
        workers=settings.web_workers if settings.web_workers > 1 else None,
    )


if __name__ == "__main__":
    main()
