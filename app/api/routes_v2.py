"""REST API routes — /api/v1/ prefix.

Follows LINHMKT pattern:
- POST /sessions — create session (returns token)
- GET  /sessions/{id} — hydrate session (auth required)
- POST /sessions/{id}/messages — send text message (auth + idempotency)
- GET  /sessions/{id}/events — poll events (auth, cursor-based)
- GET  /admin/review-items — list admin reviews (admin token)
- PATCH /admin/review-items/{id} — resolve review (admin token)
- GET  /health — health check
"""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.ids import utc_now_iso
from app.core.responses import api_json, error_response, success_envelope
from app.core.security import extract_bearer_token
from app.guards.rate_limit import check_rate_limit
from app.services.chat_service import ChatService, canonical_payload_hash
from app.services.session_service import SessionService


router = APIRouter(prefix="/api/v1")


# ============================================================
# Request models
# ============================================================


class CreateSessionRequest(BaseModel):
    channel: str = "web_text"
    client: dict[str, Any] = Field(default_factory=dict)


class SendTextMessageRequest(BaseModel):
    message_type: str = "text"
    text: str
    client_message_id: str | None = None


class ResolveReviewRequest(BaseModel):
    status: str = "RESOLVED"
    resolution_note: str | None = None


# ============================================================
# Session endpoints
# ============================================================


