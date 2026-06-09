"""Session service — session lifecycle management.

Follows LINHMKT pattern: create session with token auth,
authorize requests, hydrate session for frontend.
"""
from __future__ import annotations

from typing import Any

from app.core.ids import new_session_token
from app.core.security import hash_client_signal, hash_token
from app.services.serializers import (
    chat_event_from_message,
    empty_profile_snapshot,
    session_public_state,
)


class SessionService:
    """Manages session creation, authorization, and hydration."""

    def __init__(self, *, store, settings):
        self.store = store
        self.settings = settings

    def create_session(
        self,
        *,
        channel: str,
        client: dict[str, Any],
        ip_address: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        """Create a new session + access token.

        Returns session info including raw token (shown only once to client).
        """
        raw_token = new_session_token()
        token_hash = hash_token(raw_token, self.settings.session_token_secret)
        ip_hash = hash_client_signal(ip_address, self.settings.session_token_secret)
        user_agent_hash = hash_client_signal(user_agent, self.settings.session_token_secret)

        with self.store.database.transaction() as conn:
            session = self.store.create_session(
                conn,
                channel=channel,
                token_hash=token_hash,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                metadata={"client": client},
            )

        return {
            "session_id": session["id"],
            "session_token": raw_token,
            "status": session["status"],
            "workflow_state": session["workflow_state"],
            "events_cursor": "0",
            "expires_at": session["expires_at"],
        }

    def authorize(
        self, *, session_id: str, raw_token: str | None
    ) -> tuple[bool, str, Any | None]:
        """Verify that a raw token is valid for a session.

        Returns:
            (ok, reason, session_row)
            reason: "ok" | "unauthorized" | "session_not_found" | "forbidden"
        """
        if not raw_token:
            return False, "unauthorized", None

        token_hash = hash_token(raw_token, self.settings.session_token_secret)
        with self.store.database.transaction() as conn:
            session = self.store.get_session(conn, session_id)
            if session is None:
                return False, "session_not_found", None
            if not self.store.token_is_active(
                conn, session_id=session_id, token_hash=token_hash
            ):
                return False, "forbidden", None
            return True, "ok", session

    def hydrate_session(self, *, session_id: str) -> dict[str, Any]:
        """Load full session state for frontend restoration.

        Returns session public state + recent events + profile snapshot.
        """
        with self.store.database.transaction() as conn:
            session = self.store.get_session(conn, session_id)
            if session is None:
                raise RuntimeError("Authorized session disappeared.")
            cursor = self.store.latest_cursor(conn, session_id=session_id)
            recent_messages = self.store.list_messages(
                conn, session_id=session_id, limit=100
            )
            # Profile snapshot
            from app.services.profile_service import ProfileService
            profile_snapshot = ProfileService(self.store, self.settings).get_profile_snapshot(conn, session_id)

        state = session_public_state(session, events_cursor=cursor)
        state.update(
            {
                "recent_events": [
                    chat_event_from_message(row) for row in recent_messages
                ],
                "profile_snapshot": profile_snapshot,
                "logo_job": None,
                "zalo_cta": {
                    "visible": bool(
                        self.settings.zalo_group_url
                        and session["workflow_state"]
                        in {"LOGO_READY", "CLOSED", "ESCALATED"}
                    ),
                    "url": self.settings.zalo_group_url,
                },
            }
        )
        return state
