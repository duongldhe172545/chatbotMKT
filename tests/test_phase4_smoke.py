"""Phase 4 smoke tests — Business Logic Decomposition.

Tests: workflow engine, turn processor, and end-to-end API with real pipeline.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_workflow_engine():
    from app.parlant.workflow_engine import WorkflowEngine

    engine = WorkflowEngine()

    # Missing fields -> collect first priority field
    obj = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": ["phone_or_zalo", "main_product"],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
        },
        observations={"intent": "normal"},
    )
    assert obj["type"] == "collect_required_field"
    assert obj["target_field"] == "phone_or_zalo"

    # Blocking flag -> resolve first
    obj = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": ["phone_or_zalo"],
            "blocking_flags": ["address_blacklist"],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
        },
        observations={},
    )
    assert obj["type"] == "resolve_blocking_flag"
    assert obj["target_flag"] == "address_blacklist"

    # All fields filled, DRAFT -> show review
    obj = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
        },
        observations={},
    )
    assert obj["type"] == "show_profile_review"

    # Confirmed -> Zalo handoff (logo auto-trigger disabled; brief step removed)
    obj = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "CONFIRMED",
            "logo_issued_status": "NONE",
        },
        observations={},
    )
    assert obj["type"] == "zalo_handoff"

    # Workflow state
    state = engine.compute_workflow_state({
        "missing_required_fields": ["phone_or_zalo"],
        "blocking_flags": [],
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
    })
    assert state == "WAITING_REQUIRED_FIELD"

    state = engine.compute_workflow_state({
        "missing_required_fields": [],
        "blocking_flags": [],
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
    })
    assert state == "READY_FOR_REVIEW"

    # Optional fields flow tests
    # 1. Ask first missing optional field (est_team_size) if required are filled
    obj_opt = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {},
            "skipped_fields": [],
        },
        observations={},
    )
    assert obj_opt["type"] == "collect_optional_field"
    assert obj_opt["target_field"] == "est_team_size"

    # 2. Skip est_team_size -> ask supplier_brands
    obj_opt2 = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {},
            "skipped_fields": ["est_team_size"],
        },
        observations={},
    )
    assert obj_opt2["type"] == "collect_optional_field"
    assert obj_opt2["target_field"] == "supplier_brands"

    # 3. All optional fields skipped/filled -> ask brandkit_consent
    all_opts = ["est_team_size", "supplier_brands", "primary_contact_channel", "facebook",
                "customer_old_percentage", "local_dominance_signal", "customer_storage_method",
                "customer_pain", "payment_terms_signal", "warranty_responsibility_signal"]
    obj_consent = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {},
            "skipped_fields": all_opts,
        },
        observations={},
    )
    assert obj_consent["type"] == "collect_required_field"
    assert obj_consent["target_field"] == "brandkit_consent"

    # 4. brandkit_consent is yes -> ask color_accent
    obj_color = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {"brandkit_consent": "yes"},
            "skipped_fields": all_opts,
        },
        observations={},
    )
    assert obj_color["type"] == "collect_optional_field"
    assert obj_color["target_field"] == "color_accent"

    # 5. brandkit_consent is no -> show review card immediately
    obj_no_consent = engine.compute_objective(
        profile_snapshot={
            "missing_required_fields": [],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {"brandkit_consent": "no"},
            "skipped_fields": all_opts,
        },
        observations={},
    )
    assert obj_no_consent["type"] == "show_profile_review"

    print("  [OK] workflow_engine (4 objectives + 2 workflow states + optional fields flow)")


def test_turn_processor():
    from pathlib import Path
    from app.parlant.agent import AgentReplyGenerator
    from app.parlant.canned_responses import CannedResponseRegistry
    from app.parlant.context_builder import ContextBuilder
    from app.parlant.guideline_registry import GuidelineRegistry
    from app.parlant.turn_processor import TurnProcessor
    from app.parlant.workflow_engine import WorkflowEngine

    config_dir = Path(__file__).resolve().parents[1] / "config"

    processor = TurnProcessor(
        guideline_registry=GuidelineRegistry(config_path=config_dir / "guidelines.yaml"),
        canned_registry=CannedResponseRegistry(config_path=config_dir / "canned_responses.yaml"),
        workflow_engine=WorkflowEngine(),
        context_builder=ContextBuilder(),
        agent=AgentReplyGenerator(runtime="stub"),
    )

    # Test 1: Normal message, empty profile -> collect owner_name
    result = processor.process(
        message="Xin chao",
        profile_snapshot={
            "missing_required_fields": ["owner_name", "dealer_name", "address"],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {},
        },
        recent_messages=[],
        address_form="anh",
    )
    assert result.reply_text, "Reply should not be empty"
    assert result.suggested_objective["type"] == "collect_required_field"
    assert result.suggested_objective["target_field"] == "owner_name"
    assert result.workflow_state == "WAITING_REQUIRED_FIELD"
    assert result.trace.phase == "parlant_pipeline"

    # Test 2: Defensive message -> should detect skeptical
    result = processor.process(
        message="Cai nay lua dao a? Em la ai?",
        profile_snapshot={
            "missing_required_fields": ["owner_name"],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {},
        },
        recent_messages=[],
        address_form="anh",
    )
    assert result.observations.intent == "defensive"
    assert result.observations.is_skeptical is True

    # Test 3: Trace should have all fields populated
    trace = result.trace
    assert trace.observations
    assert trace.suggested_objective
    assert trace.workflow_state
    assert trace.reply_text

    # Test 4: Extraction stub
    result = processor.process(
        message="So dien thoai cua toi la 0901234567",
        profile_snapshot={
            "missing_required_fields": ["phone_or_zalo"],
            "blocking_flags": [],
            "review_status": "DRAFT",
            "logo_issued_status": "NONE",
            "all_fields": {},
        },
        recent_messages=[],
    )
    assert "phone_or_zalo" in result.extracted_fields
    assert result.extracted_fields["phone_or_zalo"] == "0901234567"

    print("  [OK] turn_processor (4 pipeline scenarios)")


def test_api_with_pipeline():
    """Full API test with Parlant pipeline wired in."""
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["APP_ENV"] = "test"

    from app.core.config_v2 import Settings, reset_settings
    reset_settings()

    settings = Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        session_token_secret="test-secret",
        admin_api_token="test-admin",
        conversation_runtime="parlant_local",
    )

    from app.main_v2 import create_app
    from fastapi.testclient import TestClient

    app = create_app(settings)
    client = TestClient(app)

    # Create session
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    token = session["session_token"]
    sid = session["session_id"]

    # Send first message
    resp = client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "Xin chao, toi la Hung, xuong Hung Phat"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "p4-key-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["turn_id"].startswith("turn_")
    assert len(data["events"]) >= 1
    assert data["events"][0]["source"] == "linh_mkt"
    reply_text = data["events"][0]["text"]
    assert reply_text, "Reply should not be empty"

    # Check debug info is present
    assert data["debug"] is not None
    assert "observations" in data["debug"]
    assert "matched_guidelines" in data["debug"]

    # Send defensive message
    resp2 = client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={"text": "Day co phai lua dao khong?"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "p4-key-2",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    obs = data2["debug"]["observations"]
    assert obs["intent"] == "defensive"
    assert obs["is_skeptical"] is True

    # Poll events - should have 4 messages (2 user + 2 bot)
    resp3 = client.get(
        f"/api/v1/sessions/{sid}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    events = resp3.json()["data"]["events"]
    assert len(events) == 4

    print(f"  [OK] API with Parlant pipeline (2 turns, {len(events)} events)")
    print(f"       Turn 1 reply: {reply_text[:60]}...")
    print(f"       Turn 2 intent: {obs['intent']}, dealer_type: {obs['dealer_type']}")


def main():
    print("Phase 4 Smoke Tests")
    print("=" * 50)
    test_workflow_engine()
    test_turn_processor()
    test_api_with_pipeline()
    print("=" * 50)
    print("ALL PHASE 4 TESTS PASSED [OK]")


if __name__ == "__main__":
    main()