@router.post("/sessions")
def create_session(payload: CreateSessionRequest, request: Request) -> JSONResponse:
    """Create a new chat session. Returns session_id + session_token."""
    service = SessionService(
        store=request.app.state.store,
        settings=request.app.state.settings,
    )
    user_agent = request.headers.get("User-Agent") or payload.client.get(
        "user_agent"
    )
    ip_address = request.client.host if request.client else None
    data = service.create_session(
        channel=payload.channel,
        client=payload.client,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return api_json(data, request_id=request.headers.get("X-Request-Id"))


@router.get("/sessions/{session_id}")
def hydrate_session(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JSONResponse:
    """Restore full session state (messages, profile, logo) for frontend."""
    auth = _authorize_request(request, session_id, authorization)
    if isinstance(auth, JSONResponse):
        return auth
    data = SessionService(
        store=request.app.state.store,
        settings=request.app.state.settings,
    ).hydrate_session(session_id=session_id)
    return api_json(data, request_id=request.headers.get("X-Request-Id"))


# ============================================================
# Message endpoints
# ============================================================


@router.post("/sessions/{session_id}/messages")
def send_text_message(
    session_id: str,
    payload: SendTextMessageRequest,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> JSONResponse:
    """Send a text message to a session. Requires idempotency key."""
    if not idempotency_key:
        return _bad_idempotency(request)
    if payload.message_type != "text":
        return error_response(
            "validation_failed",
            "Only text messages are accepted. Use voice-messages for voice.",
            422,
            request_id=request.headers.get("X-Request-Id"),
        )

    auth = _authorize_request(request, session_id, authorization)
    if isinstance(auth, JSONResponse):
        return auth

    # Rate limit PER SESSION (P3.3). CHÚ Ý: không limit theo IP cho message —
    # sự kiện offline cả trăm người chung WiFi hội trường = chung 1 IP public,
    # limit theo IP sẽ tự chặn khách thật. Check SAU auth để kẻ không có token
    # không đốt được bucket của session người khác.
    allowed, retry_after = check_rate_limit(
        f"msg:{session_id}",
        max_requests=request.app.state.settings.rate_limit_msg_per_minute,
    )
    if not allowed:
        resp = error_response(
            "rate_limited",
            "Anh/chị nhắn hơi nhanh, chờ vài giây rồi gửi lại giúp em nhé.",
            429,
            request_id=request.headers.get("X-Request-Id"),
        )
        resp.headers["Retry-After"] = str(int(retry_after) + 1)
        return resp

    method = "POST"
    path = f"/api/v1/sessions/{session_id}/messages"
    payload_dict = payload.model_dump(mode="json")
    replay = _maybe_replay_idempotency(
        request, session_id, method, path, idempotency_key, payload_dict
    )
    if replay:
        return replay

    result = ChatService(
        store=request.app.state.store,
        settings=request.app.state.settings,
    ).send_text_message(
        session_id=session_id,
        text=payload.text,
        client_message_id=payload.client_message_id,
    )
    return _save_idempotent_success(
        request, session_id, method, path, idempotency_key, payload_dict, result
    )


@router.get("/sessions/{session_id}/events")
def poll_events(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    cursor: Annotated[int | None, Query()] = None,
    wait_seconds: Annotated[int, Query(ge=0, le=30)] = 0,
) -> JSONResponse:
    """Poll for new events after a cursor. Supports long-polling (future)."""
    auth = _authorize_request(request, session_id, authorization)
    if isinstance(auth, JSONResponse):
        return auth

    data = ChatService(
        store=request.app.state.store,
        settings=request.app.state.settings,
    ).poll_events(session_id=session_id, cursor=cursor)
    data["wait_seconds_used"] = 0
    return api_json(data, request_id=request.headers.get("X-Request-Id"))


# ============================================================
# Admin endpoints
# ============================================================


@router.get("/admin/review-items")
def list_review_items(
    request: Request,
    status: Annotated[str, Query()] = "OPEN",
    review_type: Annotated[str | None, Query()] = None,
    admin_token: Annotated[
        str | None, Header(alias="X-Admin-Token")
    ] = None,
) -> JSONResponse:
    """List admin review items (requires admin token)."""
    auth = _authorize_admin(request, admin_token)
    if auth:
        return auth
    with request.app.state.store.database.transaction() as conn:
        if review_type:
            rows = conn.execute(
                """
                SELECT * FROM admin_review_items
                WHERE status = ? AND review_type = ?
                ORDER BY priority ASC, created_at ASC
                """,
                (status, review_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM admin_review_items
                WHERE status = ?
                ORDER BY priority ASC, created_at ASC
                """,
                (status,),
            ).fetchall()
    return api_json(
        {"items": [_review_item(row) for row in rows]},
        request_id=request.headers.get("X-Request-Id"),
    )


@router.patch("/admin/review-items/{review_item_id}")
def resolve_review_item(
    review_item_id: str,
    payload: ResolveReviewRequest,
    request: Request,
    admin_token: Annotated[
        str | None, Header(alias="X-Admin-Token")
    ] = None,
) -> JSONResponse:
    """Resolve an admin review item (requires admin token)."""
    auth = _authorize_admin(request, admin_token)
    if auth:
        return auth
    with request.app.state.store.database.transaction() as conn:
        conn.execute(
            """
            UPDATE admin_review_items
            SET status = ?, resolved_at = ?
            WHERE id = ?
            """,
            (payload.status, utc_now_iso(), review_item_id),
        )
        row = conn.execute(
            "SELECT * FROM admin_review_items WHERE id = ?",
            (review_item_id,),
        ).fetchone()
    if not row:
        return error_response(
            "not_found",
            "Review item not found.",
            404,
            request_id=request.headers.get("X-Request-Id"),
        )
    return api_json(
        {"item": _review_item(row)},
        request_id=request.headers.get("X-Request-Id"),
    )


# ============================================================
# Health
# ============================================================


@router.get("/health")
def api_health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    db_ok = request.app.state.database.health_check()
    return success_envelope(
        {
            "status": "ok" if db_ok else "degraded",
            "app_env": settings.app_env,
            "active_rules_version": settings.active_rules_version,
            "conversation_runtime": settings.conversation_runtime,
            "db": "ok" if db_ok else "failed",
        }
    )



# ============================================================
# Logo endpoints
# ============================================================


@router.get("/sessions/{session_id}/logos")
def get_session_logos(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JSONResponse:
    """Return generated local logo concepts for a confirmed dealer."""
    auth = _authorize_request(request, session_id, authorization)
    if isinstance(auth, JSONResponse):
        return auth

    from app.core.logo_jobs import get_logo_job, get_logo_variants
    job = get_logo_job(session_id)
    variants = get_logo_variants(session_id)
    return api_json(
        {
            "session_id": session_id,
            "logo_job": job,
            "logo_variants": [v.model_dump() for v in variants],
        },
        request_id=request.headers.get("X-Request-Id"),
    )


@router.post("/sessions/{session_id}/logos/retry")
def retry_session_logos(
    session_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JSONResponse:
    """Retry a failed logo generation job explicitly."""
    auth = _authorize_request(request, session_id, authorization)
    if isinstance(auth, JSONResponse):
        return auth

    from app.services.profile_service import ProfileService
    from app.models.schema import DealerProfileRaw
    
    store = request.app.state.store
    settings = request.app.state.settings
    
    with store.database.transaction() as conn:
        profile_service = ProfileService(store, settings)
        snapshot = profile_service.get_profile_snapshot(conn, session_id)
        
        # Check if consent is yes and review_status is CONFIRMED
        review_status = snapshot.get("review_status", "DRAFT")
        consent = snapshot.get("design_fields", {}).get("brandkit_consent")
        if review_status != "CONFIRMED" or consent != "yes":
            return error_response(
                "conflict",
                "Hồ sơ chưa đủ điều kiện dựng logo",
                409,
                request_id=request.headers.get("X-Request-Id"),
            )
            
        profile_dict = {}
        for field_name in DealerProfileRaw.model_fields:
            if field_name in snapshot.get("all_fields", {}):
                profile_dict[field_name] = snapshot["all_fields"][field_name]
        profile_raw = DealerProfileRaw(**profile_dict)

    from app.core.logo_jobs import start_logo_job
    job = start_logo_job(session_id, profile_raw, retry=True)
    return api_json(job, request_id=request.headers.get("X-Request-Id"))


# ============================================================
# Internal helpers
# ============================================================


def _authorize_request(
    request: Request,
    session_id: str,
    authorization: str | None,
) -> Any:
    """Verify Bearer token for a session. Returns session row or JSONResponse error."""
    raw_token = extract_bearer_token(authorization)
    service = SessionService(
        store=request.app.state.store,
        settings=request.app.state.settings,
    )
    ok, reason, session = service.authorize(
        session_id=session_id, raw_token=raw_token
    )
    if ok:
        return session
    request_id = request.headers.get("X-Request-Id")
    if reason == "unauthorized":
        return error_response(
            "unauthorized",
            "Missing or invalid session token.",
            401,
            request_id=request_id,
        )
    if reason == "session_not_found":
        return error_response(
            "session_not_found",
            "Session does not exist or you do not have access.",
            404,
            request_id=request_id,
        )
    return error_response(
        "forbidden",
        "Token does not have access to this session.",
        403,
        request_id=request_id,
    )


def _authorize_admin(
    request: Request, admin_token: str | None
) -> JSONResponse | None:
    """Verify admin API token. Returns None if OK, error response if not."""
    if admin_token == request.app.state.settings.admin_api_token:
        return None
    return error_response(
        "unauthorized",
        "Missing or invalid admin token.",
        401,
        request_id=request.headers.get("X-Request-Id"),
    )


def _bad_idempotency(request: Request) -> JSONResponse:
    return error_response(
        "bad_request",
        "Idempotency-Key header is required.",
        400,
        request_id=request.headers.get("X-Request-Id"),
    )


def _maybe_replay_idempotency(
    request: Request,
    session_id: str,
    method: str,
    path: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> JSONResponse | None:
    """Check if this request was already processed (idempotency replay).

    Read-only — không giành write-lock (P3/H4).
    """
    payload_hash = canonical_payload_hash(payload)
    store = request.app.state.store
    with store.database.read_transaction() as conn:
        existing = store.get_idempotency_record(
            conn,
            session_id=session_id,
            method=method,
            path=path,
            idempotency_key=idempotency_key,
        )
    if existing is None:
        return None
    if existing["payload_hash"] != payload_hash:
        return error_response(
            "conflict",
            "Idempotency-Key was reused with a different payload.",
            409,
            request_id=request.headers.get("X-Request-Id"),
        )
    return JSONResponse(content=json.loads(existing["response_json"]))


def _save_idempotent_success(
    request: Request,
    session_id: str,
    method: str,
    path: str,
    idempotency_key: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> JSONResponse:
    """Save successful result for idempotency replay and return response."""
    response_body = success_envelope(
        result, request_id=request.headers.get("X-Request-Id")
    )
    store = request.app.state.store
    with store.database.transaction() as conn:
        store.insert_idempotency_record(
            conn,
            session_id=session_id,
            method=method,
            path=path,
            idempotency_key=idempotency_key,
            payload_hash=canonical_payload_hash(payload),
            response=response_body,
        )
    return JSONResponse(content=response_body)


def _review_item(row) -> dict[str, Any]:
    """Convert admin_review_items row to API dict."""
    return {
        "review_item_id": row["id"],
        "profile_id": row["profile_id"],
        "session_id": row["session_id"],
        "flag_id": row["flag_id"],
        "review_type": row["review_type"],
        "status": row["status"],
        "priority": row["priority"],
        "summary": row["summary"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
    }
