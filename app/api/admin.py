"""Admin endpoints — read-only, dành cho Reviewer ADG (mục 25).

Bảo vệ bằng HTTP Basic Auth (xem app/api/auth.py).
Browser sẽ popup hỏi user/pass khi truy cập lần đầu.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.auth import require_admin
from app.config import get_storage
from app.core.md_exporter import render_bulk_md, render_profile_md, safe_filename
from app.storage.base import StorageAdapter

# Áp `require_admin` cho TẤT CẢ route trong router này.
router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/profiles")
def list_profiles(storage: StorageAdapter = Depends(get_storage)) -> dict:
    profiles = storage.list_profiles()
    return {"count": len(profiles), "items": profiles}


@router.get("/sessions")
def list_sessions(
    limit: int = 50,
    storage: StorageAdapter = Depends(get_storage),
) -> dict:
    sessions = storage.list_sessions(limit=limit)
    return {"count": len(sessions), "items": sessions}


@router.get("/session/{session_id}")
def get_session(
    session_id: str,
    storage: StorageAdapter = Depends(get_storage),
) -> dict:
    session = storage.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")
    return session.model_dump(mode="json")


@router.delete("/session/{session_id}")
def delete_session(
    session_id: str,
    storage: StorageAdapter = Depends(get_storage),
) -> dict:
    """Xoá vĩnh viễn session + profile_raw. Admin only.

    Dùng cho test/cleanup data PII trên production. KHÔNG thể recover sau khi
    xoá.
    """
    deleted = storage.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session không tồn tại")
    return {"deleted": True, "session_id": session_id}


# ---------- Export Markdown ----------

@router.get("/session/{session_id}/export.md")
def export_session_md(
    session_id: str,
    storage: StorageAdapter = Depends(get_storage),
) -> Response:
    """Xuất 1 dealer profile + hội thoại ra Markdown — tải xuống dạng file."""
    session = storage.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    md = render_profile_md(session)
    fname = safe_filename(session.profile_raw.dealer_name or session_id[:8])
    date = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"dealer_{fname}_{date}.md"

    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/profiles/export.md")
def export_profiles_md(
    ids: str | None = None,
    storage: StorageAdapter = Depends(get_storage),
) -> Response:
    """Xuất profile ra Markdown. Mặc định = tất cả CONFIRMED.

    Query `?ids=sid1,sid2` để chỉ xuất các session cụ thể (tick checkbox).
    """
    selected_ids: set[str] | None = None
    if ids:
        selected_ids = {sid.strip() for sid in ids.split(",") if sid.strip()}

    profiles = storage.list_profiles()
    sessions = []
    for p in profiles:
        sid = p.get("session_id")
        if not sid:
            continue
        if selected_ids is not None and sid not in selected_ids:
            continue
        sess = storage.load_session(sid)
        if sess:
            sessions.append(sess)

    if not sessions:
        raise HTTPException(status_code=404, detail="Không có profile để xuất")

    md = render_bulk_md(sessions)
    date = datetime.utcnow().strftime("%Y-%m-%d")
    suffix = f"_{len(sessions)}items" if selected_ids else ""
    filename = f"dealers_export{suffix}_{date}.md"

    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
