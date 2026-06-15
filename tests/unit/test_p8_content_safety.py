"""Phase 8 — luật an toàn nội dung (2026-06-12, THUẦN LUẬT).

8.1: nội dung bậy/phi pháp → KHÔNG gán field (luật trong principles_extraction).
8.2: bước trình thẻ review → CHƯA gửi link Zalo (luật trong task).
Đây là test "luật đã wire đúng prompt"; hành vi LLM verify bằng live test.
"""
from __future__ import annotations

from app.core.rules import get_extraction_principles
from app.llm.intake_fact_extractor import build_fact_extractor_prompt
from app.parlant.context_builder import _task_from_objective


class TestAbuseRuleWired:
    def test_principle_present(self):
        text = " ".join(get_extraction_principles()).lower()
        assert "phi pháp" in text or "chửi bậy" in text

    def test_in_extractor_prompt(self):
        p = build_fact_extractor_prompt().lower()
        assert "phi pháp" in p
        # nhắc rõ ca "nói thẳng slogan/sản phẩm là..." (chính là ca lọt bug)
        assert "slogan là" in p

    def test_abuse_rule_only_in_extraction_not_reply(self):
        # luật này chỉ cho bộ trích xuất, không nhồi vào prompt trả lời
        from app.core.rules import build_rules_context_for_prompt
        reply = build_rules_context_for_prompt(dealer_type="unknown", address_form="anh")
        assert "ma túy" not in reply.lower()


class TestNoMalformedYamlRules:
    """Chống lỗi YAML: dòng luật chứa ': ' mà KHÔNG bọc nháy → bị parse thành dict
    → vào prompt dưới dạng dict-repr (luật méo). Quét mọi list luật."""

    def test_all_rule_lists_are_strings(self):
        from app.core.rules import (
            get_extraction_principles,
            get_reply_principles,
            get_safety_rules,
            get_rules,
        )

        sources = {
            "extraction": get_extraction_principles(),
            "reply": get_reply_principles(),
            "safety": get_safety_rules(),
        }
        dc = get_rules().get("data_collection", {})
        for s in dc.get("slots", []):
            sources[f"slot {s.get('id')}"] = s.get("rules", [])

        bad = {
            k: [repr(p)[:80] for p in v if not isinstance(p, str)]
            for k, v in sources.items()
        }
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"Luật bị parse thành non-string (thiếu nháy quanh dấu ':'): {bad}"


class TestReviewNoLinkRuleWired:
    def test_review_task_forbids_link(self):
        t = _task_from_objective({"type": "show_profile_review"}, "anh")
        assert "CHƯA gửi link Zalo" in t

    def test_review_task_still_invites_confirm(self):
        t = _task_from_objective({"type": "show_profile_review"}, "anh").lower()
        assert "xác nhận" in t or "duyệt" in t or "xem lai" in t

    def test_handoff_still_allows_link_guidance(self):
        # bước bàn giao THẬT vẫn được hướng dẫn link (không bị 8.2 chặn nhầm)
        t = _task_from_objective({"type": "zalo_handoff"}, "anh")
        assert "zalo" in t.lower()
