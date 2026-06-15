"""Chat service — process incoming messages via Parlant TurnProcessor.

P2 (2026-06-10) — concurrency refactor: the LLM calls (intent classification +
TurnProcessor's extract/reply) NO LONGER run inside a DB write transaction.
They were the dominant bottleneck: `transaction()` opens with BEGIN IMMEDIATE
(a global SQLite write lock), so holding it across multi-second Gemini calls
serialized every concurrent user. Now a turn is processed in 3 short write
transactions with the LLM work in between, holding the write lock only for ~ms:

    tx1 (write): insert user message + read context (recent msgs, prev objective,
                 session state)
    -- compute A (no lock): intent decisions for refusal-skip / confirm (may call LLM)
    tx2 (write): apply skip/confirm writes + read profile snapshot
    -- compute B (no lock): TurnProcessor pipeline (extraction + reply = 2 Gemini calls)
    tx3 (write): persist extracted fields + conversation turn + bot reply

Cursor safety: every write still goes through BEGIN IMMEDIATE, which serializes
writers, so `MAX(event_cursor)+1` cannot collide (commit 5860e53's guarantee is
preserved). See tests/unit/test_chat_service_concurrency.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
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

# P3/M3 — số tin nhắn gần nhất đưa vào prompt LLM. DB vẫn lưu + load đủ 100
# (turn_count giữ nguyên semantics); chỉ phần gửi LLM cắt bớt để tiết kiệm
# TPM/latency. Phiên intake 10-20 lượt = 20-40 tin → thực tế vẫn trọn phiên;
# trạng thái slot đã có collection_status trong prompt lo, không cần history dài.
_LLM_HISTORY_WINDOW = 40

# Field the previous turn was asking about → its slot. Used to mark the slot's
# fields SKIPPED when the dealer refuses / says they don't know.
_FIELD_TO_SLOT = {
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

# Field bot hỏi RIÊNG nhưng không gắn 1 slot số trong _FIELD_TO_SLOT
# (brandkit phụ + C6 độ phủ địa bàn); từ chối → chỉ skip chính field đó.
_SELF_SKIP_FIELDS = {"logo_style", "slogan_preference", "local_dominance_signal"}

# Field brandkit kiểu CHỌN (màu/phong cách/slogan): "tùy em" KHÔNG phải từ chối
# mà là "đề xuất giúp tôi" → KHÔNG skip; bot sẽ đề xuất + hỏi chọn (Fix 2).
# Chỉ skip khi khách từ chối DỨT KHOÁT (refusal), không skip khi khong_biet.
_BRANDKIT_CHOICE_FIELDS = {"color_accent", "logo_style", "slogan_preference"}

# B (fix 2026-06-11): 1 optional bị hỏi lặp ngần này lượt mà chưa thu → auto-skip
# để workflow tiến, tránh bot hỏi đi hỏi lại + tránh kẹt vĩnh viễn.
_OPTIONAL_STUCK_LIMIT = 3


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


# P3/H6 — cache TurnProcessor theo runtime, share cho mọi request. ChatService
# được new mỗi request nên lazy-init per-instance = parse lại YAML mỗi lượt.
# TurnProcessor stateless sau __init__ (chỉ giữ registry read-only) → share an toàn.
_TP_CACHE: dict[str, TurnProcessor] = {}
_TP_LOCK = threading.Lock()


def _get_turn_processor(runtime: str) -> TurnProcessor:
    tp = _TP_CACHE.get(runtime)
    if tp is None:
        with _TP_LOCK:
            tp = _TP_CACHE.get(runtime)
            if tp is None:
                tp = _build_turn_processor(runtime)
                _TP_CACHE[runtime] = tp
    return tp


def reset_turn_processor_cache() -> None:
    """Clear cache (test helper)."""
    with _TP_LOCK:
        _TP_CACHE.clear()


class ChatService:
    """Process incoming text messages via Parlant TurnProcessor."""

    def __init__(self, *, store, settings):
        self.store = store
        self.settings = settings
        self._turn_processor: TurnProcessor | None = None

    @property
    def turn_processor(self) -> TurnProcessor:
        """Shared TurnProcessor từ module cache (YAML parse đúng 1 lần/process).

        `self._turn_processor` vẫn là injection point cho test (set trực tiếp
        để spy/stub) — chỉ rơi về cache khi chưa inject.
        """
        if self._turn_processor is None:
            runtime = self.settings.conversation_runtime
            # Map config value to agent runtime
            agent_runtime = "stub" if runtime in ("parlant_local", "stub") else runtime
            self._turn_processor = _get_turn_processor(agent_runtime)
        return self._turn_processor

    def _get_llm_client(self):
        """Return a shared LLM client if a real Gemini key is configured, else None."""
        key = self.settings.gemini_api_key
        if key and key.strip() and key != "your-gemini-api-key-here":
            try:
                from app.llm.client import get_default_client
                return get_default_client()
            except Exception:
                return None
        return None

    def send_text_message(
        self,
        *,
        session_id: str,
        text: str,
        client_message_id: str | None,
    ) -> dict[str, Any]:
        """Process a single user text message through the Parlant pipeline.

        3 short write transactions with the LLM work done OUTSIDE any DB lock
        (see module docstring). Behaviour is otherwise identical to before.
        """
        import time
        start_time = time.perf_counter()

        from app.services.profile_service import ProfileService
        profile_service = ProfileService(self.store, self.settings)

        # ============================================================
        # tx1 (short write): record the user message + read context
        # ============================================================
        with self.store.database.transaction() as conn:
            user_message = self.store.insert_message(
                conn,
                session_id=session_id,
                source="user",
                message_type="text",
                text=text,
                raw_payload={"client_message_id": client_message_id},
            )
            # recent_messages includes the just-inserted user message (latest).
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
            recent_obj_rows = conn.execute(
                "SELECT suggested_objective_json FROM conversation_turns "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT 4",
                (session_id,),
            ).fetchall()
            session = self.store.get_session(conn, session_id)

        user_message_id = user_message["id"]
        history_length = len(recent_messages) // 2
        workflow_state_before = session["workflow_state"] if session else None

        # Mục tiêu vài lượt gần nhất (mới → cũ): biết bot đang hỏi field nào +
        # field đó bị hỏi lặp bao nhiêu lượt liên tiếp (cho auto-skip — B).
        recent_targets: list[str | None] = []
        for row in recent_obj_rows:
            try:
                recent_targets.append(
                    (json.loads(row["suggested_objective_json"]) or {}).get("target_field")
                )
            except Exception:
                recent_targets.append(None)
        prev_field = recent_targets[0] if recent_targets else None
        slot_id = _FIELD_TO_SLOT.get(prev_field) if prev_field else None

        # ============================================================
        # compute A (NO lock): intent decisions — may call Gemini (intent L2)
        # ============================================================
        llm_client = self._get_llm_client()

        skip_fields: list[str] = []
        prev_intent: str | None = None
        # Field bot có thể hỏi nhưng KHÔNG thuộc slot số (brandkit phụ — P4.4):
        # từ chối thì chỉ skip chính nó.
        if slot_id or prev_field in _SELF_SKIP_FIELDS:
            from app.parlant.observation_detector import detect_observations
            from app.slots.definitions import SLOT_TO_ALL_FIELDS

            obs = detect_observations(
                text,
                history_length=history_length,
                llm_client=llm_client,
                stage="ASKING",
                current_slot=slot_id,
            )
            prev_intent = obs.intent
            # Brandkit choice (màu/phong cách/slogan): "tùy em" (khong_biet) =
            # nhờ đề xuất, KHÔNG skip; chỉ skip khi từ chối dứt khoát.
            _skip_intents = (
                ("refusal",)
                if prev_field in _BRANDKIT_CHOICE_FIELDS
                else ("refusal", "khong_biet")
            )
            if obs.intent in _skip_intents:
                skip_fields = (
                    list(SLOT_TO_ALL_FIELDS.get(slot_id, []))
                    if slot_id
                    else [prev_field]
                )
            # B: auto-skip nếu field này đã bị hỏi lặp >= _OPTIONAL_STUCK_LIMIT lượt
            # liên tiếp mà vẫn chưa thu được (khách né hoài / câu trả lời rơi sang
            # field khác). Nếu lượt này khách bất ngờ trả lời đúng → extraction vẫn
            # ghi đè PROVIDED lên skip, nên không mất dữ liệu.
            if not skip_fields:
                consec = 0
                for tf in recent_targets:
                    if tf == prev_field:
                        consec += 1
                    else:
                        break
                if consec >= _OPTIONAL_STUCK_LIMIT:
                    skip_fields = (
                        list(SLOT_TO_ALL_FIELDS.get(slot_id, []))
                        if slot_id
                        else [prev_field]
                    )

        do_confirm = False
        if workflow_state_before == "READY_FOR_REVIEW":
            from app.parlant.observation_detector import detect_observations

            obs = detect_observations(
                text,
                history_length=history_length,
                llm_client=llm_client,
                stage="CONFIRMING",
            )
            do_confirm = obs.intent == "affirmative"

        # ============================================================
        # tx2 (short write): apply skip/confirm, then read profile snapshot
        # ============================================================
        with self.store.database.transaction() as conn:
            if skip_fields or do_confirm:
                profile_row = self.store.get_or_create_profile(conn, session_id)
                for f_name in skip_fields:
                    self.store.upsert_profile_field(
                        conn,
                        profile_id=profile_row["id"],
                        field_name=f_name,
                        # Lưu câu khách vừa nói (gây skip) vào raw_value để admin
                        # thấy "khách nói gì" — phân biệt từ chối thật vs lảng ("ok").
                        raw_value=text,
                        normalized_value=None,
                        status="SKIPPED",
                        source_type="refusal",
                        confidence=1.0,
                        evidence_message_ids=[user_message_id],
                    )
                if do_confirm:
                    self.store.update_profile_status(
                        conn,
                        profile_id=profile_row["id"],
                        review_status="CONFIRMED",
                        logo_issued_status=profile_row["logo_issued_status"],
                    )
            profile_snapshot = profile_service.get_profile_snapshot(conn, session_id)

        # ============================================================
        # compute B (NO lock): the full Parlant pipeline (2 Gemini calls)
        # ============================================================
        # P3/M3: chỉ đưa _LLM_HISTORY_WINDOW tin gần nhất vào prompt LLM —
        # turn_count vẫn tính từ full history (semantics không đổi).
        prompt_messages = recent_messages[-_LLM_HISTORY_WINDOW:]
        # 9.1 — xưng hô tất định: suy "anh"/"chị" từ cách khách tự xưng trong lịch
        # sử (mặc định "anh"). Sticky vì cue nằm trong history → nhất quán cả phiên.
        from app.parlant.observation_detector import detect_address_form
        address_form = detect_address_form(recent_messages)
        turn_result = self.turn_processor.process(
            message=text,
            profile_snapshot=profile_snapshot,
            recent_messages=prompt_messages,
            address_form=address_form,
            turn_count=history_length,
        )

        # Fix 2 (guard cứng): "tùy em" cho field brandkit (màu/phong cách/slogan)
        # → KHÔNG nhận giá trị extractor TỰ BỊA (LLM hay tự chế màu dù luật cấm);
        # để bot đề xuất cho khách chọn. Giá trị CỤ THỂ (intent normal) vẫn nhận.
        if prev_field in _BRANDKIT_CHOICE_FIELDS and prev_intent == "khong_biet":
            turn_result.extracted_fields.pop(prev_field, None)
            if prev_field == "color_accent":
                turn_result.extracted_fields.pop("feng_shui_signal", None)

        turn_aggregation_latency_ms = int((time.perf_counter() - start_time) * 1000)
        backend_latency_ms = 200  # Stub latency (e.g. 200ms) or from agent if LLM
        reply_hash = hashlib.md5(turn_result.reply_text.encode("utf-8")).hexdigest()
        msg_type = "text"
        if (
            turn_result.suggested_objective
            and turn_result.suggested_objective.get("target_field") == "address"
        ):
            msg_type = "address_form"

        # ============================================================
        # tx3 (short write): persist fields + conversation turn + bot reply
        # ============================================================
        with self.store.database.transaction() as conn:
            updated_snapshot = profile_service.save_extracted_fields(
                conn,
                session_id=session_id,
                extracted_fields=turn_result.extracted_fields,
                evidence_message_id=user_message_id,
            )

            turn = self.store.create_turn(
                conn,
                session_id=session_id,
                user_message_id=user_message_id,
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

            self.store.update_message_turn(
                conn, message_id=user_message_id, turn_id=turn["id"]
            )

            linh_messages = [
                self.store.insert_message(
                    conn,
                    session_id=session_id,
                    turn_id=turn["id"],
                    source="linh_mkt",
                    message_type=msg_type,
                    text=turn_result.reply_text,
                    raw_payload={
                        "runtime": self.settings.conversation_runtime,
                        "agent_model": turn_result.trace.agent_model_id,
                        "canned_id": turn_result.trace.canned_response_id,
                    },
                )
            ]

            self.store.update_turn_event_count(
                conn, turn_id=turn["id"], count=len(linh_messages)
            )

            self.store.touch_session_after_message(
                conn,
                session_id=session_id,
                workflow_state=turn_result.workflow_state,
            )

        # Note: auto-trigger background logo job is intentionally DISABLED
        # (logo runs only via the manual POST /logos/retry endpoint).

        # Build response
        events = [chat_event_from_message(msg) for msg in linh_messages]
        return {
            "turn_id": turn["id"],
            "user_message_id": user_message_id,
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
        """Poll for new events after a cursor (long-polling support).

        Read-only — không giành write-lock (P3/H4).
        """
        with self.store.database.read_transaction() as conn:
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
