"""FastAPI entry point v2 — Parlant-style architecture.

Coexists with app/main.py (legacy). Run via:
    python -m app.main_v2
    uvicorn app.main_v2:app --port 8001
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_v2 import router
from app.api.admin_v2 import router as admin_router
from app.core.config_v2 import Settings, get_settings
from app.core.responses import success_envelope
from app.db.connection import Database
from app.db.store import Store


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


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
        def admin_page():
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
    uvicorn.run(
        "app.main_v2:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
