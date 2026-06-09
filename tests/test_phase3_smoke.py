"""Phase 3 smoke tests — Parlant infrastructure.

Tests: guideline registry, observation detector, context builder,
canned responses, agent reply generator.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_guideline_registry():
    from app.parlant.guideline_registry import GuidelineRegistry
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[1] / "config" / "guidelines.yaml"
    registry = GuidelineRegistry(config_path=config_path)
    registry.load()

    guidelines = registry.all()
    assert len(guidelines) >= 4, f"Expected >=4 guidelines, got {len(guidelines)}"

    # Check categories — tone/safety moved to rules.yaml, only workflow/collection remain
    workflow = registry.by_category("workflow")
    assert len(workflow) >= 2, f"Expected >=2 workflow guidelines, got {len(workflow)}"

    collection = registry.by_category("collection")
    assert len(collection) >= 1, f"Expected >=1 collection guidelines, got {len(collection)}"

    # Check specific guideline
    defensive = registry.get("workflow_defensive_handle")
    assert defensive is not None
    assert defensive.priority == 90
    assert "bảo mật" in defensive.action

    print(f"  [OK] guideline_registry ({len(guidelines)} guidelines)")


def test_observation_detector():
    from app.parlant.observation_detector import detect_observations

    # Normal message
    obs = detect_observations("Toi la Hung, xuong Hung Phat")
    assert obs.intent == "normal"
    assert obs.dealer_type in ("ban", "unknown")

    # Defensive message
    obs = detect_observations("Cai nay lua dao a? Phi bao nhieu?")
    assert obs.intent == "defensive"
    assert obs.is_skeptical is True
    assert obs.dealer_type == "unknown"

    # Busy/short message
    obs = detect_observations("OK")
    assert obs.is_busy is True
    assert obs.message_length == "short"
    assert obs.intent == "affirmative"

    # Confusion message
    obs = detect_observations("Cai nay la gi vay em?")
    assert obs.intent == "confusion"

    # Tam su (avoid "thoi" which matches refusal "thôi")
    obs = detect_observations("Hom nay met qua, stress khach hang kho tinh")
    assert obs.intent == "tam_su"
    assert obs.is_emotional is True

    # Signal list
    signals = obs.signal_list()
    assert "intent_tam_su" in signals
    assert "user_is_emotional" in signals

    print("  [OK] observation_detector (5 intent types)")


def test_context_builder():
    from app.parlant.context_builder import ContextBuilder

    builder = ContextBuilder()
    context = builder.build(
        profile_snapshot={
            "profile_id": "prof_123",
            "missing_required_fields": ["phone_or_zalo"],
            "all_fields": {"owner_name": {"normalized_value": "Hung"}},
        },
        suggested_objective={
            "type": "collect_required_field",
            "target_field": "phone_or_zalo",
            "prompt_hint": "so dien thoai/Zalo",
        },
        observations={"intent": "normal", "dealer_type": "ban"},
        matched_guidelines=[
            {"id": "tone_default", "action": "VUA 30-50 tu"},
            {"id": "collection_one_question", "action": "Dat 1 cau hoi"},
        ],
        recent_messages=[
            {"source": "user", "text": "Toi la Hung"},
            {"source": "linh_mkt", "text": "Da em ghi nhan"},
        ],
        address_form="anh",
        dealer_type="ban",
    )

    assert context["address_form"] == "anh"
    assert context["dealer_type"] == "ban"
    assert "phone_or_zalo" in context["missing_fields"]
    assert len(context["matched_guidelines"]) == 2
    assert "task" in context
    assert "history_summary" in context
    assert "Hung" in context["history_summary"]

    print("  [OK] context_builder (profile + guidelines + history)")


def test_canned_responses():
    from app.parlant.canned_responses import CannedResponseRegistry
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[1] / "config" / "canned_responses.yaml"
    registry = CannedResponseRegistry(config_path=config_path)
    registry.load()

    # Match collect phone
    resp = registry.match(
        objective_type="collect_required_field",
        target_field="phone_or_zalo",
    )
    assert resp is not None
    assert resp.id == "ask_phone"

    # Render with address form
    text = registry.render(resp, "anh")
    assert "anh" in text
    assert "Zalo" in text

    # Match defensive
    resp = registry.match(
        objective_type="collect_required_field",
        intent="defensive",
    )
    assert resp is not None
    assert resp.id == "defensive_reassure"

    # No match
    resp = registry.match(
        objective_type="nonexistent_objective",
    )
    assert resp is None

    print("  [OK] canned_responses (match + render)")


def test_agent_reply():
    from app.parlant.agent import AgentReplyGenerator

    agent = AgentReplyGenerator(runtime="stub")

    # Generate reply for collect_required_field
    result = agent.generate({
        "suggested_objective": {
            "type": "collect_required_field",
            "target_field": "phone_or_zalo",
        },
        "address_form": "anh",
        "dealer_type": "ban",
        "task": "Hoi anh so dien thoai",
        "profile_snapshot": {"all_fields": {}},
        "observations": {"intent": "normal"},
        "matched_guidelines": [],
        "history_summary": "(chua co)",
    })

    assert result.text
    assert "Zalo" in result.text or "dien thoai" in result.text
    assert result.model_id == "stub"

    # System prompt should be built
    assert result.system_prompt
    assert "Em Linh" in result.system_prompt

    print(f"  [OK] agent (stub reply: {result.text[:50]}...)")


def test_full_pipeline_integration():
    """Test the full Parlant pipeline: detect -> match -> context -> agent."""
    from app.parlant.observation_detector import detect_observations
    from app.parlant.guideline_registry import GuidelineRegistry
    from app.parlant.context_builder import ContextBuilder
    from app.parlant.canned_responses import CannedResponseRegistry
    from app.parlant.agent import AgentReplyGenerator
    from pathlib import Path

    config_dir = Path(__file__).resolve().parents[1] / "config"

    # 1. Detect observations
    obs = detect_observations("Toi la Hung, cua hang Hung Phat")

    # 2. Match guidelines
    guideline_reg = GuidelineRegistry(config_path=config_dir / "guidelines.yaml")
    guideline_reg.load()
    # For stub matching, just get all guidelines (real matching in Phase 4)
    all_guidelines = guideline_reg.all()

    # 3. Check canned response
    canned_reg = CannedResponseRegistry(config_path=config_dir / "canned_responses.yaml")
    canned_reg.load()

    # 4. Build context
    builder = ContextBuilder()
    context = builder.build(
        profile_snapshot={
            "missing_required_fields": ["address", "phone_or_zalo"],
            "all_fields": {"owner_name": {"normalized_value": "Hung"}},
        },
        suggested_objective={
            "type": "collect_required_field",
            "target_field": "address",
        },
        observations=obs.to_dict(),
        matched_guidelines=[{"id": g.id, "action": g.action} for g in all_guidelines[:3]],
        recent_messages=[{"source": "user", "text": "Toi la Hung, cua hang Hung Phat"}],
        address_form="anh",
        dealer_type=obs.dealer_type,
    )

    # 5. Generate reply
    agent = AgentReplyGenerator(runtime="stub")
    result = agent.generate(context)

    assert result.text
    assert result.model_id == "stub"
    assert result.system_prompt
    assert len(result.system_prompt) > 100

    print(f"  [OK] full pipeline (obs -> guidelines -> context -> agent)")
    print(f"       dealer_type={obs.dealer_type}, intent={obs.intent}")
    print(f"       reply: {result.text[:60]}...")


def main():
    print("Phase 3 Smoke Tests")
    print("=" * 50)
    test_guideline_registry()
    test_observation_detector()
    test_context_builder()
    test_canned_responses()
    test_agent_reply()
    test_full_pipeline_integration()
    print("=" * 50)
    print("ALL PHASE 3 TESTS PASSED [OK]")


if __name__ == "__main__":
    main()
