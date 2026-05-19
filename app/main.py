"""FastAPI entry point v8.

Run: python -m app.main (dev) hoặc uvicorn app.main:app --port 8000.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.config import get_settings
from app.scheduler import create_scheduler
from app.storage.sqlite_store import SQLiteStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown: APScheduler timeout sweep."""
    settings = get_settings()
    scheduler = None
    if settings.SCHEDULER_ENABLED:
        try:
            store = SQLiteStore(settings.SQLITE_PATH)
            scheduler = create_scheduler(store)
            scheduler.start()
            app.state.scheduler = scheduler
            logger.info("Scheduler started (sweep every %ds)", settings.SCHEDULER_SWEEP_INTERVAL_S)
        except Exception as e:
            logger.exception("Scheduler start fail: %s", e)
    yield
    # Shutdown
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler shutdown")
        except Exception as e:
            logger.exception("Scheduler shutdown fail: %s", e)


def create_app() -> FastAPI:
    """App factory."""
    settings = get_settings()
    app = FastAPI(
        title="Em Linh MKT — Chatbot Dealer v8",
        version="0.1.0",
        description="Phase 1-4 MVP — 17 slot + 12 edge case + scheduler + admin queue",
        lifespan=lifespan,
    )

    # CORS
    origins = (
        ["*"] if settings.CORS_ALLOWED_ORIGINS == "*"
        else [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",")]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(chat_router)
    app.include_router(admin_router)

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/admin")
        def admin_page():
            """Admin UI page (HTTP Basic auth ở API level, frontend trigger
            popup browser native login khi gọi API)."""
            return FileResponse(STATIC_DIR / "admin.html")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": "0.1.0", "phase": "1"}

    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    logger.info("Em Linh MKT v8 starting — %s:%d", settings.HOST, settings.PORT)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
