"""Admin endpoints — quản lý session + profile + admin queue.

Refer:
- F2C.8 (LUAT_2C_infra v0.1.4) — admin queue + review workflow + SLA
- KE_HOACH § action 21 — admin endpoints

Endpoints:
    GET    /api/admin/sessions       — list session (filter + pagination)
    GET    /api/admin/sessions/{id}  — chi tiết session + profile + history
    DELETE /api/admin/sessions/{id}  — xóa session + profile + queue (cascade)
    GET    /api/admin/queue          — list admin queue (priority sort)
    GET    /api/admin/queue/{id}     — chi tiết queue entry
    POST   /api/admin/queue/{id}/claim   — admin claim (status PENDING → IN_REVIEW)
    POST   /api/admin/queue/{id}/approve — duyệt (status → APPROVED)
    POST   /api/admin/queue/{id}/reject  — từ chối (status → REJECTED)
    GET    /api/admin/stats          — dashboard statistics
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from app.api.auth import require_admin
from app.core.md_exporter import render_full_md, render_profile_md, safe_filename
from app.models.enums import QueueStatus, Stage

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ============================================================
# Response models
# ============================================================


class SessionSummary(BaseModel):
    """Tóm tắt session cho list view."""
    session_id: str
    stage: str
    current_slot: Optional[str] = None
    turn_count: int
    confirmation_status: str
    review_status: str
    flags: list[str]
    detected_dealer_type: Optional[str] = None
    owner_name: Optional[str] = None
    dealer_name: Optional[str] = None
    phone_or_zalo: Optional[str] = None
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None


class SessionDetail(BaseModel):
    """Chi tiết session + profile + history."""
    session_id: str
    stage: str
    current_slot: Optional[str] = None
    turn_count: int
    confirmation_status: str
    review_status: str
    flags: list[str]
    skipped_slots: list[str]
    detected_dealer_type: Optional[str] = None
    address_form: str
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None
    channel: str
    ip_address: Optional[str] = None
    profile: dict
    history: list[dict]


class QueueEntry(BaseModel):
    """Admin queue entry."""
    queue_id: str
    session_id: str
    trigger: str
    priority: str
    status: str
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


class Stats(BaseModel):
    """Dashboard statistics."""
    total_sessions: int
    by_stage: dict[str, int]
    by_dealer_type: dict[str, int]
    by_confirmation: dict[str, int]
    queue_pending: int
    queue_high: int
    queue_medium: int
    queue_low: int


# ============================================================
# Helpers
# ============================================================


def _get_store():
    """Lazy import + singleton store (đồng bộ với chat.py)."""
    from app.api.chat import _get_store as get_store
    return get_store()


def _serialize_session_summary(row: dict, profile_row: dict | None) -> SessionSummary:
    """Convert DB row (sessions + profile JOIN) → SessionSummary."""
    flags = json.loads(row.get("flags") or "[]")
    return SessionSummary(
        session_id=row["session_id"],
        stage=row["stage"],
        current_slot=row.get("current_slot"),
        turn_count=row.get("turn_count", 0),
        confirmation_status=row.get("confirmation_status", "PENDING"),
        review_status=row.get("review_status", "RAW"),
        flags=flags if isinstance(flags, list) else [],
        detected_dealer_type=row.get("detected_dealer_type"),
        owner_name=(profile_row or {}).get("owner_name"),
        dealer_name=(profile_row or {}).get("dealer_name"),
        phone_or_zalo=(profile_row or {}).get("phone_or_zalo"),
        created_at=row.get("created_at") or "",
        updated_at=row.get("updated_at") or "",
        closed_at=row.get("closed_at"),
    )


# ============================================================
# Sessions endpoints
# ============================================================


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    stage: Optional[str] = Query(None, description="Filter theo stage"),
    confirmation_status: Optional[str] = Query(None),
    dealer_type: Optional[str] = Query(None),
    has_flag: Optional[str] = Query(None, description="Filter có flag X"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[SessionSummary]:
    """List session với filter + pagination."""
    store = _get_store()

    # Build query
    where_clauses: list[str] = []
    params: dict = {}

    if stage:
        where_clauses.append("s.stage = :stage")
        params["stage"] = stage
    if confirmation_status:
        where_clauses.append("s.confirmation_status = :cstatus")
        params["cstatus"] = confirmation_status
    if dealer_type:
        where_clauses.append("s.detected_dealer_type = :dtype")
        params["dtype"] = dealer_type
    # Flags là JSON list — dùng LIKE đơn giản (Phase 1)
    if has_flag:
        where_clauses.append("s.flags LIKE :flag_pattern")
        params["flag_pattern"] = f'%"{has_flag}"%'

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    sql = (
        f"SELECT s.*, p.owner_name, p.dealer_name, p.phone_or_zalo "
        f"FROM sessions s "
        f"LEFT JOIN dealer_profile_raw p ON s.session_id = p.session_id "
        f"{where_sql} "
        f"ORDER BY s.updated_at DESC "
        f"LIMIT :limit OFFSET :offset"
    )
    params["limit"] = limit
    params["offset"] = offset

    with store._connect() as conn:
        cursor = conn.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]

    return [
        _serialize_session_summary(
            {k: v for k, v in r.items()
             if k not in ("owner_name", "dealer_name", "phone_or_zalo")},
            {"owner_name": r.get("owner_name"),
             "dealer_name": r.get("dealer_name"),
             "phone_or_zalo": r.get("phone_or_zalo")},
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session_detail(session_id: str) -> SessionDetail:
    """Chi tiết 1 session — session row + profile + history."""
    store = _get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, detail=f"Session {session_id} không tồn tại")
    profile = store.get_profile(session_id)

    return SessionDetail(
        session_id=session.session_id,
        stage=session.stage.value,
        current_slot=session.current_slot,
        turn_count=session.turn_count,
        confirmation_status=session.confirmation_status.value,
        review_status=session.review_status.value,
        flags=[f.value for f in session.flags],
        skipped_slots=session.skipped_slots,
        detected_dealer_type=(
            session.detected_dealer_type.value
            if session.detected_dealer_type
            else None
        ),
        address_form=session.address_form.value,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        closed_at=session.closed_at.isoformat() if session.closed_at else None,
        channel=session.channel.value,
        ip_address=session.ip_address,
        profile=profile.model_dump() if profile else {},
        history=[m.model_dump(mode="json") for m in session.history],
    )


@router.get(
    "/sessions/{session_id}/export",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/markdown": {}}}},
)
def export_session_md(
    session_id: str,
    include_history: bool = Query(True, description="Include conversation history"),
):
    """Export 1 session profile + history ra file Markdown."""
    store = _get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, detail="Session không tồn tại")
    profile = store.get_profile(session_id)
    if profile is None:
        from app.models.schema import DealerProfileRaw
        profile = DealerProfileRaw()

    md = render_full_md(session, profile, include_history=include_history)
    # Filename: <dealer_name>_<session_short>.md
    name_part = safe_filename(
        profile.dealer_name or profile.owner_name or session.session_id[:8]
    )
    filename = f"{name_part}_{session.session_id[:8]}.md"
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class BulkExportRequest(BaseModel):
    """Body cho bulk export — list session_id."""
    session_ids: list[str]
    include_history: bool = True


@router.post(
    "/sessions/export",
    responses={200: {"content": {"application/zip": {}}}},
)
def bulk_export_sessions(req: BulkExportRequest):
    """Bulk export nhiều session thành 1 file ZIP chứa nhiều .md."""
    if not req.session_ids:
        raise HTTPException(400, detail="session_ids rỗng")
    if len(req.session_ids) > 200:
        raise HTTPException(400, detail="Max 200 session / lần export")

    store = _get_store()
    buffer = io.BytesIO()
    exported = 0
    skipped: list[str] = []

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for sid in req.session_ids:
            session = store.get_session(sid)
            if session is None:
                skipped.append(sid)
                continue
            profile = store.get_profile(sid)
            if profile is None:
                from app.models.schema import DealerProfileRaw
                profile = DealerProfileRaw()
            md = render_full_md(session, profile, include_history=req.include_history)
            name_part = safe_filename(
                profile.dealer_name or profile.owner_name or sid[:8]
            )
            filename = f"{name_part}_{sid[:8]}.md"
            zf.writestr(filename, md.encode("utf-8"))
            exported += 1

        # Add summary
        summary = (
            f"# Bulk export summary\n\n"
            f"- Requested: {len(req.session_ids)}\n"
            f"- Exported: {exported}\n"
            f"- Skipped (not found): {len(skipped)}\n"
        )
        if skipped:
            summary += "\n## Skipped session IDs\n" + "\n".join(
                f"- `{s}`" for s in skipped
            )
        zf.writestr("_SUMMARY.md", summary.encode("utf-8"))

    buffer.seek(0)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="em_linh_export_{timestamp}.zip"',
        },
    )


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """Xóa session + profile + queue (cascade qua FK)."""
    store = _get_store()
    ok = store.delete_session(session_id)
    if not ok:
        raise HTTPException(404, detail="Session không tồn tại")
    return {"deleted": True, "session_id": session_id}


# ============================================================
# Admin queue endpoints (F2C.8)
# ============================================================


@router.get("/queue", response_model=list[QueueEntry])
def list_queue(
    status: str = Query("PENDING", description="PENDING/IN_REVIEW/APPROVED/REJECTED"),
    priority: Optional[str] = Query(None, description="HIGH/MEDIUM/LOW"),
    limit: int = Query(50, ge=1, le=500),
) -> list[QueueEntry]:
    """List admin queue (priority sort, mới nhất trước)."""
    store = _get_store()
    where = ["status = :status"]
    params: dict = {"status": status}
    if priority:
        where.append("priority = :priority")
        params["priority"] = priority

    sql = (
        f"SELECT * FROM admin_queue WHERE {' AND '.join(where)} "
        f"ORDER BY "
        f"CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, "
        f"created_at ASC "
        f"LIMIT :limit"
    )
    params["limit"] = limit

    with store._connect() as conn:
        cursor = conn.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]

    return [
        QueueEntry(
            queue_id=r["queue_id"],
            session_id=r["session_id"],
            trigger=r["trigger"],
            priority=r["priority"],
            status=r["status"],
            assigned_to=r.get("assigned_to"),
            notes=r.get("notes"),
            created_at=r["created_at"],
            resolved_at=r.get("resolved_at"),
        )
        for r in rows
    ]


@router.get("/queue/{queue_id}", response_model=QueueEntry)
def get_queue_detail(queue_id: str) -> QueueEntry:
    store = _get_store()
    with store._connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM admin_queue WHERE queue_id = ?", (queue_id,)
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(404, detail="Queue entry không tồn tại")
    r = dict(row)
    return QueueEntry(
        queue_id=r["queue_id"],
        session_id=r["session_id"],
        trigger=r["trigger"],
        priority=r["priority"],
        status=r["status"],
        assigned_to=r.get("assigned_to"),
        notes=r.get("notes"),
        created_at=r["created_at"],
        resolved_at=r.get("resolved_at"),
    )


@router.post("/queue/{queue_id}/claim")
def claim_queue(queue_id: str, admin: str = Depends(require_admin)) -> dict:
    """Admin claim 1 entry. Status PENDING → IN_REVIEW + assigned_to = admin."""
    store = _get_store()
    with store._connect() as conn:
        cursor = conn.execute(
            "UPDATE admin_queue SET status = ?, assigned_to = ? "
            "WHERE queue_id = ? AND status = ?",
            (QueueStatus.IN_REVIEW.value, admin, queue_id, QueueStatus.PENDING.value),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                409, detail="Queue entry không tồn tại hoặc không ở status PENDING"
            )
    return {"queue_id": queue_id, "status": "IN_REVIEW", "assigned_to": admin}


@router.post("/queue/{queue_id}/approve")
def approve_queue(
    queue_id: str,
    notes: Optional[str] = None,
    admin: str = Depends(require_admin),
) -> dict:
    """Duyệt entry. Status → APPROVED + resolved_at = now."""
    store = _get_store()
    now = datetime.now(timezone.utc).isoformat()
    with store._connect() as conn:
        cursor = conn.execute(
            "UPDATE admin_queue SET status = ?, notes = COALESCE(?, notes), "
            "resolved_at = ?, assigned_to = COALESCE(assigned_to, ?) "
            "WHERE queue_id = ?",
            (QueueStatus.APPROVED.value, notes, now, admin, queue_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, detail="Queue entry không tồn tại")
    return {"queue_id": queue_id, "status": "APPROVED"}


@router.post("/queue/{queue_id}/reject")
def reject_queue(
    queue_id: str,
    notes: Optional[str] = None,
    admin: str = Depends(require_admin),
) -> dict:
    """Từ chối entry. Status → REJECTED."""
    store = _get_store()
    now = datetime.now(timezone.utc).isoformat()
    with store._connect() as conn:
        cursor = conn.execute(
            "UPDATE admin_queue SET status = ?, notes = COALESCE(?, notes), "
            "resolved_at = ?, assigned_to = COALESCE(assigned_to, ?) "
            "WHERE queue_id = ?",
            (QueueStatus.REJECTED.value, notes, now, admin, queue_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, detail="Queue entry không tồn tại")
    return {"queue_id": queue_id, "status": "REJECTED"}


# ============================================================
# Stats dashboard
# ============================================================


@router.get("/stats", response_model=Stats)
def get_stats() -> Stats:
    """Statistics cho dashboard."""
    store = _get_store()
    with store._connect() as conn:
        # Total sessions
        total = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]
        # By stage
        by_stage = {}
        for row in conn.execute(
            "SELECT stage, COUNT(*) as c FROM sessions GROUP BY stage"
        ):
            by_stage[row["stage"]] = row["c"]
        # By dealer_type
        by_dealer_type = {}
        for row in conn.execute(
            "SELECT detected_dealer_type, COUNT(*) as c FROM sessions "
            "WHERE detected_dealer_type IS NOT NULL GROUP BY detected_dealer_type"
        ):
            by_dealer_type[row["detected_dealer_type"]] = row["c"]
        # By confirmation
        by_confirmation = {}
        for row in conn.execute(
            "SELECT confirmation_status, COUNT(*) as c FROM sessions "
            "GROUP BY confirmation_status"
        ):
            by_confirmation[row["confirmation_status"]] = row["c"]
        # Queue stats
        queue_pending = conn.execute(
            "SELECT COUNT(*) as c FROM admin_queue WHERE status = 'PENDING'"
        ).fetchone()["c"]
        queue_priority = {}
        for row in conn.execute(
            "SELECT priority, COUNT(*) as c FROM admin_queue "
            "WHERE status = 'PENDING' GROUP BY priority"
        ):
            queue_priority[row["priority"]] = row["c"]

    return Stats(
        total_sessions=total,
        by_stage=by_stage,
        by_dealer_type=by_dealer_type,
        by_confirmation=by_confirmation,
        queue_pending=queue_pending,
        queue_high=queue_priority.get("HIGH", 0),
        queue_medium=queue_priority.get("MEDIUM", 0),
        queue_low=queue_priority.get("LOW", 0),
    )
