"""Idempotent background logo generation jobs backed by per-session manifests."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from app.core.logo_generator import DEFAULT_OUTPUT_ROOT, LogoVariant, generate_logo_variants
from app.models.schema import DealerProfileRaw

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_MANIFEST_LOCK = threading.Lock()
_RUNNING: set[str] = set()
_TOTAL = 3


def start_logo_job(session_id: str, profile: DealerProfileRaw, *, retry: bool = False) -> dict[str, Any]:
    """Start at most one background job for a session and return its status."""
    with _LOCK:
        current = get_logo_job(session_id)
        if current["status"] == "completed":
            return current
        if session_id in _RUNNING:
            return current
        if current["status"] in {"queued", "working"} and not retry:
            return current
        if current["status"] == "failed" and not retry:
            return current
        _RUNNING.add(session_id)
        _write_manifest(session_id, _status("queued"))

    snapshot = profile.model_copy(deep=True)
    thread = threading.Thread(
        target=_run_logo_job,
        args=(session_id, snapshot),
        name=f"logo-job-{session_id[:8]}",
        daemon=True,
    )
    thread.start()
    return get_logo_job(session_id)


def get_logo_job(session_id: str) -> dict[str, Any]:
    """Read job state without triggering generation."""
    manifest = _manifest_path(session_id)
    if not manifest.exists():
        return _status("idle")
    try:
        with _MANIFEST_LOCK:
            data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Logo manifest unreadable: session=%s", session_id)
        return _status("failed", error="manifest_unreadable")
    return {
        "status": str(data.get("status") or "idle"),
        "progress": int(data.get("progress") or 0),
        "total": int(data.get("total") or _TOTAL),
        "error": data.get("error"),
        "logo_variants": list(data.get("logo_variants") or []),
    }


def get_logo_variants(session_id: str) -> list[LogoVariant]:
    """Return cached variants only."""
    return [
        LogoVariant.model_validate(item)
        for item in get_logo_job(session_id)["logo_variants"]
    ]


def _run_logo_job(session_id: str, profile: DealerProfileRaw) -> None:
    try:
        _write_manifest(session_id, _status("working"))
        variants = generate_logo_variants(
            session_id,
            profile,
            progress_callback=lambda progress: _write_manifest(
                session_id,
                _status("working", progress=progress),
            ),
        )
        _write_manifest(
            session_id,
            _status(
                "completed",
                progress=len(variants),
                logo_variants=[variant.model_dump() for variant in variants],
            ),
        )
    except Exception as exc:
        logger.exception("Logo generation job failed: session=%s", session_id)
        _write_manifest(session_id, _status("failed", error=str(exc)))
    finally:
        with _LOCK:
            _RUNNING.discard(session_id)


def _status(
    status: str,
    *,
    progress: int = 0,
    error: str | None = None,
    logo_variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "progress": progress,
        "total": _TOTAL,
        "error": error,
        "logo_variants": logo_variants or [],
    }


def _manifest_path(session_id: str) -> Path:
    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_") or "session"
    return DEFAULT_OUTPUT_ROOT / safe_id / "manifest.json"


def _write_manifest(session_id: str, data: dict[str, Any]) -> None:
    manifest = _manifest_path(session_id)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with _MANIFEST_LOCK:
        manifest.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
