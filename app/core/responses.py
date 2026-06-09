"""Standardized API response envelopes.

All API endpoints return { ok, data|error, meta } format.
Follows LINHMKT pattern for consistent frontend handling.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from app.core.ids import new_id, utc_now_iso


def success_envelope(data: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    """Wrap data in a standard success envelope.

    Shape:
        {
            "ok": true,
            "data": { ... },
            "meta": { "request_id": "req_...", "server_time": "..." }
        }
    """
    return {
        "ok": True,
        "data": data,
        "meta": {
            "request_id": request_id or new_id("req"),
            "server_time": utc_now_iso(),
        },
    }


def error_response(
    code: str,
    message: str,
    status_code: int,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Return a standard error JSONResponse.

    Shape:
        {
            "ok": false,
            "error": { "code": "...", "message": "...", "details": {} },
            "meta": { "request_id": "req_...", "server_time": "..." }
        }
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "meta": {
                "request_id": request_id or new_id("req"),
                "server_time": utc_now_iso(),
            },
        },
    )


def api_json(data: dict[str, Any], request_id: str | None = None) -> JSONResponse:
    """Convenience: wrap data in success envelope and return as JSONResponse."""
    return JSONResponse(content=success_envelope(data, request_id=request_id))
