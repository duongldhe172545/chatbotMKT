"""Phase 7 — fix card hiện trước khi chốt slogan + card trùng dòng logo (2026-06-12).

7.1: khách "tùy em / gợi ý đi" (khong_biet) cho field brandkit choice → value bị
     strip TRƯỚC khi tính objective → KHÔNG bung card review sớm (bot chỉ đề xuất).
7.2: card chỉ 1 dòng "Phong cách logo" (gỡ "Gu logo" trùng).
"""
from __future__ import annotations

from pathlib import Path

from app.core.card_renderer import render_card
from app.models.schema import DealerProfileRaw
from app.parlant.observation_detector import Observations
from app.parlant.workflow_engine import OPTIONAL_FIELDS_PRIORITY

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ============================================================
# Helpers
# ============================================================


class _FakeAgent:
    runtime = "gemini"  # tránh canned (trừ greet)

    def generate(self, context):
        from app.parlant.agent import AgentResult
        return AgentResult(text="Dạ anh thích slogan kiểu nào ạ?", model_id="fake")


def _build_tp():
    from app.parlant.canned_responses import CannedResponseRegistry
    from app.parlant.context_builder import ContextBuilder
    from app.parlant.guideline_registry import GuidelineRegistry
    from app.parlant.turn_processor import TurnProcessor
    from app.parlant.workflow_engine import WorkflowEngine

    g = GuidelineRegistry(config_path=CONFIG_DIR / "guidelines.yaml"); g.load()
    c = CannedResponseRegistry(config_path=CONFIG_DIR / "canned_responses.yaml"); c.load()
    return TurnProcessor(
        guideline_registry=g, canned_registry=c,
        workflow_engine=WorkflowEngine(), context_builder=ContextBuilder(),
        agent=_FakeAgent(),
    )


def _snapshot_focus_slogan(**extra):
    """Snapshot mà objective kế tiếp = collect slogan (đã xong tất cả trước slogan)."""
    all_fields = {
        "owner_name": "Hùng", "dealer_name": "Hùng Phát", "address": "Hà Đông HN",
        "phone_or_zalo": "0912345678", "main_product": "nhôm kính",
        "business_model_signal": "xưởng", "brandkit_consent": "yes",
        "color_accent": "xanh", "logo_style": "hiện đại",
    }
    for f, _l, _h in OPTIONAL_FIELDS_PRIORITY:
        all_fields.setdefault(f, "x")
    all_fields.update(extra)
    return {
        "all_fields": all_fields,
        "required_fields": {},
        "design_fields": {},
        "missing_required_fields": [],
        "skipped_fields": [],
        "blocking_flags": [],
        "open_flags": [],
        "active_flag_details": [],
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
    }


# ============================================================
# 7.1 — strip brandkit choice khi defer → KHÔNG card sớm
# ============================================================


class TestBrandkitDeferStrip:
    def test_defer_slogan_stays_pending_no_review(self, monkeypatch):
        """'em gợi ý đi' (khong_biet) + extractor bịa slogan='auto' → strip →
        objective vẫn là HỎI slogan, KHÔNG nhảy show_profile_review (card sớm)."""
        tp = _build_tp()
        monkeypatch.setattr(
            tp, "_extract_fields",
            lambda **kw: ({"slogan_preference": "auto"}, Observations(intent="khong_biet")),
        )
        result = tp.process(
            message="em gợi ý đi",
            profile_snapshot=_snapshot_focus_slogan(),
            recent_messages=[],
            turn_count=20,
        )
        assert result.suggested_objective["type"] == "collect_optional_field"
        assert result.suggested_objective["target_field"] == "slogan_preference"
        assert "slogan_preference" not in result.extracted_fields  # đã strip
        assert result.workflow_state != "READY_FOR_REVIEW"

    def test_concrete_slogan_kept_then_preview(self, monkeypatch):
        """ADVERSARIAL: khách CHỌN câu cụ thể (intent normal) → KHÔNG strip →
        slogan lưu lại → brandkit đủ → nhảy SHOW MẪU THAM KHẢO (9.4b, trước review)."""
        tp = _build_tp()
        monkeypatch.setattr(
            tp, "_extract_fields",
            lambda **kw: ({"slogan_preference": "Tận tâm trong từng công trình"},
                          Observations(intent="normal")),
        )
        result = tp.process(
            message="anh chọn câu 2",
            profile_snapshot=_snapshot_focus_slogan(),
            recent_messages=[],
            turn_count=20,
        )
        assert result.extracted_fields.get("slogan_preference") == "Tận tâm trong từng công trình"
        assert result.suggested_objective["type"] == "show_brandkit_preview"

    def test_defer_color_strips_feng_shui_too(self, monkeypatch):
        """Defer màu → strip cả color_accent lẫn feng_shui_signal."""
        tp = _build_tp()
        snap = _snapshot_focus_slogan()
        del snap["all_fields"]["color_accent"]  # để focus = color
        del snap["all_fields"]["logo_style"]
        monkeypatch.setattr(
            tp, "_extract_fields",
            lambda **kw: ({"color_accent": "auto", "feng_shui_signal": "auto"},
                          Observations(intent="khong_biet")),
        )
        result = tp.process(
            message="tùy em", profile_snapshot=snap, recent_messages=[], turn_count=20,
        )
        assert "color_accent" not in result.extracted_fields
        assert "feng_shui_signal" not in result.extracted_fields


# ============================================================
# 7.2 — card gộp 1 dòng phong cách logo
# ============================================================


class TestCardLogoSingleLine:
    def _profile(self, **extra):
        base = dict(
            owner_name="Dương", dealer_name="Dương An", address="36 Lê Văn Thiêm HN",
            phone_or_zalo="0982371474", main_product="tủ bếp",
            brandkit_consent="yes", main_category="tu_bep",
        )
        base.update(extra)
        return DealerProfileRaw(**base)

    def test_logo_style_filled_single_line_no_duplicate(self):
        text = render_card(self._profile(logo_style="Hiện đại & Tối giản"))
        assert text.count("Phong cách logo") == 1
        assert "Gu logo" not in text
        assert "Hiện đại & Tối giản" in text

    def test_logo_style_filled_no_category_fallback(self):
        """Có logo_style thật → KHÔNG hiện 'em chọn theo ngành' nữa."""
        text = render_card(self._profile(logo_style="Mạnh mẽ"))
        line = [l for l in text.split("\n") if "Phong cách logo" in l][0]
        assert "Mạnh mẽ" in line
        assert "em chọn theo" not in line

    def test_logo_style_auto_shows_suggestion(self):
        text = render_card(self._profile(logo_style="auto"))
        assert "Phong cách logo" in text
        assert "Em đề xuất" in text
        assert "Gu logo" not in text

    def test_no_logo_style_falls_back_to_category(self):
        text = render_card(self._profile())  # logo_style None
        line = [l for l in text.split("\n") if "Phong cách logo" in l][0]
        assert "em chọn theo" in line
