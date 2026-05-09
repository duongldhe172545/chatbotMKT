"""FastAPI entrypoint. Chạy: python -m app.main

Production (Railway): set UVICORN_RELOAD=false để tắt watch.
Dev local: mặc định reload=true để auto-restart khi sửa code.
"""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import require_admin
from app.api.chat import router as chat_router
from app.api.labels_route import router as labels_router
from app.config import get_server_config
from app.logging_setup import setup_logging

setup_logging()

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

app = FastAPI(title="Em Linh MKT — Chatbot Dealer MVP")
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(labels_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin_page(_: str = Depends(require_admin)) -> FileResponse:
    """Admin viewer — yêu cầu HTTP Basic Auth (xem ADMIN_PASSWORD trong .env)."""
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    host, port = get_server_config()
    # Reload watcher: dev=true (auto-restart khi sửa code), prod=false.
    # Railway deploy phải set UVICORN_RELOAD=false (hoặc không set).
    reload = os.getenv("UVICORN_RELOAD", "true").lower() in ("1", "true", "yes")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
