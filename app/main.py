"""FastAPI entry point v8.

Run: python -m app.main (dev) hoặc uvicorn app.main:app --port 8000.
"""
from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


def create_app() -> FastAPI:
    """App factory."""
    settings = get_settings()
    app = FastAPI(
        title="Em Linh MKT — Chatbot Dealer v8",
        version="0.1.0",
        description="Phase 1 MVP — 3 REQUIRED slot + state machine 6 action + Gemini",
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

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

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
