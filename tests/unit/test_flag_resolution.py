"""Unit tests for phone_invalid_after_retry flag resolution.

Verifies:
1. ProfileService.save_extracted_fields resolves database flags khi phone_or_zalo hợp lệ.
2. TurnProcessor.process performs in-memory flag resolution.
(phone_secondary copy đã bỏ 2026-06-22 — field rác.)
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from app.db.connection import Database
from app.db.store import Store
from app.core.config_v2 import Settings
from app.services.profile_service import ProfileService
from app.parlant.turn_processor import TurnProcessor
from app.parlant.agent import AgentReplyGenerator
from app.parlant.canned_responses import CannedResponseRegistry
from app.parlant.context_builder import ContextBuilder
from app.parlant.guideline_registry import GuidelineRegistry
from app.parlant.workflow_engine import WorkflowEngine


@pytest.fixture
def test_db():
    db = Database(":memory:")
    db.initialize()
    return db


@pytest.fixture
def store(test_db):
    return Store(test_db)


@pytest.fixture
def settings():
    return Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
    )


@pytest.fixture
def profile_service(store, settings):
    return ProfileService(store, settings)


def test_db_flag_resolution(test_db, store, profile_service):
    with test_db.transaction() as conn:
        session = store.create_session(
            conn,
            channel="web",
            token_hash="hash123",
            ip_hash="ip_hash",
            user_agent_hash="ua_hash",
            metadata={"source": "test"},
        )
        session_id = session["id"]
        profile = store.get_or_create_profile(conn, session_id)
        profile_id = profile["id"]

        # Insert a message first to satisfy foreign key constraint on flags
        msg = store.insert_message(
            conn,
            session_id=session_id,
            source="user",
            message_type="text",
            text="invalid number",
        )
        msg_id = msg["id"]

        # 1. Insert an invalid phone number to raise blocking flag
        store.upsert_profile_field(
            conn,
            profile_id=profile_id,
            field_name="phone_or_zalo",
            raw_value="123",  # invalid
            normalized_value=None,
            status="INVALID",
            source_type="extraction",
            confidence=0.0,
            evidence_message_ids=[msg_id],
        )
        store.insert_flag(
            conn,
            session_id=session_id,
            profile_id=profile_id,
            message_id=msg_id,
            field_name="phone_or_zalo",
            flag_name="phone_invalid_after_retry",
            severity="BLOCKING",
        )

        # Confirm flag is active
        active = store.get_active_flags(conn, profile_id=profile_id)
        assert len(active) == 1
        assert active[0]["flag_name"] == "phone_invalid_after_retry"

        # 2. Save a valid phone_or_zalo → flag phải resolve
        profile_service.save_extracted_fields(
            conn,
            session_id=session_id,
            extracted_fields={"phone_or_zalo": "0912781373"},
            evidence_message_id=msg_id,
        )

        # Verify flag is resolved
        active_after = store.get_active_flags(conn, profile_id=profile_id)
        assert len(active_after) == 0

        # Verify phone_or_zalo lưu hợp lệ
        fields = store.get_profile_fields(conn, profile_id)
        primary = next(f for f in fields if f["field_name"] == "phone_or_zalo")
        assert primary["status"] == "PROVIDED"
        assert primary["normalized_value"] == "0912781373"


def test_turn_processor_in_memory_resolution():
    config_dir = Path(__file__).resolve().parents[2] / "config"

    processor = TurnProcessor(
        guideline_registry=GuidelineRegistry(config_path=config_dir / "guidelines.yaml"),
        canned_registry=CannedResponseRegistry(config_path=config_dir / "canned_responses.yaml"),
        workflow_engine=WorkflowEngine(),
        context_builder=ContextBuilder(),
        agent=AgentReplyGenerator(runtime="stub"),
    )

    # Scenario A: regex fallback extracts it directly into phone_or_zalo
    profile_snapshot_a = {
        "missing_required_fields": ["phone_or_zalo", "business_model_signal"],
        "blocking_flags": ["phone_invalid_after_retry"],
        "open_flags": ["phone_invalid_after_retry"],
        "all_fields": {
            "phone_or_zalo": "123",
        },
        "active_flag_details": [
            {
                "id": "flg_1",
                "flag_name": "phone_invalid_after_retry",
                "field_name": "phone_or_zalo",
                "severity": "BLOCKING",
            }
        ]
    }

    result_a = processor.process(
        message="0912781373",
        profile_snapshot=profile_snapshot_a,
        recent_messages=[],
        address_form="anh",
    )

    # 1. phone_or_zalo is validated and updated in all_fields
    assert result_a.profile_snapshot["all_fields"]["phone_or_zalo"] == "0912781373"
    # 2. phone_or_zalo is removed from missing required fields
    assert "phone_or_zalo" not in result_a.profile_snapshot["missing_required_fields"]
    # 3. blocking flags are cleared in memory
    assert "phone_invalid_after_retry" not in result_a.profile_snapshot["blocking_flags"]
    assert "phone_invalid_after_retry" not in result_a.profile_snapshot["open_flags"]
    # 4. Objective has moved forward
    assert result_a.suggested_objective["type"] == "collect_required_field"
    assert result_a.suggested_objective["target_field"] == "business_model_signal"

    # (Scenario B "copy phone_secondary→phone_or_zalo" đã bỏ 2026-06-22 — field rác)
