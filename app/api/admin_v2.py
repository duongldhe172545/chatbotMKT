"""Admin API endpoints for Parlant-style v2 database schema.

Enables the admin dashboard to query sessions, message history, review queues,
and detailed turn traces.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from pydantic import BaseModel

from app.core.ids import utc_now_iso

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
)

_basic_security = HTTPBasic()


def require_admin_v2(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(_basic_security),
) -> str:
    """HTTP Basic authentication for admin endpoints."""
    settings = request.app.state.settings
    correct_user = secrets.compare_digest(credentials.username, settings.admin_username)
    correct_pass = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai username/password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.get("/stats")
def get_stats(request: Request, admin: str = Depends(require_admin_v2)):
    """Fetch statistics for the admin dashboard dashboard."""
    store = request.app.state.store
    with store.database.transaction() as conn:
        # total sessions
        total_sessions = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]

        # stage distribution
        by_stage = {}
        for r in conn.execute("SELECT workflow_state, COUNT(*) as c FROM sessions GROUP BY workflow_state"):
            by_stage[r["workflow_state"]] = r["c"]

        # confirmation status
        confirmed_cnt = conn.execute("SELECT COUNT(*) as c FROM dealer_profiles WHERE review_status = 'CONFIRMED'").fetchone()["c"]
        by_confirmation = {
            "CONFIRMED": confirmed_cnt,
            "PENDING": total_sessions - confirmed_cnt,
        }

        # manual categorization status counts
        active_cnt = conn.execute("SELECT COUNT(*) as c FROM sessions WHERE status = 'ACTIVE'").fetchone()["c"]
        closed_cnt = conn.execute("SELECT COUNT(*) as c FROM sessions WHERE status = 'CLOSED'").fetchone()["c"]
        rejected_cnt = conn.execute("SELECT COUNT(*) as c FROM sessions WHERE status = 'REJECTED'").fetchone()["c"]
        by_status = {
            "ACTIVE": active_cnt,
            "CLOSED": closed_cnt,
            "REJECTED": rejected_cnt,
        }

    return {
        "total_sessions": total_sessions,
        "by_stage": by_stage,
        "by_dealer_type": {},
        "by_confirmation": by_confirmation,
        "by_status": by_status,
    }


@router.get("/sessions")
def list_sessions(
    request: Request,
    stage: str | None = Query(None),
    status: str | None = Query(None),
    confirmation_status: str | None = Query(None),
    dealer_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: str = Depends(require_admin_v2),
):
    """List sessions with filter and pagination."""
    store = request.app.state.store
    with store.database.transaction() as conn:
        query = "SELECT s.*, p.review_status, p.logo_issued_status FROM sessions s LEFT JOIN dealer_profiles p ON s.profile_id = p.id"
        clauses = []
        params = []
        if stage:
            clauses.append("s.workflow_state = ?")
            params.append(stage)
        if status:
            clauses.append("s.status = ?")
            params.append(status)
        if confirmation_status:
            clauses.append("p.review_status = ?")
            params.append(confirmation_status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY s.last_message_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()

        sessions = []
        for r in rows:
            sid = r["id"]
            pid = r["profile_id"]

            # Fetch profile fields
            owner_name = None
            dealer_name = None
            phone = None
            if pid:
                fields = conn.execute("SELECT field_name, normalized_value FROM profile_fields WHERE profile_id = ?", (pid,)).fetchall()
                for f in fields:
                    if f["field_name"] == "owner_name":
                        owner_name = f["normalized_value"]
                    elif f["field_name"] == "dealer_name":
                        dealer_name = f["normalized_value"]
                    elif f["field_name"] == "phone_or_zalo":
                        phone = f["normalized_value"]

            # Turn count
            turn_cnt = conn.execute("SELECT COUNT(*) as c FROM conversation_turns WHERE session_id = ?", (sid,)).fetchone()["c"]

            # Flags
            active_flags = conn.execute("SELECT flag_name FROM flags WHERE session_id = ? AND status = 'ACTIVE'", (sid,)).fetchall()
            flags = [f["flag_name"] for f in active_flags]

            sessions.append({
                "session_id": sid,
                "status": r["status"],
                "stage": r["workflow_state"],
                "current_slot": None,
                "current_focus_field": None,
                "turn_count": turn_cnt,
                "confirmation_status": r["review_status"] or "PENDING",
                "review_status": r["review_status"] or "RAW",
                "flags": flags,
                "detected_dealer_type": r["logo_issued_status"] or "unknown",
                "owner_name": owner_name,
                "dealer_name": dealer_name,
                "phone_or_zalo": phone,
                "created_at": r["started_at"],
                "updated_at": r["last_message_at"] or r["started_at"],
                "closed_at": r["closed_at"],
            })
    return sessions


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request, admin: str = Depends(require_admin_v2)):
    """Fetch detail for a single session including messages and full trace log."""
    store = request.app.state.store
    with store.database.transaction() as conn:
        session = store.get_session(conn, session_id)
        if not session:
            raise HTTPException(404, detail="Session not found")

        pid = session["profile_id"]

        # Fetch profile fields
        profile_data = {}
        if pid:
            fields = conn.execute("SELECT field_name, normalized_value FROM profile_fields WHERE profile_id = ?", (pid,)).fetchall()
            for f in fields:
                profile_data[f["field_name"]] = f["normalized_value"]

        # History
        messages = store.list_messages(conn, session_id=session_id, limit=200)
        history = []
        for m in messages:
            history.append({
                "role": "dealer" if m["source"] == "user" else "bot",
                "content": m["text"],
                "created_at": m["created_at"],
            })

        # Active flags
        active_flags = conn.execute("SELECT flag_name FROM flags WHERE session_id = ? AND status = 'ACTIVE'", (session_id,)).fetchall()
        flags = [f["flag_name"] for f in active_flags]

        # Turns
        turns_rows = conn.execute("SELECT * FROM conversation_turns WHERE session_id = ? ORDER BY created_at ASC", (session_id,)).fetchall()

        turns_traces = []
        for t in turns_rows:
            turns_traces.append({
                "turn_id": t["id"],
                "created_at": t["created_at"],
                "suggested_objective": json.loads(t["suggested_objective_json"]),
                "observations": json.loads(t["observations_json"]),
                "matched_guideline_ids": json.loads(t["matched_guideline_ids_json"]),
                "trace": json.loads(t["backend_turn_trace_json"]),
                "field_status_summary": json.loads(t["field_status_summary_json"]),
                "model_id": t["model_id"],
                "backend_latency_ms": t["backend_latency_ms"],
                "turn_aggregation_latency_ms": t["turn_aggregation_latency_ms"],
            })

        review_status = "RAW"
        logo_issued_status = "NONE"
        if pid:
            profile_row = conn.execute("SELECT review_status, logo_issued_status FROM dealer_profiles WHERE id = ?", (pid,)).fetchone()
            if profile_row:
                review_status = profile_row["review_status"]
                logo_issued_status = profile_row["logo_issued_status"]

        detail = {
            "session_id": session["id"],
            "status": session["status"],
            "stage": session["workflow_state"],
            "current_slot": None,
            "current_focus_field": None,
            "turn_count": len(turns_rows),
            "confirmation_status": review_status,
            "review_status": review_status,
            "flags": flags,
            "skipped_slots": [],
            "detected_dealer_type": logo_issued_status,
            "address_form": "anh",
            "created_at": session["started_at"],
            "updated_at": session["last_message_at"] or session["started_at"],
            "closed_at": session["closed_at"],
            "channel": session["channel"],
            "ip_address": session["ip_hash"],
            "profile": profile_data,
            "history": history,
            "turns": turns_traces,  # Trace logs
        }
    return detail


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request, admin: str = Depends(require_admin_v2)):
    """Delete a session (cascades profiles and turns)."""
    store = request.app.state.store
    with store.database.transaction() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
        session = conn.execute("SELECT profile_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if session and session["profile_id"]:
            pid = session["profile_id"]
            conn.execute("DELETE FROM dealer_profiles WHERE id = ?", (pid,))
            conn.execute("DELETE FROM profile_fields WHERE profile_id = ?", (pid,))
            conn.execute("DELETE FROM flags WHERE profile_id = ?", (pid,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return {"deleted": True}


class UpdateSessionStatusRequest(BaseModel):
    status: str


@router.post("/sessions/{session_id}/status")
def update_session_status(
    session_id: str,
    payload: UpdateSessionStatusRequest,
    request: Request,
    admin: str = Depends(require_admin_v2),
):
    """Manually update the classification status of a session."""
    if payload.status not in ("ACTIVE", "CLOSED", "REJECTED"):
        raise HTTPException(400, detail="Trạng thái không hợp lệ. Phải là ACTIVE, CLOSED, hoặc REJECTED.")
    
    store = request.app.state.store
    with store.database.transaction() as conn:
        session = store.get_session(conn, session_id)
        if not session:
            raise HTTPException(404, detail="Session không tồn tại")
        
        closed_at = None
        if payload.status in ("CLOSED", "REJECTED"):
            closed_at = utc_now_iso()
        
        conn.execute(
            "UPDATE sessions SET status = ?, closed_at = ? WHERE id = ?",
            (payload.status, closed_at, session_id),
        )
    return {"status": payload.status}


class BulkExportRequest(BaseModel):
    session_ids: list[str]
    include_history: bool = True


@router.get(
    "/sessions/{session_id}/export",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/markdown": {}}}},
)
def export_session_md(
    session_id: str,
    request: Request,
    include_history: bool = Query(True, description="Include conversation history"),
    admin: str = Depends(require_admin_v2),
):
    """Export 1 session profile + history ra file Markdown."""
    from fastapi.responses import PlainTextResponse
    from app.core.md_exporter import render_full_md, safe_filename
    store = request.app.state.store
    with store.database.transaction() as conn:
        session_obj, profile_obj = _load_pydantic_session_and_profile(conn, session_id)
        
    if session_obj is None:
        raise HTTPException(404, detail="Session không tồn tại")

    md = render_full_md(session_obj, profile_obj, include_history=include_history)
    name_part = safe_filename(
        profile_obj.dealer_name or profile_obj.owner_name or session_id[:8]
    )
    filename = f"{name_part}_{session_id[:8]}.md"
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/sessions/export",
    responses={200: {"content": {"application/zip": {}}}},
)
def bulk_export_sessions(
    req: BulkExportRequest,
    request: Request,
    admin: str = Depends(require_admin_v2),
):
    """Bulk export nhiều session thành 1 file ZIP chứa nhiều .md."""
    from app.core.md_exporter import render_full_md, safe_filename
    import io
    import zipfile
    from datetime import datetime, timezone
    store = request.app.state.store
    buffer = io.BytesIO()
    exported = 0
    skipped: list[str] = []

    with store.database.transaction() as conn:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for sid in req.session_ids:
                session_obj, profile_obj = _load_pydantic_session_and_profile(conn, sid)
                if session_obj is None:
                    skipped.append(sid)
                    continue
                md = render_full_md(session_obj, profile_obj, include_history=req.include_history)
                name_part = safe_filename(
                    profile_obj.dealer_name or profile_obj.owner_name or sid[:8]
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


def _load_pydantic_session_and_profile(conn, session_id: str):
    from app.models.schema import SessionState, DealerProfileRaw, HistoryMessage
    from app.models.enums import Stage, ConfirmationStatus, ReviewStatus, DealerType, Channel
    from app.db.store import Store
    import json
    from datetime import datetime

    store = Store(None)
    session_row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session_row:
        return None, None

    # Load messages for history
    message_rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY event_cursor ASC",
        (session_id,)
    ).fetchall()
    
    history = []
    for m in message_rows:
        dt = None
        if m["created_at"]:
            try:
                dt = datetime.fromisoformat(m["created_at"])
            except Exception:
                pass
        history.append(
            HistoryMessage(
                role="dealer" if m["source"] == "user" else "bot",
                content=m["text"] or "",
                ts=dt or datetime.utcnow()
            )
        )

    # Load profile Snapshot
    pid = session_row["profile_id"]
    profile_row = None
    profile_fields = {}
    review_status = "RAW"
    logo_issued_status = "NONE"
    
    if pid:
        profile_row = conn.execute("SELECT * FROM dealer_profiles WHERE id = ?", (pid,)).fetchone()
        fields = conn.execute("SELECT field_name, normalized_value FROM profile_fields WHERE profile_id = ?", (pid,)).fetchall()
        for f in fields:
            name = f["field_name"]
            val = f["normalized_value"]
            if val is not None:
                if val.startswith("[") and val.endswith("]"):
                    try:
                        val = json.loads(val)
                    except Exception:
                        pass
                profile_fields[name] = val
        if profile_row:
            review_status = profile_row["review_status"]
            logo_issued_status = profile_row["logo_issued_status"]

    # Construct Pydantic profile
    profile_obj = DealerProfileRaw(**profile_fields)
    
    # Construct Pydantic session
    dt_started = None
    if session_row["started_at"]:
        try:
            dt_started = datetime.fromisoformat(session_row["started_at"])
        except Exception:
            pass
    dt_updated = None
    if session_row["last_message_at"]:
        try:
            dt_updated = datetime.fromisoformat(session_row["last_message_at"])
        except Exception:
            pass
    dt_closed = None
    if session_row["closed_at"]:
        try:
            dt_closed = datetime.fromisoformat(session_row["closed_at"])
        except Exception:
            pass

    # Map workflow_state to Stage enum
    stage_val = Stage.GREETING
    wf = session_row["workflow_state"]
    if wf == "WAITING_REQUIRED_FIELD":
        stage_val = Stage.ASKING
    elif wf == "READY_FOR_REVIEW":
        stage_val = Stage.CONFIRMING
    elif wf in ("LOGO_PENDING", "LOGO_READY", "CLOSED", "ESCALATED", "CONFIRMED"):
        stage_val = Stage.DONE

    # Map confirmation status
    conf_status = ConfirmationStatus.PENDING
    if review_status == "CONFIRMED":
        conf_status = ConfirmationStatus.CONFIRMED

    # Flags
    flag_rows = conn.execute("SELECT flag_name FROM flags WHERE session_id = ? AND status = 'ACTIVE'", (session_id,)).fetchall()
    from app.models.enums import Flag
    flags = []
    for fr in flag_rows:
        try:
            flags.append(Flag(fr["flag_name"]))
        except Exception:
            pass

    review_status_enum = ReviewStatus.RAW
    if review_status == "CONFIRMED":
        review_status_enum = ReviewStatus.APPROVED

    session_obj = SessionState(
        session_id=session_id,
        status=session_row["status"],
        stage=stage_val,
        turn_count=len(history) // 2,
        confirmation_status=conf_status,
        review_status=review_status_enum,
        history=history,
        flags=flags,
        detected_dealer_type=DealerType(logo_issued_status) if logo_issued_status in [e.value for e in DealerType] else DealerType.UNKNOWN,
        created_at=dt_started or datetime.utcnow(),
        updated_at=dt_updated or dt_started or datetime.utcnow(),
        closed_at=dt_closed,
        channel=Channel.WEB,
        ip_address=session_row["ip_hash"],
        user_agent=None
    )
    return session_obj, profile_obj
