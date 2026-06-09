"""Chat service — process incoming messages via Parlant TurnProcessor.

Wires the full Parlant pipeline (Phase 4):
1. Insert user message
2. Load recent messages for context
3. Run TurnProcessor (observe → extract → workflow → guidelines → agent → guards)
4. Insert bot message(s)
5. Create conversation turn with full trace
6. Return events + profile snapshot
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.core.ids import utc_now_iso
from app.parlant.agent import AgentReplyGenerator
from app.parlant.canned_responses import CannedResponseRegistry
from app.parlant.context_builder import ContextBuilder
from app.parlant.guideline_registry import GuidelineRegistry
from app.parlant.turn_processor import TurnProcessor
from app.parlant.workflow_engine import WorkflowEngine
from app.services.serializers import (
    chat_event_from_message,
    empty_profile_snapshot,
)

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _build_turn_processor(runtime: str = "stub") -> TurnProcessor:
    """Build a TurnProcessor with all dependencies wired."""
    guideline_reg = GuidelineRegistry(config_path=CONFIG_DIR / "guidelines.yaml")
    guideline_reg.load()

    canned_reg = CannedResponseRegistry(config_path=CONFIG_DIR / "canned_responses.yaml")
    canned_reg.load()

    return TurnProcessor(
        guideline_registry=guideline_reg,
        canned_registry=canned_reg,
        workflow_engine=WorkflowEngine(),
        context_builder=ContextBuilder(),
        agent=AgentReplyGenerator(runtime=runtime),
    )


class ChatService:
    """Process incoming text messages via Parlant TurnProcessor."""

    def __init__(self, *, store, settings):
        self.store = store
        self.settings = settings
        self._turn_processor: TurnProcessor | None = None

    @property
    def turn_processor(self) -> TurnProcessor:
        """Lazy-init TurnProcessor (loads YAML configs once)."""
        if self._turn_processor is None:
            runtime = self.settings.conversation_runtime
            # Map config value to agent runtime
            agent_runtime = "stub" if runtime in ("parlant_local", "stub") else runtime
            self._turn_processor = _build_turn_processor(agent_runtime)
        return self._turn_processor

    def send_text_message(
        self,
        *,
        session_id: str,
        text: str,
        client_message_id: str | None,
    ) -> dict[str, Any]:
        """Process a single user text message through the Parlant pipeline.

        Pipeline:
        1. Insert user message
        2. Load recent messages for context
        3. Run TurnProcessor
        4. Insert bot reply message(s)
        5. Create conversation turn with full trace
        6. Return result
        """
        import time
        start_time = time.perf_counter()

        with self.store.database.transaction() as conn:
            # 1. Insert user message
            user_message = self.store.insert_message(
                conn,
                session_id=session_id,
                source="user",
                message_type="text",
                text=text,
                raw_payload={"client_message_id": client_message_id},
            )

            # 2. Load recent messages for context (Tăng lên 100 tin nhắn để nhớ lâu hơn)
            recent_rows = self.store.list_messages(
                conn, session_id=session_id, limit=100
            )
            recent_messages = [
                {
                    "source": row["source"],
                    "text": row["text"],
                    "message_type": row["message_type"],
                    "created_at": row["created_at"],
                }
                for row in recent_rows
            ]

            # 3. Load profile snapshot from ProfileService
            from app.services.profile_service import ProfileService
            profile_service = ProfileService(self.store, self.settings)

            # Initialize llm_client if available
            llm_client = None
            if self.settings.gemini_api_key and self.settings.gemini_api_key.strip() and self.settings.gemini_api_key != "your-gemini-api-key-here":
                try:
                    from app.llm.client import get_default_client
                    llm_client = get_default_client()
                except Exception:
                    pass

            # Intercept refusals on optional fields
            latest_turn = conn.execute(
                "SELECT suggested_objective_json FROM conversation_turns WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,)
            ).fetchone()
            if latest_turn:
                try:
                    prev_obj = json.loads(latest_turn["suggested_objective_json"])
                except Exception:
                    prev_obj = {}
                prev_field = prev_obj.get("target_field")
                if prev_field:
                    field_to_slot = {
                        "est_team_size": "2.3",
                        "supplier_brands": "2.4",
                        "primary_contact_channel": "2.5",
                        "facebook": "2.6",
                        "customer_old_percentage": "3.1",
                        "customer_storage_method": "3.2",
                        "customer_pain": "3.3",
                        "payment_terms_signal": "3.4",
                        "warranty_responsibility_signal": "3.5",
                        "color_accent": "4.2",
                    }
                    slot_id = field_to_slot.get(prev_field)
                    from app.parlant.observation_detector import detect_observations
                    obs = detect_observations(
                        text,
                        history_length=len(recent_messages) // 2,
                        llm_client=llm_client,
                        stage="ASKING",
                        current_slot=slot_id,
                    )
                    if obs.intent in ("refusal", "khong_biet"):
                        if slot_id:
                            from app.slots.definitions import SLOT_TO_ALL_FIELDS
                            profile_row = self.store.get_or_create_profile(conn, session_id)
                            for f_name in SLOT_TO_ALL_FIELDS.get(slot_id, []):
                                self.store.upsert_profile_field(
                                    conn,
                                    profile_id=profile_row["id"],
                                    field_name=f_name,
                                    raw_value=None,
                                    normalized_value=None,
                                    status="SKIPPED",
                                    source_type="refusal",
                                    confidence=1.0,
                                    evidence_message_ids=[user_message["id"]],
                                )
            
            # Transition review_status to CONFIRMED if user is in READY_FOR_REVIEW stage and confirms
            session = self.store.get_session(conn, session_id)
            if session and session["workflow_state"] == "READY_FOR_REVIEW":
                from app.parlant.observation_detector import detect_observations
                obs = detect_observations(
                    text,
                    history_length=len(recent_messages) // 2,
                    llm_client=llm_client,
                    stage="CONFIRMING",
                )
                if obs.intent == "affirmative":
                    profile_row = self.store.get_or_create_profile(conn, session_id)
                    self.store.update_profile_status(
                        conn,
                        profile_id=profile_row["id"],
                        review_status="CONFIRMED",
                        logo_issued_status=profile_row["logo_issued_status"]
                    )
            
            profile_snapshot = profile_service.get_profile_snapshot(conn, session_id)

            # 4. Run TurnProcessor — the full Parlant pipeline
            turn_result = self.turn_processor.process(
                message=text,
                profile_snapshot=profile_snapshot,
                recent_messages=recent_messages,
                address_form="anh",  # Phase 4+ will detect from profile/session
                turn_count=len(recent_messages) // 2,
            )

            # 5. Persist extracted fields
            updated_snapshot = profile_service.save_extracted_fields(
                conn,
                session_id=session_id,
                extracted_fields=turn_result.extracted_fields,
                evidence_message_id=user_message["id"],
            )

            # Compute latencies
            turn_aggregation_latency_ms = int((time.perf_counter() - start_time) * 1000)
            backend_latency_ms = 200  # Stub latency (e.g. 200ms) or from agent if LLM
            reply_hash = hashlib.md5(turn_result.reply_text.encode("utf-8")).hexdigest()

            # 6. Create conversation turn with full trace
            turn = self.store.create_turn(
                conn,
                session_id=session_id,
                user_message_id=user_message["id"],
                profile_id=updated_snapshot.get("profile_id"),
                active_rules_version=self.settings.active_rules_version,
                backend_turn_trace=turn_result.trace.to_dict(),
                profile_snapshot=updated_snapshot,
                suggested_objective=turn_result.suggested_objective,
                observations=turn_result.observations.signal_list(),
                matched_guideline_ids=turn_result.trace.matched_guideline_ids,
                field_status_summary=updated_snapshot,
                model_id=turn_result.trace.agent_model_id,
                backend_latency_ms=backend_latency_ms,
                turn_aggregation_latency_ms=turn_aggregation_latency_ms,
                final_reply_hash=reply_hash,
            )

            # 7. Associate user message with turn
            self.store.update_message_turn(
                conn, message_id=user_message["id"], turn_id=turn["id"]
            )

            # 8. Insert bot reply message
            linh_messages = [
                self.store.insert_message(
                    conn,
                    session_id=session_id,
                    turn_id=turn["id"],
                    source="linh_mkt",
                    message_type="text",
                    text=turn_result.reply_text,
                    raw_payload={
                        "runtime": self.settings.conversation_runtime,
                        "agent_model": turn_result.trace.agent_model_id,
                        "canned_id": turn_result.trace.canned_response_id,
                    },
                )
            ]

            # 9. Update turn event count
            self.store.update_turn_event_count(
                conn, turn_id=turn["id"], count=len(linh_messages)
            )

            # 10. Touch session with workflow state
            self.store.touch_session_after_message(
                conn,
                session_id=session_id,
                workflow_state=turn_result.workflow_state,
            )

            # 11. Trigger background logo job if state is LOGO_PENDING and consent is yes
            if turn_result.workflow_state == "LOGO_PENDING" and updated_snapshot.get("design_fields", {}).get("brandkit_consent") == "yes":
                from app.core.logo_jobs import start_logo_job
                from app.models.schema import DealerProfileRaw
                
                profile_dict = {}
                for field_name in DealerProfileRaw.model_fields:
                    if field_name in updated_snapshot.get("all_fields", {}):
                        profile_dict[field_name] = updated_snapshot["all_fields"][field_name]
                
                profile_raw = DealerProfileRaw(**profile_dict)
                start_logo_job(session_id, profile_raw)

        # Build response
        events = [chat_event_from_message(msg) for msg in linh_messages]
        return {
            "turn_id": turn["id"],
            "user_message_id": user_message["id"],
            "session_id": session_id,
            "workflow_state": turn_result.workflow_state,
            "events": events,
            "next_cursor": events[-1]["cursor"] if events else "0",
            "profile_snapshot": updated_snapshot,
            "logo_job": None,
            "debug": {
                "observations": turn_result.observations.to_dict(),
                "matched_guidelines": turn_result.trace.matched_guideline_ids,
                "canned_response_id": turn_result.trace.canned_response_id,
                "agent_model": turn_result.trace.agent_model_id,
            },
        }

    def poll_events(
        self, *, session_id: str, cursor: int | None, limit: int = 100
    ) -> dict[str, Any]:
        """Poll for new events after a cursor (long-polling support)."""
        with self.store.database.transaction() as conn:
            messages = self.store.list_messages(
                conn,
                session_id=session_id,
                after_cursor=cursor,
                limit=limit,
            )
            latest_cursor = self.store.latest_cursor(conn, session_id=session_id)

        events = [chat_event_from_message(row) for row in messages]
        next_cursor = (
            events[-1]["cursor"] if events else str(cursor or latest_cursor)
        )
        return {
            "events": events,
            "next_cursor": next_cursor,
            "has_more": False,
        }


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    """Deterministic hash of payload for idempotency check."""
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
